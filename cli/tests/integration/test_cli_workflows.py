"""End-to-end integration tests across ingest, annotate, translate, and verify-db."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from photosphere.main import cli
from photosphere.pipeline.annotate import AnnotatePipeline
from photosphere.pipeline.common import MEDIA_DB_FILENAME
from photosphere.pipeline.ingest import IngestPipeline
from tests.conftest import FakeAIProvider, create_sample_jpeg, make_gcs


def test_end_to_end_ingest_no_ai_then_annotate_then_verify_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_translator: Any,
) -> None:
    from photosphere.config import PhotosphereSettings

    settings = PhotosphereSettings(
        media_bucket="test-media-archive",
        media_storage_class="ARCHIVE",
        data_bucket="test-data-standard",
        data_storage_class="STANDARD",
        skipped_dir=tmp_path / "skipped",
        cache_dir=tmp_path / "cache",
        target_lang="it",
        device="cpu",
    )
    media_dir = tmp_path / "photos"
    create_sample_jpeg(media_dir / "trip.jpg", color=(30, 140, 90))

    gcs, _, _ = make_gcs()

    # 1. Ingest with --no-ai
    ingest_summary = IngestPipeline(settings, gcs).run(
        media_dir, init_db=True, no_ai=True
    )
    assert ingest_summary.ingested == 1
    assert ingest_summary.ai_annotated == 0

    # 2. Backfill AI tags + captions + Italian translations via AnnotatePipeline
    fake_ai = FakeAIProvider(labels=["forest", "green"], caption="Green forest.")
    annotate_summary = AnnotatePipeline(
        settings, gcs, ai_provider=fake_ai, translator=fake_translator
    ).run(local_media_dir=media_dir)
    assert annotate_summary.candidates == 1
    assert annotate_summary.ai_annotated == 1
    assert annotate_summary.translated_entries == 3

    # 3. Verify all 4 databases through Click `verify-db`
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    monkeypatch.setenv("PHOTOSPHERE_MEDIA_BUCKET", settings.media_bucket)
    monkeypatch.setenv("PHOTOSPHERE_DATA_BUCKET", settings.data_bucket)
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(settings.cache_dir))
    monkeypatch.setattr(
        "photosphere.storage.gcs_client._build_storage_client",
        lambda *args, **kwargs: gcs._client,
    )

    runner = CliRunner()
    res_en = runner.invoke(cli, ["verify-db", "--lang", "en"])
    assert res_en.exit_code == 0, res_en.output
    en_counts = json.loads(res_en.output)
    assert en_counts["media_count"] == 1
    assert en_counts["labels_count"] == 2
    assert en_counts["captions_count"] == 1

    res_it = runner.invoke(cli, ["verify-db", "--lang", "it"])
    assert res_it.exit_code == 0, res_it.output
    it_counts = json.loads(res_it.output)
    assert it_counts["labels_count"] == 2
    assert it_counts["captions_count"] == 1
    media_raw, _ = gcs.download_json(settings.data_bucket, MEDIA_DB_FILENAME)
    assert len(media_raw) == 1
