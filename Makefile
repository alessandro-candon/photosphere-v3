.PHONY: setup init dev dev-gcs cli cli-docker lint typecheck test check build docker-build migrate-v2

ARGS ?=
MEDIA_DIR ?= ./data/media

setup:
	cd cli && uv sync --dev
	cd ssr && pnpm install --frozen-lockfile

init:
	uv run --project cli python -m scripts.init $(ARGS)

dev:
	cd ssr && pnpm dev

# Automated test GCS emulator only (runtime dev/prod targets a real GCP project)
dev-gcs:
	docker compose up -d fake-gcs-server

cli:
	cd cli && uv run photosphere $(ARGS)

cli-docker:
	mkdir -p $(MEDIA_DIR) skipped .photosphere-cache
	HOST_UID=$$(id -u) HOST_GID=$$(id -g) MEDIA_DIR=$(MEDIA_DIR) docker compose --profile cli run --rm cli $(ARGS)

lint:
	cd cli && uv run ruff check . ../scripts && uv run ruff format --check . ../scripts
	cd ssr && pnpm format

typecheck:
	cd cli && uv run pyright src tests ../scripts && uv run mypy src tests ../scripts
	cd ssr && pnpm type-check

test:
	cd cli && uv run pytest tests ../scripts
	cd ssr && pnpm test

check: lint typecheck test

build:
	cd ssr && pnpm build

docker-build:
	docker build -f cli/Dockerfile -t photosphere-cli:local .
	docker build -f ssr/Dockerfile -t photosphere-ssr:local .

migrate-v2:
	uv run --project cli python scripts/migrate_v2_to_v3.py $(ARGS)

reset-doc:
	rm -f comprehension_report.md concepts_brief.md critic_report.md design_draft.md evaluation_report.md zoom_out_report.md