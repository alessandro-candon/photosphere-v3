# CLI Refactor Follow-ups (Post-Review Hardening)

*   **Author:** alessandro-candon
*   **Status:** Proposed
*   **Date:** 2026-11-20

--------------------------------------------------------------------------------

## Overview

This design covers five targeted reliability and maintainability fixes on the `refactor` branch of the `photosphere` CLI, along with test-suite packaging and coverage additions. None of the changes alter external CLI commands, flags, environment variables, or JSON schemas.

## The Problem

A code review of the `refactor` branch identified five gaps that leave the CLI harder to debug, risk silent data inconsistency, or duplicate logic:

1.  **Opaque concurrent-write failures**: When two CLI runs write to the remote database at the same time and hit a GCS precondition failure (HTTP 412), the user sees a generic upload error instead of being told that the remote state changed concurrently and to re-run the command.
2.  **Duplicated hash-similarity math**: Similarity calculation between perceptual hashes is implemented twice, increasing the chance that edge-case handling (length mismatches, `0b` prefixes, invalid hex, empty hashes) drifts between callers.
3.  **Unchecked `KeyValueStore` index state**: Callers can mutate `KeyValueStore.store` directly without updating `_value_to_index`, allowing the forward map and reverse lookup index to fall out of sync.
4.  **Overly broad video exception handling**: Video metadata and first-frame extraction wrap container reads in `except Exception  # pragma: no cover`, which hides unexpected bugs and leaves error paths untested.
5.  **Duplicate dictionary-loading paths in CLI entrypoints**: The `translate` and `verify-db` commands still carry their own dictionary download/parse logic instead of reusing the shared loader, and `cli/tests/` subdirectories lack `__init__.py` files, risking pytest module-name collisions.

## Goals

*   Surface concurrent GCS write conflicts (HTTP 412 / `PreconditionFailed`) with a clear, actionable message while keeping non-412 upload failures unchanged.
*   Consolidate perceptual-hash similarity arithmetic into a single shared helper with identical edge-case behavior across all callers.
*   Enforce `KeyValueStore` index consistency by routing all mutations through dedicated methods while keeping `.store` readable for upload payloads.
*   Replace `except Exception  # pragma: no cover` in video processing with the specific exceptions expected from container/stream reads, and cover those paths with tests.
*   Route `translate` and `verify-db` dictionary loading through the shared loader without changing CLI `--help` output, options, or exit codes.
*   Add `__init__.py` to all `cli/tests/` subpackages and add unit tests covering each fix, keeping `ruff`, `pyright`, and `mypy` at zero errors and maintaining test coverage above 92%.

## Non-Goals

*   Changing external CLI commands, flags, environment variables, exit codes, or JSON schemas.
*   Modifying the API service, PaddleOCR engine, or the `MODEL` / `VARIANT` / `COLOR` partitioning contract.
*   Reworking `TAGS_PROMPT` or `.gitignore` (already handled separately).
*   Renaming the `refactor` git branch (noted as a repository housekeeping decision before opening the PR, not a code design change).

## Open Questions

*   None.

## Critical User Journeys (CUJs)

### CUJ 1: Concurrent CLI Write Conflict (HTTP 412)

*   **Given**: Two CLI processes (`ingest`, `annotate`, or `translate`) download the same remote JSON database generation `G` and attempt `upload_json_atomic(..., if_generation_match=G)`.
*   **When**: The first process commits generation `G + 1` and the second process attempts its conditional upload, causing GCS to raise `google.api_core.exceptions.PreconditionFailed`.
*   **Then**: `GCSStorageClient` catches `PreconditionFailed` before `GoogleAPICallError` and raises `StorageConflictError` (a subclass of `StorageSyncError`) with a message stating that the remote database changed concurrently and instructing the user to re-run the command. `main.py` converts it to `click.ClickException` and exits non-zero.

### CUJ 2: Corrupt Video Stream Handling

