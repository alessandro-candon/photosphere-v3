"""Unit tests for photosphere.pipeline.annotate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from photosphere.config import PhotosphereSettings
from photosphere.models.database import FileType, MediaDatabase, MediaRecord
from photosphere.pipeline.annotate import AnnotatePipeline
from photosphere.pipeline.common import (
    CAPTIONS_DB_SUFFIX,
    LABELS_DB_SUFFIX,
    MEDIA_DB_FILENAME,
)
from tests.conftest import FakeAIProvider, create_sample_jpeg, make_gcs


def test_annotate_pipeline_backfills_only_unannotated_records(
    cli_settings: PhotosphereSettings, fake_translator: Any, tmp_path: Path
) -> None:
    gcs, media_bkt, _ = make_gcs()
    thumb1 = create_sample_jpeg(tmp_path / "thumbs" / "a.jpg", size=(280, 280))
    media_bkt.objects["thumbnails/a.jpg"] = thumb1.read_bytes()
    media_bkt.generations["thumbnails/a.jpg"] = 1

    unannotated = MediaRecord(
        hash="a" * 40,
        average_hash="0" * 64,
        source_bucket_uri=f"gs://{cli_settings.media_bucket}/2024/01/01/a.jpg",
        thumbnail_bucket_uri=f"gs://{cli_settings.media_bucket}/thumbnails/a.jpg",
        file_type=FileType.IMAGE,
        label_indexes=[],
        caption_index=None,
    )
    already_done = MediaRecord(
        hash="b" * 40,
        average_hash="f" * 64,
        source_bucket_uri=f"gs://{cli_settings.media_bucket}/2024/01/01/b.jpg",
        thumbnail_bucket_uri=f"gs://{cli_settings.media_bucket}/thumbnails/b.jpg",
        file_type=FileType.IMAGE,
        label_indexes=[0],
        caption_index=0,
    )
    gcs.upload_json_atomic(
        cli_settings.data_bucket,
        MEDIA_DB_FILENAME,
        MediaDatabase(
            root={unannotated.hash: unannotated, already_done.hash: already_done}
        ).model_dump(mode="json"),
    )
    gcs.upload_json_atomic(
        cli_settings.data_bucket, f"en_{LABELS_DB_SUFFIX}", {"0": "existing"}
    )
    gcs.upload_json_atomic(
        cli_settings.data_bucket, f"en_{CAPTIONS_DB_SUFFIX}", {"0": "Existing caption."}
    )

    fake_ai = FakeAIProvider(labels=["mountain", "snow"], caption="Snowy peak.")
    pipeline = AnnotatePipeline(
        cli_settings, gcs, ai_provider=fake_ai, translator=fake_translator
    )

    dry_summary = pipeline.run(dry_run=True)
    assert dry_summary.candidates == 1
    assert dry_summary.ai_annotated == 0

    summary = pipeline.run()
    assert summary.candidates == 1
    assert summary.ai_annotated == 1

    updated_raw, _ = gcs.download_json(cli_settings.data_bucket, MEDIA_DB_FILENAME)
    updated_db = MediaDatabase.model_validate(updated_raw).root
    assert updated_db[unannotated.hash].label_indexes == [1, 2]
    assert updated_db[unannotated.hash].caption_index == 1
    assert updated_db[already_done.hash].label_indexes == [0]
