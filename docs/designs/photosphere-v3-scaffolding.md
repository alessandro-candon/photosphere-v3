# Photosphere v3 Monorepo Scaffolding & Dual-Bucket JSON Architecture

*   **Author:** alessandro-candon
*   **Status:** Draft
*   **Date:** 2026-11-15

--------------------------------------------------------------------------------

## Overview

Photosphere v3 establishes a clean two-package monorepo (`cli/` and `ssr/`), paired with shared schema definitions (`contracts/`), Firebase/GCS configuration (`infra/`), an isolated one-time migration script (`scripts/migrate_v2_to_v3.py`), and a unified root `Makefile` for building, linting, type-checking, testing, and running workflows across the entire repository.

The system preserves existing high-resolution media, `thumbnails/`, Firebase login configuration, and GCP project layout from `photosphere-v2` while splitting the four frequently updated JSON databases (`photosphere_database_cloud.json`, `<lang>_photosphere_image_labelling_database_cloud.json`, `<lang>_photosphere_image_caption_database_cloud.json`, and `photosphere_albums.json`) into a Standard-class GCS bucket, removing Protobuf (`.pb`) artifacts, converting TinyDB's `_default` wrapper into a flat SHA-1-keyed JSON dictionary, and hardening the SSR cache boundary against unauthorized access.

## The Problem

Continuing to extend `photosphere-v2` directly introduces four operational, security, and maintainability problems:

1. **Archive GCS Cost Spikes on Mutable Metadata:** `photosphere-v2` stores frequently overwritten and frequently read JSON databases in the same Archive-class GCS bucket as original photos and videos, incurring Archive retrieval fees and 365-day early-deletion charges on repeated CLI ingestion runs and SSR cache refreshes.
2. **Unnecessary Serialization Overhead (`.pb` and TinyDB):** `photosphere-v2` generates and maintains `photosphere_database_cloud.pb` alongside TinyDB's `{"_default": {"1": ...}}` wrapper even though the Nuxt SSR app reads database state into server memory and `/mnt/photosphere` disk caches, gaining no speed or data savings from Protobuf while carrying extra schema build steps and transient `local_file_path` fields.
3. **SSR Cache-Bypass Vulnerability & Unfinished v2 SSR Gaps:** In `photosphere-v2/ssr`, authentication middleware verifies that an incoming Firebase ID token is a valid JWT without checking `user.email` against an allowlist. Once an authorized user populates the SSR in-memory and `/mnt/photosphere` disk caches, any user with a Google account can obtain a Firebase ID token via the public `FIREBASE_API_KEY` and read cached databases and cached media without triggering Firebase `storage.rules`. Furthermore, `photosphere-v2/ssr` only supports one GCS bucket, buffers full videos in browser memory as `Blob` objects, and leaves album write handlers unimplemented.
4. **Fragile Legacy CLI Packaging & Coupled ML Dependencies:** `photosphere-v2/script` lacks modern static checks and container packaging (`mise`, `uv`, `ruff`, `pyright`, `mypy`, `pytest`, `pydantic`, `structlog`, two-stage `Dockerfile`), hardcodes macOS `device_map="mps"` inference, couples heavy `torch`/`transformers` ML dependencies to simple file operations, and uses non-deterministic `KeyValueStore` disk flushes.

## Goals

*   **Unified Root Orchestration:** Provide a root `Makefile` so every `cli/`, `ssr/`, lint, typecheck, unit test, Docker build, local dev server, and one-time migration command runs consistently from the project root.
*   **Dual-Bucket Storage Split:** Move the four JSON databases (`photosphere_database_cloud.json`, `<lang>_photosphere_image_labelling_database_cloud.json`, `<lang>_photosphere_image_caption_database_cloud.json`, `photosphere_albums.json`) to a Standard-class GCS bucket while keeping existing original media and `thumbnails/` in the Archive-class GCS bucket under identical email-gated Firebase `storage.rules`.
*   **Flat Portable JSON Schema & Isolated Migration:** Replace TinyDB's `_default` wrapper with a flat minified JSON dictionary keyed by byte SHA-1 `hash` (dropping `local_file_path` and eliminating `.pb` completely), validated via shared `contracts/` schemas. Execute the `v2 -> v3` migration through a standalone, disposable script (`scripts/migrate_v2_to_v3.py`) designed to be deleted immediately after cutover so `cli/` and `ssr/` carry zero legacy TinyDB code.
*   **Production-Grade Python CLI & Docker Packaging:** Scaffold `cli/` using the `../255/ocr-label` toolchain (`mise.toml`, `uv`, `ruff.toml`, `pyrightconfig.json`, `mypy`, `pytest`, `pydantic`, `pydantic-settings`, `structlog`, `rich`, and a two-stage `uv` `Dockerfile`), modularize vision AI behind a `Protocol` and optional `[ai]` extras (deferring `Tag2Text` tuning to phase 2), retain `EasyNMT` for dictionary translation, isolate unsupported and duplicate files into `skipped/` with a `skipped_manifest.json` audit log, and add crash-safe checkpointing.
*   **Hardened Nuxt SSR App:** Scaffold `ssr/` reusing `photosphere-v2/ssr`'s Firebase Auth + Firebase Storage token-forwarding pattern across both buckets, enforcing `email_verified === true` and `ALLOWED_EMAILS` membership in server middleware before any memory or disk cache access, implementing album write APIs, separating thumbnail disk cache from video streaming, and adding structured Pino logging plus `/api/healthz` and `/api/readyz`.

## Non-Goals

*   Generating, reading, or maintaining `photosphere_database_cloud.pb` or any Protobuf code.
*   Keeping TinyDB `_default` backward-compatibility logic inside `cli/` or `ssr/` once the disposable migration script has been run and deleted.
*   Rewriting or migrating the legacy Vue 3 `spa/` application.
*   Moving existing original media files or `thumbnails/` out of the Archive-class GCS bucket.
*   Selecting, downloading, or benchmarking specific `Tag2Text` model checkpoints and GPU optimization flags during initial scaffolding (handled behind the AI `Protocol` in phase 2).
*   Introducing a hosted SQL or NoSQL database server.

## Open Questions

*   **Phase-2 Vision AI Model Selection:** Which exact checkpoint (`Tag2Text` Swin-B vs. RAM++ vs. a lighter quantized captioner) gives the best CPU/Docker memory footprint and tag/caption accuracy inside the modular `AIProvider` `Protocol`? (Explicitly deferred to phase 2 after monorepo scaffolding is complete.)

## Critical User Journeys (CUJs)

### CUJ 1: Unified Root Makefile Development & Verification

*   **Given**: A developer clones `photosphere-v3` with `mise`, `uv`, `pnpm`, and Docker installed.
*   **When**: The developer runs root `Makefile` targets such as `make setup`, `make check` (`ruff`, `pyright`, `mypy`, `pytest`, `pnpm lint`, `pnpm typecheck`, `vitest`), `make docker-build`, or `make dev`.
*   **Then**: Both `cli/` and `ssr/` install cleanly, pass static checks and unit tests without downloading multi-GB ML weights during core checks, and start or build reproducibly from the root directory.

