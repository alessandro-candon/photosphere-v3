# CLI-Only `--routing-mode`, Non-Destructive `--dry-run`, and Periodic GCS Commits

*   **Author:** alessandro-candon
*   **Status:** Proposed
*   **Date:** 2026-11-16

--------------------------------------------------------------------------------

## Overview

This design moves GCS object-key routing out of static configuration (`photosphere.config.json` and environment variables) into an explicit `--routing-mode` option on `photosphere ingest` (`chronological` by default, or `preserve`). It also makes `photosphere ingest --dry-run` a strictly read-only preview of planned destination paths and collisions, pairs `ingest_checkpoint.ndjson` with periodic atomic GCS database commits for large-batch crash recovery, and isolates colliding target keys into `skipped/` with a warning instead of silently overwriting existing media in GCS.

## The Problem

1. **Hidden and inflexible routing configuration:** `photosphere ingest` currently reads `routing_mode` only from `photosphere.config.json` or `PHOTOSPHERE_ROUTING_MODE`, with no CLI flag. Operators who alternate between chronological uploads (`YYYY/MM/DD/<filename>`, or `no_datetime/<filename>`) and folder-preserving uploads (`preserve`) cannot switch modes per run from the CLI, and `routing_mode` does not belong in infrastructure/bootstrap config (`photosphere.config.json`).
2. **Unsafe `--dry-run` behavior:** `photosphere ingest --dry-run` still moves duplicate and unsupported files into `skipped/`, writes JPEG thumbnails to cache, and runs AI inference, while discarding planned GCS destination paths without showing them. Operators have no safe way to verify where files will land before uploading.
3. **All-or-nothing cloud DB commits & silent overwrites:** `photosphere_database_cloud.json` is currently committed once at the end of `ingest`. Large interrupted runs rely solely on local `ingest_checkpoint.ndjson`, which does not track `routing_mode`. Meanwhile, `chronological` mode flattens subdirectories into `YYYY/MM/DD/<filename>` or `no_datetime/<filename>`, where distinct files with identical names silently overwrite each other in GCS.

## Goals

*   Expose `--routing-mode` (`chronological` | `preserve`, default `chronological`) directly on `photosphere ingest` as a CLI-only parameter with no environment-variable or config-file override.
*   Remove `pipeline.routing_mode` cleanly across `photosphere.config.json`, `contracts/`, `scripts/init/`, `cli/`, and `ssr/`.
*   Make `photosphere ingest --dry-run` strictly read-only (no `skipped/` moves, no thumbnail writes, no AI inference, no checkpoint writes) and print the active `routing_mode`, planned GCS destination keys, and any collisions.
*   Make large-batch `ingest` runs idempotent and crash-safe by combining `routing_mode`-validated `ingest_checkpoint.ndjson` with periodic atomic GCS commits every `N` new uploads (e.g., `N=100`), while keeping English tag/caption generation inline and running `EasyNMT` translation once at end-of-run.
*   Detect target-key collisions before upload (in memory and via GCS preconditions), log a warning, and move colliding files to `skipped/` (`target_key_collision`) instead of overwriting existing GCS objects.

## Non-Goals

*   Backward compatibility with legacy `photosphere.config.json` files that still contain `pipeline.routing_mode` (the project is not in production).
*   Adding a separate `photosphere organize` command to move local source files into `YYYY/MM/DD/` or `no_datetime/` folders on disk.
*   Changing the `chronological` path format away from `YYYY/MM/DD/<filename>` and `no_datetime/<filename>`.
*   Running `EasyNMT` target-language translation inside every periodic commit batch.

## Critical User Journeys (CUJs)

### CUJ 1: Previewing a Chronological Upload with `--dry-run`

*   **Given**: A local directory containing dated photos, undated photos, an unsupported `.json` file, and two distinct photos with the same filename taken on the same day.
*   **When**: The operator runs `photosphere ingest ./photos --routing-mode chronological --dry-run`.
*   **Then**: No files are moved to `skipped/`, no thumbnails or checkpoints are written, no AI inference runs, and the CLI outputs `routing_mode: "chronological"`, planned `YYYY/MM/DD/<filename>` and `no_datetime/<filename>` keys, and flags the duplicate target key collision.

### CUJ 2: Resuming an Interrupted Large Batch

*   **Given**: An operator runs `photosphere ingest ./photos --routing-mode chronological` on 350 novel files with periodic commits every 100 files, and the process is interrupted at file 240 (after 200 files were committed to GCS and 40 are in `ingest_checkpoint.ndjson`).
*   **When**: The operator re-runs `photosphere ingest ./photos --routing-mode chronological`.
*   **Then**: Files 1–200 are recognized as already ingested without being moved to `skipped/`, files 201–240 resume from the checkpoint without re-uploading, files 241–350 are uploaded and committed, and `EasyNMT` translates new `en_` entries once at the end.