*   **Given**: A video file whose container opens via `av.open`, but whose metadata tags, first frame, or seekable frames raise a decode, OS, value, or stream-lookup error.
*   **When**: `VideoProcessor.process` extracts metadata, thumbnail, and video hash.
*   **Then**: Narrowly matched exceptions (`FFmpegError`, `ValueError`, `OSError`, `KeyError`, `StopIteration`) are logged as warnings and fall back gracefully (e.g., `None` metadata or thumbnail-based hash). Unexpected programming errors (such as `TypeError` or `AttributeError`) propagate instead of being swallowed.

## Technical Plan (Architecture)

The five fixes are independent and can be landed sequentially on the branch without altering external interfaces:

```text
+--------------------+     PreconditionFailed (412)     +-----------------------------------+
| main.py commands   | <------------------------------- | GCSStorageClient                  |
| (ingest, annotate, |     StorageConflictError         | - upload_blob()                   |
|  translate,        |     (extends StorageSyncError)   | - upload_json_atomic()            |
|  verify-db)        |                                  +-----------------------------------+
|                    |     load_remote_kv_store()       +-----------------------------------+
|  verify_db() ------+--------------------------------> | pipeline/common.py                |
+--------------------+                                  | -> KeyValueStore.from_mapping()   |
                                                        +-----------------------------------+

+--------------------+     _similarity_from_decoded()   +-----------------------------------+
| dedup/hashing.py   | <------------------------------- | hamming_distance_percentage()     |
|                    |                                  | find_similar_annotated_record()   |
+--------------------+                                  +-----------------------------------+

+--------------------+     add_unique_value()           +-----------------------------------+
| KeyValueStore      |     set_value_at_index()         | self.store: dict[str, str]        |
| (ai/translator.py) | -------------------------------> | self._value_to_index: dict[..int] |
+--------------------+     (all mutations sync both)    +-----------------------------------+
```

### 1. GCS Precondition Conflict Handling (`cli/src/photosphere/storage/gcs_client.py`)

*   Import `PreconditionFailed` from `google.api_core.exceptions` and define `class StorageConflictError(StorageSyncError):`.
*   In `upload_blob()` and `upload_json_atomic()`, catch `PreconditionFailed` before `GoogleAPICallError` and raise `StorageConflictError` with `"Remote database changed concurrently while uploading gs://{bucket_name}/{object_name}; re-run the command."` chained `from exc`.
*   Non-412 `GoogleAPICallError` exceptions continue raising `StorageSyncError(f"Failed to upload gs://{bucket_name}/{object_name}: {exc}") from exc`.
*   Because `main.py` already catches `StorageSyncError` and wraps it in `click.ClickException`, `ingest`, `annotate`, `translate`, and `verify-db` require no handler changes.

### 2. Shared Perceptual Hash Similarity Helper (`cli/src/photosphere/dedup/hashing.py`)

*   Extract `_similarity_from_decoded(int_1: int, int_2: int, total_bits: int) -> tuple[int, float, float]` to compute `(raw_distance, distance_pct, similarity_pct)` using `(int_1 ^ int_2).bit_count()`.
*   Call `_similarity_from_decoded` from both `hamming_distance_percentage` and `find_similar_annotated_record`, preserving all existing validation guards (empty hashes, length mismatch, `0b` prefix mismatch, and `ValueError` on invalid hex/binary digits).

### 3. `KeyValueStore` Mutation Encapsulation (`cli/src/photosphere/ai/translator.py`)

*   Keep `KeyValueStore.store` as a plain `dict[str, str]` so `upload_json_atomic` and `json.dumps` continue to serialize it without conversion.
*   Route all mutations through `add_unique_value`, `add_unique_multiple_values`, `set_value_at_index`, `from_mapping`, and `load_file`, each of which keeps `self.store` and `self._value_to_index` synchronized.
*   Code audit confirms `pipeline/ingest.py` only reads `en_labels.store[str(idx)]` and `EasyNMTTranslator.translate_missing_entries` already calls `target_store.set_value_at_index(key, cleaned)`. Any remaining direct `.store[...] =` writes outside `KeyValueStore` will be replaced if introduced.

### 4. Narrowed Video Exception Handling (`cli/src/photosphere/media/video.py`)

