"""Offline unit tests for photosphere.init bootstrapper."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from photosphere.init.command import init_command
from photosphere.init.models import (
    AuthConfig,
    BootstrapConfigError,
    FirebaseConfig,
    GcpConfig,
    PhotosphereConfig,
    PipelineConfig,
    StorageConfig,
    load_and_validate_config,
    write_config_atomic,
)
from photosphere.init.provisioner import BootstrapOptions, BootstrapProvisioner
from photosphere.init.rest_client import GoogleRestClient
from photosphere.main import cli


@dataclass
class _FakeResponse:
    status_code: int
    body: Any

    @property
    def text(self) -> str:
        if self.body is None:
            return ""
        if isinstance(self.body, str):
            return self.body
        return json.dumps(self.body)

    def json(self) -> Any:
        if isinstance(self.body, str):
            return json.loads(self.body)
        return self.body


class _FakeSession:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        json: Any = None,
        data: bytes | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> _FakeResponse:
        call = {
            "method": method,
            "url": url,
            "json": json,
            "data": data,
            "params": params,
            "headers": dict(headers or {}),
            "timeout": timeout,
        }
        self.calls.append(call)
        return self.handler(call)


class _FakeRestRouter:
    def __init__(self) -> None:
        self.blaze_upgraded = False
        self.google_idp_enabled = False
        self.prompts: list[tuple[str, str]] = []

    def prompt(self, url: str, instruction: str) -> None:
        self.prompts.append((url, instruction))
        if "usage/details" in url:
            self.blaze_upgraded = True
        if "authentication/providers" in url:
            self.google_idp_enabled = True

    def handle(self, call: dict[str, Any]) -> _FakeResponse:
        url = str(call["url"])
        method = str(call["method"])
        for checker in (
            self._handle_service_and_firebase,
            self._handle_storage,
            self._handle_rules_and_auth,
        ):
            response = checker(method, url, call)
            if response is not None:
                return response
        raise AssertionError(f"Unexpected REST call: {method} {url}")

    def _handle_service_and_firebase(
        self, method: str, url: str, call: dict[str, Any]
    ) -> _FakeResponse | None:
        if "services:batchEnable" in url:
            if "x-goog-user-project" in call["headers"]:
                return _FakeResponse(403, {"error": {"message": "quota header retry"}})
            return _FakeResponse(200, {"name": "operations/svc-1", "done": False})
        if "serviceusage.googleapis.com/v1/operations/" in url:
            return _FakeResponse(200, {"done": True})
        if url.endswith("/projects/proj-dev") and method == "GET":
            return _FakeResponse(404, {"error": {"message": "not found"}})
        if url.endswith(":addFirebase") and "firebase.googleapis.com" in url:
            return _FakeResponse(200, {"done": True})
        if url.endswith("/webApps") and method == "GET":
            return _FakeResponse(200, {"apps": []})
        if url.endswith("/webApps") and method == "POST":
            return _FakeResponse(200, {"done": True, "appId": "1:123:web:abc"})
        if url.endswith("/webApps/1:123:web:abc/config"):
            return _FakeResponse(
                200,
                {
                    "projectId": "proj-dev",
                    "appId": "1:123:web:abc",
                    "apiKey": "AIzaRealKey",
                    "authDomain": "proj-dev.firebaseapp.com",
                    "storageBucket": "proj-dev-media",
                    "messagingSenderId": "123",
                },
            )
        return None

    def _handle_storage(
        self, method: str, url: str, call: dict[str, Any]
    ) -> _FakeResponse | None:
        if url.endswith("/storage/v1/b?project=proj-dev"):
            if call["json"]["name"] == "proj-dev-data":
                return _FakeResponse(409, {"error": {"message": "exists"}})
            return _FakeResponse(200, {"name": call["json"]["name"]})
        if url.endswith("/storage/v1/b/proj-dev-data") and method == "GET":
            return _FakeResponse(
                200, {"name": "proj-dev-data", "storageClass": "STANDARD"}
            )
        if url.endswith("/storage/v1/b/proj-dev-data") and method == "PATCH":
            return _FakeResponse(200, {"name": "proj-dev-data"})
        if "upload/storage/v1/b/proj-dev-data/o" in url:
            if "photosphere_albums.json" in url:
                return _FakeResponse(412, {"error": {"message": "already seeded"}})
            return _FakeResponse(200, {"name": "seeded"})
        if "firebasestorage.googleapis.com" in url and url.endswith(":addFirebase"):
            if not self.blaze_upgraded and "proj-dev-data" in url:
                return _FakeResponse(400, {"error": {"message": "Blaze required"}})
            return _FakeResponse(200, {"name": "linked"})
        return None

    def _handle_rules_and_auth(
        self, method: str, url: str, call: dict[str, Any]
    ) -> _FakeResponse | None:
        if url.endswith("/rulesets") and method == "POST":
            content = call["json"]["source"]["files"][0]["content"]
            assert '["alice@example.com"]' in content
            return _FakeResponse(200, {"name": "projects/proj-dev/rulesets/rs-1"})
        if url.endswith("/releases") and method == "POST":
            if "proj-dev-data" in call["json"]["name"]:
                return _FakeResponse(409, {"error": {"message": "exists"}})
            return _FakeResponse(200, {"name": call["json"]["name"]})
        if "firebaserules.googleapis.com/v1/projects/proj-dev/releases/" in url:
            return _FakeResponse(200, {"name": "patched"})
        if url.endswith("identityPlatform:initializeAuth"):
            return _FakeResponse(200, {})
        if url.endswith("/defaultSupportedIdpConfigs/google.com") and method == "GET":
            if not self.google_idp_enabled:
                return _FakeResponse(404, {"error": {"message": "not enabled"}})
            return _FakeResponse(200, {"enabled": True})
        return None


def _sample_config() -> PhotosphereConfig:
    return PhotosphereConfig(
        version=1,
        gcp=GcpConfig(project_id="proj-dev", location="europe-west1"),
        storage=StorageConfig(
            media_bucket="proj-dev-media",
            media_storage_class="STANDARD",
            data_bucket="proj-dev-data",
            data_storage_class="STANDARD",
        ),
        firebase=FirebaseConfig(
            project_id="proj-dev",
            app_id="1:123:web:abc",
            api_key="AIzaTestKey",
            auth_domain="proj-dev.firebaseapp.com",
            storage_bucket="proj-dev-media",
            messaging_sender_id="123",
        ),
        auth=AuthConfig(
            allowed_emails=["Alice@Example.com", "alice@example.com"],
            admin_email="Alice@Example.com",
        ),
        pipeline=PipelineConfig(default_lang="en", target_lang="it"),
    )


def _setup_infra(tmp_path: Path) -> Path:
    infra = tmp_path / "infra"
    infra.mkdir(parents=True, exist_ok=True)
    (infra / "cors.json").write_text(
        json.dumps([{"origin": ["*"], "method": ["GET"], "maxAgeSeconds": 3600}]),
        encoding="utf-8",
    )
    (infra / "storage.rules").write_text(
        "rules_version = '2';\n"
        "service firebase.storage {\n"
        "  match /b/{bucket}/o {\n"
        "    function isAllowedUser() {\n"
        "      return request.auth.token.email in ['<your-email>'];\n"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    return infra


def test_fast_path_prints_existing_config_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = tmp_path / "photosphere.config.json"
    write_config_atomic(cfg_path, _sample_config())

    def _fail_client(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("GoogleRestClient must not be called on fast path")

    monkeypatch.setattr("photosphere.init.command.GoogleRestClient", _fail_client)
    runner = CliRunner()
    result = runner.invoke(cli, ["--config-file", str(cfg_path), "init"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["gcp"]["project_id"] == "proj-dev"
    assert parsed["auth"]["allowed_emails"] == ["alice@example.com"]


def test_provisioner_idempotent_rest_sequence_and_console_fallbacks(
    tmp_path: Path,
) -> None:
    infra = _setup_infra(tmp_path)
    rules_before = (infra / "storage.rules").read_text(encoding="utf-8")
    router = _FakeRestRouter()
    session = _FakeSession(router.handle)
    client = GoogleRestClient("proj-dev", session=session)
    provisioner = BootstrapProvisioner(client, router.prompt, templates_dir=infra)
    opts = BootstrapOptions(
        project_id="proj-dev",
        location="europe-west1",
        media_bucket="proj-dev-media",
        data_bucket="proj-dev-data",
        media_storage_class="STANDARD",
        data_storage_class="STANDARD",
        allowed_emails=["Alice@Example.com"],
        admin_email="Alice@Example.com",
        target_lang="it",
    )
    cfg = provisioner.run(opts)

    assert cfg.storage.media_storage_class == "STANDARD"
    assert cfg.firebase.api_key == "AIzaRealKey"
    assert len(router.prompts) == 2
    assert "usage/details" in router.prompts[0][0]
    assert "authentication/providers" in router.prompts[1][0]
    actual_rules = (infra / "storage.rules").read_text(encoding="utf-8")
    assert actual_rules == rules_before

    cfg_path = tmp_path / "photosphere.config.json"
    write_config_atomic(cfg_path, cfg)
    assert load_and_validate_config(cfg_path) == cfg


def test_provisioner_uses_bundled_templates_without_repo_infra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    router = _FakeRestRouter()
    session = _FakeSession(router.handle)
    client = GoogleRestClient("proj-dev", session=session)
    provisioner = BootstrapProvisioner(client, router.prompt)
    opts = BootstrapOptions(
        project_id="proj-dev",
        location="europe-west1",
        media_bucket="proj-dev-media",
        data_bucket="proj-dev-data",
        media_storage_class="STANDARD",
        data_storage_class="STANDARD",
        allowed_emails=["Alice@Example.com"],
        admin_email="Alice@Example.com",
        target_lang="it",
    )
    cfg = provisioner.run(opts)
    assert cfg.firebase.api_key == "AIzaRealKey"


def test_bundled_templates_match_repo_infra_files() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    infra_dir = repo_root / "infra"
    pkg_templates = resources.files("photosphere.init.templates")
    for filename in ("cors.json", "storage.rules"):
        assert pkg_templates.joinpath(filename).read_text(encoding="utf-8") == (
            infra_dir / filename
        ).read_text(encoding="utf-8")

    rules_text = (infra_dir / "storage.rules").read_text(encoding="utf-8")
    assert "match /photosphere_albums.json {" in rules_text
    assert "allow read, write: if isAllowedUser();" in rules_text
    assert "match /{allPaths=**} {\n      allow read: if isAllowedUser();" in rules_text


def test_missing_config_and_non_interactive_cli_errors(tmp_path: Path) -> None:
    with pytest.raises(BootstrapConfigError, match="photosphere init"):
        load_and_validate_config(tmp_path / "missing.json")

    runner = CliRunner()
    res = runner.invoke(
        init_command,
        ["--config-path", str(tmp_path / "out.json"), "--non-interactive"],
    )
    assert res.exit_code != 0
    assert "non-interactive" in res.output


def test_root_cli_forwards_creds_to_init_rest_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creds_file = tmp_path / "sa.json"
    creds_file.write_text("{}", encoding="utf-8")
    out_cfg = tmp_path / "photosphere.config.json"
    captured: dict[str, Any] = {}

    class _StubRestClient:
        def __init__(
            self, project_id: str, *, credentials_path: Path | None = None
        ) -> None:
            captured["project_id"] = project_id
            captured["credentials_path"] = credentials_path

    class _StubProvisioner:
        def __init__(
            self, rest_client: Any, prompt_fn: Any, *, templates_dir: Path | None = None
        ) -> None:
            _ = rest_client, prompt_fn
            captured["templates_dir"] = templates_dir

        def run(self, options: BootstrapOptions) -> PhotosphereConfig:
            _ = options
            return _sample_config()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("photosphere.init.command.GoogleRestClient", _StubRestClient)
    monkeypatch.setattr(
        "photosphere.init.command.BootstrapProvisioner", _StubProvisioner
    )

    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            "--creds",
            str(creds_file),
            "--config-file",
            str(out_cfg),
            "init",
            "--project-id",
            "proj-dev",
            "--location",
            "europe-west1",
            "--mode",
            "dev",
            "--media-bucket",
            "proj-dev-media",
            "--data-bucket",
            "proj-dev-data",
            "--allowed-emails",
            "alice@example.com",
            "--admin-email",
            "alice@example.com",
            "--non-interactive",
        ],
    )
    assert res.exit_code == 0, res.output
    assert captured["project_id"] == "proj-dev"
    assert captured["credentials_path"] == creds_file
    assert captured["templates_dir"] is None
    assert out_cfg.exists()


def test_google_rest_client_overrides_adc_quota_project_and_retries_propagation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google.auth.credentials import CredentialsWithQuotaProject

    class _FakeAdcCreds(CredentialsWithQuotaProject):
        def __init__(self, quota_project_id: str | None) -> None:
            super().__init__()
            self._quota_project_id = quota_project_id

        def refresh(self, request: Any) -> None:
            _ = request

        def with_quota_project(self, quota_project_id: str | None) -> _FakeAdcCreds:
            return _FakeAdcCreds(quota_project_id)

    captured_creds: list[Any] = []

    class _FakeAuthSession:
        def __init__(self, creds: Any) -> None:
            captured_creds.append(creds)

    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "photosphere.storage.gcs_client.google.auth.default",
        lambda scopes: (_FakeAdcCreds("staging-255"), "staging-255"),
    )
    monkeypatch.setattr(
        "photosphere.init.rest_client.AuthorizedSession", _FakeAuthSession
    )

    GoogleRestClient("target-project")
    assert len(captured_creds) == 1
    assert captured_creds[0]._quota_project_id == "target-project"

    # Verify API propagation retry on 403 SERVICE_DISABLED
    attempts = {"get_firebase": 0}

    def _propagation_handler(call: dict[str, Any]) -> _FakeResponse:
        if "firebase.googleapis.com" in str(call["url"]) and call["method"] == "GET":
            attempts["get_firebase"] += 1
            if attempts["get_firebase"] == 1:
                return _FakeResponse(
                    403,
                    {
                        "error": {
                            "status": "PERMISSION_DENIED",
                            "message": (
                                "Firebase Management API has not been used in "
                                "project target-project"
                            ),
                        }
                    },
                )
            return _FakeResponse(200, {"projectId": "target-project"})
        raise AssertionError(f"Unexpected call: {call}")

    slept: list[float] = []
    client = GoogleRestClient(
        "target-project", session=_FakeSession(_propagation_handler)
    )
    provisioner = BootstrapProvisioner(
        client,
        lambda u, s: None,
        templates_dir=_setup_infra(tmp_path),
        sleep_fn=slept.append,
    )
    provisioner.ensure_firebase_project("target-project")
    assert attempts["get_firebase"] == 2
    assert slept == [5.0]


def test_provision_bucket_prompts_for_billing_and_retries(tmp_path: Path) -> None:
    billing_state = {"enabled": False}
    prompts: list[tuple[str, str]] = []

    def _prompt(url: str, instruction: str) -> None:
        prompts.append((url, instruction))
        billing_state["enabled"] = True

    def _handler(call: dict[str, Any]) -> _FakeResponse:
        if "/storage/v1/b?project=proj-dev" in str(call["url"]):
            if not billing_state["enabled"]:
                return _FakeResponse(
                    403,
                    {
                        "error": {
                            "message": (
                                "The billing account for the owning project is "
                                "disabled in state absent"
                            )
                        }
                    },
                )
            return _FakeResponse(200, {"name": call["json"]["name"]})
        raise AssertionError(f"Unexpected call: {call}")

    client = GoogleRestClient("proj-dev", session=_FakeSession(_handler))
    provisioner = BootstrapProvisioner(
        client, _prompt, templates_dir=_setup_infra(tmp_path)
    )
    provisioner.provision_bucket(
        "proj-dev", "proj-dev-media", "europe-west8", "STANDARD", []
    )
    assert len(prompts) == 1
    assert "usage/details" in prompts[0][0]