### CUJ 2: Local Media Ingestion, Deduplication & Dual-Bucket Sync via CLI

*   **Given**: A local staging folder of new photos, videos, duplicates, and unsupported files (e.g., Google Photos JSON exports), plus ADC credentials (`gcloud auth application-default login` or `GOOGLE_APPLICATION_CREDENTIALS`) and Standard/Archive bucket configuration.
*   **When**: The user runs the ingestion CLI (either standalone via `uv run` or inside the Docker container).
*   **Then**: Unsupported files and duplicates (matching existing database keys) are moved to `skipped/` and recorded in `skipped_manifest.json`; valid media gets EXIF/ffprobe metadata, `280x280` JPEG thumbnails, SHA-1 `hash`, and `average_hash`; optional AI tagging/captioning and `EasyNMT` translation update deduplicated `<lang>_` tables; originals and `thumbnails/` upload to the Archive bucket; and the flat JSON databases update in the Standard bucket using GCS generation preconditions.

### CUJ 3: One-Time Disposable v2-to-v3 Database Migration

*   **Given**: Existing `photosphere-v2` TinyDB `photosphere_database_cloud.json`, label/caption JSON files, and `photosphere_albums.json` in the legacy Archive bucket, plus a newly created Standard GCS bucket.
*   **When**: The author runs `make migrate-v2` (invoking `scripts/migrate_v2_to_v3.py --dry-run` followed by live execution).
*   **Then**: The script backs up the `v2` JSON files, converts `photosphere_database_cloud.json` from TinyDB `_default` into a flat SHA-1-keyed dictionary (`{ "<sha1_hash>": { ... } }`) without `local_file_path`, validates all `label_indexes`/`caption_index` references and `photosphere_albums.json` hash links, uploads the 4 JSON files to the Standard bucket, and can then be deleted cleanly from the repository.

### CUJ 4: Authenticated SSR Browsing, Search & Album Updates

*   **Given**: The `ssr/` server running with `ALLOWED_EMAILS`, Firebase client config, `PHOTOSPHERE_MEDIA_BUCKET` (Archive), and `PHOTOSPHERE_DATA_BUCKET` (Standard), with both buckets linked under email-gated Firebase `storage.rules`.
*   **When**: An authorized user signs in with Google via Firebase Auth and browses the gallery, searches tags/captions, opens a photo/video, or modifies an album.
*   **Then**: Every `/api/*` request validates the Firebase ID token signature, `email_verified`, and `ALLOWED_EMAILS` membership before reading cached databases or cached media (rejecting unauthorized Google accounts with HTTP `403`); metadata reads fetch from the Standard bucket; thumbnail and media requests route to the Archive bucket with isolated thumbnail disk caching and byte-range video streaming; and album edits persist to `photosphere_albums.json` in the Standard bucket while refreshing server cache immediately.

## Technical Plan (Architecture)

### 1. Monorepo Boundaries & Root `Makefile`

The repository is split into five clear top-level areas driven by a single root `Makefile`:

*   **`Makefile` (Root Orchestrator):** Provides uniform targets across all subprojects: `setup`, `dev`, `lint`, `typecheck`, `test`, `check`, `build`, `docker-build`, `docker-run`, and `migrate-v2` (invoking `uv`, `pnpm`, and `docker` inside their respective subdirectories).
*   **`cli/` (Python Ingestion & Sync Package):** Standalone Python 3.12 package (`uv` + `mise`) and multi-stage `Dockerfile` handling local file scanning, metadata/hash/thumbnail extraction, SHA-1 deduplication into `skipped/`, modular AI labeling/captioning (`Protocol` boundary, model chosen in phase 2), `EasyNMT` translation, and dual-bucket GCS synchronization.
*   **`ssr/` (Nuxt 4 SSR Web Application):** Node 22 / `pnpm` server application (`Dockerfile` for Cloud Run or Docker Compose) providing Firebase Google authentication, server-side search/filter APIs, mounted-volume JSON database caching, isolated thumbnail/media disk caching, and album persistence.
*   **`contracts/` (Shared Data Contracts):** Canonical JSON Schema files (`media_database.schema.json`, `kv_dictionary.schema.json`, `albums.schema.json`) and shared fixture JSON payloads tested by both `cli/` (`pytest`) and `ssr/` (`vitest`).
*   **`infra/` (Cloud & Firebase Templates):** Multi-bucket `firebase.json` storage targets, email-gated `storage.rules`, `cors.json`, and provisioning documentation for linking both GCS buckets.
*   **`scripts/migrate_v2_to_v3.py` (Disposable Migration Tool):** Isolated standalone script executed once via `make migrate-v2` to convert legacy `photosphere-v2` TinyDB JSONs into `v3` flat JSON inside the Standard bucket, then deleted from the repository.

### 2. End-to-End Architecture & Data Flow

```text
+-----------------------------------------------------------------------------+
| Local Machine / cli Docker Container (ADC via ~/.config/gcloud)             |
|                                                                             |
|  Source Media ---> [Scan & Classify] ---> Unsupported / SHA-1 Duplicate     |
|                          |                      |                           |
|                          | Valid & New          v                           |
|                          v               skipped/ + skipped_manifest.json   |
|               [EXIF / ffprobe / 280x280 JPEG / SHA-1 + average_hash]        |
|                          |                                                  |
|                          v                                                  |
|               [Check average_hash >= 90% -> AIProvider Protocol -> EasyNMT] |
|                          |                                                  |
|          +---------------+---------------+                                  |
|          | Originals + thumbnails/       | 4 Flat JSON DBs (if_gen_match)   |
+----------|-------------------------------|----------------------------------+
           v                               v
+-----------------------------+  +--------------------------------------------+
| GCS Archive Bucket          |  | GCS Standard Bucket                        |
| (PHOTOSPHERE_MEDIA_BUCKET)  |  | (PHOTOSPHERE_DATA_BUCKET)                  |
| - Year/Month/Day/<file>     |  | - photosphere_database_cloud.json          |
| - no_datetime/<file>        |  | - <lang>_..._labelling_database_cloud.json |
| - thumbnails/*.thumbnail.jpg|  | - <lang>_..._caption_database_cloud.json   |
+-----------------------------+  | - photosphere_albums.json                  |
           ^                     +--------------------------------------------+
           | Firebase Token REST GET        ^               ^ Firebase Token
           | (/api/img/...)                 | REST GET      | REST PUT (albums)
+----------|--------------------------------|---------------|-----------------+
| Nuxt SSR Server (ssr/) - Firebase JWT + email_verified + ALLOWED_EMAILS     |
|                                                                             |
|  /mnt/photosphere/                                                          |
|   ├── db-cache/           (parsed & pre-sorted flat JSONs in RAM + disk)    |
|   ├── thumbnail-cache/    (dedicated quota protecting Archive thumbnails)   |
|   └── media-cache/        (bounded cache / Range-streamed originals)        |
+-----------------------------------------------------------------------------+
                                  ^
                                  | HTTPS + Bearer Firebase ID Token
+-----------------------------------------------------------------------------+
| Browser (Firebase Google Sign-In)                                           |
+-----------------------------------------------------------------------------+
```