*   Replace `except Exception  # pragma: no cover` in `_extract_video_metadata`, `_extract_first_frame_jpeg`, `_compute_video_hash`, and the two inner `try` blocks in `VideoProcessor.process`, as well as `except Exception` in `_sample_video_frames`, with the specific exceptions raised by PyAV, Pillow, and metadata parsing: `(FFmpegError, ValueError, OSError, KeyError, StopIteration)` (tailored per block).
*   Remove `# pragma: no cover` on those blocks and keep `except FFmpegError` around `av.open(...)` in `VideoProcessor.process` raising `MediaDecodeError`.
*   Unexpected exceptions outside that tuple will propagate so programming bugs are not hidden.

### 5. Shared Dictionary Loading in `main.py` (`cli/src/photosphere/main.py`)

*   `translate` already calls `pipeline.common.load_remote_kv_store`.
*   Update `verify_db` to load `{lang}_{LABELS_DB_SUFFIX}` and `{lang}_{CAPTIONS_DB_SUFFIX}` via `load_remote_kv_store(..., allow_missing=False, flush=False)` instead of calling `gcs_client.download_json` directly, then validate `.store` with `KeyValueDictionary.model_validate` so schema validation is preserved without writing local cache files.
*   Note: `load_remote_kv_store` silently coerces `None` when `raw` is not a `dict`, so `verify_db` must still validate `store.store` (or `load_remote_kv_store` / `KeyValueStore.from_mapping` must validate non-missing mappings) to ensure malformed JSON dictionaries still fail `verify-db`.

### 6. Test Packaging & Unit Tests (`cli/tests/`)

*   Add empty `__init__.py` files to `cli/tests/ai/`, `dedup/`, `integration/`, `media/`, `models/`, `pipeline/`, and `storage/` so pytest module names cannot collide across subpackages.
*   Add unit tests for 412 conflict handling (`storage/test_gcs_client.py`), shared hash helper equivalence (`dedup/test_hashing.py`), `KeyValueStore` index consistency across all mutation/load paths (`ai/test_translator.py`), and narrowed video exception handling plus propagation (`media/test_video.py`).

## Alternatives Considered

### Alternative A: Raise `StorageSyncError` Directly Without a Subclass

*   **Pros**: Keeps the storage exception hierarchy minimal (`StorageSyncError` and `BucketClassError` only) and requires no new exported symbol.
*   **Cons**: Callers and tests must match on error message text to distinguish a 412 concurrent-write conflict from network, permission, or other `GoogleAPICallError` failures.
*   **Reason for Rejection**: Rejected by author: adding `StorageConflictError(StorageSyncError)` lets callers and tests match on exception type while existing `except StorageSyncError` handlers in `main.py` continue to work unchanged.

### Alternative B: Wrap `KeyValueStore.store` in `MappingProxyType` or Make It Private (`_store`)

*   **Pros**: Enforces read-only access to `.store` at runtime instead of relying on convention and code audits.
*   **Cons**: `MappingProxyType` is not JSON-serializable (`json.dumps` raises `TypeError`), and `pipeline/common.py` plus `main.py` pass `store.store` directly to `upload_json_atomic`. Making `.store` private or wrapping it would force callers to copy or convert the dictionary before every upload.
*   **Reason for Rejection**: Rejected by author: keeping `.store` as a plain `dict[str, str]` preserves compatibility with `upload_json_atomic` and `json.dumps` while routing all mutations through `KeyValueStore` methods.

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Backward Compatibility**: External CLI commands, flags, environment variables, exit codes, and JSON schemas remain unchanged (`photosphere --help` and all subcommand `--help` outputs must remain byte-identical to `main`).
*   **Verification Thresholds**: `ruff check`, `ruff format --check`, `pyright`, and `mypy` must report zero errors, and `pytest --cov=photosphere` must remain above 92%.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

Execute the changes in order so each step remains independently committable: `gcs_client.py` -> `hashing.py` -> `translator.py` -> `video.py` -> `main.py` -> `cli/tests/`.

### Target Files to Create/Modify

#### 1. `cli/src/photosphere/storage/gcs_client.py` (Modify)

