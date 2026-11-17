"""Isolated one-time migration script: converts v2 TinyDB JSONs to v3 flat JSON.

Designed to be executed once (`make migrate-v2`) and deleted cleanly after cutover.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import jsonschema
from google.api_core.exceptions import NotFound
from google.auth.credentials import AnonymousCredentials
from google.cloud import storage

SHA1_HEX_RE = re.compile(r"^[0-9a-f]{40}$")
MEDIA_DB_FILENAME = "photosphere_database_cloud.json"
LABELS_DB_SUFFIX = "photosphere_image_labelling_database_cloud.json"
CAPTIONS_DB_SUFFIX = "photosphere_image_caption_database_cloud.json"
ALBUMS_FILENAME = "photosphere_albums.json"
DEFAULT_CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"


class MigrationValidationError(RuntimeError):
    """Raised when legacy v2 data fails conversion, schema, or FK checks."""


@dataclass(slots=True)
class MigrationReport:
    """Summary counts emitted by a dry-run or live v2-to-v3 migration."""

    records_converted: int
    languages_migrated: list[str]
    albums_migrated: int
    backup_dir: str
    applied: bool


def _build_client(client: storage.Client | None = None) -> storage.Client:
    if client is not None:
        return client
    if os.getenv("STORAGE_EMULATOR_HOST"):
        return storage.Client(
            credentials=AnonymousCredentials(),
            project="photosphere-local",
        )
    return storage.Client()


def convert_tinydb_to_flat(legacy_payload: object) -> dict[str, dict[str, Any]]:
    """Convert TinyDB {'_default': {'1': ...}} JSON to flat SHA-1 dictionary."""
    if not isinstance(legacy_payload, dict) or "_default" not in legacy_payload:
        raise MigrationValidationError("Expected TinyDB '_default' dictionary.")

    rows = legacy_payload["_default"]
    if not isinstance(rows, dict):
        raise MigrationValidationError("Expected TinyDB '_default' to be an object.")

    flat: dict[str, dict[str, Any]] = {}
    for row_id, raw_record in rows.items():
        if not isinstance(raw_record, dict):
            raise MigrationValidationError(f"Record '{row_id}' is not an object.")
        sha1 = raw_record.get("hash")
        if not isinstance(sha1, str) or not SHA1_HEX_RE.match(sha1):
            raise MigrationValidationError(
                f"Record '{row_id}' has invalid SHA-1: {sha1!r}"
            )
        if sha1 in flat:
            raise MigrationValidationError(f"Duplicate SHA-1 '{sha1}' in TinyDB.")

        cleaned = {
            key: value for key, value in raw_record.items() if key != "local_file_path"
        }
        flat[sha1] = cleaned

    return flat


def _validate_schema(instance: object, schema_path: Path, label: str) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as exc:
        raise MigrationValidationError(
            f"Schema validation failed for {label}: {exc.message}"
        ) from exc


def _check_foreign_keys(
    media_db: dict[str, dict[str, Any]],
    labels_by_lang: dict[str, dict[str, str]],
    captions_by_lang: dict[str, dict[str, str]],
    albums: list[dict[str, Any]],
) -> None:
    primary_labels = next(iter(labels_by_lang.values()), {})
    primary_captions = next(iter(captions_by_lang.values()), {})

    for sha1, record in media_db.items():
        for label_idx in record.get("label_indexes", []):
            if str(label_idx) not in primary_labels:
                raise MigrationValidationError(
                    f"Record '{sha1}' references missing label index {label_idx}."
                )
        caption_idx = record.get("caption_index")
        if caption_idx is not None and str(caption_idx) not in primary_captions:
            raise MigrationValidationError(
                f"Record '{sha1}' references missing caption index {caption_idx}."
            )

    for album in albums:
        for member_hash in album.get("hashes", []):
            if member_hash not in media_db:
                raise MigrationValidationError(
                    f"Album '{album.get('name')}' references missing '{member_hash}'."
                )


def validate_migration_outputs(
    media_db: dict[str, dict[str, Any]],
    labels_by_lang: dict[str, dict[str, str]],
    captions_by_lang: dict[str, dict[str, str]],
    albums: list[dict[str, Any]],
    contracts_dir: Path = DEFAULT_CONTRACTS_DIR,
) -> None:
    """Validate all converted payloads against contracts and FK bounds."""
    _validate_schema(
        media_db,
        contracts_dir / "media_database.schema.json",
        MEDIA_DB_FILENAME,
    )
    kv_schema = contracts_dir / "kv_dictionary.schema.json"
    for lang, label_map in labels_by_lang.items():
        _validate_schema(label_map, kv_schema, f"{lang}_{LABELS_DB_SUFFIX}")
    for lang, caption_map in captions_by_lang.items():
        _validate_schema(caption_map, kv_schema, f"{lang}_{CAPTIONS_DB_SUFFIX}")
    _validate_schema(albums, contracts_dir / "albums.schema.json", ALBUMS_FILENAME)
    _check_foreign_keys(media_db, labels_by_lang, captions_by_lang, albums)


def _download_raw_bytes(
    client: storage.Client,
    bucket_name: str,
    object_name: str,
    *,
    allow_missing: bool = False,
) -> bytes | None:
    blob = client.bucket(bucket_name).blob(object_name)
    try:
        return blob.download_as_bytes()
    except NotFound as exc:
        if allow_missing:
            return None
        raise MigrationValidationError(
            f"Required v2 object gs://{bucket_name}/{object_name} not found."
        ) from exc


def _download_lang_dict(
    client: storage.Client,
    bucket_name: str,
    lang: str,
    suffix: str,
    downloaded: dict[str, bytes],
) -> dict[str, str] | None:
    prefixed = f"{lang}_{suffix}"
    raw = _download_raw_bytes(
        client, bucket_name, prefixed, allow_missing=(lang == "en")
    )
    source_name = prefixed
    if raw is None and lang == "en":
        raw = _download_raw_bytes(client, bucket_name, suffix, allow_missing=True)
        source_name = suffix
    if raw is None:
        return None
    downloaded[source_name] = raw
    parsed = json.loads(raw.decode("utf-8"))
    return {str(k): str(v) for k, v in parsed.items()}


def write_verbatim_backups(
    downloaded_files: dict[str, bytes],
    backup_dir: Path,
    *,
    timestamp: str,
    client: storage.Client | None = None,
    data_bucket: str | None = None,
) -> Path:
    """Write verbatim v2 JSON backups locally and optionally to data_bucket."""
    local_backup = backup_dir / f"v2_{timestamp}"
    local_backup.mkdir(parents=True, exist_ok=True)
    for filename, raw_bytes in downloaded_files.items():
        (local_backup / filename).write_bytes(raw_bytes)
        if client is not None and data_bucket is not None:
            blob = client.bucket(data_bucket).blob(f"backups/v2_{timestamp}/{filename}")
            blob.upload_from_string(raw_bytes, content_type="application/json")
    return local_backup


def _upload_json(
    client: storage.Client,
    bucket_name: str,
    object_name: str,
    payload: object,
) -> None:
    blob = client.bucket(bucket_name).blob(object_name)
    generation = 0
    if blob.exists():
        blob.reload()
        generation = blob.generation or 0
    serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    blob.upload_from_string(
        serialized,
        content_type="application/json",
        if_generation_match=generation,
    )


def _upload_all_converted(
    client: storage.Client,
    data_bucket: str,
    media_db: dict[str, dict[str, Any]],
    labels_by_lang: dict[str, dict[str, str]],
    captions_by_lang: dict[str, dict[str, str]],
    albums: list[dict[str, Any]],
) -> None:
    if not os.getenv("STORAGE_EMULATOR_HOST"):
        target_bkt = client.get_bucket(data_bucket)
        if target_bkt.storage_class != "STANDARD":
            raise MigrationValidationError(
                f"Target bucket '{data_bucket}' must have storage_class STANDARD, "
                f"found '{target_bkt.storage_class}'."
            )

    _upload_json(client, data_bucket, MEDIA_DB_FILENAME, media_db)
    for lang, label_map in labels_by_lang.items():
        _upload_json(client, data_bucket, f"{lang}_{LABELS_DB_SUFFIX}", label_map)
    for lang, caption_map in captions_by_lang.items():
        _upload_json(client, data_bucket, f"{lang}_{CAPTIONS_DB_SUFFIX}", caption_map)
    _upload_json(client, data_bucket, ALBUMS_FILENAME, albums)


def run_migration(
    *,
    media_bucket: str,
    data_bucket: str,
    languages: list[str],
    backup_dir: Path,
    apply: bool,
    init_missing_albums: bool = False,
    contracts_dir: Path = DEFAULT_CONTRACTS_DIR,
    client: storage.Client | None = None,
) -> MigrationReport:
    """Execute v2 Archive -> v3 Standard bucket conversion with verbatim backups."""
    gcs = _build_client(client)
    downloaded: dict[str, bytes] = {}

    raw_media_bytes = _download_raw_bytes(gcs, media_bucket, MEDIA_DB_FILENAME)
    assert raw_media_bytes is not None
    downloaded[MEDIA_DB_FILENAME] = raw_media_bytes
    media_db = convert_tinydb_to_flat(json.loads(raw_media_bytes.decode("utf-8")))

    labels_by_lang: dict[str, dict[str, str]] = {}
    captions_by_lang: dict[str, dict[str, str]] = {}
    for lang in languages:
        loaded_labels = _download_lang_dict(
            gcs, media_bucket, lang, LABELS_DB_SUFFIX, downloaded
        )
        if loaded_labels is not None:
            labels_by_lang[lang] = loaded_labels
        loaded_captions = _download_lang_dict(
            gcs, media_bucket, lang, CAPTIONS_DB_SUFFIX, downloaded
        )
        if loaded_captions is not None:
            captions_by_lang[lang] = loaded_captions

    raw_albums = _download_raw_bytes(
        gcs, media_bucket, ALBUMS_FILENAME, allow_missing=init_missing_albums
    )
    albums: list[dict[str, Any]] = []
    if raw_albums is not None:
        downloaded[ALBUMS_FILENAME] = raw_albums
        albums = list(json.loads(raw_albums.decode("utf-8")))

    validate_migration_outputs(
        media_db, labels_by_lang, captions_by_lang, albums, contracts_dir=contracts_dir
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    local_backup_path = write_verbatim_backups(
        downloaded,
        backup_dir,
        timestamp=timestamp,
        client=gcs if apply else None,
        data_bucket=data_bucket if apply else None,
    )

    if apply:
        _upload_all_converted(
            gcs, data_bucket, media_db, labels_by_lang, captions_by_lang, albums
        )

    return MigrationReport(
        records_converted=len(media_db),
        languages_migrated=sorted(labels_by_lang.keys()),
        albums_migrated=len(albums),
        backup_dir=str(local_backup_path),
        applied=apply,
    )


@click.command()
@click.option("--media-bucket", required=True, help="Source Archive v2 bucket name.")
@click.option("--data-bucket", required=True, help="Target Standard v3 bucket name.")
@click.option(
    "--languages",
    default="en",
    show_default=True,
    help="Comma-separated language codes.",
)
@click.option(
    "--backup-dir",
    default=Path("./backups"),
    type=click.Path(path_type=Path),
    show_default=True,
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Convert, backup locally, and validate without uploading.",
)
@click.option(
    "--apply",
    is_flag=True,
    help="Upload converted v3 databases to data-bucket.",
)
@click.option(
    "--init-missing-albums",
    is_flag=True,
    help="Default missing albums file to [].",
)
def main(
    media_bucket: str,
    data_bucket: str,
    languages: str,
    backup_dir: Path,
    dry_run: bool,
    apply: bool,
    init_missing_albums: bool,
) -> None:
    """One-time v2 TinyDB to v3 flat JSON migration command."""
    if dry_run and apply:
        raise click.UsageError("Pass either --dry-run or --apply, not both.")
    parsed_langs = [lang.strip() for lang in languages.split(",") if lang.strip()]
    report = run_migration(
        media_bucket=media_bucket,
        data_bucket=data_bucket,
        languages=parsed_langs or ["en"],
        backup_dir=backup_dir,
        apply=apply,
        init_missing_albums=init_missing_albums,
    )
    click.echo(json.dumps(report.__dict__, indent=2))


if __name__ == "__main__":
    main()