### CUJ 3: Handling Target-Key Collisions Safely

*   **Given**: A photo `2025/01/02/IMG_0001.JPG` already exists in `photosphere_database_cloud.json` (or earlier in the same batch), and a second file with a different SHA-1 hash also resolves to `2025/01/02/IMG_0001.JPG`.
*   **When**: `photosphere ingest` processes the second file.
*   **Then**: The pipeline logs a `target_key_collision` warning, leaves the first GCS object untouched, and moves the second file to `skipped/` with reason `target_key_collision` in `skipped_manifest.json`.

## Technical Plan (Architecture)

### 1. CLI-Only `--routing-mode` & Config Schema Removal

`routing_mode` is removed from `photosphere.config.json`, `PhotosphereSettings` (so `PHOTOSPHERE_ROUTING_MODE` is no longer bound), `contracts/photosphere_config.schema.json`, `scripts/init/`, and `ssr/server/utils/photosphere-config.ts`. Instead:

*   `photosphere ingest` in `cli/src/photosphere/main.py` accepts `--routing-mode` (`click.Choice(["chronological", "preserve"], case_sensitive=False)`, `default="chronological"`) and `--commit-every` (`int`, default `100`).
*   `IngestPipeline.run(...)` receives `routing_mode` and `commit_every` directly as explicit parameters and passes `routing_mode` into `_build_remote_object_key(...)`.
*   In `preserve` mode, `_build_remote_object_key` guards `source_path.resolve().relative_to(input_dir.resolve())` against out-of-tree symlinks (falling back to `skipped/` with `processing_error` or raising a clear error instead of crashing mid-batch).

### 2. In-Memory State, Checkpointing & Periodic Atomic Commits

At the start of `IngestPipeline.run()`, `db_records` is loaded into memory alongside `db_gen`, `en_labels_gen`, and `en_captions_gen`. Two in-memory sets guard deduplication and collisions:

*   `known_sha1s`: initialized from `db_records.keys()`.
*   `known_target_uris`: initialized from `{rec.source_bucket_uri for rec in db_records.values() if rec.source_bucket_uri}` and updated as new keys are planned/uploaded in the current batch.

```text
  file in input_dir
        │
        ├─ unsupported extension ──► (if not dry_run) move to skipped/ (unsupported_extension)
        │
        ▼
  extract metadata + sha1
        │
        ├─ sha1 in checkpoint ─────► verify entry.routing_mode == active routing_mode
        │                            (if mismatch: fail fast; else reuse entry without re-uploading)
        │
        ├─ sha1 in known_sha1s ────► (if not dry_run) move to skipped/ (duplicate_sha1)
        │
        ▼
  plan target_uri (chronological: YYYY/MM/DD/<name> or no_datetime/<name>; preserve: relpath)
        │
        ├─ target_uri in known_target_uris ──► log warning (target_key_collision)
        │                                      (if not dry_run) move to skipped/ (target_key_collision)
        │
        ▼
  (if dry_run) record PlannedKeyPreview & return (no thumbnails, no AI, no GCS, no checkpoint)
        │
        ▼
  inline AI (unless --no-ai) ─► upload media (if_generation_match=0) + thumb ─► append checkpoint
        │
        ▼
  every N new uploads: flush en_* to disk ─► upload en_labels, en_captions ─► upload media_db
        │                                    (threading updated generations; clear checkpoint batch)
        ▼
  end of run: final en_* + media_db commit ─► run EasyNMT once for target_lang ─► clear checkpoint
```

Key invariants of this flow:

1. **Checkpoint before `db_records`:** Checking `self.checkpoint.is_completed(metadata.sha1)` before `metadata.sha1 in known_sha1s` guarantees that items committed in an earlier periodic batch of the same interrupted run are resumed cleanly instead of being moved to `skipped/`.
2. **Mode-checked `CheckpointEntry`:** `CheckpointEntry` records `routing_mode`. Resuming a checkpoint created with a different `routing_mode` fails fast before any uploads occur.
3. **Generation token chaining & commit order:** Each periodic commit calls `upload_json_atomic` for `en_labels`, then `en_captions`, then `photosphere_database_cloud.json`, storing the returned `blob.generation` values back into `(en_labels_gen, en_captions_gen, db_gen)`. `EasyNMTTranslator` runs once at end-of-run (or via `photosphere translate`) so periodic commits never block on translation.
4. **Atomic GCS media guard:** `GCSStorageClient.upload_blob` accepts `if_generation_match: int | None = None`, and novel media uploads pass `if_generation_match=0` so an untracked object in GCS cannot be overwritten silently.

### 3. Read-Only `--dry-run` Output Contract

