# Implementation Plan: CLI Clean-Code Refactoring, Optimization, Resilience & Mirrored Test Suite

## Goal Description

Refactor and harden the `photosphere` CLI (`cli/`) without altering any external CLI commands, flags, or JSON schema contracts. The improvements focus on five pillars:
1. **DRY & Clean Architecture**: Eliminate duplicated database loading, atomic committing, AI provider resolution, and translation orchestration across `IngestPipeline`, `AnnotatePipeline`, and `main.py` via `photosphere.pipeline.common`.
2. **Performance & Algorithmic Optimization**: Replace `O(N)` linear scans in `KeyValueStore` with an `O(1)` reverse index, pre-decode perceptual hashes in `photosphere.dedup.hashing`, avoid redundant SHA-1 hashing, and consolidate `av.open()` metadata + thumbnail extraction in `VideoProcessor`.
3. **Resilience & Fault Tolerance**: Isolate unreadable/corrupt media files via a narrow `MediaDecodeError` boundary to `skipped/` (`reason="processing_error"`), survive a truncated trailing line in `ingest_checkpoint.ndjson`, and normalize all GCS upload exceptions into `StorageSyncError`.
4. **Python Best Practices & Type Safety**: Standardize Click option decorators, keep McCabe complexity `<= 10` (`ruff`), and maintain zero `pyright` and `mypy` errors.
5. **1:1 Mirrored Test Architecture**: Reorganize `cli/tests/` to mirror `cli/src/photosphere/` directory-for-directory and add targeted unit and integration tests (raising `pytest --cov=photosphere` line coverage from 83% to >92%).

---

## User Review Required

> [!IMPORTANT]
> **Preserved CLI & Schema Contracts**: All CLI commands (`ingest`, `annotate`, `translate`, `verify-db`, `prefetch-models`, `doctor`, `version`), flags, environment variables, and JSON contracts remain backward-compatible. Existing module exports (`from photosphere.pipeline.ingest import CAPTIONS_DB_SUFFIX, LABELS_DB_SUFFIX, MEDIA_DB_FILENAME, IngestPipeline`) remain re-exported.

> [!NOTE]
> **Corrupt Media Isolation Semantics**:
> - `ImageProcessor` and `VideoProcessor` raise `MediaDecodeError` (defined in `photosphere.media.base`) when a file container/image cannot be decoded, while transient `OSError` (disk full, permission denied) continues to fail loudly.
> - During non-`dry_run` ingestion, `IngestPipeline` catches `MediaDecodeError`, logs `media_processing_failed`, moves the file to `skipped/` with `reason="processing_error"` (matching `SkippedEntry.reason` in `cli/src/photosphere/models/database.py` and `contracts/`), and increments `skipped_unsupported`. During `--dry-run`, it logs `media_processing_failed`, appends `PlannedUpload(action="skip_unsupported")`, and increments `skipped_unsupported` without moving files.

---

## Proposed Changes (4 Incremental Phases)

### Phase 1: DRY Pipeline & Database Sync Layer (`src/photosphere/pipeline/`)

#### [NEW] [common.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/pipeline/common.py)
- Canonical database filename constants: `MEDIA_DB_FILENAME`, `LABELS_DB_SUFFIX`, `CAPTIONS_DB_SUFFIX`, `ALBUMS_DB_FILENAME`.
- `create_ai_provider(settings: PhotosphereSettings) -> AIProvider`
- `load_remote_media_db(gcs: GCSStorageClient, settings: PhotosphereSettings, *, init_db: bool) -> tuple[dict[str, MediaRecord], int | None]`
- `load_remote_kv_store(gcs: GCSStorageClient, settings: PhotosphereSettings, object_name: str, *, allow_missing: bool) -> tuple[KeyValueStore, int | None]`
- `commit_media_and_english_dbs(...) -> tuple[int | None, int | None, int | None]` (keeps existing sequential append-only GCS upload order).
- `sync_target_language_dictionaries(...) -> int` (returns total newly translated entries; preserves `show_progress` compatibility for mock translators that omit the keyword arg).

#### [MODIFY] [ingest.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/pipeline/ingest.py) & [annotate.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/pipeline/annotate.py)
- Delegate `_load_remote_db`, `_load_kv_store`, `_resolve_ai_provider` (preserving `self.ai_provider` caching), `_commit_databases`, and `_run_translation` (preserving the `ai_annotated == 0 and self.translator is None` guard) to `pipeline.common`.
- Re-export `MEDIA_DB_FILENAME`, `LABELS_DB_SUFFIX`, `CAPTIONS_DB_SUFFIX` in `ingest.py`.
- In `ingest.py`, compute `sha1 = compute_sha1(file_path)` once upfront for supported media files, pass `sha1=sha1` into `ImageProcessor.process()` / `VideoProcessor.process()`, and catch `MediaDecodeError` as described above.

