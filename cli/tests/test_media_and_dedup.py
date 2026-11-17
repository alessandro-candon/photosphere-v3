"""Tests for media processing parity, thumbnail scaling, translation, and dedup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from photosphere.ai.translator import KeyValueStore, translate_text
from photosphere.dedup.hashing import (
    find_similar_annotated_record,
    hamming_distance_percentage,
)
from photosphere.dedup.skipped import SkippedManager
from photosphere.media.base import compute_sha1
from photosphere.media.gps import dms_to_decimal, encode_geohash
from photosphere.media.image import THUMBNAIL_PIXEL_SIZE, ImageProcessor
from photosphere.media.video import VideoProcessor
from photosphere.models.database import FileType, MediaRecord
from tests.conftest import create_sample_jpeg, create_sample_rgba_png


def test_image_processor_scales_thumbnails_transposes_exif_and_preserves_rgba(
    tmp_path: Path,
) -> None:
    png_path = create_sample_rgba_png(tmp_path / "input" / "wide.png", size=(800, 400))
    # Orientation 6 rotates a portrait frame 270 deg (640x480 -> transposed 480x640)
    jpg_path = create_sample_jpeg(
        tmp_path / "input" / "rotated.jpg", size=(640, 480), orientation=6
    )

    processor = ImageProcessor()
    thumb_dir = tmp_path / "thumbs"

    png_meta = processor.process(png_path, thumb_dir)
    assert png_meta.file_type == FileType.IMAGE
    assert png_meta.average_hash is not None
    assert len(png_meta.average_hash) == 64  # 16x16 = 256 bits = 64 hex chars
    assert png_meta.thumbnail_path is not None
    with Image.open(png_meta.thumbnail_path) as png_thumb:
        assert png_thumb.format == "JPEG"
        assert png_thumb.mode == "RGB"
        assert max(png_thumb.size) == THUMBNAIL_PIXEL_SIZE
        assert png_thumb.size == (280, 140)

    jpg_meta = processor.process(jpg_path, thumb_dir)
    assert jpg_meta.thumbnail_path is not None
    with Image.open(jpg_meta.thumbnail_path) as jpg_thumb:
        assert jpg_thumb.format == "JPEG"
        assert max(jpg_thumb.size) == THUMBNAIL_PIXEL_SIZE
        assert jpg_thumb.size == (210, 280)


def test_video_processor_scales_first_frame_identically_to_images(
    tmp_path: Path,
) -> None:
    import av
    import numpy as np

    clip_path = tmp_path / "input" / "clip.mp4"
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(clip_path), mode="w") as container:
        container.metadata["creation_time"] = "2024-06-15T10:30:00Z"
        container.metadata["location"] = "+45.4642+009.1900/"
        stream = container.add_stream("mpeg4", rate=2)
        stream.width = 640
        stream.height = 480
        stream.pix_fmt = "yuv420p"
        arr = np.full((480, 640, 3), (30, 80, 160), dtype=np.uint8)
        for _ in range(4):
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)

    processor = VideoProcessor()
    meta = processor.process(clip_path, tmp_path / "thumbs")
    assert meta.file_type == FileType.VIDEO
    assert meta.sha1 == compute_sha1(clip_path)
    assert meta.created_at is not None and meta.created_at.year == 2024
    assert meta.geohash is not None and meta.geohash.startswith("u0nd9")
    assert meta.thumbnail_path is not None
    assert meta.average_hash is not None and meta.average_hash.startswith("0b")
    assert len(meta.average_hash) == 66
    with Image.open(meta.thumbnail_path) as thumb:
        assert thumb.format == "JPEG"
        assert thumb.mode == "RGB"
        assert max(thumb.size) == THUMBNAIL_PIXEL_SIZE
        assert thumb.size == (280, 210)


@pytest.mark.parametrize(
    ("ext", "codec"),
    [(".avi", "mpeg4"), (".mpg", "mpeg1video")],
)
def test_video_processor_supports_avi_and_mpg(
    tmp_path: Path,
    ext: str,
    codec: str,
) -> None:
    import av
    import numpy as np

    from photosphere.media.base import classify_media_type

    assert classify_media_type(Path(f"SAMPLE{ext.upper()}")) == FileType.VIDEO

    clip_path = tmp_path / "input" / f"clip{ext}"
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(clip_path), mode="w") as container:
        stream = container.add_stream(codec, rate=25)
        assert isinstance(stream, av.VideoStream)
        stream.width = 320
        stream.height = 240
        stream.pix_fmt = "yuv420p"
        arr = np.full((240, 320, 3), (40, 120, 200), dtype=np.uint8)
        for _ in range(4):
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)

    processor = VideoProcessor()
    meta = processor.process(clip_path, tmp_path / "thumbs")
    assert meta.file_type == FileType.VIDEO
    assert meta.sha1 == compute_sha1(clip_path)
    assert meta.thumbnail_path is not None and meta.thumbnail_path.exists()
    assert meta.average_hash is not None and meta.average_hash.startswith("0b")
    assert len(meta.average_hash) == 66
    with Image.open(meta.thumbnail_path) as thumb:
        assert thumb.format == "JPEG"
        assert thumb.mode == "RGB"
        assert max(thumb.size) == THUMBNAIL_PIXEL_SIZE


def test_gps_encoding_and_hamming_similarity_lookup() -> None:
    lat = dms_to_decimal(45.0, 27.0, 51.12, "N")
    lon = dms_to_decimal(9.0, 11.0, 24.0, "E")
    geohash = encode_geohash(lat, lon)
    assert geohash.startswith("u0nd9")

    dist, _, sim = hamming_distance_percentage("ffff", "ffff")
    assert dist == 0 and sim == 100.0
    dist_bin, _, sim_bin = hamming_distance_percentage("0b11110000", "0b11110000")
    assert dist_bin == 0 and sim_bin == 100.0
    assert hamming_distance_percentage("ffff", "ff")[2] == 0.0
    assert hamming_distance_percentage("0b1010", "abcd")[2] == 0.0
    assert hamming_distance_percentage("zzzz", "ffff")[2] == 0.0
    assert hamming_distance_percentage("0b", "0b")[2] == 0.0
    assert hamming_distance_percentage(None, "ffff")[2] == 0.0

    existing = MediaRecord(
        hash="a" * 40,
        average_hash="ffff" * 16,
        source_bucket_uri="gs://b/a.jpg",
        file_type=FileType.IMAGE,
        label_indexes=[0, 1],
        caption_index=0,
    )
    unannotated = MediaRecord(
        hash="b" * 40,
        average_hash="ffff" * 16,
        source_bucket_uri="gs://b/b.jpg",
        file_type=FileType.IMAGE,
        label_indexes=[],
        caption_index=None,
    )
    assert find_similar_annotated_record(None, [existing]) is None
    assert find_similar_annotated_record("ffff" * 16, [unannotated]) is None
    matched = find_similar_annotated_record("ffff" * 16, [existing], threshold_pct=90.0)
    assert matched is existing
    unmatched = find_similar_annotated_record(
        "0000" * 16, [existing], threshold_pct=90.0
    )
    assert unmatched is None


def test_skipped_manager_moves_collision_safely_and_logs_manifest(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "staging"
    skipped_dir = tmp_path / "skipped"
    f1 = create_sample_jpeg(source_root / "nested" / "photo.jpg")
    f2 = create_sample_jpeg(source_root / "nested" / "photo.2.copy.jpg")
    # Force collision under skipped/nested/photo.jpg on second move
    f2_renamed = source_root / "nested" / "photo.jpg"

    mgr = SkippedManager(skipped_dir)
    entry1 = mgr.move_to_skipped(
        f1, reason="duplicate_sha1", sha1=compute_sha1(f1), source_root=source_root
    )
    assert not f1.exists()
    assert Path(entry1.skipped_path).exists()

    f2.rename(f2_renamed)
    entry2 = mgr.move_to_skipped(
        f2_renamed,
        reason="duplicate_sha1",
        sha1=compute_sha1(f2_renamed),
        source_root=source_root,
    )
    assert Path(entry2.skipped_path).exists()
    assert entry1.skipped_path != entry2.skipped_path

    manifest_raw = json.loads(
        (skipped_dir / "skipped_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest_raw["entries"]) == 2


def test_key_value_store_deterministic_flush_and_meta_cleanup(
    tmp_path: Path,
) -> None:
    store = KeyValueStore(tmp_path / "en_labels.json")
    idx0 = store.add_unique_value("dog")
    idx1 = store.add_unique_value("park")
    idx0_again = store.add_unique_value("dog")
    assert (idx0, idx1, idx0_again) == (0, 1, 0)
    store.flush_to_disk()
    assert (tmp_path / "en_labels.json").read_text(
        encoding="utf-8"
    ) == '{"0":"dog","1":"park"}'

    cleaned = translate_text(
        "cane",
        "it",
        translator_fn=lambda t, _: f"{t} (proper noun - keep in english)",
    )
    assert cleaned == "cane"

    cleaned_trailing = translate_text(
        "Milano",
        "it",
        translator_fn=lambda t, _: f"{t} city name optional",
    )
    assert cleaned_trailing == "Milano"