When `dry_run=True`, `IngestPipeline.run()` bypasses `SkippedManager.move_to_skipped`, skips thumbnail generation and AI inference, skips checkpoint writes, and never uploads to GCS. `IngestSummary` (returned as JSON to stdout) includes `routing_mode`, `dry_run`, integer counters (including `skipped_collision`), and a `planned_uploads` / `collisions` preview list (bounded or full per-file entries) so operators can verify destination keys and collisions before a live run.

## Alternatives Considered

### Alternative A: Separate `photosphere organize` Command for Local Dry-Run

*   **Pros**: Gives users a dedicated local folder-reorganization step before running `ingest`.
*   **Cons**: Duplicates scan/metadata/routing logic across two commands, reintroduces v2's two-step workflow, and mutates local directories when the actual goal is previewing upload paths.
*   **Reason for Rejection**: Rejected by author in favor of fixing `photosphere ingest --dry-run` to preview planned GCS keys without touching local files.

### Alternative B: Keep `routing_mode` in `photosphere.config.json` and `PHOTOSPHERE_ROUTING_MODE`

*   **Pros**: Requires zero changes to `contracts/`, `scripts/init/`, `ssr/`, or `PhotosphereSettings`; allows project-level defaults and environment-variable overrides.
*   **Cons**: Hides routing behavior inside config files/env vars rather than making it an explicit, discoverable CLI parameter on `photosphere ingest`.
*   **Reason for Rejection**: Rejected by author; explicit CLI parameters with defaults (`--routing-mode`) are preferred over config-file or environment-variable overrides.

### Alternative C: Keep `routing_mode` Optional/Deprecated in `contracts/photosphere_config.schema.json`

*   **Pros**: Preserves backward compatibility for existing `photosphere.config.json` files on user machines.
*   **Cons**: Leaves dead schema fields and deprecation logic in `contracts/`, `scripts/init/`, and `cli/` even though no production deployment exists yet.
*   **Reason for Rejection**: Rejected by author because the project is not in production, allowing a clean hard removal across all components.

### Alternative D: Auto-Rename Colliding Keys with a SHA-1 Suffix or Abort the Batch

*   **Pros**: Auto-renaming (`<stem>_<sha1[:8]><ext>`) uploads every distinct file without skipping; failing fast halts immediately on the first collision.
*   **Cons**: Auto-renaming alters user filenames unpredictably in GCS; aborting the whole batch stops unrelated valid uploads.
*   **Reason for Rejection**: Rejected by author in favor of logging a warning and moving colliding files to `skipped/` (`target_key_collision`).

## Non-Functional Requirements

*   **Performance & GCS Quota**: Collision detection runs in `O(1)` in memory against `known_target_uris` (zero extra per-file GCS `HEAD` requests). Periodic commits default to `N=100` newly uploaded files so `photosphere_database_cloud.json` rewrites stay well below GCS's 1-mutation/second per-object limit while bounding uncommitted work on crash.
*   **Rollout & Rollback**: Because `routing_mode` is removed from `photosphere.config.json` (`additionalProperties: false`), existing local dev `photosphere.config.json` files must be regenerated or have `pipeline.routing_mode` removed when deploying this change.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `contracts/photosphere_config.schema.json` (Modify)
*   **Type / Scope**: JSON Schema Contract
*   **Proposed Changes**: Remove `"routing_mode"` from `properties.pipeline.required` and `properties.pipeline.properties` so `photosphere.config.json` no longer carries routing configuration.

#### 2. `contracts/fixtures/valid_photosphere_config.json` and `photosphere.config.json` (Modify)
*   **Type / Scope**: Contract Fixture & Repo Config
*   **Proposed Changes**: Remove `"routing_mode": "chronological"` from `pipeline` in both files to match the updated schema.

#### 3. `scripts/init/models.py`, `scripts/init/cli.py`, and `scripts/init/provisioner.py` (Modify)
*   **Type / Scope**: Bootstrap CLI & Config Models
*   **Proposed Changes**: Remove `RoutingMode` / `PipelineConfig.routing_mode` (`models.py`), `BootstrapOptions.routing_mode` (`provisioner.py`), and the `--routing-mode` prompt/option (`cli.py`) so `make init` does not write `routing_mode` into `photosphere.config.json`.

#### 4. `ssr/server/utils/photosphere-config.ts` (Modify)
*   **Type / Scope**: TypeScript SSR Config Loader
*   **Proposed Changes**: Remove `RoutingMode` and `pipeline.routing_mode` validation from `validatePhotosphereConfig` so SSR startup accepts configs without `routing_mode`.

#### 5. `cli/src/photosphere/config.py` (Modify)
*   **Type / Scope**: Python CLI Settings
*   **Proposed Changes**: Define `RoutingMode = Literal["chronological", "preserve"]` as a shared type alias, and remove `routing_mode` from `_extract_settings_from_json` and `PhotosphereSettings` (so `PHOTOSPHERE_ROUTING_MODE` env var and `photosphere.config.json` no longer override or store `routing_mode`).

