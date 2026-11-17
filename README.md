# photosphere-v3 Blueprint

## System Overview

Project **Photosphere v3** is an Edge-First, serverless multimedia (photo and video) storage, indexing, and search platform. All heavy media processing—metadata extraction, perceptual/cryptographic hashing, thumbnail generation, AI tagging/captioning, and local translation—runs locally on the user's machine via a CLI ingestion pipeline, while GCP and Firebase provide passive storage and identity management.

The functional specification is defined in [INITIAL_SPEC.MD](./INITIAL_SPEC.MD), constrained by immutable data, authentication, and storage-location contracts inherited from `photosphere-v2` so existing cloud databases, media archives, and Firebase/GCP configurations remain compatible without recreation.

## Subdirectories & System Boundaries

- `./cli/` ([cli/README.md](./cli/README.md)): Python 3.12 ingestion, metadata/thumbnail/hashing extraction, SHA-1 deduplication into `skipped/`, modular AI labeling/captioning (`Protocol` boundary), `EasyNMT` translation, and dual-bucket GCS synchronization.
- `./ssr/` ([ssr/README.md](./ssr/README.md)): Nuxt 4 SSR web server with Firebase Authentication + `ALLOWED_EMAILS` enforcement, mounted-volume DB/thumbnail/media caching, album persistence, and Firebase Storage API proxying across both buckets.
- `./contracts/` ([contracts/README.md](./contracts/README.md)): Canonical JSON Schemas and cross-language fixture payloads verified by both Python (`pytest`) and TypeScript (`vitest`).
- `./infra/` ([infra/README.md](./infra/README.md)): Multi-bucket Firebase Storage target configuration, email-gated `storage.rules`, and GCS `cors.json`.
- `./scripts/` ([scripts/init/](./scripts/init/)): Portable Python bootstrap package (`make init` / `docker compose run --rm init`) for provisioning GCS buckets, Firebase Storage rules, Web App config, and Auth into a single root `photosphere.config.json`, plus the one-time `migrate_v2_to_v3.py` conversion script.
- Functional & Architectural Specification: [INITIAL_SPEC.MD](./INITIAL_SPEC.MD)
- Monorepo Scaffolding Design Document: [docs/designs/photosphere-v3-scaffolding.md](./docs/designs/photosphere-v3-scaffolding.md)

## Global Invariants

### 1. Database Contracts (Migrated from `photosphere-v2`)
To reuse existing media, labels, captions, and albums without re-ingesting files while removing TinyDB and Protobuf overhead:
- **Main Media Table (`photosphere_database_cloud.json`)**: Flat minified JSON dictionary keyed by byte SHA-1 `hash` (`{ "<sha1_hash>": { ... } }`), migrated from `photosphere-v2`'s TinyDB `{"_default": ...}` wrapper (dropping `local_file_path`). Each record includes:
  - `source_bucket_uri` (`gs://<media-bucket>/<path>`), `thumbnail_bucket_uri` (`gs://<media-bucket>/thumbnails/<basename>.<hash>.thumbnail.jpg`)
  - `file_type` (`"FILE"`, `"IMAGE"`, `"VIDEO"`)
  - `created_at` (ISO 8601 string), `created_at_timestamp` (integer Unix timestamp)
  - `latitude`, `longitude`, `geohash`
  - `hash` (SHA-1 hex digest of file bytes, primary key), `average_hash` (16x16 average perceptual hash string)
  - `label_indexes` (array of integer IDs), `caption_index` (integer ID or `null`)
- **No Protobuf Export (`.pb` Eliminated)**: `photosphere_database_cloud.pb` and all Protobuf conversion/decoding logic from `photosphere-v2` are deprecated and eliminated in `photosphere-v3`; `photosphere_database_cloud.json` is used directly.
- **Labels / Tags Table (`<lang>_photosphere_image_labelling_database_cloud.json`)**: Minified JSON object mapping stringified integer index keys (`"0"`, `"1"`, ...) to unique tag strings (e.g., `en_photosphere_image_labelling_database_cloud.json`).
- **Captions Table (`<lang>_photosphere_image_caption_database_cloud.json`)**: Minified JSON object mapping stringified integer index keys (`"0"`, `"1"`, ...) to caption strings (e.g., `en_photosphere_image_caption_database_cloud.json`).
- **Albums Table (`photosphere_albums.json`)**: Client-writable JSON album definitions referencing media by SHA-1 `hash`.

### 2. Authentication, GCP Project & Media Location
- **Firebase Authentication & SSR Allowlist**: Frontend login uses Firebase Auth with Google Sign-In (`GoogleAuthProvider`), preserving existing Firebase project configuration (`FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_STORAGE_BUCKET`, `FIREBASE_MESSAGING_SENDER_ID`, `FIREBASE_APP_ID`). Both GCS buckets use identical email-gated `storage.rules` (`request.auth != null && request.auth.token.email == '<your-email>'`, with write access restricted to `/photosphere_albums.json` on the Standard bucket). In addition, SSR middleware must verify `email_verified === true` and membership in `ALLOWED_EMAILS` on every request before serving cached data or media.
- **GCP Project & Original Media Location**: The existing GCP project and Archive-class GCS media bucket (`gs://<media-bucket>/...`) and existing object paths (`Year/Month/Day/<filename>`, preserved relative paths, and `thumbnails/`) must remain unchanged.
- **Thumbnail Format**: JPEG thumbnails resized to max `280x280` pixels (`thumbnails/<basename>.<sha1_hash>.thumbnail.jpg`).
- **Local Ingestion Auth**: CLI authenticates to GCP using local Application Default Credentials / Workload Identity (`gcloud auth application-default login` or `GOOGLE_APPLICATION_CREDENTIALS`).

### 3. Dual-Bucket Split (Cost Optimization)
- **Archive GCS Bucket (Media & Thumbnails)**: Retains original high-resolution photos and videos plus `thumbnails/`.
- **Standard GCS Bucket (JSON Databases)**: Hosts the four frequently read/overwritten JSON database files (`photosphere_database_cloud.json`, `<lang>_photosphere_image_labelling_database_cloud.json`, `<lang>_photosphere_image_caption_database_cloud.json`, and `photosphere_albums.json`), eliminating Archive-class retrieval and early-deletion cost spikes during repeated ingestion uploads and SSR downloads.

## Global Side Effects

- **Local Filesystem**: Ingestion moves unsupported, auxiliary, and duplicate files to a local `skipped/` directory (with a `skipped_manifest.json` audit log) and stages temporary thumbnails outside `/tmp` or in configured cache paths.
- **Cloud Storage (Archive Bucket)**: Write-once uploads of new original media objects and `thumbnails/`.
- **Cloud Storage (Standard Bucket)**: Frequent overwrites of `photosphere_database_cloud.json`, `<lang>_photosphere_image_labelling_database_cloud.json`, `<lang>_photosphere_image_caption_database_cloud.json`, and `photosphere_albums.json`.
- **Frontend Client State**: Authenticated web clients update `photosphere_albums.json` via Firebase Storage / SSR APIs.

## System Verification

- Bootstrap a new GCP/Firebase dev or prod project into root `photosphere.config.json`: `make init` (or `docker compose run --rm init`). Runtime `cli`, `ssr`, and `docker-build` fail fast if `photosphere.config.json` is missing.
- Run offline lint, typechecks, and unit tests: `make check` (runs `ruff`, `pyright`, `mypy`, `pytest` across `cli/` and `scripts/`, plus `prettier`, `nuxt typecheck`, `vue-tsc`, and `vitest` across `ssr/`). `make dev-gcs` starts `fake-gcs-server` strictly for automated testing.
