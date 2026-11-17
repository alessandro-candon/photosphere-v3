"""Unit tests for the isolated disposable v2-to-v3 migration script."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.migrate_v2_to_v3 import (
    ALBUMS_FILENAME,
    CAPTIONS_DB_SUFFIX,
    LABELS_DB_SUFFIX,
    MEDIA_DB_FILENAME,
    MigrationValidationError,
    convert_tinydb_to_flat,
    run_migration,
    validate_migration_outputs,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"


class _MemoryBlob:
    def __init__(self, bucket: _MemoryBucket, name: str) -> None:
        self.bucket = bucket
        self.name = name
        self.generation = 1

    def exists(self) -> bool:
        return self.name in self.bucket.objects

    def reload(self) -> None:
        self.generation = self.bucket.generations.get(self.name, 1)

    def download_as_bytes(self) -> bytes:
        from google.api_core.exceptions import NotFound

        if self.name not in self.bucket.objects:
            raise NotFound(self.name)
        return self.bucket.objects[self.name]

    def upload_from_string(
        self,
        data: str | bytes,
        *,
        content_type: str | None = None,
        if_generation_match: int | None = None,
    ) -> None:
        _ = content_type
        _ = if_generation_match
        raw = data.encode("utf-8") if isinstance(data, str) else data
        self.bucket.objects[self.name] = raw
        prev_gen = self.bucket.generations.get(self.name, 0)
        self.bucket.generations[self.name] = prev_gen + 1


class _MemoryBucket:
    def __init__(self, storage_class: str) -> None:
        self.storage_class = storage_class
        self.objects: dict[str, bytes] = {}
        self.generations: dict[str, int] = {}

    def blob(self, name: str) -> _MemoryBlob:
        return _MemoryBlob(self, name)


class _MemoryGCSClient:
    def __init__(self, buckets: dict[str, _MemoryBucket]) -> None:
        self._buckets = buckets

    def bucket(self, name: str) -> _MemoryBucket:
        return self._buckets[name]

    def get_bucket(self, name: str) -> _MemoryBucket:
        return self._buckets[name]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_convert_tinydb_to_flat_removes_local_file_path_and_keys_by_hash() -> None:
    legacy = _load_json(CONTRACTS_DIR / "fixtures" / "legacy_v2_tinydb.json")
    flat = convert_tinydb_to_flat(legacy)

    assert len(flat) == 2
    for key, record in flat.items():
        assert key == record["hash"]
        assert "local_file_path" not in record


def test_convert_tinydb_rejects_duplicate_hash() -> None:
    legacy = _load_json(CONTRACTS_DIR / "fixtures" / "legacy_v2_tinydb.json")
    legacy["_default"]["3"] = dict(legacy["_default"]["1"])
    with pytest.raises(MigrationValidationError, match="Duplicate SHA-1"):
        convert_tinydb_to_flat(legacy)


def test_validate_migration_outputs_catches_broken_foreign_key() -> None:
    media_db = _load_json(CONTRACTS_DIR / "fixtures" / "valid_media_db.json")
    en_labels = _load_json(CONTRACTS_DIR / "fixtures" / "valid_en_labels.json")
    en_captions = _load_json(CONTRACTS_DIR / "fixtures" / "valid_en_captions.json")
    albums = _load_json(CONTRACTS_DIR / "fixtures" / "valid_albums.json")

    albums[0]["hashes"].append("f" * 40)
    with pytest.raises(MigrationValidationError, match="references missing"):
        validate_migration_outputs(
            media_db,
            {"en": en_labels},
            {"en": en_captions},
            albums,
            contracts_dir=CONTRACTS_DIR,
        )

    albums[0]["hashes"].pop()
    first_key = next(iter(media_db))
    orig_caption = media_db[first_key]["caption_index"]
    media_db[first_key]["caption_index"] = 999
    with pytest.raises(MigrationValidationError, match="missing caption index"):
        validate_migration_outputs(
            media_db,
            {"en": en_labels},
            {"en": en_captions},
            albums,
            contracts_dir=CONTRACTS_DIR,
        )
    media_db[first_key]["caption_index"] = orig_caption

    media_db[first_key]["label_indexes"] = [999]
    with pytest.raises(MigrationValidationError, match="missing label index"):
        validate_migration_outputs(
            media_db,
            {"en": en_labels},
            {"en": en_captions},
            albums,
            contracts_dir=CONTRACTS_DIR,
        )


def test_dry_run_and_apply_preserve_archive_and_write_backups(tmp_path: Path) -> None:
    archive = _MemoryBucket("ARCHIVE")
    standard = _MemoryBucket("STANDARD")

    legacy_bytes = (CONTRACTS_DIR / "fixtures" / "legacy_v2_tinydb.json").read_bytes()
    labels_bytes = (CONTRACTS_DIR / "fixtures" / "valid_en_labels.json").read_bytes()
    captions_bytes = (
        CONTRACTS_DIR / "fixtures" / "valid_en_captions.json"
    ).read_bytes()
    albums_bytes = (CONTRACTS_DIR / "fixtures" / "valid_albums.json").read_bytes()

    archive.objects[MEDIA_DB_FILENAME] = legacy_bytes
    archive.objects[f"en_{LABELS_DB_SUFFIX}"] = labels_bytes
    archive.objects[f"en_{CAPTIONS_DB_SUFFIX}"] = captions_bytes
    archive.objects[ALBUMS_FILENAME] = albums_bytes

    client: Any = _MemoryGCSClient({"archive-bkt": archive, "data-bkt": standard})

    dry_report = run_migration(
        media_bucket="archive-bkt",
        data_bucket="data-bkt",
        languages=["en"],
        backup_dir=tmp_path,
        apply=False,
        contracts_dir=CONTRACTS_DIR,
        client=client,
    )
    assert dry_report.applied is False
    assert dry_report.records_converted == 2
    assert standard.objects == {}
    assert (
        Path(dry_report.backup_dir) / MEDIA_DB_FILENAME
    ).read_bytes() == legacy_bytes

    live_report = run_migration(
        media_bucket="archive-bkt",
        data_bucket="data-bkt",
        languages=["en"],
        backup_dir=tmp_path,
        apply=True,
        contracts_dir=CONTRACTS_DIR,
        client=client,
    )
    assert live_report.applied is True
    assert MEDIA_DB_FILENAME in standard.objects
    assert archive.objects[MEDIA_DB_FILENAME] == legacy_bytes
    assert any(key.startswith("backups/v2_") for key in standard.objects)
