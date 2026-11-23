"""Unit tests for photosphere.media.image."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from photosphere.media.base import MediaDecodeError
from photosphere.media.image import (
    THUMBNAIL_PIXEL_SIZE,
    ImageProcessor,
    _extract_gps_pair,
    _parse_exif_datetime,
)
from photosphere.models.database import FileType
from tests.conftest import create_sample_jpeg, create_sample_rgba_png


def test_image_processor_scales_thumbnails_transposes_exif_and_preserves_rgba(
    tmp_path: Path,
) -> None:
    png_path = create_sample_rgba_png(tmp_path / "input" / "wide.png", size=(800, 400))
    jpg_path = create_sample_jpeg(
        tmp_path / "input" / "rotated.jpg", size=(640, 480), orientation=6
    )

    processor = ImageProcessor()
    thumb_dir = tmp_path / "thumbs"

    png_meta = processor.process(png_path, thumb_dir)
    assert png_meta.file_type == FileType.IMAGE
    assert png_meta.average_hash is not None
    assert len(png_meta.average_hash) == 64
    assert png_meta.thumbnail_path is not None
    with Image.open(png_meta.thumbnail_path) as png_thumb:
        assert png_thumb.format == "JPEG"
        assert png_thumb.mode == "RGB"
        assert max(png_thumb.size) == THUMBNAIL_PIXEL_SIZE
        assert png_thumb.size == (280, 140)

    jpg_meta = processor.process(jpg_path, thumb_dir, sha1="c" * 40)
    assert jpg_meta.sha1 == "c" * 40
    assert jpg_meta.thumbnail_path is not None
    with Image.open(jpg_meta.thumbnail_path) as jpg_thumb:
        assert jpg_thumb.format == "JPEG"
        assert max(jpg_thumb.size) == THUMBNAIL_PIXEL_SIZE
        assert jpg_thumb.size == (210, 280)


def test_image_processor_raises_media_decode_error_on_corrupt_file(
    tmp_path: Path,
) -> None:
    bad_img = tmp_path / "corrupt.jpg"
    bad_img.write_bytes(b"not-a-valid-jpeg")
    with pytest.raises(MediaDecodeError, match="Failed to decode image"):
        ImageProcessor().process(bad_img, tmp_path / "thumbs")


def test_exif_datetime_and_gps_parsers() -> None:
    assert _parse_exif_datetime("0000:00:00 00:00:00") is None
    assert _parse_exif_datetime("2024:06:15 10:30:00") is not None
    assert _parse_exif_datetime("15/06/20249:05") is not None
    assert _parse_exif_datetime("not-a-date") is None
    assert _extract_gps_pair(None) == (None, None)
    assert _extract_gps_pair(
        {1: "N", 2: (45.0, 0.0, 0.0), 3: "E", 4: (9.0, 0.0, 0.0)}
    ) == (
        45.0,
        9.0,
    )
    assert _extract_gps_pair(
        {1: "N", 2: (float("nan"), 0, 0), 3: "E", 4: (9, 0, 0)}
    ) == (
        None,
        None,
    )


def test_process_for_ingest_single_pass_cascade_and_skip_thumbnail(
    tmp_path: Path,
) -> None:
    jpg_path = create_sample_jpeg(
        tmp_path / "input" / "wide.jpg", size=(1200, 600), orientation=6
    )
    processor = ImageProcessor()
    thumb_dir = tmp_path / "thumbs"

    baseline = processor.process(jpg_path, thumb_dir / "baseline")
    meta, ai_image = processor.process_for_ingest(
        jpg_path,
        thumb_dir / "cascade",
        generate_thumbnail=True,
        extract_exif=True,
        ai_max_image_size=378,
    )
    assert meta.average_hash == baseline.average_hash
    assert ai_image is not None
    try:
        assert ai_image.mode == "RGB"
        assert max(ai_image.size) == 378
        assert ai_image.size == (189, 378)
    finally:
        ai_image.close()

    assert meta.thumbnail_path is not None and meta.thumbnail_path.exists()
    with Image.open(meta.thumbnail_path) as thumb:
        assert thumb.size == (140, 280)

    no_thumb_meta, no_ai = processor.process_for_ingest(
        jpg_path,
        thumb_dir / "no_thumb",
        generate_thumbnail=False,
        extract_exif=False,
        ai_max_image_size=None,
    )
    assert no_thumb_meta.average_hash == baseline.average_hash
    assert no_thumb_meta.thumbnail_path is None
    assert no_ai is None
    assert not (thumb_dir / "no_thumb").exists()
