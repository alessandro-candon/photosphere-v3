# Portable GCP/Firebase Bootstrap (`scripts/init/`) & Unified `photosphere.config.json`

*   **Author:** alessandro-candon
*   **Status:** Draft
*   **Date:** 2026-11-16

--------------------------------------------------------------------------------

## Overview

This design introduces a portable Python infrastructure bootstrap package in `scripts/init/` (callable from `make init` and `docker-compose.yml`) together with a single root configuration file (`photosphere.config.json`) shared across `cli/`, `ssr/`, `Makefile`, and `docker-compose.yml`.

On a fresh project, `scripts/init/` uses Google Cloud Application Default Credentials and direct GCP/Firebase REST APIs to enable required cloud services, create the media and data GCS buckets with user-selected storage classes (such as `STANDARD` for both buckets in a real GCP development project, or `ARCHIVE` plus `STANDARD` in production), apply `infra/cors.json`, seed the four empty JSON database files, link both buckets to Firebase Storage, compile and deploy email-gated `infra/storage.rules` in memory, register a Firebase Web App, initialize Firebase Authentication, and write `photosphere.config.json`. When `photosphere.config.json` already exists, `scripts/init/` prints its contents and exits without touching cloud resources. Both `cli/` and `ssr/` validate and consume `photosphere.config.json` directly, failing Docker image builds and application startup when the file is missing or invalid, while `fake-gcs-server` remains available solely for automated tests.

## The Problem

Starting Photosphere v3 from scratch on a new development or production GCP/Firebase project currently suffers from three operational barriers:

