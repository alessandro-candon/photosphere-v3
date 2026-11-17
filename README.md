# Photosphere v3

An edge-first, serverless personal photo and video library backed by Google Cloud Storage and Firebase. All heavy media processing—metadata extraction, thumbnails, deduplication, AI tagging/captioning, and translation—runs locally on your machine through the `photosphere` CLI, while a lightweight web app lets you browse, search, and organize albums.

## Features

- **Zero system media dependencies**: Processes photos (including HEIC) and videos natively on macOS, Linux, and Windows—no local `ffmpeg` or `libheif` install required.
- **Smart deduplication**: Detects exact duplicates and visually similar media locally before uploading, moving skipped files to `./skipped/`.
- **Local or remote AI**: Optionally generates English tags and captions (with CUDA, Apple Silicon MPS, CPU, or a remote API) and translates dictionaries into other languages.
- **Cost-conscious cloud storage**: Keeps original media and `280x280` thumbnails in an Archive bucket and lightweight JSON indexes in a Standard bucket.
- **Web gallery (`ssr/`)**: Browse your library, filter by tags/dates, and manage albums behind Google Sign-In.

---

## Quick Start (CLI)

### 1. Install the CLI

Requires [uv](https://docs.astral.sh/uv/) (`>= 0.6`) and Python `>= 3.12`.

```bash
# Core CLI (scanning, thumbnails, deduplication, cloud sync)
uv tool install "git+https://github.com/<owner>/<repo>#subdirectory=cli"

# With local AI tagging, captioning, and translation
uv tool install "photosphere[ai] @ git+https://github.com/<owner>/<repo>#subdirectory=cli" --torch-backend=auto
```

If you are working from a local clone of this repository:

```bash
uv tool install ./cli
# or with AI extras:
uv tool install "./cli[ai]" --torch-backend=auto
```

To upgrade later:

```bash
uv tool upgrade photosphere
```

### 2. Set Up Cloud & Credentials

**First-time project bootstrap (admin):**  
From a cloned repo with `gcloud` authenticated, provision your GCP buckets, Firebase Storage rules, and `photosphere.config.json`:

```bash
make init
```

**On any machine using the CLI:**

1. Place your generated `photosphere.config.json` at `~/.photosphere/photosphere.config.json` (or pass `--config-file <path>`).
2. Authenticate with Google Cloud:
   ```bash
   gcloud auth application-default login
   ```
   *(Alternatively, pass `--creds <path-to-key.json>`, set `GOOGLE_APPLICATION_CREDENTIALS`, or save credentials to `~/.photosphere/credentials.json`.)*
3. Verify your setup:
   ```bash
   photosphere doctor
   ```

### 3. Common CLI Workflows

**Preview an import without uploading anything:**

```bash
photosphere ingest /path/to/photos --dry-run
```

**Ingest a folder of photos and videos:**

```bash
# First run on a brand-new empty bucket (add --init-db)
photosphere ingest /path/to/photos --init-db

# Standard run (organizes files as YYYY/MM/DD/<filename> in the bucket)
photosphere ingest /path/to/photos

# Keep your existing folder hierarchy instead of organizing by date
photosphere ingest /path/to/photos --routing-mode preserve

# Skip AI tagging/captioning for faster uploads
photosphere ingest /path/to/photos --no-ai
```

**Backfill AI tags & captions later:**

```bash
# Preview how many records need annotation
photosphere annotate --dry-run

# Annotate existing cloud records (using local files if available, or cloud thumbnails)
photosphere annotate --local-media-dir /path/to/photos
```

**Translate tags and captions into another language:**

```bash
photosphere translate --target-lang it
```

**Verify cloud databases:**

```bash
photosphere verify-db
```

**Useful global flags:**

- `--config-file <path>` — Use a specific `photosphere.config.json`
- `--creds <path>` — Use a specific GCP credentials JSON file
- `--verbose` — Show debug logs
- `--no-progress` — Disable progress bars

---

## Web App (`ssr/`)

Once you have a `photosphere.config.json` at the repo root, you can run the Nuxt web interface locally:

```bash
make setup
make dev
```

Or run it with Docker:

```bash
docker compose --profile full up -d ssr
```

---

## Repository Layout

- [`cli/`](./cli/README.md) — `photosphere` Python CLI package
- [`ssr/`](./ssr/README.md) — Nuxt 4 web application and Firebase Auth proxy
- [`scripts/`](./scripts/init/) — GCP/Firebase bootstrap (`make init`) and v2-to-v3 migration tools
- [`infra/`](./infra/README.md) — Firebase Storage rules and GCS CORS templates
- [`contracts/`](./contracts/README.md) — Shared JSON schemas and fixtures
- [`docs/`](./docs/) — Architecture and design documents

## Development

```bash
make setup     # Install CLI and SSR dependencies
make check     # Run linters, typechecks, and unit tests
make dev-gcs   # Start local fake-gcs-server for integration tests
```
