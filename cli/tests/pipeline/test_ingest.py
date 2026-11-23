"""Unit tests for photosphere.pipeline.ingest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

from photosphere.ai.protocol import AIInferenceError, MediaAnnotation
from photosphere.config import PhotosphereSettings
from photosphere.media.base import compute_sha1
from photosphere.pipeline.ingest import (
    CAPTIONS_DB_SUFFIX,
    LABELS_DB_SUFFIX,
    MEDIA_DB_FILENAME,
    IngestPipeline,
)
from photosphere.storage.checkpoint import CheckpointEntry, CheckpointModeMismatchError
from tests.conftest import FakeAIProvider, create_sample_jpeg, make_gcs


def test_ingest_pipeline_dedup_ai_translation_and_dual_bucket_routing(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "media"
    img1 = create_sample_jpeg(media_dir / "photo_a.jpg", color=(10, 80, 160))
    create_sample_jpeg(media_dir / "photo_a_dup.jpg", color=(10, 80, 160))
    unsupported = media_dir / "notes.txt"
    unsupported.parent.mkdir(parents=True, exist_ok=True)
    unsupported.write_text("ignore me", encoding="utf-8")

    gcs, media_bkt, data_bkt = make_gcs()
    fake_ai = FakeAIProvider(labels=["ocean", "blue"], caption="A calm blue frame.")
    pipeline = IngestPipeline(
        cli_settings, gcs, ai_provider=fake_ai, translator=fake_translator
    )

    summary = pipeline.run(media_dir, init_db=True)
    assert summary.scanned == 3
    assert summary.ingested == 1
    assert summary.skipped_duplicate == 1
    assert summary.skipped_unsupported == 1
    assert summary.ai_annotated == 1
    assert summary.translated_entries == 3

    sha1 = compute_sha1(img1)
    assert f"no_datetime/{img1.name}" in media_bkt.objects
    assert f"thumbnails/{img1.name}.{sha1}.thumbnail.jpg" in media_bkt.objects
    assert MEDIA_DB_FILENAME in data_bkt.objects
    assert f"en_{LABELS_DB_SUFFIX}" in data_bkt.objects
    assert f"it_{LABELS_DB_SUFFIX}" in data_bkt.objects
    assert f"it_{CAPTIONS_DB_SUFFIX}" in data_bkt.objects
    assert not cli_settings.checkpoint_path.exists()
    assert (cli_settings.skipped_dir / "skipped_manifest.json").exists()


def test_ingest_isolates_corrupt_media_without_aborting_batch(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "media"
    create_sample_jpeg(media_dir / "good.jpg", color=(40, 120, 200))
    corrupt = media_dir / "corrupt.jpg"
    corrupt.write_bytes(b"not-a-valid-jpeg")

    gcs, _, _ = make_gcs()
    pipeline = IngestPipeline(
        cli_settings, gcs, ai_provider=FakeAIProvider(), translator=fake_translator
    )
    dry_summary = pipeline.run(media_dir, init_db=True, dry_run=True)
    assert dry_summary.ingested == 1
    assert dry_summary.skipped_unsupported == 1
    assert corrupt.exists()

    summary = pipeline.run(media_dir, init_db=True)
    assert summary.ingested == 1
    assert summary.skipped_unsupported == 1
    assert not corrupt.exists()
    manifest = json.loads(
        cli_settings.skipped_manifest_path.read_text(encoding="utf-8")
    )
    assert manifest["entries"][0]["reason"] == "processing_error"


def test_ingest_pipeline_resumes_from_checkpoint_without_ai_or_reupload(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "media"
    img = create_sample_jpeg(media_dir / "resumed.jpg")
    sha1 = compute_sha1(img)

    gcs, media_bkt, data_bkt = make_gcs()
    pipeline = IngestPipeline(
        cli_settings, gcs, ai_provider=FakeAIProvider(), translator=fake_translator
    )
    pipeline.checkpoint.record(
        CheckpointEntry(
            sha1=sha1,
            source_bucket_uri=f"gs://{cli_settings.media_bucket}/no_datetime/resumed.jpg",
            thumbnail_bucket_uri=f"gs://{cli_settings.media_bucket}/thumbnails/resumed.jpg.{sha1}.thumbnail.jpg",
            label_indexes=[0],
            caption_index=0,
        )
    )

    summary = pipeline.run(media_dir, init_db=True)
    assert summary.resumed_from_checkpoint == 1
    assert summary.ingested == 1
    assert summary.ai_annotated == 0
    assert media_bkt.objects == {}
    assert MEDIA_DB_FILENAME in data_bkt.objects


def test_dry_run_is_read_only_and_previews_keys_and_collisions(
    cli_settings: PhotosphereSettings,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "media"
    (media_dir / "a").mkdir(parents=True)
    (media_dir / "b").mkdir(parents=True)
    create_sample_jpeg(
        media_dir / "a" / "shared.jpg", size=(32, 32), color=(10, 10, 10)
    )
    create_sample_jpeg(
        media_dir / "b" / "shared.jpg", size=(32, 32), color=(250, 250, 250)
    )
    (media_dir / "notes.txt").write_text("skip me", encoding="utf-8")

    gcs, media_bkt, data_bkt = make_gcs()
    pipeline = IngestPipeline(cli_settings, gcs, ai_provider=FakeAIProvider())
    summary = pipeline.run(media_dir, init_db=True, no_ai=True, dry_run=True)

    assert summary.dry_run is True
    assert summary.ingested == 1
    assert summary.skipped_collision == 1
    assert summary.skipped_unsupported == 1
    assert media_bkt.objects == {}
    assert data_bkt.objects == {}
    assert not cli_settings.skipped_manifest_path.exists()


def test_target_key_collision_moves_to_skipped_and_preserves_first_blob(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "media"
    (media_dir / "dir1").mkdir(parents=True)
    (media_dir / "dir2").mkdir(parents=True)
    first = create_sample_jpeg(
        media_dir / "dir1" / "dup_name.jpg", size=(32, 32), color=(15, 25, 35)
    )
    second = create_sample_jpeg(
        media_dir / "dir2" / "dup_name.jpg", size=(32, 32), color=(200, 100, 50)
    )

    gcs, media_bkt, _ = make_gcs()
    pipeline = IngestPipeline(
        cli_settings, gcs, ai_provider=FakeAIProvider(), translator=fake_translator
    )
    summary = pipeline.run(media_dir, init_db=True, no_ai=True)

    assert summary.ingested == 1
    assert summary.skipped_collision == 1
    assert media_bkt.objects["no_datetime/dup_name.jpg"] == first.read_bytes()
    assert not second.exists()
    manifest = json.loads(
        cli_settings.skipped_manifest_path.read_text(encoding="utf-8")
    )
    assert manifest["entries"][0]["reason"] == "target_key_collision"


def test_periodic_commits_and_checkpoint_mode_mismatch(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "media"
    for idx in range(3):
        create_sample_jpeg(
            media_dir / f"img_{idx}.jpg",
            size=(32, 32),
            color=(idx * 60 + 10, 40, 80),
        )

    gcs, _, _ = make_gcs()
    pipeline = IngestPipeline(
        cli_settings, gcs, ai_provider=FakeAIProvider(), translator=fake_translator
    )
    summary = pipeline.run(media_dir, init_db=True, no_ai=True, commit_every=2)
    assert summary.ingested == 3
    assert summary.periodic_commits == 1

    pipeline.checkpoint.record(
        CheckpointEntry(
            sha1="a" * 40,
            routing_mode="preserve",
            source_bucket_uri="gs://test-media-archive/x.jpg",
        )
    )
    with pytest.raises(CheckpointModeMismatchError, match="preserve"):
        pipeline.run(media_dir, routing_mode="chronological", init_db=True, no_ai=True)


def test_ingest_caches_provider_uses_source_path_and_handles_retry_fallback(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_dir = tmp_path / "media"
    create_sample_jpeg(media_dir / "a.jpg", size=(400, 300), color=(10, 20, 30))
    img2 = create_sample_jpeg(media_dir / "b.jpg", size=(400, 300), color=(240, 10, 10))
    with Image.open(img2) as im:
        draw = ImageDraw.Draw(im)
        draw.rectangle([0, 0, 200, 300], fill=(255, 255, 255))
        im.save(img2, format="JPEG")

    gcs, _, _ = make_gcs()
    load_calls = 0
    analyzed_paths: list[Path] = []
    released = False

    class CountingProvider:
        def analyze(self, image_path: Path) -> MediaAnnotation:
            analyzed_paths.append(image_path)
            if image_path.name == "b.jpg":
                raise AIInferenceError("transient OOM")
            return MediaAnnotation(labels=["sky", "blue"], caption="Blue frame.")

        def release(self) -> None:
            nonlocal released
            released = True

    def fake_loader(*args: Any, **kwargs: Any) -> CountingProvider:
        _ = args, kwargs
        nonlocal load_calls
        load_calls += 1
        return CountingProvider()

    monkeypatch.setattr(
        "photosphere.pipeline.ingest.load_optional_ai_provider", fake_loader
    )
    pipeline = IngestPipeline(cli_settings, gcs, translator=fake_translator)
    summary = pipeline.run(media_dir, init_db=True)

    assert load_calls == 1
    assert summary.ai_annotated == 1
    assert summary.ai_retried == 1
    assert summary.ai_failed == 1
    assert released is True
    assert all(p.parent == media_dir for p in analyzed_paths)


def test_dry_run_preview_ai_populates_planned_upload_labels_and_caption(
    cli_settings: PhotosphereSettings,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "media"
    create_sample_jpeg(media_dir / "ocean.jpg", color=(10, 80, 160))

    gcs, _, _ = make_gcs()
    fake_ai = FakeAIProvider(
        labels=["ocean", "blue"], caption="A calm blue ocean frame."
    )
    pipeline = IngestPipeline(cli_settings, gcs, ai_provider=fake_ai)
    summary = pipeline.run(media_dir, init_db=True, dry_run=True, preview_ai=True)
    assert summary.dry_run is True
    assert summary.ingested == 1
    planned = summary.planned_uploads[0]
    assert planned.action == "upload"
    assert planned.labels == ["ocean", "blue"]
    assert planned.caption == "A calm blue ocean frame."


def test_ingest_skips_thumbnails_on_duplicates_and_batches_kv_flushes(
    cli_settings: PhotosphereSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image, ImageDraw

    from photosphere.ai.translator import KeyValueStore

    media_dir = tmp_path / "media"
    img1 = create_sample_jpeg(
        media_dir / "one.jpg", size=(800, 400), color=(20, 40, 60)
    )
    img2_path = media_dir / "two.jpg"
    img2 = Image.new("RGB", (800, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img2)
    for x in range(0, 800, 50):
        for y in range(0, 400, 50):
            if (x // 50 + y // 50) % 2 == 0:
                draw.rectangle([x, y, x + 49, y + 49], fill=(0, 0, 0))
    img2.save(img2_path, format="JPEG")
    img2.close()

    gcs, _, _ = make_gcs()
    flush_calls = 0
    original_flush = KeyValueStore.flush_to_disk

    def counting_flush(self: KeyValueStore) -> None:
        nonlocal flush_calls
        flush_calls += 1
        original_flush(self)

    monkeypatch.setattr(KeyValueStore, "flush_to_disk", counting_flush)

    received_images: list[tuple[int, int]] = []

    class InMemoryAIProvider:
        def analyze(self, image_path: Path) -> MediaAnnotation:
            raise AssertionError(f"Should use analyze_image for {image_path}")

        def analyze_image(
            self, image: Any, *, source_label: str = "<in-memory>"
        ) -> MediaAnnotation:
            _ = source_label
            received_images.append(image.size)
            return MediaAnnotation(labels=["sample"], caption="A sample photo.")

    pipeline = IngestPipeline(
        cli_settings, gcs, ai_provider=InMemoryAIProvider(), translator=None
    )
    cli_settings.target_lang = "en"
    summary = pipeline.run(media_dir, init_db=True, commit_every=100)

    assert summary.ingested == 2
    assert received_images == [(378, 189), (378, 189)]
    # Only the 2 flushes from final commit (zero per-file flushes during the loop).
    assert flush_calls == 2

    # Re-run on a duplicate copy of img1 in a fresh input dir and confirm no new
    # thumbnail is written to cache_dir/thumbnails.
    dup_dir = tmp_path / "dup_media"
    dup_dir.mkdir()
    dup_file = dup_dir / "one_copy.jpg"
    dup_file.write_bytes(img1.read_bytes())
    thumb_dir = cli_settings.cache_dir / "thumbnails"
    for existing_thumb in thumb_dir.glob("*"):
        existing_thumb.unlink()

    dup_summary = pipeline.run(dup_dir, init_db=False)
    assert dup_summary.skipped_duplicate == 1
    assert list(thumb_dir.glob("*")) == []


def test_chronological_routing_prefixes_dated_media_with_result(
    cli_settings: PhotosphereSettings,
    tmp_path: Path,
) -> None:
    from datetime import datetime

    from photosphere.media.base import MediaMetadata
    from photosphere.models.database import FileType
    from photosphere.pipeline.ingest import _build_remote_object_key

    dated = MediaMetadata(
        source_path=tmp_path / "photo.jpg",
        file_type=FileType.IMAGE,
        sha1="a" * 40,
        average_hash="ffff" * 16,
        created_at=datetime(2024, 5, 9, 14, 22, 10),
        latitude=None,
        longitude=None,
    )
    undated = MediaMetadata(
        source_path=tmp_path / "undated.jpg",
        file_type=FileType.IMAGE,
        sha1="b" * 40,
        average_hash="ffff" * 16,
        created_at=None,
        latitude=None,
        longitude=None,
    )

    assert (
        _build_remote_object_key(dated, tmp_path, cli_settings, "chronological")
        == "result/2024/05/09/photo.jpg"
    )
    assert (
        _build_remote_object_key(undated, tmp_path, cli_settings, "chronological")
        == "no_datetime/undated.jpg"
    )