### 3. Shared Data Contracts (`contracts/`) & Dual-Bucket Layout

Protobuf (`photosphere_database_cloud.pb`) is eliminated completely. Both `cli/` and `ssr/` validate against four portable JSON artifacts stored in the **Standard GCS bucket** (`PHOTOSPHERE_DATA_BUCKET`), while original media and `thumbnails/` remain in the **Archive GCS bucket** (`PHOTOSPHERE_MEDIA_BUCKET`):

1.  **`photosphere_database_cloud.json` (Flat SHA-1 Dictionary):**
    Replaces TinyDB's `{"_default": {"1": ...}}` wrapper and omits transient `local_file_path` strings. Keys are lowercase 40-char SHA-1 hex digests (`hash`):
    ```json
    {
      "<sha1_hash>": {
        "hash": "<sha1_hash>",
        "average_hash": "<hex_or_0b_perceptual_hash>",
        "source_bucket_uri": "gs://<media-bucket>/<relative-path>",
        "thumbnail_bucket_uri": "gs://<media-bucket>/thumbnails/<basename>.<sha1_hash>.thumbnail.jpg",
        "file_type": "IMAGE",
        "created_at": "2024-05-09T14:22:10+00:00",
        "created_at_timestamp": 1715264530,
        "latitude": 45.4642,
        "longitude": 9.19,
        "geohash": "u0nd9...",
        "label_indexes": [0, 4],
        "caption_index": 12
      }
    }
    ```
    *   Keeping `gs://<media-bucket>/...` values in `source_bucket_uri` and `thumbnail_bucket_uri` avoids rewriting existing Archive paths during migration and allows `ssr/` to validate every URI host against `PHOTOSPHERE_MEDIA_BUCKET`.
    *   Allowed `file_type` values remain `"FILE"`, `"IMAGE"`, and `"VIDEO"` for legacy record compatibility, while new ingestion isolates non-image/video files into `skipped/`.
2.  **`<lang>_photosphere_image_labelling_database_cloud.json`:** Flat minified dictionary mapping stringified integer IDs to unique tag strings (`{"0": "dog", "1": "mountain"}`).
3.  **`<lang>_photosphere_image_caption_database_cloud.json`:** Flat minified dictionary mapping stringified integer IDs to caption sentences (`{"0": "a brown dog running on grass"}`).
4.  **`photosphere_albums.json`:** Array of album objects (`[{"name": "Summer 2024", "hashes": ["<sha1_hash>"]}]`), matching `v2` clients.

### 4. CLI Package Design (`cli/`)

*   **Toolchain & Code Quality (`../255/ocr-label` baseline):**
    *   `mise.toml` pins `python = "3.12"` and `uv = "latest"`.
    *   `pyproject.toml` separates core dependencies (`click`, `google-cloud-storage`, `pydantic>=2`, `pydantic-settings`, `pillow`, `pillow-heif`, `imagehash`, `python-geohash`, `structlog`, `rich`, `tqdm`) from optional `[project.optional-dependencies] ai = [...]` (`torch`, `transformers`, `timm`, `easynmt`, `videohash2`), so scanning, hashing, thumbnailing, GCS sync, and unit tests run without multi-GB ML packages.
    *   `ruff.toml` enforces `E`, `W`, `F`, `I`, `B`, and `C90` (`max-complexity = 10`); `pyrightconfig.json` runs in `standard` mode alongside `mypy` and `pytest`.
    *   Two-stage `cli/Dockerfile` builds dependencies with `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` into a `python:3.12-slim-bookworm` runtime image with `ffmpeg` and `libheif` system packages, running as non-root `appuser` with mount points for host media, model caches (`HF_HOME`, `TORCH_HOME`), and ADC credentials (`~/.config/gcloud`).
*   **Media Processing & Inherited `v2` Parity:**
    *   `ImageProcessor` registers `pillow-heif`, applies `ImageOps.exif_transpose()`, preserves `v2` thumbnail scale and quality (`THUMBNAIL_PIXEL_SIZE = 280` bounding box via `pilImage.thumbnail((280, 280))` saved as `"JPEG"` with Pillow default `quality=75`, preserving original `PIL.Image` state and normalizing modes via `.convert("RGB")`), computes `16x16` `average_hash` (`imagehash.average_hash(..., 16)`), and falls back cleanly on missing/malformed EXIF tags.
    *   `VideoProcessor` parses `ffprobe` timestamps without requiring `.%fZ`, safely guards optional GPS `location` metadata, computes `VideoHash` (`0b...`), and extracts the first frame via `ffmpeg` (`ss=0`, `vframes=1`) before processing it through the same image thumbnail pipeline (`THUMBNAIL_PIXEL_SIZE = 280` bounding box via `pilImage.thumbnail((280, 280))`, `.convert("RGB")`, saved as `"JPEG"` with default `quality=75`).
*   **Deduplication & `skipped/` Auditability:**
    *   Before scanning, `cli` downloads `photosphere_database_cloud.json` from `PHOTOSPHERE_DATA_BUCKET` (aborting on any non-404 error unless `--init-db` is passed on an empty bucket).
    *   Unsupported/auxiliary files (e.g., Google Photos `.json` exports) and files whose byte **SHA-1 `hash`** matches an existing key in `photosphere_database_cloud.json` are moved to `skipped/` using collision-safe relative paths and recorded in `skipped_manifest.json` (`source_path`, `skipped_path`, `reason`, `sha1`, `average_hash`).
    *   Novel files with `>= 90.0%` `average_hash` Hamming similarity (`hamming_distance_percentage` matching `v2`, supporting both hex and `0b` hashes) to an existing record reuse its `label_indexes` and `caption_index` instead of invoking the vision model again.
*   **Modular AI, Translation & Crash-Safe Sync:**
    *   Vision labeling/captioning sits behind an `AIProvider` `Protocol` (`analyze(image_path: Path) -> MediaAnnotation`), auto-selecting `cuda`, `mps`, or `cpu` and emitting a clear error when `[ai]` extras are absent unless `--no-ai` is specified.
    *   `Translator` wraps `EasyNMT` over canonical `en_` dictionaries (`KeyValueStore` deterministic disk writes, no random 50% flushes), translating only newly added tag/caption keys per target `<lang>`.
    *   A local write-ahead NDJSON checkpoint logs completed hashes and GCS uploads so interrupted runs resume without redoing AI inference. Uploads run preflight checks confirming `PHOTOSPHERE_DATA_BUCKET` has storage class `STANDARD` and `PHOTOSPHERE_MEDIA_BUCKET` has `ARCHIVE`, then upload media/thumbnails before committing updated JSON DBs with GCS `if_generation_match` optimistic preconditions.

