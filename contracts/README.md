# contracts

Canonical JSON Schema (Draft 2020-12) definitions and cross-language test fixtures shared between `../cli/README.md` and `../ssr/README.md`.

## Package Boundary & Ownership

- Owns the wire format for the four JSON files stored in the Standard GCS bucket (`PHOTOSPHERE_DATA_BUCKET`) and the unified root configuration file:
  - [media_database.schema.json](./media_database.schema.json): Flat SHA-1-keyed dictionary (`photosphere_database_cloud.json`). Rejects TinyDB `_default` wrappers and transient `local_file_path` fields.
  - [kv_dictionary.schema.json](./kv_dictionary.schema.json): Flat stringified non-negative integer dictionaries (`<lang>_photosphere_image_labelling_database_cloud.json` and `<lang>_photosphere_image_caption_database_cloud.json`).
  - [albums.schema.json](./albums.schema.json): User-editable album list (`photosphere_albums.json`).
  - [photosphere_config.schema.json](./photosphere_config.schema.json): Unified root `photosphere.config.json` contract shared across `../cli/` (`photosphere init`), `../ssr/`, and container builds.
- Shared fixtures live under [fixtures/](./fixtures/): `valid_media_db.json`, `valid_en_labels.json`, `valid_en_captions.json`, `valid_albums.json`, `valid_photosphere_config.json`, and `legacy_v2_tinydb.json`.

## Invariants

1. Primary key in `photosphere_database_cloud.json` is the lowercase 40-character hexadecimal byte SHA-1 digest (`hash`), and `record["hash"]` must equal the enclosing dictionary key.
2. `source_bucket_uri` and `thumbnail_bucket_uri` always reference `gs://<media-bucket>/...` (the Archive bucket) so existing objects never move.
3. Protobuf (`.pb`) schemas are excluded.

## Verification

- Python (`cli/`): `cd ../cli && uv run pytest tests/test_models_contracts.py`
- TypeScript (`ssr/`): `cd ../ssr && pnpm test`