*   **Type / Scope**: Python storage client module.
*   **Proposed Changes**:
    *   Import `PreconditionFailed` from `google.api_core.exceptions`.
    *   Define `class StorageConflictError(StorageSyncError):` with a concise docstring.
    *   In `GCSStorageClient.upload_blob` and `GCSStorageClient.upload_json_atomic`, add an `except PreconditionFailed as exc:` clause **before** `except GoogleAPICallError as exc:` that raises `StorageConflictError(f"Remote database changed concurrently while uploading gs://{bucket_name}/{object_name}; re-run the command.") from exc`.
    *   Keep the existing `except GoogleAPICallError as exc:` handler raising `StorageSyncError(f"Failed to upload gs://{bucket_name}/{object_name}: {exc}") from exc` for all non-412 errors.
*   **Rationale**: Surfaces concurrent-write 412 conflicts distinctly while preserving existing `StorageSyncError` handling in `main.py` (`ingest`, `annotate`, `translate`, `verify-db`).

#### 2. `cli/src/photosphere/dedup/hashing.py` (Modify)

*   **Type / Scope**: Python perceptual-hash comparison module.
*   **Proposed Changes**:
    *   Extract `_similarity_from_decoded(int_1: int, int_2: int, total_bits: int) -> tuple[int, float, float]` returning `(raw_distance, distance_pct, similarity_pct)` via `(int_1 ^ int_2).bit_count()`.
    *   Update `hamming_distance_percentage` and `find_similar_annotated_record` to call `_similarity_from_decoded` instead of duplicating the XOR/percentage arithmetic.
    *   Keep all existing input guards (empty hash, length mismatch, `0b` prefix mismatch, `ValueError` on invalid hex/binary) unchanged.
*   **Rationale**: Eliminates duplicated bit-distance math so both functions cannot drift.

#### 3. `cli/src/photosphere/ai/translator.py` (Modify)

*   **Type / Scope**: Python dictionary store and translation module.
*   **Proposed Changes**:
    *   Keep `KeyValueStore.store: dict[str, str]` as a plain dict for `json.dumps` / `upload_json_atomic` compatibility.
    *   Ensure all mutations inside `KeyValueStore` (`load_file`, `from_mapping`, `add_unique_value`, `set_value_at_index`) update both `self.store` and `self._value_to_index` consistently.
    *   Verify no external callers write to `.store[...]` directly (audit of `pipeline/`, `main.py`, and `EasyNMTTranslator.translate_missing_entries` confirmed only `pipeline/ingest.py` reads `.store[...]` and `translate_missing_entries` uses `set_value_at_index`).
*   **Rationale**: Prevents `KeyValueStore.store` and `_value_to_index` from falling out of sync.

#### 4. `cli/src/photosphere/media/video.py` (Modify)

*   **Type / Scope**: Python video metadata, thumbnail, and perceptual-hash module.
*   **Proposed Changes**:
    *   Remove `except Exception  # pragma: no cover` from `_extract_video_metadata`, `_extract_first_frame_jpeg`, `_compute_video_hash`, and the two inner `try` blocks in `VideoProcessor.process`, as well as `except Exception` in `_sample_video_frames`.
    *   Catch only the specific exceptions raised by PyAV, Pillow, and metadata parsing:
        *   `_extract_video_metadata` and `VideoProcessor.process` metadata block: `(FFmpegError, ValueError, OSError, KeyError)`.
        *   `_extract_first_frame_jpeg` and `VideoProcessor.process` thumbnail block: `(FFmpegError, ValueError, OSError, StopIteration)`.
        *   `_sample_video_frames` and `_compute_video_hash`: `(FFmpegError, ValueError, OSError)`.
    *   Keep `except FFmpegError` around `av.open(...)` in `VideoProcessor.process` raising `MediaDecodeError`.
*   **Rationale**: Stops swallowing unexpected programming errors while preserving graceful fallback for corrupt streams or missing metadata.

#### 5. `cli/src/photosphere/main.py` (Modify)

*   **Type / Scope**: Python Click CLI entrypoint.
*   **Proposed Changes**:
    *   In `verify_db`, replace the direct `gcs_client.download_json` calls for `{lang}_{LABELS_DB_SUFFIX}` and `{lang}_{CAPTIONS_DB_SUFFIX}` with `load_remote_kv_store(gcs_client, settings, ..., allow_missing=False, flush=False)`.
    *   Validate the loaded dictionaries with `KeyValueDictionary.model_validate(labels_store.store)` and `KeyValueDictionary.model_validate(captions_store.store)`.
    *   Leave `translate` (which already uses `load_remote_kv_store`), all Click options, `--help` text, stdout JSON format, and exit codes unchanged.