### 5. Nuxt SSR Application Design (`ssr/`)

*   **Auth & Cache-Bypass Fix (`server/middleware/auth.ts` + `server/services/auth.service.ts`):**
    *   Every `/api/*` request (except public `/api/healthz`) requires a valid `Authorization: Bearer <firebase_id_token>` header.
    *   `verifyIdToken` verifies signature/expiry via `firebase-admin` and returns `uid`, `email`, and `email_verified`.
    *   `auth.ts` rejects requests with HTTP `403` unless `user.email_verified === true` and `user.email` matches the comma-separated `ALLOWED_EMAILS` runtime configuration—running **before** any read from in-memory caches or `/mnt/photosphere`.
*   **Dual-Bucket Configuration & Firebase Proxy (`nuxt.config.ts` + `server/utils/storage-download.ts`):**
    *   `runtimeConfig.storage` exposes `mediaBucket` (`PHOTOSPHERE_MEDIA_BUCKET`), `dataBucket` (`PHOTOSPHERE_DATA_BUCKET`), and `mountedVolumePath` (`PHOTOSPHERE_MOUNTED_VOLUME_PATH`).
    *   `downloadFileFromBucket` and album writes target `dataBucket` using the caller's Firebase ID token against `firebasestorage.googleapis.com/v0/b/<dataBucket>/o/...`.
    *   `/api/img/[...path]` validates path traversal and enforces `bucketName === config.storage.mediaBucket` when proxying originals and `thumbnails/`.
*   **Strict Flat JSON Parsing, Cache Isolation & Video Streaming:**
    *   `file-database-cache.ts` validates that `photosphere_database_cloud.json` parses as a non-null JSON object keyed by SHA-1 hashes (failing closed with HTTP `500` on schema errors instead of returning `200 []`), resolves URI bucket targets, and pre-sorts items by `createdAtTimestamp` once at load time.
    *   Disk caching separates `thumbnail-cache/` (dedicated persistent quota protecting Archive-backed thumbnails from eviction) from `media-cache/` (bounded cache for images), while large video playback streams directly through `<video src="/api/img/...">` (or authenticated Range-capable stream) instead of buffering full blobs with `fetchMediaAsBlob`.
*   **Album Persistence, Language Support & SRE Observability:**
    *   Implement `GET /api/albums`, `POST /api/albums`, `PUT /api/albums/:name`, and `DELETE /api/albums/:name`, forwarding the caller's Firebase ID token to overwrite `photosphere_albums.json` in `dataBucket` and immediately updating in-memory `albumsCache` plus the mounted volume file.
    *   Expose language selection (`?language=en|it|fr|es`) consistently across gallery search and metadata views.
    *   Replace `console.*` calls across `ssr/server/` with per-request Pino child loggers carrying `requestId`, `traceId` (`X-Cloud-Trace-Context` / `traceparent`), and `uid`; add `/api/healthz` and `/api/readyz` probes and structured cache hit/miss logs including `bucketTier`.

### 6. Disposable Migration Script (`scripts/migrate_v2_to_v3.py`) & Cloud Infra (`infra/`)

*   `scripts/migrate_v2_to_v3.py` uses `google-cloud-storage` via ADC to:
    1.  Download `photosphere_database_cloud.json`, `<lang>_photosphere_image_labelling_database_cloud.json`, `<lang>_photosphere_image_caption_database_cloud.json`, and `photosphere_albums.json` from the legacy Archive bucket (handling unprefixed legacy filenames if present) without modifying or deleting any legacy files in the Archive bucket.
    2.  Write timestamped verbatim backup copies of all downloaded `v2` JSON files both locally (`backups/v2_<timestamp>/`) and to `gs://<data-bucket>/backups/v2_<timestamp>/` before mutating or uploading converted files, ensuring full recovery if anything fails.
    3.  Convert TinyDB `{"_default": {"1": ...}}` into a flat dictionary keyed by `hash` (`SHA-1`), strip `local_file_path`, validate every record against `contracts/media_database.schema.json`, verify `label_indexes` / `caption_index` bounds and `photosphere_albums.json` hash integrity, and report summary counts (`--dry-run` stops here).
    4.  Verify `PHOTOSPHERE_DATA_BUCKET` is `STANDARD`, upload the 4 flat JSON files to `PHOTOSPHERE_DATA_BUCKET` with `if_generation_match`, and remain standalone so it can be deleted from the repo after verification (while retaining the cloud backups in Archive and `gs://<data-bucket>/backups/`).
*   `infra/` stores multi-bucket `firebase.json` storage target mappings, `storage.rules` (enforcing read allowlist on both buckets and `/photosphere_albums.json` write permission on `dataBucket`), and `cors.json` for `gsutil`/`gcloud storage buckets update`.

## Alternatives Considered

### Alternative A: Retaining Protobuf (`photosphere_database_cloud.pb`)

*   **Pros**: Smaller binary payload for client-side browser downloads in static SPAs and preserves direct compatibility with legacy `photosphere-v2/spa`.
*   **Cons**: Requires compiling and shipping `.proto` schemas across Python and TypeScript while adding extra upload/download steps, yet offers no meaningful speed or data advantage because the SSR server already loads JSON into memory and disk cache.
*   **Reason for Rejection**: Rejected by author: no speed or data savings in the SSR architecture and adds unnecessary schema maintenance.

### Alternative B: Keeping TinyDB (`{"_default": {"1": ...}}`) or Permanent Migration Logic Inside `cli/`

*   **Pros**: Zero upfront conversion work; avoids running a migration script against existing cloud JSON files.
*   **Cons**: Retains TinyDB's `_default` wrapper, sequential integer keys, and transient `local_file_path` fields, forcing both `cli/` and `ssr/` to carry legacy deserialization paths indefinitely.
*   **Reason for Rejection**: Rejected by author: TinyDB was used in `v2` only to avoid hand-writing file storage; isolating a one-time disposable migration script keeps `cli/` and `ssr/` on a clean flat SHA-1-keyed JSON format while preserving full backups of the old files.

### Alternative C: Continuing to Maintain `vikhyatk/moondream2` for Local AI Labeling

*   **Pros**: Already wired into `photosphere-v2/script` without defining a new `AIProvider` `Protocol`.
*   **Cons**: `v2` pinned `moondream2` to `device_map="mps"` and causal decoding, making Linux Docker/CPU execution slow and fragile.
*   **Reason for Rejection**: Rejected by author: author prefers a faster tag-and-caption model such as `Tag2Text` integrated cleanly behind a modular `AIProvider` interface in phase 2.

### Alternative D: Moving `thumbnails/` from Archive GCS to Standard GCS

