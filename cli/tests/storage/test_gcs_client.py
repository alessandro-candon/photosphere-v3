"""Unit tests for photosphere.storage.gcs_client."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from photosphere.storage.gcs_client import (
    BucketClassError,
    GCSStorageClient,
    StorageConflictError,
    StorageSyncError,
    resolve_credentials_source,
)
from tests.conftest import make_gcs


def test_gcs_storage_client_enforces_bucket_classes_and_aborts_on_missing_db() -> None:
    bad_gcs, _, _ = make_gcs(media_class="STANDARD", data_class="STANDARD")
    with pytest.raises(BucketClassError, match="ARCHIVE"):
        bad_gcs.verify_bucket_classes("test-media-archive", "test-data-standard")

    good_gcs, _, _ = make_gcs(media_class="ARCHIVE", data_class="STANDARD")
    with pytest.raises(StorageSyncError, match="Pass --init-db"):
        good_gcs.download_json(
            "test-data-standard", "photosphere_database_cloud.json", init_db=False
        )


def test_gcs_upload_errors_wrap_in_storage_sync_error(tmp_path: Path) -> None:
    from google.api_core.exceptions import PreconditionFailed, ServiceUnavailable

    class FailingBlob:
        generation = 1

        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        def upload_from_filename(self, *args: Any, **kwargs: Any) -> None:
            _ = args, kwargs
            raise self._exc

        def upload_from_string(self, *args: Any, **kwargs: Any) -> None:
            _ = args, kwargs
            raise self._exc

    class FailingBucket:
        storage_class = "STANDARD"

        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        def blob(self, name: str) -> FailingBlob:
            _ = name
            return FailingBlob(self._exc)

    class FailingClient:
        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        def bucket(self, name: str) -> FailingBucket:
            _ = name
            return FailingBucket(self._exc)

    sample = tmp_path / "a.jpg"
    sample.write_bytes(b"data")

    gcs_generic = GCSStorageClient(
        client=FailingClient(ServiceUnavailable("backend error"))  # type: ignore[arg-type]
    )
    with pytest.raises(StorageSyncError, match="Failed to upload gs://bkt/a.jpg"):
        gcs_generic.upload_blob("bkt", sample, "a.jpg", if_generation_match=0)

    with pytest.raises(StorageSyncError, match="Failed to upload gs://bkt/db.json"):
        gcs_generic.upload_json_atomic(
            "bkt", "db.json", {"a": 1}, if_generation_match=1
        )

    gcs_conflict = GCSStorageClient(
        client=FailingClient(PreconditionFailed("gen mismatch"))  # type: ignore[arg-type]
    )
    with pytest.raises(
        StorageConflictError,
        match="Remote database changed concurrently.*bkt/a.jpg.*re-run",
    ):
        gcs_conflict.upload_blob("bkt", sample, "a.jpg", if_generation_match=0)

    with pytest.raises(
        StorageConflictError,
        match="Remote database changed concurrently.*bkt/db.json.*re-run",
    ):
        gcs_conflict.upload_json_atomic(
            "bkt", "db.json", {"a": 1}, if_generation_match=1
        )


def test_resolve_credentials_source_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    missing_creds = tmp_path / "missing.json"
    with pytest.raises(StorageSyncError, match="Credentials file not found"):
        resolve_credentials_source(missing_creds)

    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    source, _ = resolve_credentials_source()
    assert source == "emulator"

    seen_scopes: list[list[str]] = []

    def _fake_default(*, scopes: list[str]) -> tuple[object, str]:
        seen_scopes.append(list(scopes))
        return object(), "proj"

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "photosphere.storage.gcs_client.google.auth.default", _fake_default
    )
    custom_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    source_no_emu, _ = resolve_credentials_source(
        scopes=custom_scopes, allow_emulator=False
    )
    assert source_no_emu == "gcloud_adc"
    assert seen_scopes == [custom_scopes]