---

### Phase 2: Algorithmic & Media Processing Optimizations (`src/photosphere/ai/`, `dedup/`, `media/`)

#### [MODIFY] [translator.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/ai/translator.py)
- Maintain an `O(1)` reverse index `_value_to_index: dict[str, int]` in `KeyValueStore` synchronized across `__init__()`, `load_file()`, `from_mapping()`, `set_value_at_index()`, and `add_unique_value()`.
- Add `@classmethod KeyValueStore.from_mapping(cls, db_path: Path, raw: Mapping[str, Any] | None, *, flush: bool = False) -> KeyValueStore`.

#### [MODIFY] [hashing.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/dedup/hashing.py)
- Pre-decode `average_hash` once in `find_similar_annotated_record()`, returning `None` early if `average_hash` is empty or fails `_decode_hash_bits` / `ValueError`, and compare candidate hashes against the pre-decoded bits while preserving exact `hamming_distance_percentage` semantics.

#### [MODIFY] [base.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/media/base.py), [image.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/media/image.py), & [video.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/media/video.py)
- Add `MediaDecodeError(RuntimeError)` in `media/base.py`.
- Accept optional `sha1: str | None = None` in `ImageProcessor.process()` and `VideoProcessor.process()`.
- Raise `MediaDecodeError` in `ImageProcessor.process()` on `PIL.UnidentifiedImageError` / `ValueError` / `OSError` during image decoding, and in `VideoProcessor.process()` when `av.open(video_path)` fails on a corrupt container (preserving inner metadata/frame fallbacks for partially tagged videos).
- Combine metadata extraction and first-frame thumbnail extraction into a single `av.open()` pass in `video.py` (keeping `_extract_video_metadata` and `_extract_first_frame_jpeg` as thin wrappers/helpers for compatibility).

---

### Phase 3: Storage, Checkpoint Resilience & CLI Cleanup (`src/photosphere/storage/`, `main.py`)

#### [MODIFY] [gcs_client.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/storage/gcs_client.py)
- Wrap `GoogleAPICallError` in `upload_blob()` and `upload_json_atomic()` with `StorageSyncError`.

#### [MODIFY] [checkpoint.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/storage/checkpoint.py)
- Add `structlog` logger and `pydantic.ValidationError` import; in `CheckpointStore._load()`, tolerate `ValidationError` **only on the final non-empty line** (logging `checkpoint_line_corrupt`) while still failing fast on mid-file corruption.

#### [MODIFY] [main.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/main.py)
- Extract shared Click decorator `_ai_runtime_options` and `_build_ai_overrides(...)` for `ingest` and `annotate`.
- Use `ALBUMS_DB_FILENAME` and `load_remote_kv_store` / `KeyValueStore.from_mapping` in `translate` and `verify_db`.
- Move `verify_bucket_classes(...)` inside the `try` block in `translate` and wrap `ingest`, `translate`, and `verify_db` in `try/except StorageSyncError` -> `click.ClickException`.

---

### Phase 4: 1:1 Mirrored Test Suite (`cli/tests/`)

#### [DELETE] Legacy flat test files
- `cli/tests/test_ai_normalize.py`
- `cli/tests/test_annotate_pipeline.py`
- `cli/tests/test_ingest_pipeline.py`
- `cli/tests/test_media_and_dedup.py`
- `cli/tests/test_models_contracts.py`
- `cli/tests/test_moondream2_provider.py`
- `cli/tests/test_remote_ai_provider.py`

#### [NEW] 1:1 Mirrored test modules (keeping `conftest.py`, `test_config.py`, `test_main.py`, `test_progress.py` at `cli/tests/` root)
- `cli/tests/ai/`: `test_moondream2.py`, `test_normalize.py`, `test_protocol.py`, `test_remote.py`, `test_translator.py`
- `cli/tests/dedup/`: `test_hashing.py`, `test_skipped.py`
- `cli/tests/media/`: `test_base.py`, `test_gps.py`, `test_image.py`, `test_video.py`
- `cli/tests/models/`: `test_database.py`
- `cli/tests/pipeline/`: `test_common.py`, `test_ingest.py`, `test_annotate.py`
- `cli/tests/storage/`: `test_checkpoint.py`, `test_gcs_client.py`
- `cli/tests/integration/`: `test_cli_workflows.py`

---

## Verification Plan

### Automated Tests
```bash
cd /home/ubuntu/dev/photosphere-v3/cli
uv run ruff check . ../scripts
uv run ruff format --check . ../scripts
uv run pyright src tests ../scripts
uv run mypy src tests ../scripts
uv run pytest tests ../scripts --cov=photosphere --cov-report=term-missing
```

### Manual Verification
1. Run `uv run photosphere doctor` and `uv run photosphere --help`.