*   **Pros**: Eliminates GCS Archive Class B `GET` and retrieval charges whenever `ssr/` misses its disk cache or `cli/` downloads thumbnails.
*   **Cons**: Requires migrating all existing thumbnail objects between buckets, increases resting GB-month storage cost for thumbnails, and alters legacy `thumbnail_bucket_uri` paths.
*   **Reason for Rejection**: Rejected by author: author prefers leaving `thumbnails/` in the existing Archive bucket alongside original media to preserve existing object locations, paired with dedicated thumbnail disk caching in `ssr/`.

### Alternative E: Switching SSR to GCS IAM V4 Signed URLs Instead of Firebase Token Proxy

*   **Pros**: Lets browsers range-stream photos and videos directly from GCS without passing media bytes through the Cloud Run server or requiring Firebase Storage multi-bucket Blaze linking.
*   **Cons**: Requires granting `iam.serviceAccounts.signBlob` permissions to the SSR runtime and bypasses Firebase `storage.rules` at object fetch time.
*   **Reason for Rejection**: Rejected by author: author prefers preserving the existing Firebase Auth token + `storage.rules` authorization flow through SSR, closing the cache-bypass vulnerability with server-side `ALLOWED_EMAILS` verification.

### Alternative F: Keying `photosphere_database_cloud.json` on `average_hash` and Auto-Skipping Visual Collisions

*   **Pros**: Aggressively collapses burst photos and resized re-uploads into a single record and saves Archive storage space.
*   **Cons**: `16x16` `average_hash` collides on dark frames, uniform skies, and black `t=0` video frames, risking silent overwrites of distinct user photos and breaking `photosphere_albums.json` references keyed by SHA-1 `hash`.
*   **Reason for Rejection**: Rejected by author: SHA-1 `hash` remains the primary key and sole trigger for moving duplicate files to `skipped/`, while `average_hash >= 90.0%` similarity reuses existing AI labels/captions without discarding files.

### Alternative G: Evolving `../photosphere-v2` In Place Instead of Greenfield `photosphere-v3`

*   **Pros**: Avoids setting up new directories and porting existing EXIF, geohash, translation, and Nuxt components.
*   **Cons**: Carries legacy `spa/` surface, `.pb` pipelines, mixed JS/Python conventions, and lacks a unified root `Makefile` or the `../255/ocr-label` Python toolchain (`mise`, `uv`, `ruff`, `pyright`, `mypy`, `pytest`, `pydantic`, `structlog`).
*   **Reason for Rejection**: Rejected by author: greenfield monorepo scaffolding cleanly isolates the dual-bucket flat JSON architecture, removes `.pb` and `spa/`, and establishes consistent root tooling while porting verified `v2` helpers.

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Security & Privacy**:
    *   `ssr/` enforces valid Firebase JWT signature, `email_verified === true`, and `ALLOWED_EMAILS` membership in `server/middleware/auth.ts` before reading any in-memory cache or `/mnt/photosphere` files.
    *   Both GCS buckets link to Firebase Storage under email-gated `storage.rules`, with client writes limited to `/photosphere_albums.json` on `PHOTOSPHERE_DATA_BUCKET`.
    *   Local CLI and Docker containers consume Application Default Credentials (`~/.config/gcloud` bind-mount or `GOOGLE_APPLICATION_CREDENTIALS`) rather than committing service-account JSON keys into the repository or Docker images.
*   **Performance & Storage Cost**:
    *   Pre-sorting cached records on load in `ssr/` prevents repeated `O(N log N)` sorting on every `/api/files` request.
    *   Separating `thumbnail-cache/` from `media-cache/` prevents 100 MiB media reads from evicting cached thumbnails stored in Archive GCS, and native byte-range streaming avoids full-video browser `Blob` allocations.
*   **Rollout & Rollback**:
    *   `scripts/migrate_v2_to_v3.py` leaves all legacy `v2` files in the Archive bucket intact and writes timestamped verbatim backups locally and to `gs://<data-bucket>/backups/v2_<timestamp>/` before uploading `v3` JSON files (`--dry-run` verifies schema and foreign-key integrity first).
    *   Because `v2` files remain untouched in Archive, rollback requires zero data reconstruction until the user explicitly removes legacy files.

--------------------------------------------------------------------------------

### Additional Resources

*   Functional Specification: [INITIAL_SPEC.MD](../../INITIAL_SPEC.MD)
*   Repository Blueprint: [README.md](../../README.md)
*   Brainstorm Brief: [concepts_brief.md](../../concepts_brief.md)
*   Legacy Reference System: `../photosphere-v2` (`script/`, `ssr/`, `storage.rules`, `cors.json`)
*   Python Toolchain Reference: `../255/ocr-label` (`mise.toml`, `pyproject.toml`, `ruff.toml`, `pyrightconfig.json`, `Dockerfile`)

### Future Improvements

*   **Phase-2 Vision AI Selection**: Benchmark `Tag2Text` against newer lightweight caption/tag checkpoints inside `cli/`'s `AIProvider` `Protocol` and tune batch/GPU inference.
*   **Automatic GCS Eventarc Cache Refresh**: Trigger `/api/admin/refresh-database` or invalidate SSR mounted caches automatically when `cli/` commits a new `photosphere_database_cloud.json` generation in `PHOTOSPHERE_DATA_BUCKET`.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `./Makefile` (Create)

*   **Type / Scope**: Root Monorepo Orchestrator
*   **Proposed Changes**: Define `.PHONY` targets wrapping both packages and infrastructure workflows from the repository root:
    *   `setup`: Install `cli/` dependencies via `cd cli && uv sync --dev` and `ssr/` dependencies via `cd ssr && pnpm install --frozen-lockfile`.
    *   `dev`: Run Nuxt dev server (`cd ssr && pnpm dev`) and provide `dev-gcs` (`docker compose up -d fake-gcs-server`) for local storage testing.
    *   `cli`: Forward arguments (`ARGS=...`) to `cd cli && uv run photosphere $(ARGS)`.
    *   `lint`: Run `cd cli && uv run ruff check . && uv run ruff format --check .` and `cd ssr && pnpm format`.
    *   `typecheck`: Run `cd cli && uv run pyright && uv run mypy src tests` and `cd ssr && pnpm type-check`.
    *   `test`: Run `cd cli && uv run pytest` and `cd ssr && pnpm test`.
    *   `check`: Run `lint`, `typecheck`, and `test` sequentially.
    *   `docker-build`: Build `photosphere-cli:local` (`cli/Dockerfile`) and `photosphere-ssr:local` (`ssr/Dockerfile`).
    *   `migrate-v2`: Run `uv run --project cli python scripts/migrate_v2_to_v3.py $(ARGS)` (isolated wrapper so `scripts/migrate_v2_to_v3.py` and this target can be deleted cleanly after cutover).

#### 2. `./.gitignore` & `./docker-compose.yml` (Create)

