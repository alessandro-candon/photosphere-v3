"""Tests for the photosphere annotate backfill pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from photosphere.config import PhotosphereSettings
from photosphere.models.database import FileType, MediaDatabase, MediaRecord
from photosphere.pipeline.annotate import AnnotatePipeline
from photosphere.pipeline.ingest import (
    CAPTIONS_DB_SUFFIX,
    LABELS_DB_SUFFIX,
    MEDIA_DB_FILENAME,
)
from tests.conftest import FakeAIProvider, create_sample_jpeg


class _FakeAnnotateGCS:
    def __init__(self, settings: PhotosphereSettings, tmp_path: Path) -> None:
        self.settings = settings
        self.tmp_path = tmp_path
        self.jsons: dict[tuple[str, str], Any] = {}
        self.blobs: dict[tuple[str, str], Path] = {}
        self.downloaded_blobs: list[tuple[str, str]] = []

    def verify_bucket_classes(self, *args: Any, **kwargs: Any) -> None:
        return None

    def download_json(
        self, bucket_name: str, object_name: str, *, init_db: bool = False
    ) -> tuple[Any, int | None]:
        key = (bucket_name, object_name)
        if key not in self.jsons:
            return {}, None
        return self.jsons[key], 1

    def download_blob(
        self, bucket_name: str, object_name: str, destination: Path
    ) -> Path:
        self.downloaded_blobs.append((bucket_name, object_name))
        src = self.blobs[(bucket_name, object_name)]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(src.read_bytes())
        return destination

    def upload_json_atomic(
        self,
        bucket_name: str,
        object_name: str,
        payload: Any,
        *,
        if_generation_match: int | None = None,
    ) -> int:
        self.jsons[(bucket_name, object_name)] = payload
        return 2


def test_annotate_pipeline_backfills_only_unannotated_records(
    cli_settings: PhotosphereSettings, fake_translator: Any, tmp_path: Path
) -> None:
    gcs = _FakeAnnotateGCS(cli_settings, tmp_path)
    thumb1 = create_sample_jpeg(tmp_path / "thumbs" / "a.jpg", size=(280, 280))
    gcs.blobs[(cli_settings.media_bucket, "thumbnails/a.jpg")] = thumb1

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
    gcs.jsons[(cli_settings.data_bucket, MEDIA_DB_FILENAME)] = MediaDatabase(
        root={unannotated.hash: unannotated, already_done.hash: already_done}
    ).model_dump(mode="json")
    gcs.jsons[(cli_settings.data_bucket, f"en_{LABELS_DB_SUFFIX}")] = {"0": "existing"}
    gcs.jsons[(cli_settings.data_bucket, f"en_{CAPTIONS_DB_SUFFIX}")] = {
        "0": "Existing caption."
    }

    fake_ai = FakeAIProvider(labels=["mountain", "snow"], caption="Snowy peak.")
    pipeline = AnnotatePipeline(
        cli_settings, gcs, ai_provider=fake_ai, translator=fake_translator  # type: ignore[arg-type]
    )

    dry_summary = pipeline.run(dry_run=True)
    assert dry_summary.candidates == 1
    assert dry_summary.ai_annotated == 0

    summary = pipeline.run()
    assert summary.candidates == 1
    assert summary.ai_annotated == 1
    assert gcs.downloaded_blobs == [(cli_settings.media_bucket, "thumbnails/a.jpg")]

    updated_db = MediaDatabase.model_validate(
        gcs.jsons[(cli_settings.data_bucket, MEDIA_DB_FILENAME)]
    ).root
    assert updated_db[unannotated.hash].label_indexes == [1, 2]
    assert updated_db[unannotated.hash].caption_index == 1
    assert updated_db[already_done.hash].label_indexes == [0]
