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
- **Project Bootstrap ([src/photosphere/init/](./src/photosphere/init/)):**
  - `photosphere init` provisions GCP/Firebase APIs, dual GCS buckets, CORS, empty JSON database seeds, Firebase Storage links, email-gated `storage.rules` (using `./infra/` or bundled `templates/`), Firebase Web App SDK config, and Firebase Auth into `photosphere.config.json`.
- **Storage & Pipeline ([src/photosphere/storage/](./src/photosphere/storage/), [src/photosphere/pipeline/](./src/photosphere/pipeline/)):**
  - Supports isolated profiles via `--profile <name>` / `PHOTOSPHERE_PROFILE` (default `default`, with an interactive confirmation prompt unless `-y`/`--yes` or non-TTY). Loads `photosphere.config.json` via `--config-file` > `PHOTOSPHERE_CONFIG_PATH` > `~/.photosphere/profiles/<profile>/photosphere.config.json` (plus CWD/parent/legacy `~/.photosphere/photosphere.config.json` fallback for `default`), resolves GCP credentials (`STORAGE_EMULATOR_HOST` > `--creds` > `GOOGLE_APPLICATION_CREDENTIALS` > `~/.photosphere/credentials.json` > `gcloud` ADC), verifies bucket classes, logs progress to a per-profile NDJSON checkpoint, uploads originals and `thumbnails/` to the media bucket, and updates JSON databases in the data bucket using `if_generation_match`.

## Host-Native Install & Diagnostics

```bash
uv tool install ./cli
# Or with Phase-2 AI extras:
uv tool install "./cli[ai]" --torch-backend=auto

photosphere init
photosphere doctor
photosphere prefetch-models --lang it
photosphere ingest /path/to/media --routing-mode chronological --init-db --no-ai
photosphere ingest /path/to/media --routing-mode chronological --dry-run
photosphere ingest /path/to/media --offline
```

- Shared AI model cache: `~/.photosphere/cache` (override with `PHOTOSPHERE_MODELS_DIR`); stores Hugging Face weights, `transformers_modules`, and EasyNMT models across all profiles.
- Per-profile runtime state: `~/.photosphere/profiles/<profile>/{photosphere.config.json,cache/,skipped/}` (override with `PHOTOSPHERE_CACHE_DIR` and `PHOTOSPHERE_SKIPPED_DIR`); isolates thumbnails, `ingest_checkpoint.ndjson`, DB snapshots, and skipped files per profile.
- `--offline` (or `PHOTOSPHERE_AI_OFFLINE=1`): Loads local AI and translation models with `local_files_only=True` without contacting `huggingface.co`.
- `PHOTOSPHERE_AI_MAX_IMAGE_SIZE`: Max pixel dimension for in-memory AI image resizing (default `378`, matching Moondream2's native single tile; set `1024` for multi-crop detail).
- `PHOTOSPHERE_AI_DTYPE`: Local AI floating-point dtype (`auto`, `float16`, `bfloat16`, `float32`; `auto` selects `bfloat16` on macOS MPS and CPU, and `bfloat16`/fallback `float16` on CUDA).
- `--routing-mode`: `chronological` (default; `result/YYYY/MM/DD/<filename>` or `no_datetime/<filename>`) or `preserve` (relative path from input directory).
- `--commit-every`: Commits `en_` dictionaries and `photosphere_database_cloud.json` every `N` new uploads (default `100`).
- `--dry-run`: Previews active `routing_mode`, planned GCS destination keys, and collisions without uploading, moving files to `skipped/`, writing thumbnails, or running AI.

## Invariants

1. Non-404 database download failures abort immediately unless `--init-db` is passed on an initialized empty bucket.
2. Core CLI commands and tests never require PyTorch or ML model weights.
3. No `.pb` or TinyDB `_default` structures are generated or accepted.

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright src tests
uv run mypy src tests
uv run pytest tests
```