*   **Type / Scope**: Root VCS Hygiene & Local Integration Compose
*   **Proposed Changes**:
    *   `.gitignore`: Exclude `.env`, `.env.local*`, `firebase.json`, `.venv/`, `__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `.nuxt/`, `.output/`, `backups/`, `skipped/`, `data/photosphere/`, and model weight caches (`*.pth`, `*.bin`, `*.safetensors`).
    *   `docker-compose.yml`: Define `fake-gcs-server` (`fsouza/fake-gcs-server:latest` on port `4443`, mirrored from `../255/ocr-label/docker-compose.yml`) and optional `ssr` / `cli` service profiles for local end-to-end verification.

#### 3. `./README.md` (Modify)

*   **Type / Scope**: Repository Blueprint Documentation
*   **Proposed Changes**: Update `## Subdirectories & System Boundaries` with relative links to `./cli/README.md`, `./ssr/README.md`, `./contracts/README.md`, and `./infra/README.md`, and replace `<test-command>` under `## System Verification` with `make check`.

#### 4. `./contracts/media_database.schema.json`, `./contracts/kv_dictionary.schema.json`, `./contracts/albums.schema.json` & `./contracts/fixtures/*.json` (Create)

*   **Type / Scope**: Shared Cross-Language JSON Schemas & Parity Fixtures
*   **Proposed Changes**:
    *   `media_database.schema.json`: JSON Schema (Draft 2020-12) specifying top-level object mapping 40-char lowercase SHA-1 hex keys to `MediaRecord` objects (`hash`, `average_hash`, `source_bucket_uri`, `thumbnail_bucket_uri`, `file_type` enum `["FILE", "IMAGE", "VIDEO"]`, `created_at`, `created_at_timestamp`, `latitude`, `longitude`, `geohash`, `label_indexes`, `caption_index`). Reject `_default` wrapper and `local_file_path`.
    *   `kv_dictionary.schema.json`: JSON Schema specifying object mapping stringified non-negative integer keys (`"0"`, `"1"`, ...) to non-empty strings.
    *   `albums.schema.json`: JSON Schema specifying array of `{ "name": string, "hashes": string[] }`.
    *   `contracts/fixtures/`: Commit `valid_media_db.json`, `valid_en_labels.json`, `valid_en_captions.json`, `valid_albums.json`, and `legacy_v2_tinydb.json` (used by migration tests and cross-checked in both `cli/` and `ssr/` test suites).
    *   `contracts/README.md`: EGM package contract documenting schema versioning and parity test expectations.

#### 5. `./infra/firebase.json`, `./infra/storage.rules`, `./infra/cors.json` & `./infra/README.md` (Create)

*   **Type / Scope**: Firebase Multi-Bucket & GCS CORS Configuration
*   **Proposed Changes**:
    *   `firebase.json`: Multi-target `storage` entries binding `media` (`PHOTOSPHERE_MEDIA_BUCKET`) and `data` (`PHOTOSPHERE_DATA_BUCKET`) to `storage.rules` (note Blaze plan requirement for secondary buckets).
    *   `storage.rules`: Preserve `v2` email-gated `allow read` rule (`request.auth != null && request.auth.token.email == '<your-email>'` or allowlist list check) across both targets, and restrict `allow write` to `/photosphere_albums.json`.
    *   `cors.json`: Preserve `v2` CORS origins/methods (`GET`, `PUT`, `POST`, `DELETE`, `HEAD`, `OPTIONS`) for application to both GCS buckets via `gcloud storage buckets update`.
    *   `infra/README.md`: Document bucket creation (`STANDARD` for data, `ARCHIVE` for media), CORS application, and Firebase multi-target deployment commands.

#### 6. `./scripts/migrate_v2_to_v3.py` & `./scripts/test_migrate_v2_to_v3.py` (Create — Disposable)

*   **Type / Scope**: Isolated One-Time `v2 -> v3` Migration Tool & Unit Tests
*   **Proposed Changes**:
    *   CLI flags: `--media-bucket`, `--data-bucket`, `--languages` (default `en`), `--backup-dir` (default `./backups`), `--dry-run`, `--apply`, `--init-missing-albums`.
    *   Behavior: Download `photosphere_database_cloud.json`, `<lang>_photosphere_image_labelling_database_cloud.json`, `<lang>_photosphere_image_caption_database_cloud.json` (also handling unprefixed legacy `v2` filenames if encountered and normalizing to `<lang>_`), and `photosphere_albums.json` from `--media-bucket` without modifying or deleting Archive objects. Save timestamped verbatim backups under `<backup-dir>/v2_<timestamp>/` and `gs://<data-bucket>/backups/v2_<timestamp>/`. Convert TinyDB `_default` records into `{ "<sha1_hash>": ... }`, drop `local_file_path`, preserve existing `source_bucket_uri` and `thumbnail_bucket_uri` verbatim, validate all outputs against `contracts/*.schema.json` and foreign-key bounds (`label_indexes`, `caption_index`, album `hashes`), verify `--data-bucket` has storage class `STANDARD`, and upload via `if_generation_match` when `--apply` is passed.
    *   `test_migrate_v2_to_v3.py`: Test TinyDB conversion, duplicate-hash detection, foreign-key validation errors, `--dry-run` no-write guarantee, and verbatim backup creation using `contracts/fixtures/legacy_v2_tinydb.json`.

#### 7. `./cli/mise.toml`, `./cli/.python-version`, `./cli/pyproject.toml`, `./cli/ruff.toml`, `./cli/pyrightconfig.json`, `./cli/Dockerfile`, `./cli/.env.example` & `./cli/README.md` (Create)

