# cli

Python 3.12 CLI package (`photosphere`) for local media scanning, EXIF/`ffprobe` extraction, `280x280` JPEG thumbnail generation, cryptographic/perceptual hashing, `skipped/` duplicate isolation, modular AI labeling/captioning (`AIProvider` `Protocol`), `EasyNMT` translation, and dual-bucket GCS synchronization.

## Package Boundary & Ownership

- **Media Processing ([src/photosphere/media/](./src/photosphere/media/)):**
  - `base.py`: Byte SHA-1 digest (`compute_sha1`) and extension classification (`IMAGE`, `VIDEO`, `FILE`).
  - `gps.py`: Base-32 `encode_geohash` and `dms_to_decimal` helpers matching `photosphere-v2`.
  - `image.py`: `pillow-heif` registration, `ImageOps.exif_transpose()`, EXIF date/GPS parsing, `16x16` `average_hash`, and `280x280` RGB JPEG `quality=75` thumbnails.
  - `video.py`: PyAV (`av`) in-process timestamp/GPS extraction, `DisplayMatrix` rotation handling, `0b...` 64-bit wavelet perceptual hash collage, and first-frame extraction scaled and saved through the same `280x280` RGB JPEG `quality=75` thumbnail pipeline (no host `ffmpeg`/`ffprobe` required).
- **Deduplication ([src/photosphere/dedup/](./src/photosphere/dedup/)):**
  - Exact byte SHA-1 `hash` matches, unsupported files, and `target_key_collision` files move to `skipped/` and append to `skipped_manifest.json`.
  - Novel files with `>= 90.0%` `average_hash` Hamming similarity reuse existing `label_indexes` and `caption_index`.
- **AI & Translation ([src/photosphere/ai/](./src/photosphere/ai/)):**
  - `AIProvider` `Protocol` decouples vision inference (`[ai]` optional extras; concrete model selected in phase 2).
  - `KeyValueStore` writes deterministic minified JSON (no random flushes); `EasyNMTTranslator` translates new `en_` entries with MT meta-note sanitization.
- **Storage & Pipeline ([src/photosphere/storage/](./src/photosphere/storage/), [src/photosphere/pipeline/](./src/photosphere/pipeline/)):**
  - Loads `photosphere.config.json` via `--config-file` > `PHOTOSPHERE_CONFIG_PATH` > `./photosphere.config.json` > `../photosphere.config.json` > `~/.photosphere/photosphere.config.json`, resolves GCP credentials (`STORAGE_EMULATOR_HOST` > `--creds` > `GOOGLE_APPLICATION_CREDENTIALS` > `~/.photosphere/credentials.json` > `gcloud` ADC), verifies bucket classes, logs progress to a local NDJSON checkpoint, uploads originals and `thumbnails/` to the media bucket, and updates JSON databases in the data bucket using `if_generation_match`.

## Host-Native Install & Diagnostics

```bash
uv tool install ./cli
# Or with Phase-2 AI extras:
uv tool install "./cli[ai]" --torch-backend=auto

photosphere doctor
photosphere ingest /path/to/media --routing-mode chronological --init-db --no-ai
photosphere ingest /path/to/media --routing-mode chronological --dry-run
```

- `--routing-mode`: `chronological` (default; `YYYY/MM/DD/<filename>` or `no_datetime/<filename>`) or `preserve` (relative path from input directory).
- `--commit-every`: Commits `en_` dictionaries and `photosphere_database_cloud.json` every `N` new uploads (default `100`).
- `--dry-run`: Previews active `routing_mode`, planned GCS destination keys, and collisions without uploading, moving files to `skipped/`, writing thumbnails, or running AI.

## Invariants

1. Non-404 database download failures abort immediately unless `--init-db` is passed on an initialized empty bucket.
2. Core CLI commands and tests never require PyTorch or ML model weights.
3. No `.pb` or TinyDB `_default` structures are generated or accepted.

## Verification

```bash
uv run ruff check . ../scripts
uv run ruff format --check . ../scripts
uv run pyright src tests ../scripts
uv run mypy src tests ../scripts
uv run pytest tests ../scripts
```