*   **Rationale**: Eliminates duplicate dictionary-download logic in `verify_db` without writing local cache files or bypassing schema validation.

#### 6. `cli/tests/<pkg>/__init__.py` (Create — 7 files)

*   **Type / Scope**: Test package markers (`cli/tests/ai/__init__.py`, `cli/tests/dedup/__init__.py`, `cli/tests/integration/__init__.py`, `cli/tests/media/__init__.py`, `cli/tests/models/__init__.py`, `cli/tests/pipeline/__init__.py`, `cli/tests/storage/__init__.py`).
*   **Proposed Changes**: Create empty `__init__.py` in each subdirectory.
*   **Rationale**: Prevents pytest module-name import collisions across test subpackages.

#### 7. `cli/tests/storage/test_gcs_client.py` (Modify)

*   **Type / Scope**: Unit tests for `GCSStorageClient`.
*   **Proposed Changes**: Add tests verifying that `PreconditionFailed` during `upload_blob` and `upload_json_atomic` raises `StorageConflictError` (which is also a `StorageSyncError`) with the concurrency message, and that non-412 `GoogleAPICallError` still raises `StorageSyncError` with the `Failed to upload gs://...` message.
*   **Rationale**: Covers the new 412 conflict path and non-regression on generic upload errors.

#### 8. `cli/tests/dedup/test_hashing.py` (Modify)

*   **Type / Scope**: Unit tests for perceptual-hash comparison.
*   **Proposed Changes**: Add a parametrized test verifying `hamming_distance_percentage` and `find_similar_annotated_record` produce identical similarity results across equal, differing, mixed-prefix (`0b` vs. hex), different-length, invalid, and empty hashes.
*   **Rationale**: Proves behavioral equivalence after extracting `_similarity_from_decoded`.

#### 9. `cli/tests/ai/test_translator.py` (Modify)

*   **Type / Scope**: Unit tests for `KeyValueStore` and `EasyNMTTranslator`.
*   **Proposed Changes**: Add tests asserting that `KeyValueStore._value_to_index` matches `KeyValueStore.store` after `load_file`, `from_mapping`, `add_unique_value`, `add_unique_multiple_values`, and `set_value_at_index`.
*   **Rationale**: Verifies forward/reverse index consistency across every mutation and load path.

#### 10. `cli/tests/media/test_video.py` (Modify)

*   **Type / Scope**: Unit tests for `VideoProcessor` and video helpers.
*   **Proposed Changes**: Add tests covering each narrowed exception path (`FFmpegError`, `ValueError`, `OSError`, `KeyError`, `StopIteration`) in metadata, thumbnail, and hash extraction, plus a test confirming an unexpected exception (e.g., `RuntimeError` or `TypeError`) propagates rather than being swallowed.
*   **Rationale**: Replaces the removed `# pragma: no cover` guards with direct test coverage.

#### 11. `cli/tests/test_main.py` (Modify)

*   **Type / Scope**: Unit tests for CLI commands.
*   **Proposed Changes**: Update or add `verify-db` test coverage confirming it delegates dictionary loading to `load_remote_kv_store(..., flush=False)` and still validates via `KeyValueDictionary`, and confirm `StorageConflictError` surfaces as `click.ClickException` with non-zero exit across `ingest`, `annotate`, `translate`, and `verify-db`.
*   **Rationale**: Verifies `main.py` integration without altering CLI output or exit codes.

### Verification Plan

*   **Unit Tests & Coverage**: `uv run pytest --cov=photosphere` (all tests pass, no collection/import-mismatch errors, coverage > 92%).
*   **Static Analysis & Linting**: `uv run ruff check . ../scripts`, `uv run ruff format --check . ../scripts`, `uv run pyright`, and `uv run mypy` (all report zero errors).
*   **CLI Surface Check**: Compare `photosphere --help` and every subcommand `--help` output against `main` to confirm byte-identical CLI help.

--------------------------------------------------------------------------------

*Drafted with EGM*