*   **Type / Scope**: Python Package Configuration, Tooling & Container Build (`../255/ocr-label` Baseline)
*   **Proposed Changes**:
    *   `mise.toml` & `.python-version`: Pin Python `3.12` and `uv = "latest"`.
    *   `pyproject.toml`: Package `photosphere` (`requires-python = ">=3.12"`), `click` entrypoint `photosphere = "photosphere.main:cli"`, core dependencies (`pydantic>=2`, `pydantic-settings`, `google-cloud-storage`, `pillow`, `pillow-heif`, `imagehash`, `ffmpeg-python`, `python-geohash`, `structlog`, `rich`, `tqdm`), optional `[project.optional-dependencies] ai` (`torch`, `transformers`, `timm`, `easynmt`, `videohash2`), and `[dependency-groups] dev` (`pytest`, `pytest-cov`, `ruff`, `mypy`, `pyright`, `jsonschema`). Configure `pytest` (`pythonpath = ["src", "."]`) and `mypy` overrides for `google.cloud.*`, `imagehash`, `videohash2`, `geohash`, and `ffmpeg`.
    *   `ruff.toml`: Copy `../255/ocr-label/ruff.toml` settings (`target-version = "py312"`, `line-length = 88`, rules `E`, `W`, `F`, `C90`, `I`, `B`, McCabe `max-complexity = 10`).
    *   `pyrightconfig.json`: Configure `include = ["src", "tests"]`, `pythonVersion = "3.12"`, `typeCheckingMode = "standard"`.
    *   `Dockerfile`: Two-stage build using `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (`uv sync --locked --no-install-project --no-dev`, optional build-arg `INSTALL_AI=false`) into `python:3.12-slim-bookworm` with `ffmpeg` and `libheif1`, non-root `appuser`, `HF_HOME`/`TORCH_HOME` cache env vars, and `ENTRYPOINT ["photosphere"]`.
    *   `.env.example`: Document `PHOTOSPHERE_MEDIA_BUCKET`, `PHOTOSPHERE_DATA_BUCKET`, `PHOTOSPHERE_SKIPPED_DIR`, `PHOTOSPHERE_CACHE_DIR`, `HF_HOME`, `TORCH_HOME`, and `GOOGLE_APPLICATION_CREDENTIALS` / `STORAGE_EMULATOR_HOST`.
    *   `README.md`: Document package interface, invariants, side effects, and `uv run pytest` verification.

#### 8. `./cli/src/photosphere/` Core Modules (Create)

*   **Type / Scope**: Python CLI Source Modules
*   **Proposed Changes**:
    *   `config.py`: `PhotosphereSettings(BaseSettings)` validating bucket names, routing mode (`chronological` | `preserve`), missing-date fallback (`no_datetime/`), `target_lang`, `device` (`auto` | `cuda` | `mps` | `cpu`), and cache/checkpoint directories via `pydantic-settings`.
    *   `models/database.py`: Pydantic v2 models (`FileType`, `MediaRecord`, `MediaDatabase`, `KeyValueDictionary`, `AlbumRecord`, `SkippedEntry`, `SkippedManifest`) enforcing SHA-1 keys and serialization matching `contracts/*.schema.json`.
    *   `media/gps.py`: Port `dms_to_decimal` and `encode_geohash` from `photosphere-v2`.
    *   `media/base.py`: Abstract media reader + SHA-1 computation (`file_hash`) and `MediaType` extension classification.
    *   `media/image.py`: `ImageProcessor` with `pillow-heif`, `ImageOps.exif_transpose()`, EXIF date/GPS extraction, `THUMBNAIL_PIXEL_SIZE = 280` JPEG `quality=75` thumbnail generation (non-mutating copy + `.convert("RGB")`), and `16x16` `imagehash.average_hash`.
    *   `media/video.py`: `VideoProcessor` wrapping `ffprobe` (hardened timestamp and optional GPS parsing), `VideoHash` (`0b...`), and `ffmpeg` (`ss=0`, `vframes=1`) first-frame extraction scaled and saved via the shared image thumbnail pipeline (`THUMBNAIL_PIXEL_SIZE = 280` bounding box, `.convert("RGB")`, JPEG `quality=75`).
    *   `dedup/hashing.py`: Port `hamming_distance_percentage` (`>= 90.0%` similarity lookup supporting both hex and `0b` binary hashes).
    *   `dedup/skipped.py`: Collision-safe move of unsupported/auxiliary files and exact **SHA-1 `hash`** duplicates into `skipped/` with append/write of `skipped_manifest.json`.
    *   `ai/protocol.py`: `MediaAnnotation` model and `AIProvider` `Protocol` (`analyze(image_path: Path) -> MediaAnnotation`), device resolution helper (`cuda` -> `mps` -> `cpu`), and clear runtime error if `[ai]` optional extras are missing without `--no-ai`.
    *   `ai/translator.py`: Deterministic `KeyValueStore` (no random disk flushes; explicit flush + minified JSON) and `EasyNMTTranslator` wrapping `EasyNMT` + `translate.py` meta-note sanitization over newly added `en_` keys.
    *   `storage/gcs_client.py`: `GCSStorageClient` using `google-cloud-storage` ADC, `verify_bucket_classes()` (`STANDARD` for `dataBucket`, `ARCHIVE` for `mediaBucket`), JSON download (aborting on non-404 errors unless `--init-db`), and `upload_json_atomic(..., if_generation_match=...)`.
    *   `storage/checkpoint.py`: Local NDJSON write-ahead log recording completed SHA-1 hashes, cloud URIs, and AI outputs for crash-safe resumption.
    *   `pipeline/ingest.py`: End-to-end pipeline orchestrator (`scan -> skipped/ isolation -> extract/hash/thumb -> SHA-1 dedup -> average_hash >= 90% label reuse or AIProvider -> EasyNMT -> route -> checkpoint -> upload media/thumbs to Archive -> upload JSONs to Standard`).
    *   `main.py`: `click` CLI entrypoint with `ingest`, `translate`, `verify-db`, and `version` subcommands plus structured `structlog` + `rich` console logging.

#### 9. `./cli/tests/` (Create)

*   **Type / Scope**: Python Unit & Local Emulator Integration Tests
*   **Proposed Changes**:
    *   `conftest.py`: Temporary media/skipped directories, deterministic fake `AIProvider`, fake `EasyNMTTranslator`, and synthetic fixture media (small JPEG, RGBA PNG, HEIC if available, mock/tiny MP4).
    *   `test_models_contracts.py`: Validate `cli` Pydantic models against all `contracts/fixtures/*.json` and `contracts/*.schema.json`.
    *   `test_media_and_dedup.py`: Verify `280x280` JPEG thumbnail scale/quality, `ImageOps.exif_transpose()`, SHA-1 exact deduplication into `skipped/` + `skipped_manifest.json`, and `>= 90.0%` `average_hash` label reuse without dropping distinct files.
    *   `test_ingest_pipeline.py`: Test full pipeline resume from NDJSON checkpoint, `--no-ai` mode, non-404 DB download abort safety, and dual-bucket upload routing against mocked GCS (plus optional `fake-gcs-server` marker test).

#### 10. `./ssr/` Package Config, Env & Container (Create)

*   **Type / Scope**: Nuxt 4 Runtime Configuration, Packaging & Docker (`../photosphere-v2/ssr` Baseline)
*   **Proposed Changes**:
    *   `package.json`: Pin `pnpm@12.5.1`, Nuxt 4, Pinia, Quasar, Firebase client/admin SDKs, Pino, Prettier, TypeScript, `vue-tsc`, and `vitest` (matching `v2/ssr/package.json` without any Protobuf dependencies).
    *   `nuxt.config.ts`: Replace single `sourceBucket` and `pbFileName` with `storage.mediaBucket` (`PHOTOSPHERE_MEDIA_BUCKET`), `storage.dataBucket` (`PHOTOSPHERE_DATA_BUCKET`), `storage.mountedVolumePath`, `auth.allowedEmails` (`ALLOWED_EMAILS`), and separated `thumbnailCache` (`directoryName`, `ttlMs`, `maxCacheBytes`) + `mediaCache` configuration.
    *   `.env.example`: Document `FIREBASE_*`, `PHOTOSPHERE_MEDIA_BUCKET`, `PHOTOSPHERE_DATA_BUCKET`, `PHOTOSPHERE_MOUNTED_VOLUME_PATH`, `ALLOWED_EMAILS`, and `ADMIN_EMAIL`.
    *   `Dockerfile` & `docker-compose.yml`: Two-stage Node 22 / `pnpm` build and runtime exporting `NUXT_STORAGE_MEDIA_BUCKET`, `NUXT_STORAGE_DATA_BUCKET`, `NUXT_AUTH_ALLOWED_EMAILS`, and `/mnt/photosphere` volume mount.
    *   `tsconfig.json` & `README.md`: Strict TypeScript config and EGM package documentation.

#### 11. `./ssr/server/` API, Auth, Dual-Bucket Proxy & Cache Modules (Create)

*   **Type / Scope**: Nitro Server Middleware, Services, Utilities & Endpoints
*   **Proposed Changes**:
    *   `services/logger.service.ts` & `middleware/request-logger.ts`: Configure Pino JSON logger and bind per-request child logger (`requestId`, `traceId` from `X-Cloud-Trace-Context`/`traceparent`) onto `event.context.logger` (eliminating raw `console.*` calls).
    *   `services/auth.service.ts` & `middleware/auth.ts`: Verify Firebase ID tokens (`verifyIdToken`), populate `email_verified`, skip auth only for `/api/healthz`, and reject any `/api/*` request with HTTP `403` when `user.email_verified !== true` or `user.email` is not in `config.auth.allowedEmails`—executed before any cache read.
    *   `utils/storage-download.ts`: Split bucket helpers into `downloadDataFile(fileName, destPath, token)` targeting `config.storage.dataBucket`, `uploadDataFile(fileName, content, token)` targeting `config.storage.dataBucket` (for albums), and `fetchMediaObject(event, gsUri, token)` enforcing `bucketName === config.storage.mediaBucket`.
    *   `utils/file-database-cache.ts`: Parse flat SHA-1-keyed `photosphere_database_cloud.json` (fail closed with HTTP `500` on invalid schema; zero TinyDB `_default` logic), parse flat `<lang>_` label/caption maps, pre-sort records on load, and track cache staleness TTL cleanly.
    *   `utils/albums-cache.ts`: Load `photosphere_albums.json` from `dataBucket` with atomic write-back + immediate in-memory `albumsCache` update on mutation.
    *   `services/media-cache.service.ts`: Isolate `thumbnail-cache/` from `media-cache/` so large media reads never evict cached Archive thumbnails; emit structured cache hit/miss/eviction logs including `bucketTier`.
    *   `utils/url.ts` & `utils/file-filters.ts`: Port proxy URL generation (`/api/img/<path>`) and tag/caption/date/geohash/file-type filters.
    *   `api/healthz.get.ts` & `api/readyz.get.ts`: Liveness and readiness probes checking mounted volume access and database cache status.
    *   `api/files/index.ts`, `api/files/[hash].ts`, `api/search/suggestions.get.ts`, `api/location/search.get.ts`: Serve paginated filtered media, single item details, search suggestions (supporting non-`en` languages), and geocoding (returning structured errors rather than silent `200 []`).
    *   `api/img/[...path].ts`: Authenticate allowlisted user, validate clean object path, route to `mediaBucket`, serve thumbnails via isolated `thumbnail-cache/`, and stream videos with native HTTP `Range` support.
    *   `api/albums/index.get.ts`, `api/albums/index.post.ts`, `api/albums/[albumName].put.ts`, `api/albums/[albumName].delete.ts`, `api/admin/refresh-database.post.ts`: Implement full album CRUD persisted to `dataBucket` (`photosphere_albums.json`) with immediate cache refresh, and update admin refresh to refresh both media DB and `albumsCache`.

#### 12. `./ssr/app/` & `./ssr/test/` Frontend Pages, Composables & Tests (Create)

*   **Type / Scope**: Nuxt 4 UI Layer, Client Auth/API Composables & Vitest Suite
*   **Proposed Changes**:
    *   `app/types/*` & `app/constants/api/index.ts`: Port clean TypeScript interfaces (`IPhotosphereFile`, `IPhotosphereViewFile`, `IAlbum`, `IFileFilters`) aligned with `contracts/*.schema.json` (renaming misnamed `SignedUrls` types to `ProxyUrls`).
    *   `app/composables/usePhotosphereApi.ts` & `app/stores/*`: Wire Firebase Google Sign-In, dynamic UI `language` selector (`en`, `it`, `fr`, `es`), Range-capable `<video src>` streaming (replacing `fetchMediaAsBlob` on full videos), and real album create/add/remove API calls; fix `v2` bugs (`FileDetailModal.vue` seconds-to-ms `Date(timestamp * 1000)` conversion and `isAuthenticated.value` checks).
    *   `ssr/test/`: `vitest` unit and API handler tests covering `ALLOWED_EMAILS` `403` enforcement before cache hits, flat JSON contract parsing against `contracts/fixtures/valid_media_db.json`, dual-bucket `storage-download.ts` routing, thumbnail vs. media cache isolation, and album mutation persistence.

### Verification Plan

*   **Compilation/Build**:
    *   `make docker-build` builds `photosphere-cli:local` and `photosphere-ssr:local` cleanly.
    *   `cd ssr && pnpm build` compiles the Nuxt 4 Nitro server bundle with zero errors.
*   **Unit Tests**:
    *   `cd cli && uv run pytest` passes all schema parity, thumbnail scale/quality, SHA-1 deduplication (`skipped/`), `average_hash >= 90%` label reuse, checkpoint resume, and migration dry-run tests.
    *   `cd ssr && pnpm test` passes all `vitest` suites covering `ALLOWED_EMAILS` auth rejection, flat JSON schema loading, dual-bucket routing, cache isolation, and album CRUD endpoints.
*   **Static Analysis & Linting**:
    *   `make lint` passes `ruff check .`, `ruff format --check .`, and `pnpm format`.
    *   `make typecheck` passes `pyright`, `mypy src tests`, `nuxt typecheck`, and `vue-tsc --noEmit`.
*   **Test Coverage Requirement**: >= 85% line/branch coverage across `cli/src/photosphere/dedup/`, `cli/src/photosphere/models/`, `scripts/migrate_v2_to_v3.py`, and `ssr/server/` auth, cache, and storage modules.
*   **E2E/Integration**:
    *   Start `fake-gcs-server` via `make dev-gcs`, run `make migrate-v2 ARGS="--media-bucket test-archive --data-bucket test-data --apply"` against `contracts/fixtures/legacy_v2_tinydb.json`, run `make cli ARGS="ingest ..."` on mixed fixture media, and verify `ssr/` serves authenticated requests while rejecting non-allowlisted Firebase tokens with HTTP `403`.

--------------------------------------------------------------------------------

*Drafted with EGM*
