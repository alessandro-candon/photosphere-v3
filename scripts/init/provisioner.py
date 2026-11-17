"""Idempotent GCP and Firebase REST provisioning orchestrator."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.init.models import (
    AuthConfig,
    BootstrapConfigError,
    FirebaseConfig,
    GcpConfig,
    PhotosphereConfig,
    PipelineConfig,
    StorageClass,
    StorageConfig,
)
from scripts.init.rest_client import GoogleRestClient, RestApiError

REQUIRED_APIS = [
    "storage.googleapis.com",
    "firebase.googleapis.com",
    "firebasestorage.googleapis.com",
    "firebaserules.googleapis.com",
    "identitytoolkit.googleapis.com",
]

MEDIA_DB_FILENAME = "photosphere_database_cloud.json"
LABELS_DB_SUFFIX = "photosphere_image_labelling_database_cloud.json"
CAPTIONS_DB_SUFFIX = "photosphere_image_caption_database_cloud.json"
ALBUMS_DB_FILENAME = "photosphere_albums.json"

_RULES_EMAIL_PLACEHOLDER = "['<your-email>']"


@dataclass(frozen=True)
class BootstrapOptions:
    """User-selected provisioning parameters for BootstrapProvisioner."""

    project_id: str
    location: str
    media_bucket: str
    data_bucket: str
    media_storage_class: StorageClass
    data_storage_class: StorageClass
    allowed_emails: list[str]
    admin_email: str
    default_lang: str = "en"
    target_lang: str = "it"
    web_app_name: str = "photosphere-ssr"
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None


class BootstrapProvisioner:
    """Provisions GCS buckets, Firebase Storage, rules, Web App, and Auth."""

    def __init__(
        self,
        rest_client: GoogleRestClient,
        repo_root: Path,
        prompt_fn: Callable[[str, str], None],
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rest = rest_client
        self._repo_root = repo_root
        self._prompt = prompt_fn
        self._sleep = sleep_fn

    def _load_cors_rules(self) -> list[dict[str, Any]]:
        cors_path = self._repo_root / "infra" / "cors.json"
        if not cors_path.exists():
            raise BootstrapConfigError(f"Missing CORS template at {cors_path}")
        raw = json.loads(cors_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise BootstrapConfigError(f"Invalid CORS JSON array in {cors_path}")
        return raw

    def _compile_storage_rules(self, allowed_emails: list[str]) -> str:
        rules_path = self._repo_root / "infra" / "storage.rules"
        if not rules_path.exists():
            raise BootstrapConfigError(
                f"Missing storage.rules template at {rules_path}"
            )
        template = rules_path.read_text(encoding="utf-8")
        if _RULES_EMAIL_PLACEHOLDER not in template:
            raise BootstrapConfigError(
                f"Expected placeholder {_RULES_EMAIL_PLACEHOLDER} in {rules_path}"
            )
        normalized = [email.strip().lower() for email in allowed_emails]
        return template.replace(_RULES_EMAIL_PLACEHOLDER, json.dumps(normalized))

    def enable_required_apis(self, project_id: str) -> None:
        """Enable all required GCP and Firebase APIs on the target project."""
        url = (
            f"https://serviceusage.googleapis.com/v1/projects/{project_id}"
            "/services:batchEnable"
        )
        try:
            _, data = self._rest.request_json(
                "POST",
                url,
                json_body={"serviceIds": REQUIRED_APIS},
                retry_without_quota_header=True,
            )
        except RestApiError as exc:
            if (
                exc.status_code != 403
                or "serviceusage.googleapis.com" not in exc.message
            ):
                raise
            console_url = (
                "https://console.developers.google.com/apis/api/"
                f"serviceusage.googleapis.com/overview?project={project_id}"
            )
            self._prompt(
                console_url,
                f"Enable the Service Usage API on project '{project_id}'.",
            )
            _, data = self._rest.request_json(
                "POST",
                url,
                json_body={"serviceIds": REQUIRED_APIS},
                retry_without_quota_header=True,
            )
        if not data.get("done") and data.get("name"):
            self._rest.poll_lro(
                f"https://serviceusage.googleapis.com/v1/{data['name']}"
            )

    def ensure_firebase_project(self, project_id: str) -> None:
        """Attach Firebase to the GCP project if it is not yet enabled."""
        base_url = f"https://firebase.googleapis.com/v1beta1/projects/{project_id}"
        status, _ = self._get_with_propagation_retry(base_url, allow_statuses=(404,))
        if status != 404:
            return
        _, op = self._rest.request_json("POST", f"{base_url}:addFirebase", json_body={})
        if not op.get("done") and op.get("name"):
            self._rest.poll_lro(f"https://firebase.googleapis.com/v1beta1/{op['name']}")

    def _get_with_propagation_retry(
        self,
        url: str,
        *,
        allow_statuses: tuple[int, ...] = (),
        attempts: int = 6,
        delay_seconds: float = 5.0,
    ) -> tuple[int, dict[str, Any]]:
        for attempt in range(attempts):
            try:
                return self._rest.request_json(
                    "GET", url, allow_statuses=allow_statuses
                )
            except RestApiError as exc:
                is_propagating = exc.status_code == 403 and (
                    exc.reason == "SERVICE_DISABLED"
                    or "has not been used in project" in exc.message
                )
                if not is_propagating or attempt == attempts - 1:
                    raise
                self._sleep(delay_seconds)
        raise AssertionError("unreachable")

    def provision_bucket(
        self,
        project_id: str,
        bucket_name: str,
        location: str,
        storage_class: StorageClass,
        cors_rules: list[dict[str, Any]],
    ) -> None:
        """Create or reconcile a GCS bucket with uniform access and CORS."""
        create_url = f"https://storage.googleapis.com/storage/v1/b?project={project_id}"
        body = {
            "name": bucket_name,
            "location": location,
            "storageClass": storage_class,
            "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}},
            "cors": cors_rules,
        }
        try:
            status, _ = self._rest.request_json(
                "POST", create_url, json_body=body, allow_statuses=(409,)
            )
        except RestApiError as exc:
            if exc.status_code != 403 or "billing" not in exc.message.lower():
                raise
            console_url = f"https://console.firebase.google.com/project/{project_id}/usage/details"
            self._prompt(
                console_url,
                f"Link a billing account (Blaze plan) to project '{project_id}' "
                "so GCS buckets can be created.",
            )
            status, _ = self._rest.request_json(
                "POST", create_url, json_body=body, allow_statuses=(409,)
            )
        if status != 409:
            return

        bucket_url = f"https://storage.googleapis.com/storage/v1/b/{bucket_name}"
        _, existing = self._rest.request_json("GET", bucket_url)
        found_class = existing.get("storageClass")
        if found_class and found_class != storage_class:
            raise BootstrapConfigError(
                f"Existing bucket '{bucket_name}' has storageClass '{found_class}', "
                f"expected '{storage_class}'."
            )
        self._rest.request_json("PATCH", bucket_url, json_body={"cors": cors_rules})

    def seed_empty_databases(self, data_bucket: str, target_lang: str) -> None:
        """Seed baseline JSON databases in data_bucket with ifGenerationMatch=0."""
        objects: dict[str, bytes] = {
            MEDIA_DB_FILENAME: b"{}",
            f"en_{LABELS_DB_SUFFIX}": b"{}",
            f"en_{CAPTIONS_DB_SUFFIX}": b"{}",
            ALBUMS_DB_FILENAME: b"[]",
        }
        if target_lang != "en":
            objects[f"{target_lang}_{LABELS_DB_SUFFIX}"] = b"{}"
            objects[f"{target_lang}_{CAPTIONS_DB_SUFFIX}"] = b"{}"

        for object_name, payload in objects.items():
            upload_url = (
                f"https://storage.googleapis.com/upload/storage/v1/b/{data_bucket}"
                f"/o?name={object_name}"
            )
            self._rest.upload_bytes(
                upload_url,
                payload,
                content_type="application/json",
                if_generation_match=0,
                allow_statuses=(412,),
            )

    def link_buckets_to_firebase(self, project_id: str, buckets: list[str]) -> None:
        """Link GCS buckets to Firebase Storage, pausing for Blaze if rejected."""
        for bucket in buckets:
            self._link_single_bucket(project_id, bucket)

    def _link_single_bucket(self, project_id: str, bucket: str) -> None:
        url = (
            f"https://firebasestorage.googleapis.com/v1beta/projects/{project_id}"
            f"/buckets/{bucket}:addFirebase"
        )
        try:
            self._rest.request_json("POST", url, json_body={}, allow_statuses=(409,))
        except RestApiError as exc:
            if exc.status_code not in (400, 403):
                raise
            console_url = f"https://console.firebase.google.com/project/{project_id}/usage/details"
            self._prompt(
                console_url,
                f"Upgrade project '{project_id}' to the Blaze billing plan so "
                f"Firebase Storage can link bucket '{bucket}'.",
            )
            self._rest.request_json("POST", url, json_body={}, allow_statuses=(409,))

    def compile_and_bind_storage_rules(
        self,
        project_id: str,
        allowed_emails: list[str],
        buckets: list[str],
    ) -> None:
        """Compile infra/storage.rules in memory and bind releases to both buckets."""
        compiled = self._compile_storage_rules(allowed_emails)
        rulesets_url = (
            f"https://firebaserules.googleapis.com/v1/projects/{project_id}/rulesets"
        )
        _, ruleset = self._rest.request_json(
            "POST",
            rulesets_url,
            json_body={
                "source": {"files": [{"name": "storage.rules", "content": compiled}]}
            },
        )
        ruleset_name = str(ruleset["name"])
        for bucket in buckets:
            self._bind_release(project_id, bucket, ruleset_name)

    def _bind_release(self, project_id: str, bucket: str, ruleset_name: str) -> None:
        release_name = f"projects/{project_id}/releases/firebase.storage/{bucket}"
        releases_url = (
            f"https://firebaserules.googleapis.com/v1/projects/{project_id}/releases"
        )
        payload = {"name": release_name, "rulesetName": ruleset_name}
        status, _ = self._rest.request_json(
            "POST", releases_url, json_body=payload, allow_statuses=(409,)
        )
        if status == 409:
            self._rest.request_json(
                "PATCH",
                f"https://firebaserules.googleapis.com/v1/{release_name}",
                json_body={"release": payload},
            )

    def ensure_firebase_web_app(
        self, project_id: str, display_name: str, media_bucket: str
    ) -> FirebaseConfig:
        """Reuse or create a Firebase Web App and fetch its public SDK config."""
        list_url = (
            f"https://firebase.googleapis.com/v1beta1/projects/{project_id}/webApps"
        )
        _, listed = self._rest.request_json("GET", list_url)
        app_id = self._find_web_app_id(listed.get("apps", []), display_name)
        if app_id is None:
            _, op = self._rest.request_json(
                "POST", list_url, json_body={"displayName": display_name}
            )
            result = (
                op
                if op.get("done")
                else self._rest.poll_lro(
                    f"https://firebase.googleapis.com/v1beta1/{op['name']}"
                )
            )
            app_id = str(result["appId"])

        _, sdk_cfg = self._rest.request_json("GET", f"{list_url}/{app_id}/config")
        return FirebaseConfig(
            project_id=str(sdk_cfg.get("projectId") or project_id),
            app_id=str(sdk_cfg["appId"]),
            api_key=str(sdk_cfg["apiKey"]),
            auth_domain=str(
                sdk_cfg.get("authDomain") or f"{project_id}.firebaseapp.com"
            ),
            storage_bucket=str(sdk_cfg.get("storageBucket") or media_bucket),
            messaging_sender_id=str(sdk_cfg.get("messagingSenderId") or "0"),
        )

    def _find_web_app_id(
        self, apps: list[dict[str, Any]], display_name: str
    ) -> str | None:
        for app in apps:
            if app.get("displayName") == display_name and app.get("appId"):
                return str(app["appId"])
        return None

    def initialize_firebase_auth(
        self,
        project_id: str,
        *,
        oauth_client_id: str | None = None,
        oauth_client_secret: str | None = None,
    ) -> None:
        """Initialize Firebase Auth and verify Google Sign-In is enabled."""
        init_url = (
            f"https://identitytoolkit.googleapis.com/v2/projects/{project_id}"
            "/identityPlatform:initializeAuth"
        )
        self._rest.request_json("POST", init_url, json_body={}, allow_statuses=(409,))

        idp_base = (
            f"https://identitytoolkit.googleapis.com/v2/projects/{project_id}"
            "/defaultSupportedIdpConfigs"
        )
        if oauth_client_id and oauth_client_secret:
            self._upsert_google_idp(idp_base, oauth_client_id, oauth_client_secret)
            return

        if self._is_google_idp_enabled(f"{idp_base}/google.com"):
            return

        console_url = (
            f"https://console.firebase.google.com/project/{project_id}"
            "/authentication/providers"
        )
        self._prompt(
            console_url,
            "Enable the Google Sign-In provider under "
            "Authentication -> Sign-in method.",
        )
        if not self._is_google_idp_enabled(f"{idp_base}/google.com"):
            raise BootstrapConfigError(
                "Google Sign-In provider is still disabled in Firebase Auth."
            )

    def _upsert_google_idp(
        self, idp_base: str, client_id: str, client_secret: str
    ) -> None:
        body = {
            "enabled": True,
            "clientId": client_id,
            "clientSecret": client_secret,
        }
        status, _ = self._rest.request_json(
            "POST",
            f"{idp_base}?idpId=google.com",
            json_body=body,
            allow_statuses=(409,),
        )
        if status == 409:
            self._rest.request_json("PATCH", f"{idp_base}/google.com", json_body=body)

    def _is_google_idp_enabled(self, google_idp_url: str) -> bool:
        status, cfg = self._rest.request_json(
            "GET", google_idp_url, allow_statuses=(404,)
        )
        return status == 200 and bool(cfg.get("enabled"))

    def run(self, options: BootstrapOptions) -> PhotosphereConfig:
        """Execute the full idempotent provisioning sequence."""
        cors_rules = self._load_cors_rules()
        self.enable_required_apis(options.project_id)
        self.ensure_firebase_project(options.project_id)
        self.provision_bucket(
            options.project_id,
            options.media_bucket,
            options.location,
            options.media_storage_class,
            cors_rules,
        )
        self.provision_bucket(
            options.project_id,
            options.data_bucket,
            options.location,
            options.data_storage_class,
            cors_rules,
        )
        self.seed_empty_databases(options.data_bucket, options.target_lang)
        buckets = [options.media_bucket, options.data_bucket]
        self.link_buckets_to_firebase(options.project_id, buckets)
        self.compile_and_bind_storage_rules(
            options.project_id, options.allowed_emails, buckets
        )
        firebase_cfg = self.ensure_firebase_web_app(
            options.project_id, options.web_app_name, options.media_bucket
        )
        self.initialize_firebase_auth(
            options.project_id,
            oauth_client_id=options.google_oauth_client_id,
            oauth_client_secret=options.google_oauth_client_secret,
        )
        return PhotosphereConfig(
            version=1,
            gcp=GcpConfig(project_id=options.project_id, location=options.location),
            storage=StorageConfig(
                media_bucket=options.media_bucket,
                media_storage_class=options.media_storage_class,
                data_bucket=options.data_bucket,
                data_storage_class=options.data_storage_class,
            ),
            firebase=firebase_cfg,
            auth=AuthConfig(
                allowed_emails=options.allowed_emails,
                admin_email=options.admin_email,
            ),
            pipeline=PipelineConfig(
                default_lang=options.default_lang,
                target_lang=options.target_lang,
            ),
        )