#### 6. `cli/src/photosphere/main.py` (Modify)
*   **Type / Scope**: Click CLI Entrypoint
*   **Proposed Changes**: Add `--routing-mode` (`click.Choice(["chronological", "preserve"], case_sensitive=False)`, `default="chronological"`) and `--commit-every` (`click.IntRange(min=1)`, `default=100`) to `ingest`, and pass them to `IngestPipeline.run(..., routing_mode=routing_mode.lower(), commit_every=commit_every)`.

#### 7. `cli/src/photosphere/models/database.py` and `cli/src/photosphere/dedup/skipped.py` (Modify)
*   **Type / Scope**: Pydantic Models & Skipped Isolation
*   **Proposed Changes**: Add `"target_key_collision"` to `SkippedEntry.reason` (`database.py`) and `SkipReason` (`skipped.py`) so colliding files are recorded cleanly in `skipped/skipped_manifest.json`.

#### 8. `cli/src/photosphere/storage/checkpoint.py` (Modify)
*   **Type / Scope**: NDJSON Checkpoint Store
*   **Proposed Changes**: Add `routing_mode: RoutingMode` to `CheckpointEntry`, and add a validation helper (or check on load/resume) so resuming a checkpoint with a mismatched `--routing-mode` fails fast with an actionable error.

#### 9. `cli/src/photosphere/storage/gcs_client.py` (Modify)
*   **Type / Scope**: GCS Storage Client
*   **Proposed Changes**: Add optional `if_generation_match: int | None = None` to `GCSStorageClient.upload_blob` and pass it to `blob.upload_from_filename(...)` so novel media uploads can enforce `if_generation_match=0`.

#### 10. `cli/src/photosphere/pipeline/ingest.py` (Modify)
*   **Type / Scope**: Core Ingestion Pipeline
*   **Proposed Changes**:
    *   Update `IngestSummary` to include `routing_mode: str`, `dry_run: bool`, `skipped_collision: int = 0`, `periodic_commits: int = 0`, and `planned_uploads: list[PlannedUpload]` (populated in `--dry-run` with `source_path`, `target_key`, `action`).
    *   Accept `routing_mode` and `commit_every` in `IngestPipeline.run()`, and pass `routing_mode` to `_build_remote_object_key` (guarding `preserve` mode against out-of-tree symlinks).
    *   Initialize `known_sha1s` and `known_target_uris` from `db_records` in memory; check `checkpoint.is_completed(sha1)` **before** `sha1 in known_sha1s`; detect `target_uri in known_target_uris` before upload, log a `target_key_collision` warning, and move colliding files to `skipped/` (when not `dry_run`).
    *   In `dry_run=True`, skip `move_to_skipped`, thumbnail writes, AI inference, checkpoint writes, and GCS uploads.
    *   In live runs, pass `if_generation_match=0` to `upload_blob` for novel media, flush `en_labels`/`en_captions` on disk alongside checkpoints, commit `en_labels` then `en_captions` then `photosphere_database_cloud.json` every `commit_every` newly uploaded items while threading updated `(en_labels_gen, en_captions_gen, db_gen)` tokens, and run `EasyNMT` translation once at end-of-run.

#### 11. `cli/README.md` (Modify)
*   **Type / Scope**: CLI Documentation
*   **Proposed Changes**: Document `--routing-mode` (`chronological` vs `preserve`), `--commit-every`, `--dry-run` preview behavior, and `target_key_collision` isolation into `skipped/`.

#### 12. `cli/tests/conftest.py`, `cli/tests/test_models_contracts.py`, and `cli/tests/test_ingest_pipeline.py` (Modify)
*   **Type / Scope**: Unit & Contract Tests
*   **Proposed Changes**: Remove `routing_mode` from `PhotosphereSettings` fixtures (`conftest.py`), update contract validation tests (`test_models_contracts.py`), and add tests in `test_ingest_pipeline.py` for: `--routing-mode` CLI flag (`chronological` vs `preserve`), read-only `--dry-run` preview (no `skipped/` moves, no thumbnails, no AI), `target_key_collision` warning + `skipped/` isolation, checkpoint `routing_mode` mismatch failure, and multi-batch periodic commits with generation token chaining.

### Verification Plan

*   **Unit & Contract Tests**: `cd cli && uv run pytest tests ../scripts`
*   **Static Analysis & Linting**: `cd cli && uv run ruff check . ../scripts`, `uv run ruff format --check . ../scripts`, `uv run pyright src tests ../scripts`, `uv run mypy src tests ../scripts`
*   **SSR Typecheck**: `cd ssr && npm run typecheck` (or `nuxt typecheck`) if applicable.

--------------------------------------------------------------------------------

*Drafted with EGM*
