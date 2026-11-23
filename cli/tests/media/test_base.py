"""Unit tests for photosphere.media.base."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from photosphere.media.base import (
    MediaDecodeError,
    MediaMetadata,
    classify_media_type,
    compute_sha1,
)
from photosphere.models.database import FileType


def test_compute_sha1_and_classify_media_type(tmp_path: Path) -> None:
    sample = tmp_path / "data.bin"
    payload = b"photosphere-media-bytes"
    sample.write_bytes(payload)
    assert compute_sha1(sample) == hashlib.sha1(payload).hexdigest()

    assert classify_media_type(Path("IMG.HEIC")) == FileType.IMAGE
    assert classify_media_type(Path("clip.MOV")) == FileType.VIDEO
    assert classify_media_type(Path("notes.txt")) is None


def test_media_metadata_properties_and_decode_error(tmp_path: Path) -> None:
    dt = datetime(2024, 5, 1, 12, 0, 0)
    meta = MediaMetadata(
        source_path=tmp_path / "a.jpg",
        file_type=FileType.IMAGE,
        sha1="a" * 40,
        average_hash="0" * 64,
        created_at=dt,
        latitude=45.4642,
        longitude=9.1900,
    )
    assert meta.created_at_timestamp == int(dt.timestamp())
    assert meta.geohash is not None and meta.geohash.startswith("u0nd9")

    no_gps = MediaMetadata(
        source_path=tmp_path / "b.jpg",
        file_type=FileType.IMAGE,
        sha1="b" * 40,
        average_hash=None,
        created_at=None,
        latitude=None,
        longitude=None,
    )
    assert no_gps.created_at_timestamp is None
    assert no_gps.geohash is None
    assert isinstance(MediaDecodeError("bad"), RuntimeError)
