"""GCS dual-bucket storage client with storage-class and generation guards."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import google.auth
from google.api_core.exceptions import GoogleAPICallError, NotFound, PreconditionFailed
from google.auth.credentials import AnonymousCredentials
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from google.cloud import storage

_GCS_SCOPES = ["https://www.googleapis.com/auth/devstorage.read_write"]


class StorageSyncError(RuntimeError):
    """Raised on unsafe GCS database download or conditional upload errors."""


class BucketClassError(StorageSyncError):
    """Raised when media or data GCS buckets do not match expected storage classes."""


class StorageConflictError(StorageSyncError):
    """Raised on HTTP 412 precondition failures from concurrent GCS writes."""


def resolve_credentials_source(
    credentials_path: Path | None = None,
    *,
    scopes: list[str] = _GCS_SCOPES,
    allow_emulator: bool = True,
) -> tuple[str, Any]:
    """Resolve GCP credentials in strict precedence order.

    Order: STORAGE_EMULATOR_HOST > --creds > GOOGLE_APPLICATION_CREDENTIALS
    > ~/.photosphere/credentials.json > standard gcloud ADC.
    """
    if allow_emulator and os.getenv("STORAGE_EMULATOR_HOST"):
        return "emulator", AnonymousCredentials()

    if credentials_path is not None:
        resolved = credentials_path.expanduser().resolve()
        if not resolved.exists():
            raise StorageSyncError(f"Credentials file not found: {resolved}")
        creds, _ = google.auth.load_credentials_from_file(str(resolved), scopes=scopes)
        return f"creds:{resolved}", creds

    env_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_creds:
        try:
            creds, _ = google.auth.default(scopes=scopes)
            return f"env:{env_creds}", creds
        except DefaultCredentialsError as exc:
            raise StorageSyncError(
                f"Failed to load GOOGLE_APPLICATION_CREDENTIALS ({env_creds}): {exc}"
            ) from exc

    photosphere_creds = Path.home() / ".photosphere" / "credentials.json"
    if photosphere_creds.exists():
        creds, _ = google.auth.load_credentials_from_file(
            str(photosphere_creds), scopes=scopes
        )
        return f"file:{photosphere_creds}", creds

    try:
        creds, _ = google.auth.default(scopes=scopes)
        return "gcloud_adc", creds
    except (DefaultCredentialsError, RefreshError) as exc:
        raise StorageSyncError(
            "No valid GCP credentials found. Run `gcloud auth application-default "
            "login` or pass `--creds <service-account.json>`."
        ) from exc


def _build_storage_client(
    client: storage.Client | None = None,
    project: str | None = None,
    credentials_path: Path | None = None,
) -> storage.Client:
    if client is not None:
        return client
    source, creds = resolve_credentials_source(credentials_path)
    if source == "emulator":
        return storage.Client(credentials=creds, project="photosphere-local")
    return storage.Client(project=project, credentials=creds)


class GCSStorageClient:
    """Thin GCS wrapper supporting dual-bucket validation and atomic JSON uploads."""

    def __init__(
        self,
        client: storage.Client | None = None,
        *,
        project: str | None = None,
        credentials_path: Path | None = None,
    ) -> None:
        self._client = _build_storage_client(
            client, project=project, credentials_path=credentials_path
        )

    def verify_bucket_classes(
        self,
        media_bucket: str,
        data_bucket: str,
        *,
        expected_media_class: str = "ARCHIVE",
        expected_data_class: str = "STANDARD",
        strict: bool = True,
    ) -> None:
        """Verify data_bucket and media_bucket match expected GCS storage classes."""
        if not strict or os.getenv("STORAGE_EMULATOR_HOST"):
            return

        media_bkt = self._client.get_bucket(media_bucket)
        data_bkt = self._client.get_bucket(data_bucket)
        if data_bkt.storage_class != expected_data_class:
            raise BucketClassError(
                f"Expected data bucket '{data_bucket}' storage_class "
                f"{expected_data_class}, found '{data_bkt.storage_class}'."
            )
        if media_bkt.storage_class != expected_media_class:
            raise BucketClassError(
                f"Expected media bucket '{media_bucket}' storage_class "
                f"{expected_media_class}, found '{media_bkt.storage_class}'."
            )

    def download_json(
        self,
        bucket_name: str,
        object_name: str,
        *,
        init_db: bool = False,
    ) -> tuple[Any, int | None]:
        """Download JSON object and generation; abort on non-404 errors."""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        try:
            blob.reload()
            raw_text = blob.download_as_text(encoding="utf-8")
            return json.loads(raw_text), blob.generation
        except NotFound as exc:
            if init_db:
                return None, None
            raise StorageSyncError(
                f"Object gs://{bucket_name}/{object_name} not found. "
                "Pass --init-db only when initializing an empty database."
            ) from exc
        except (GoogleAPICallError, json.JSONDecodeError) as exc:
            raise StorageSyncError(
                f"Failed to download gs://{bucket_name}/{object_name}: {exc}"
            ) from exc

    def download_blob(
        self,
        bucket_name: str,
        object_name: str,
        destination: Path,
    ) -> Path:
        """Download a GCS object to destination and return the destination path."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        try:
            blob.download_to_filename(str(destination))
            return destination
        except GoogleAPICallError as exc:
            raise StorageSyncError(
                f"Failed to download gs://{bucket_name}/{object_name}: {exc}"
            ) from exc

    def upload_blob(
        self,
        bucket_name: str,
        source_path: Path,
        object_name: str,
        content_type: str | None = None,
        *,
        if_generation_match: int | None = None,
    ) -> str:
        """Upload a local media or thumbnail file to GCS and return its gs:// URI."""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        kwargs: dict[str, Any] = {}
        if content_type is not None:
            kwargs["content_type"] = content_type
        if if_generation_match is not None:
            kwargs["if_generation_match"] = if_generation_match
        try:
            blob.upload_from_filename(str(source_path), **kwargs)
        except PreconditionFailed as exc:
            raise StorageConflictError(
                f"Remote database changed concurrently while uploading "
                f"gs://{bucket_name}/{object_name}; re-run the command."
            ) from exc
        except GoogleAPICallError as exc:
            raise StorageSyncError(
                f"Failed to upload gs://{bucket_name}/{object_name}: {exc}"
            ) from exc
        return f"gs://{bucket_name}/{object_name}"

    def upload_json_atomic(
        self,
        bucket_name: str,
        object_name: str,
        payload: object,
        *,
        if_generation_match: int | None = None,
    ) -> int | None:
        """Serialize minified JSON and upload with optional GCS generation match."""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        kwargs: dict[str, Any] = {"content_type": "application/json"}
        if if_generation_match is not None:
            kwargs["if_generation_match"] = if_generation_match
        try:
            blob.upload_from_string(serialized, **kwargs)
        except PreconditionFailed as exc:
            raise StorageConflictError(
                f"Remote database changed concurrently while uploading "
                f"gs://{bucket_name}/{object_name}; re-run the command."
            ) from exc
        except GoogleAPICallError as exc:
            raise StorageSyncError(
                f"Failed to upload gs://{bucket_name}/{object_name}: {exc}"
            ) from exc
        return blob.generation