1. **Fragmented Manual Provisioning and Tracked Template Mutation:** Setting up the cloud infrastructure requires running disjoint `gcloud` and `firebase-tools` commands across buckets, CORS, `.firebaserc` targets, and Firebase Web App registration, plus editing `['<your-email>']` directly inside the git-tracked [infra/storage.rules](file:///home/ubuntu/dev/photosphere-v3/infra/storage.rules) file. That workflow requires multiple host CLI installations and risks committing personal email addresses and project IDs.
2. **Duplicated, Unvalidated Runtime Configuration:** Runtime settings are split across `cli/.env`, `ssr/.env`, [docker-compose.yml](file:///home/ubuntu/dev/photosphere-v3/docker-compose.yml) (which reads `./ssr/.env.example`), and `infra/firebase.json`. Missing values only surface late at request or upload time rather than failing early during container build or startup.
3. **Storage-Class Lock-In and Dev Cost Exposure:** [cli/src/photosphere/storage/gcs_client.py](file:///home/ubuntu/dev/photosphere-v3/cli/src/photosphere/storage/gcs_client.py#L57-L61) rejects any real GCS media bucket whose storage class is not `ARCHIVE`. Testing against a real GCP dev project with an `ARCHIVE` media bucket exposes developers to 365-day early-deletion charges and per-GB retrieval fees when uploading, modifying, or wiping test media, whereas pointing runtime containers at `fake-gcs-server` omits Firebase Auth and `storage.rules` verification.

## Goals

*   Provide a portable Python bootstrap command (`scripts/init/`, runnable via `make init` and `docker compose run --rm init`) that uses `google.auth` REST API calls rather than external `gcloud`, `firebase-tools`, or `terraform` binaries.
*   Short-circuit safely when `photosphere.config.json` already exists (unless explicitly forced): validate, print the JSON configuration to stdout, and exit `0` without making cloud API calls.
*   Allow per-environment storage class selection (`STANDARD` for both buckets in dev mode, or `ARCHIVE` + `STANDARD` in production) and update `cli` validation (`verify_bucket_classes`) to check against the configured storage classes in `photosphere.config.json` rather than hardcoding `ARCHIVE`.
*   Provision both GCS buckets, apply `infra/cors.json`, seed the 4 initial empty JSON database objects (`ifGenerationMatch=0`), link both buckets to Firebase Storage, compile and bind email-gated `storage.rules` in memory without modifying files under `infra/`, register/fetch the Firebase Web App config, and initialize Firebase Auth.
*   Support interactive browser confirmation prompts (printing the direct Firebase Console URL and retrying API verification after user confirmation) for console-only actions such as Blaze billing upgrades and manual Google Sign-In activation.
*   Consolidate runtime configuration across `cli/`, `ssr/`, `Makefile`, and `docker-compose.yml` into a single git-ignored root `photosphere.config.json` validated against a shared schema in `contracts/`.
*   Enforce fail-fast errors when `photosphere.config.json` is missing or invalid during `docker build` (`cli/Dockerfile`, `ssr/Dockerfile`) and `cli` / `ssr` startup, while keeping `make check` automated unit tests and `fake-gcs-server` integration tests runnable without a live GCP project.

## Non-Goals

*   Creating the parent GCP or Firebase project itself, or programmatically attaching/creating Cloud Billing accounts without user action in the Firebase Console.
*   Using `fake-gcs-server` or Firebase local emulators as a runtime development environment (retained strictly for automated tests).
*   Modifying tracked files under `infra/` (`storage.rules`, `firebase.json`, `cors.json`) with user-specific emails or project IDs during provisioning.
*   Generating multiple scattered `.env` files across `cli/` and `ssr/` subdirectories.

## Open Questions

None — all architectural questions were resolved during ideation.

## Critical User Journeys (CUJs)

### CUJ 1: First-Time Dev Project Bootstrap from Scratch

*   **Given**: The user has created a GCP/Firebase project and authenticated locally (`gcloud auth application-default login` or `GOOGLE_APPLICATION_CREDENTIALS`), and no `photosphere.config.json` exists in the repository root.
*   **When**: The user runs `make init` (or `docker compose run --rm init`), enters the project details, selects `STANDARD` storage classes for dev mode, and completes any prompted Firebase Console steps (such as Blaze billing upgrade or Google Sign-In provider activation) when instructed.
*   **Then**: `scripts/init/` enables the required Google APIs, creates both `STANDARD` GCS buckets with CORS, seeds the 4 empty JSON database files, links both buckets to Firebase Storage, compiles and binds `storage.rules` in memory with the user's allowed emails, retrieves the Firebase Web App SDK credentials, initializes Firebase Auth, and atomically writes `photosphere.config.json` to the repository root so `make dev`, `make cli`, and `make docker-build` run immediately.

### CUJ 2: Idempotent Config Check When Already Provisioned

*   **Given**: A valid `photosphere.config.json` already exists at the repository root.
*   **When**: The user or an automation script runs `make init` without a force/reconcile flag.
*   **Then**: `scripts/init/` validates and prints the contents of `photosphere.config.json` to stdout and exits `0` without issuing any GCP or Firebase API calls.

### CUJ 3: Fail-Fast Build and Startup Enforcement vs. Offline Automated Testing

*   **Given**: `photosphere.config.json` is missing or malformed at the repository root.
*   **When**: A developer runs `make docker-build`, `make dev`, `make build`, `make cli ARGS="ingest ..."`, or starts an already-built `ssr` or `cli` container without `photosphere.config.json`.
*   **Then**: The Docker build or process startup fails immediately with a message instructing the user to run `make init`. Conversely, running `make check` or `make dev-gcs` test suites continues to execute offline using synthetic fixtures and `fake-gcs-server` (`STORAGE_EMULATOR_HOST`).

## Technical Plan (Architecture)

### 1. Architecture & Provisioning Data Flow

The bootstrap and runtime configuration system splits into a single provisioning package (`scripts/init/`), a canonical root configuration schema (`contracts/photosphere_config.schema.json`), and fail-fast config readers inside `cli/`, `ssr/`, and the container build files.

```text
  make init / docker compose run --rm init
                       |
                       v
        [Check photosphere.config.json]
           |                        |
      exists & !--force          missing or --force
           |                        |
           v                        v
   Validate & print        Google Auth ADC / Service Account
   JSON to stdout;            (AuthorizedSession + x-goog-user-project)
     exit 0                         |
                                    +--> 1. serviceusage.googleapis.com (batchEnable + LRO poll)
                                    +--> 2. firebase.googleapis.com (GET / :addFirebase LRO)
                                    +--> 3. storage.googleapis.com (create/reconcile buckets + CORS)
                                    +--> 4. storage upload API (seed 4 JSON DBs, ifGenerationMatch=0)
                                    +--> 5. firebasestorage.googleapis.com (:addFirebase)
                                    |       `-- [billing error] -> Console URL prompt & retry
                                    +--> 6. firebaserules.googleapis.com (in-memory ruleset + releases)
                                    +--> 7. firebase.googleapis.com (WebApp + SDK config)
                                    +--> 8. identitytoolkit.googleapis.com (initializeAuth + Google IdP)
                                    |       `-- [IdP not enabled] -> Console URL prompt & retry
                                    v
                       Atomic Write (tmp -> fsync -> os.replace)
                                    |
                                    v
                       ./photosphere.config.json (gitignored)
                          /         |          \
                         v          v           v
              cli/Dockerfile   cli runtime   ssr/Dockerfile + Nuxt/Nitro
              (build fails if  (verify exact (build & boot fail if missing;
               file missing)    bucket class) hydrates runtimeConfig & env)
```

### 2. Unified Configuration Schema & Precedence

All runtime parameters live in a single git-ignored root file, `photosphere.config.json`, validated by `contracts/photosphere_config.schema.json`:

```json
{
  "version": 1,
  "gcp": {
    "project_id": "my-gcp-project",
    "location": "europe-west1"
  },
  "storage": {
    "media_bucket": "my-gcp-project-photosphere-media",
    "media_storage_class": "STANDARD",
    "data_bucket": "my-gcp-project-photosphere-data",
    "data_storage_class": "STANDARD"
  },
  "firebase": {
    "project_id": "my-gcp-project",
    "app_id": "1:1234567890:web:abcdef123456",
    "api_key": "AIzaSy...",
    "auth_domain": "my-gcp-project.firebaseapp.com",
    "storage_bucket": "my-gcp-project-photosphere-media",
    "messaging_sender_id": "1234567890"
  },
  "auth": {
    "allowed_emails": ["user@example.com"],
    "admin_email": "user@example.com"
  },
  "pipeline": {
    "default_lang": "en",
    "target_lang": "it",
    "routing_mode": "chronological"
  }
}
```

Configuration lookup resolves in strict precedence order:

1. **Explicit CLI flags or function arguments** (e.g., `photosphere translate --target-lang es`).
2. **Explicit process environment variables** (`PHOTOSPHERE_*`, `FIREBASE_*`, `ALLOWED_EMAILS`, `ADMIN_EMAIL`, `NUXT_PUBLIC_DEFAULT_LANG`, `STORAGE_EMULATOR_HOST`).
3. **`photosphere.config.json`** discovered from `PHOTOSPHERE_CONFIG_PATH`, `./photosphere.config.json`, or repository-root parent traversal (`../photosphere.config.json`).

### 3. REST API Provisioning Sequence & Interactive Console Fallback

`scripts/init/` reuses `google.auth.default()` and `google.auth.transport.requests.AuthorizedSession` (already present in the `cli/` environment via `google-cloud-storage`) instead of wrapping `gcloud` or `firebase-tools`.

*   **Quota Project Header (`x-goog-user-project`):** User ADC credentials (`gcloud auth application-default login`) require `x-goog-user-project: <project_id>` on Firebase, Service Usage, Rules, Storage, and Identity Toolkit calls. If the first `serviceusage` call rejects the header before Service Usage is active, the REST client retries that call once without the header.
*   **Idempotent Provisioning Steps:**
    1. **Fast-Path Config Check:** When `photosphere.config.json` exists and `--force` is unset, validate its schema, print the formatted JSON to stdout, and exit `0` with zero network calls.
    2. **API Enablement (`serviceusage.googleapis.com/v1`):** Call `POST /v1/projects/{project_id}/services:batchEnable` for `storage.googleapis.com`, `firebase.googleapis.com`, `firebasestorage.googleapis.com`, `firebaserules.googleapis.com`, and `identitytoolkit.googleapis.com`, polling the returned Long-Running Operation (`GET /v1/{operation.name}`) until `done: true`.
    3. **Firebase Project Linking (`firebase.googleapis.com/v1beta1`):** Call `GET /v1beta1/projects/{project_id}`. On `404`, invoke `POST /v1beta1/projects/{project_id}:addFirebase` and poll the LRO until completion.
    4. **GCS Bucket Creation & CORS (`storage.googleapis.com/storage/v1`):** Accept dev (`STANDARD` / `STANDARD`) or prod (`ARCHIVE` / `STANDARD`) or per-bucket storage class selections via prompts or CLI flags. Create `media_bucket` and `data_bucket` with `iamConfiguration.uniformBucketLevelAccess.enabled = true` and the CORS rules loaded from `infra/cors.json` (`POST /storage/v1/b?project={project_id}`). On `409 Conflict`, fetch the bucket (`GET /storage/v1/b/{bucket}`) to confirm ownership, verify `storageClass`, and patch `cors` (`PATCH /storage/v1/b/{bucket}`).
    5. **Initial JSON Database Seeding (`storage.googleapis.com/upload/storage/v1`):** Upload the baseline JSON objects to `data_bucket` using `ifGenerationMatch=0` (`412 Precondition Failed` is treated as an idempotent no-op so existing data is never overwritten):
       *   `photosphere_database_cloud.json` -> `{}`
       *   `en_photosphere_image_labelling_database_cloud.json` -> `{}` (plus `<target_lang>_photosphere_image_labelling_database_cloud.json` when `target_lang != "en"`)
       *   `en_photosphere_image_caption_database_cloud.json` -> `{}` (plus `<target_lang>_photosphere_image_caption_database_cloud.json` when `target_lang != "en"`)
       *   `photosphere_albums.json` -> `[]`
    6. **Firebase Storage Linking & Blaze Billing Fallback (`firebasestorage.googleapis.com/v1beta`):** Call `POST /v1beta/projects/{project_id}/buckets/{bucket}:addFirebase` for both `media_bucket` and `data_bucket` (`409 ALREADY_EXISTS` succeeds). If Firebase rejects secondary bucket linking due to Spark plan limits (`400 FAILED_PRECONDITION` or `403 PERMISSION_DENIED`), `prompt_console_step` prints `https://console.firebase.google.com/project/{project_id}/usage/details`, waits for the user to upgrade to Blaze in a browser (`Press Enter once completed...`), and retries `addFirebase`.
    7. **In-Memory `storage.rules` Compilation (`firebaserules.googleapis.com/v1`):** Read `infra/storage.rules` into memory, replace `['<your-email>']` with the normalized lowercase `allowed_emails` list without modifying `infra/storage.rules` on disk, create a ruleset (`POST /v1/projects/{project_id}/rulesets`), and bind both `projects/{project_id}/releases/firebase.storage/{media_bucket}` and `projects/{project_id}/releases/firebase.storage/{data_bucket}` via `/v1/projects/{project_id}/releases` (`POST`, falling back to `PATCH` when a release already exists).
    8. **Web App Registration (`firebase.googleapis.com/v1beta1`):** Reuse an existing Web App matching `displayName` (`GET /v1beta1/projects/{project_id}/webApps`) or create one (`POST .../webApps` + LRO poll), then fetch `GET .../webApps/{app_id}/config` for `apiKey`, `authDomain`, `projectId`, `storageBucket`, `messagingSenderId`, and `appId`.
    9. **Firebase Authentication & Google Sign-In Fallback (`identitytoolkit.googleapis.com`):** Call `POST /v2/projects/{project_id}/identityPlatform:initializeAuth`. If `--google-oauth-client-id` and `--google-oauth-client-secret` are provided, upsert `defaultSupportedIdpConfigs/google.com` (`enabled: true`). Otherwise, query `GET /v2/projects/{project_id}/defaultSupportedIdpConfigs/google.com`; if missing or disabled, `prompt_console_step` prints `https://console.firebase.google.com/project/{project_id}/authentication/providers`, waits for the user to enable Google Sign-In in the browser, and re-verifies via `GET`.
    10. **Atomic Config Persistence:** Validate the complete config dictionary against `contracts/photosphere_config.schema.json`, write to a temporary sibling file, `fsync`, and `os.replace()` into `photosphere.config.json`.

### 4. Consumer Integration, Fail-Fast Enforcement & Test-Only Emulator Boundary

*   **`cli/` Config Loading & Dynamic Storage-Class Validation:**
    *   `PhotosphereSettings` in `cli/src/photosphere/config.py` adds `media_storage_class` and `data_storage_class` and introduces a required `load_runtime_settings()` boundary for CLI commands (`ingest`, `translate`, `verify-db`) that fails immediately when `photosphere.config.json` is absent or invalid (unless `STORAGE_EMULATOR_HOST` is explicitly set for automated tests).
    *   `GCSStorageClient.verify_bucket_classes()` in `cli/src/photosphere/storage/gcs_client.py` accepts `expected_media_class` and `expected_data_class` from `PhotosphereSettings` rather than hardcoding `"ARCHIVE"` and `"STANDARD"`, while retaining the `STORAGE_EMULATOR_HOST` bypass for automated test runs against `fake-gcs-server`.
*   **`ssr/` Build-Time and Runtime Fail-Fast Hydration:**
    *   `ssr/nuxt.config.ts` loads and validates `photosphere.config.json` during `pnpm dev` and `pnpm build` (skipping the file check only when `VITEST` or `NODE_ENV === "test"` is active so offline unit tests and `pnpm type-check` can supply test values).
    *   A Nitro startup plugin (`ssr/server/plugins/00.photosphere-config.ts`) runs at server boot (including pre-built Docker containers), validates `photosphere.config.json` on disk—terminating process startup if missing or invalid—and populates `useRuntimeConfig()` and missing `process.env` variables consumed by `ssr/server/utils/storage-download.ts` (`getStorageConfig()`) and `ssr/server/services/firebase-admin.service.ts`.
*   **Docker Build Context, `Makefile`, and Test-Only Emulator Boundary:**
    *   Both `cli/Dockerfile` and `ssr/Dockerfile` switch their build context in `Makefile` (`docker-build`) and `docker-compose.yml` to the repository root (`.`). Each Dockerfile executes `COPY photosphere.config.json ./photosphere.config.json` so `docker build` fails immediately if `photosphere.config.json` does not exist; `cli/Dockerfile` also copies `scripts/` and `infra/` so `docker compose run --rm init` can execute `python -m scripts.init`.
    *   `docker-compose.yml` defines an `init` service (mounting `.:/app` and `${HOME}/.config/gcloud:/home/appuser/.config/gcloud:ro`), mounts `./photosphere.config.json:/app/photosphere.config.json:ro` on runtime containers, removes the `./ssr/.env.example` `env_file`, and removes `depends_on: fake-gcs-server` and default `STORAGE_EMULATOR_HOST` from `cli`.
    *   `fake-gcs-server` in `docker-compose.yml` and `dev-gcs` in `Makefile` remain intact strictly for automated testing (`pytest` / integration runs when `STORAGE_EMULATOR_HOST` is explicitly passed).

## Alternatives Considered

### Alternative A: Shell Script Wrapping `gcloud` and `firebase-tools` CLIs

*   **Pros**: Uses standard vendor CLI commands (`gcloud storage buckets create`, `firebase target:apply`, `firebase deploy --only storage`) without writing REST client code.
*   **Cons**: Requires developers and CI/Docker containers to install both Google Cloud SDK and Node-based `firebase-tools`, authenticate two separate CLI sessions, and mutate tracked files (`infra/firebase.json`, `.firebaserc`, and `infra/storage.rules`) on disk when deploying email-gated rules.
*   **Reason for Rejection**: Calling Google Cloud and Firebase REST endpoints through `google.auth` (`AuthorizedSession`) removes external CLI binary dependencies, runs inside the existing `cli` Python environment and Docker image, and keeps all templates under `infra/` untouched in git.

### Alternative B: Terraform / OpenTofu Module Under `infra/`

*   **Pros**: Declarative infrastructure-as-code resource graph with built-in diffing and dependency ordering.
*   **Cons**: Requires installing an external Terraform/OpenTofu binary, managing `terraform.tfstate` locking/storage for a single-user setup, and does not solve unifying `cli` and `ssr` runtime configuration without a secondary output export step.
*   **Reason for Rejection**: Rejected by author: requires installing and maintaining an external tool, requires managing `terraform.tfstate`, and cannot run in interactive pause-and-retry mode when browser-based console steps (Blaze billing upgrade and Google Sign-In activation) are required.

### Alternative C: Generating Separate `cli/.env` and `ssr/.env` Files Instead of `photosphere.config.json`

*   **Pros**: Matches existing `pydantic-settings` `.env` discovery in `cli/` and standard `dotenv` loading in `ssr/` and `docker-compose.yml`.
*   **Cons**: Splits configuration across multiple flat files that drift out of sync, forces comma-delimited string parsing for arrays like `allowed_emails`, and breaks the single-file check-and-print contract.
*   **Reason for Rejection**: A single git-ignored root `photosphere.config.json` validated against a shared JSON Schema prevents configuration drift and provides typed nested fields across Python and TypeScript.

### Alternative D: Using `fake-gcs-server` as the Runtime Dev Environment Instead of a Real GCP Dev Project

*   **Pros**: Zero cloud setup or billing requirements and works offline.
*   **Cons**: `fake-gcs-server` only emulates basic GCS object operations; it does not emulate Firebase Authentication, Google Sign-In tokens, Firebase Storage rules (`storage.rules`), or multi-bucket Firebase Storage linking.
*   **Reason for Rejection**: Rejected by author: `fake-gcs-server` does not emulate Firebase Auth, Google Sign-In, or `storage.rules` evaluation, so it is retained strictly for automated tests while development workflows target a real GCP project with `STANDARD` storage classes.

### Alternative E: Disabling `verify_bucket_classes()` in Dev Mode Instead of Checking Configured Storage Classes

*   **Pros**: Simpler than adding storage-class fields to configuration and updating `GCSStorageClient.verify_bucket_classes()`.
*   **Cons**: Silently disables bucket-class safety checks for anyone running in dev mode or accidentally swapping media and data buckets.
*   **Reason for Rejection**: Rejected by author: validating against `media_storage_class` and `data_storage_class` recorded in `photosphere.config.json` preserves bucket-class verification in both dev (`STANDARD`/`STANDARD`) and production (`ARCHIVE`/`STANDARD`).

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Security & Privacy**: `photosphere.config.json` contains project IDs, Firebase Web App keys, and allowed user emails and must remain git-ignored (`./.gitignore`). `scripts/init/` compiles `infra/storage.rules` purely in memory before uploading to `firebaserules.googleapis.com` so `infra/storage.rules` stays a clean template in version control. Fail-fast schema validation prevents starting `ssr` with empty `ALLOWED_EMAILS` or missing Firebase project settings.
*   **Idempotency & Data Safety**: Existing JSON databases in the data bucket are seeded with `ifGenerationMatch=0`, guaranteeing that re-running `scripts/init/` with `--force` never overwrites existing photo records, tag/caption dictionaries, or user albums. Writing `photosphere.config.json` uses a temporary sibling file, `fsync`, and `os.replace()` so interrupted runs never leave a truncated configuration file.
*   **Startup & Build Determinism**: Docker builds (`cli/Dockerfile`, `ssr/Dockerfile`), `cli` runtime commands, and `ssr` dev/prod startup fail immediately with actionable messages pointing to `make init` when `photosphere.config.json` is absent or invalid, while offline unit tests (`pytest`, `vitest`, `pnpm type-check`) remain independent of live cloud state.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `./contracts/photosphere_config.schema.json` (Create)

*   **Type / Scope**: JSON Schema (Draft 2020-12) Contract
*   **Rationale & Proposed Changes**: Defines the single canonical schema shared by `scripts/init/`, `cli/`, `ssr/`, and contract tests for `./photosphere.config.json`. Specifies `additionalProperties: false` at root (`version: 1`, `gcp`, `storage`, `firebase`, `auth`, `pipeline`), non-empty `project_id` and bucket names, `storage` class enums (`"STANDARD"` | `"ARCHIVE"`), Firebase Web App fields (`app_id`, `api_key`, `auth_domain`, `storage_bucket`, `messaging_sender_id`), `auth.allowed_emails` (non-empty array of email strings) plus `auth.admin_email`, and `pipeline` defaults (`default_lang`, `target_lang`, `routing_mode` in `"chronological" | "preserve"`).

#### 2. `./contracts/fixtures/valid_photosphere_config.json` (Create)

*   **Type / Scope**: Cross-Language Contract Fixture
*   **Rationale & Proposed Changes**: Provides a canonical valid configuration payload tested by both Python `pytest` and TypeScript `vitest` contract suites so Python and TypeScript parsers cannot drift.

#### 3. `./contracts/README.md` (Modify)

*   **Type / Scope**: Package Documentation
*   **Rationale & Proposed Changes**: Documents `./photosphere_config.schema.json` and `./fixtures/valid_photosphere_config.json` under package boundaries so contributors know the root configuration schema is owned by `contracts/`.

#### 4. `./.gitignore` (Modify)

*   **Type / Scope**: Repository Hygiene
*   **Rationale & Proposed Changes**: Appends `photosphere.config.json` and `photosphere.config.json.*.tmp` so generated project IDs, Firebase Web App API keys, and personal email allowlists are never committed to git.

#### 5. `./scripts/init/__init__.py` (Create)

*   **Type / Scope**: Python Package Initialization
*   **Rationale & Proposed Changes**: Marks `scripts/init/` as an importable Python package and exports top-level symbols (`BootstrapConfigError`, `PhotosphereConfig`) needed by `scripts/init/__main__.py` and unit tests.

#### 6. `./scripts/init/__main__.py` (Create)

*   **Type / Scope**: Python CLI Entrypoint
*   **Rationale & Proposed Changes**: Invokes `scripts.init.cli.main()` under `if __name__ == "__main__":` so both `uv run --project cli python -m scripts.init` and the `cli` Docker image run the bootstrap package identically.

#### 7. `./scripts/init/models.py` (Create)

*   **Type / Scope**: Pydantic v2 Data Models & Atomic File I/O
*   **Rationale & Proposed Changes**: Centralizes config parsing and persistence without needing `jsonschema` as a runtime dependency in `cli/pyproject.toml`. Defines Pydantic models (`GcpConfig`, `StorageConfig`, `FirebaseConfig`, `AuthConfig`, `PipelineConfig`, `PhotosphereConfig` with `model_config = ConfigDict(extra="forbid")` and email normalization to lowercase), plus:
    *   `resolve_config_path(explicit_path: Path | None = None) -> Path`: inspects explicit path, `PHOTOSPHERE_CONFIG_PATH`, `./photosphere.config.json`, or repo root parent.
    *   `load_and_validate_config(path: Path) -> PhotosphereConfig`: reads UTF-8 JSON and raises `BootstrapConfigError` on invalid JSON or validation failures.
    *   `write_config_atomic(path: Path, config: PhotosphereConfig) -> None`: writes formatted JSON (2-space indent + trailing newline) to `photosphere.config.json.<uuid>.tmp`, calls `fsync`, and atomically swaps via `os.replace()`.

#### 8. `./scripts/init/rest_client.py` (Create)

*   **Type / Scope**: Google Auth REST Client & Interactive Console Helper
*   **Rationale & Proposed Changes**: Keeps `scripts/init/` free of external `gcloud`/`firebase-tools` binaries and `google-api-python-client` dependencies by wrapping `google.auth.default()` and `AuthorizedSession`. Defines:
    *   `RestApiError(RuntimeError)` carrying `status_code`, `reason`, `message`, and `response_body`.
    *   `GoogleRestClient(project_id: str, session: AuthorizedSession | None = None, timeout: float = 30.0)`: injects `x-goog-user-project: <project_id>` header on GCP/Firebase REST calls, exposes `request_json(method, url, *, json_body=None, params=None, headers=None, allow_statuses=(), retry_without_quota_header=False)`, `upload_bytes(url, data, *, content_type, if_generation_match=None)`, and `poll_lro(operation_url, *, timeout_seconds=180.0, interval_seconds=2.0)`.
    *   `prompt_console_step(url: str, instruction: str, *, non_interactive: bool = False) -> None`: prints the direct Firebase Console URL and step instructions, pauses for `input("Press Enter once completed...")` (or raises `BootstrapConfigError` immediately if `non_interactive=True` or stdin is not a TTY).

#### 9. `./scripts/init/provisioner.py` (Create)

*   **Type / Scope**: Idempotent GCP/Firebase Resource Provisioner
*   **Rationale & Proposed Changes**: Implements the 10-step cloud provisioning pipeline with functions kept below `cli/ruff.toml` cyclomatic complexity limits (`<= 10`). Defines `BootstrapOptions` and `BootstrapProvisioner(rest_client: GoogleRestClient, repo_root: Path, prompt_fn: Callable[[str, str], None])`:
    *   `enable_required_apis()`: `POST serviceusage.googleapis.com/v1/projects/{project_id}/services:batchEnable` for `storage`, `firebase`, `firebasestorage`, `firebaserules`, and `identitytoolkit` + LRO poll.
    *   `ensure_firebase_project()`: `GET firebase.googleapis.com/v1beta1/projects/{project_id}`; if `404`, `POST ...:addFirebase` + LRO poll.
    *   `provision_bucket(bucket_name, location, storage_class, cors_rules)`: creates via `POST storage.googleapis.com/storage/v1/b?project={project_id}` with UBLA enabled; on `409`, verifies ownership and `storageClass` match (`GET`) and patches `cors` (`PATCH`).
    *   `seed_empty_databases(data_bucket, target_lang)`: uploads `photosphere_database_cloud.json` (`{}`), `en_photosphere_image_labelling_database_cloud.json` (`{}`), `en_photosphere_image_caption_database_cloud.json` (`{}`), plus `<target_lang>_` dictionaries when `target_lang != "en"`, and `photosphere_albums.json` (`[]`) with `ifGenerationMatch=0`, ignoring `412 Precondition Failed`.
    *   `link_buckets_to_firebase(buckets)`: calls `POST firebasestorage.googleapis.com/v1beta/projects/{project_id}/buckets/{bucket}:addFirebase` (`409` treated as linked); on `400`/`403` billing/precondition errors, triggers `prompt_console_step` with `https://console.firebase.google.com/project/{project_id}/usage/details` and retries.
    *   `compile_and_bind_storage_rules(allowed_emails, buckets)`: reads `./infra/storage.rules` in memory, replaces `['<your-email>']` with normalized lowercase email literals, creates ruleset (`POST firebaserules.googleapis.com/v1/projects/{project_id}/rulesets`), and creates or patches releases `firebase.storage/{bucket}`.
    *   `ensure_firebase_web_app(display_name="photosphere-ssr") -> FirebaseConfig`: reuses matching Web App or creates one + LRO poll, then fetches `GET .../webApps/{app_id}/config`.
    *   `initialize_firebase_auth(oauth_client_id=None, oauth_client_secret=None)`: calls `POST identitytoolkit.googleapis.com/v2/projects/{project_id}/identityPlatform:initializeAuth`, upserts `google.com` IdP config when OAuth credentials are given, or checks `GET .../defaultSupportedIdpConfigs/google.com` and calls `prompt_console_step` with `https://console.firebase.google.com/project/{project_id}/authentication/providers` + re-check.

#### 10. `./scripts/init/cli.py` (Create)

*   **Type / Scope**: Click CLI Interface & Interactive Prompter
*   **Rationale & Proposed Changes**: Provides the user-facing command invoked by `make init` and `docker compose run --rm init`. Checks `resolve_config_path()` first: if the file exists and `--force` is not set, validates it via `load_and_validate_config()`, prints formatted JSON to stdout, and exits `0` with zero network calls. Otherwise collects missing parameters via interactive Click prompts (defaulting dev mode to `STANDARD`/`STANDARD` and prod mode to `ARCHIVE`/`STANDARD`, or accepting `--project-id`, `--location`, `--mode`, `--media-bucket`, `--data-bucket`, `--media-storage-class`, `--data-storage-class`, `--allowed-emails`, `--admin-email`, `--target-lang`, `--non-interactive`, `--force`, `--google-oauth-client-id`, `--google-oauth-client-secret`), executes `BootstrapProvisioner`, and calls `write_config_atomic()`.

#### 11. `./scripts/init/test_bootstrap.py` (Create)

*   **Type / Scope**: Automated Unit Tests (`pytest`)
*   **Rationale & Proposed Changes**: Verifies bootstrap behavior offline with mocked HTTP transport (`AuthorizedSession`): existing-config print-and-exit fast path, `--force` re-provisioning, all 10 REST API steps, quota-header fallback retry, `412` DB seed idempotency, in-memory compilation verifying `./infra/storage.rules` remains unmodified on disk, Blaze billing and Google Sign-In pause-and-retry loops, `--non-interactive` failure on console steps, and atomic config writing.

#### 12. `./cli/src/photosphere/config.py` (Modify)

*   **Type / Scope**: CLI Configuration Loader
*   **Rationale & Proposed Changes**: Updates `PhotosphereSettings` so it reads runtime configuration from `./photosphere.config.json` (discovered via `PHOTOSPHERE_CONFIG_PATH`, `./photosphere.config.json`, or `../photosphere.config.json`) below explicit CLI/function kwargs and `PHOTOSPHERE_*` env vars, replacing `.env` reliance as the primary source. Adds `media_storage_class: Literal["ARCHIVE", "STANDARD"]` and `data_storage_class: Literal["ARCHIVE", "STANDARD"]` plus `require_runtime_config(cls, config_path: Path | None = None) -> PhotosphereSettings` that raises a clear startup error when `photosphere.config.json` is absent or invalid outside explicit test overrides (`STORAGE_EMULATOR_HOST`).

#### 13. `./cli/src/photosphere/storage/gcs_client.py` (Modify)

*   **Type / Scope**: GCS Storage Client Guardrails
*   **Rationale & Proposed Changes**: Updates `GCSStorageClient.verify_bucket_classes()` signature to accept `expected_media_class: str = "ARCHIVE"` and `expected_data_class: str = "STANDARD"`, validating `data_bkt.storage_class == expected_data_class` and `media_bkt.storage_class == expected_media_class` instead of hardcoding `"ARCHIVE"` so dev deployments using `STANDARD` buckets pass validation while misconfigured buckets still fail. Retains the `STORAGE_EMULATOR_HOST` bypass strictly for automated `fake-gcs-server` tests.

#### 14. `./cli/src/photosphere/pipeline/ingest.py` (Modify)

*   **Type / Scope**: Ingestion Pipeline Integration
*   **Rationale & Proposed Changes**: Updates `IngestPipeline.run()` call to `self.gcs.verify_bucket_classes(...)` to pass `expected_media_class=self.settings.media_storage_class` and `expected_data_class=self.settings.data_storage_class`.

#### 15. `./cli/src/photosphere/main.py` (Modify)

*   **Type / Scope**: CLI Runtime Entrypoints
*   **Rationale & Proposed Changes**: Updates `ingest`, `translate`, and `verify_db` commands to load settings through `PhotosphereSettings.require_runtime_config()` (failing immediately if `photosphere.config.json` is missing or invalid outside emulator test mode) and passes `settings.media_storage_class` and `settings.data_storage_class` to `verify_bucket_classes()` in `translate` and `verify_db`.

#### 16. `./cli/tests/test_models_contracts.py` (Modify)

*   **Type / Scope**: Python Contract Tests (`pytest`)
*   **Rationale & Proposed Changes**: Adds contract validation test ensuring `./contracts/fixtures/valid_photosphere_config.json` passes `./contracts/photosphere_config.schema.json` (`jsonschema`) and `PhotosphereConfig` Pydantic validation.

#### 17. `./cli/tests/test_ingest_pipeline.py` (Modify)

*   **Type / Scope**: CLI Unit Tests (`pytest`)
*   **Rationale & Proposed Changes**: Adds tests verifying `verify_bucket_classes()` accepts `STANDARD`/`STANDARD` when configured, rejects mismatched classes, and verifies `PhotosphereSettings.require_runtime_config()` fails cleanly when `photosphere.config.json` is absent and succeeds when valid or when `STORAGE_EMULATOR_HOST` is explicitly set for tests.

#### 18. `./ssr/server/utils/photosphere-config.ts` (Create)

*   **Type / Scope**: SSR Shared Config Loader & Validator
*   **Rationale & Proposed Changes**: Implements `resolvePhotosphereConfigPath()`, `loadPhotosphereConfig()` (mirroring `contracts/photosphere_config.schema.json` validation in TypeScript with actionable error messages pointing to `make init`), and `applyConfigToProcessEnv(config)` so `nuxt.config.ts`, Nitro startup, `storage-download.ts`, and `firebase-admin.service.ts` share one parser. Allows bypassing only when `process.env.VITEST` or `process.env.NUXT_TYPECHECK` / explicit test mode is active.

#### 19. `./ssr/server/plugins/00.photosphere-config.ts` (Create)

*   **Type / Scope**: Nitro Server Startup Plugin
*   **Rationale & Proposed Changes**: Runs before `./ssr/server/plugins/firebase.server.ts` (alphabetical Nitro plugin order `00.*` before `firebase.server.ts`) on every SSR server boot (including pre-built Docker images). Calls `loadPhotosphereConfig()`, terminates startup on missing/invalid `photosphere.config.json`, populates missing `process.env` variables (`PHOTOSPHERE_MEDIA_BUCKET`, `PHOTOSPHERE_DATA_BUCKET`, `FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_STORAGE_BUCKET`, `FIREBASE_APP_ID`, `ALLOWED_EMAILS`, `ADMIN_EMAIL`, `NUXT_PUBLIC_DEFAULT_LANG`), and updates `useRuntimeConfig()` so runtime container config mounts take effect immediately.

#### 20. `./ssr/nuxt.config.ts` (Modify)

*   **Type / Scope**: Nuxt Configuration
*   **Rationale & Proposed Changes**: Imports `loadPhotosphereConfig()` from `./server/utils/photosphere-config.ts` to fail `pnpm dev` and `pnpm build` when `photosphere.config.json` is absent or invalid (outside `VITEST` / `pnpm type-check` runs) and seeds `runtimeConfig.public.firebase`, `runtimeConfig.storage`, `runtimeConfig.auth`, and `runtimeConfig.public.defaultLang` from `photosphere.config.json` with explicit `process.env.*` overrides taking priority.

#### 21. `./ssr/test/server/database-contracts.test.ts` (Modify)

*   **Type / Scope**: SSR Contract & Startup Tests (`vitest`)
*   **Rationale & Proposed Changes**: Adds tests validating `./contracts/fixtures/valid_photosphere_config.json`, verifying `loadPhotosphereConfig()` fails on missing/malformed `photosphere.config.json`, and verifying `applyConfigToProcessEnv()` hydrates `process.env` without overriding explicit env vars.

#### 22. `./cli/Dockerfile` (Modify)

*   **Type / Scope**: CLI Container Build
*   **Rationale & Proposed Changes**: Updates `COPY` instructions for repository-root `.` build context (`cli/pyproject.toml`, `cli/uv.lock`, `cli/README.md`, `cli/src/`) and defines a `bootstrap` multi-stage target containing `scripts/`, `infra/`, and `contracts/` (without `photosphere.config.json`, so `docker compose run --rm init` can run from a clean checkout). The default final `runtime` stage inherits from `bootstrap` and executes `COPY photosphere.config.json ./photosphere.config.json`, ensuring `docker build -f cli/Dockerfile .` fails immediately if `photosphere.config.json` does not exist.

#### 23. `./ssr/Dockerfile` (Modify)

*   **Type / Scope**: SSR Container Build
*   **Rationale & Proposed Changes**: Updates `COPY` instructions for repository-root `.` build context (`ssr/package.json`, `ssr/pnpm-lock.yaml`, `ssr/pnpm-workspace.yaml`, `ssr/`), executes `COPY photosphere.config.json ./photosphere.config.json` before `pnpm build` and in the `runner` stage so `docker build` fails immediately when `photosphere.config.json` is absent while `00.photosphere-config.ts` enforces runtime config presence on container start.

#### 24. `./Makefile` (Modify)

*   **Type / Scope**: Developer Task Orchestration
*   **Rationale & Proposed Changes**: Adds `init` to `.PHONY` (`uv run --project cli python -m scripts.init $(ARGS)`), updates `docker-build` to pass repo root `.` as the Docker build context (`docker build -f cli/Dockerfile -t photosphere-cli:local .` and `docker build -f ssr/Dockerfile -t photosphere-ssr:local .`), and retains `dev-gcs` (`docker compose up -d fake-gcs-server`) solely for automated test runs.

#### 25. `./docker-compose.yml` (Modify)

*   **Type / Scope**: Container Orchestration
*   **Rationale & Proposed Changes**:
    *   Adds an interactive `init` service (`build: { context: ., dockerfile: cli/Dockerfile, target: bootstrap }`, `entrypoint: ["python", "-m", "scripts.init"]`, `stdin_open: true`, `tty: true`, mounting `.:/app` and `${HOME}/.config/gcloud:/home/appuser/.config/gcloud:ro`) so `docker compose run --rm init` works from a clean checkout before `photosphere.config.json` exists, without local Python or `uv` installation.
    *   Updates `cli` and `ssr` services to build from context `.` (`dockerfile: cli/Dockerfile`, `dockerfile: ssr/Dockerfile`), mounts `./photosphere.config.json:/app/photosphere.config.json:ro`, and removes the `./ssr/.env.example` `env_file`.
    *   Removes `depends_on: fake-gcs-server` and default `STORAGE_EMULATOR_HOST: http://fake-gcs-server:4443` from `cli`, keeping `fake-gcs-server` and `fake_gcs_data` intact for automated tests.

#### 26. `./README.md` (Modify)

*   **Type / Scope**: Root Blueprint Documentation
*   **Rationale & Proposed Changes**: Updates root setup instructions, directory descriptions (`./scripts/`), and verification instructions to cover `make init`, `photosphere.config.json`, configurable dev/prod storage classes, and the test-only role of `fake-gcs-server`.

#### 27. `./cli/README.md` (Modify)

*   **Type / Scope**: CLI Package Documentation
*   **Rationale & Proposed Changes**: Documents `photosphere.config.json` loading, `media_storage_class` / `data_storage_class` verification in `GCSStorageClient`, and `make init` bootstrapping.

#### 28. `./ssr/README.md` (Modify)

*   **Type / Scope**: SSR Package Documentation
*   **Rationale & Proposed Changes**: Documents `photosphere.config.json` build/startup validation (`nuxt.config.ts` and `00.photosphere-config.ts`) replacing `.env`-only runtime setup.

#### 29. `./infra/README.md` (Modify)

*   **Type / Scope**: Infra Package Documentation
*   **Rationale & Proposed Changes**: Documents `make init` / `scripts/init/` automated provisioning alongside the existing manual command reference, clarifying that `infra/storage.rules` remains an unmodified template in git.

### Verification Plan

*   **Compilation/Build**:
    *   Verify `docker build -f cli/Dockerfile .` and `docker build -f ssr/Dockerfile .` fail when `./photosphere.config.json` is absent, and succeed when a valid `./photosphere.config.json` is present.
    *   Verify `docker compose build init` (`target: bootstrap`) succeeds **before** `./photosphere.config.json` exists so `docker compose run --rm init` can generate `./photosphere.config.json` from a clean checkout.
    *   Verify `make build` (`cd ssr && pnpm build`) fails fast without `./photosphere.config.json` and succeeds when `./photosphere.config.json` is present.
*   **Unit Tests**:
    *   `cd cli && uv run pytest tests ../scripts` passes all existing tests plus `./scripts/init/test_bootstrap.py` (fast-path print-and-exit, idempotent 10-step mocked REST sequence, `412` DB seed skip, Blaze/Google Sign-In console pause-and-retry, atomic write), `./cli/tests/test_models_contracts.py`, and `./cli/tests/test_ingest_pipeline.py`.
    *   `cd ssr && pnpm test` passes all existing `vitest` tests plus schema validation, fail-fast missing-config check, and `process.env`/runtimeConfig hydration tests.
*   **Static Analysis & Linting**:
    *   `make check` (`cd cli && uv run ruff check . ../scripts && uv run ruff format --check . ../scripts && uv run pyright src tests ../scripts && uv run mypy src tests ../scripts && uv run pytest tests ../scripts` and `cd ssr && pnpm format && pnpm type-check && pnpm test`) completes with zero errors and keeps cyclomatic complexity `<= 10`.
*   **Test Coverage Requirement**:
    *   Maintain `>= 85%` branch/line coverage across new modules in `./scripts/init/`, `./cli/src/photosphere/config.py`, `./cli/src/photosphere/storage/gcs_client.py`, and `./ssr/server/utils/photosphere-config.ts`.
*   **E2E/Integration**:
    *   Automated integration suite (`make dev-gcs` + `STORAGE_EMULATOR_HOST=http://localhost:4443`) continues to pass against `fake-gcs-server`.
    *   Manual smoke run against a fresh GCP/Firebase dev project using `make init` (`STANDARD`/`STANDARD`) followed by `make cli ARGS="verify-db"` and `make dev` confirms live buckets, CORS, 4 empty DBs, Firebase Storage rules, and Google Sign-In startup end to end.

--------------------------------------------------------------------------------

*Drafted with EGM*