"""Unit tests for photosphere.media.video."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from photosphere.media.base import MediaDecodeError, classify_media_type, compute_sha1
from photosphere.media.image import THUMBNAIL_PIXEL_SIZE
from photosphere.media.video import VideoProcessor
from photosphere.models.database import FileType


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
    meta = processor.process(clip_path, tmp_path / "thumbs", sha1="d" * 40)
    assert meta.file_type == FileType.VIDEO
    assert meta.sha1 == "d" * 40
    assert meta.thumbnail_path is not None and meta.thumbnail_path.exists()
    assert meta.average_hash is not None and meta.average_hash.startswith("0b")
    assert len(meta.average_hash) == 66
    with Image.open(meta.thumbnail_path) as thumb:
        assert thumb.format == "JPEG"
        assert thumb.mode == "RGB"
        assert max(thumb.size) == THUMBNAIL_PIXEL_SIZE


def test_video_processor_raises_media_decode_error_on_corrupt_container(
    tmp_path: Path,
) -> None:
    bad_video = tmp_path / "corrupt.mp4"
    bad_video.write_bytes(b"not-a-video-container")
    with pytest.raises(MediaDecodeError, match="Failed to open video container"):
        VideoProcessor().process(bad_video, tmp_path / "thumbs")


@pytest.mark.parametrize(
    ("meta_exc", "thumb_exc"),
    [
        (OSError("io error"), OSError("io error")),
        (ValueError("bad value"), ValueError("bad value")),
        (KeyError("missing key"), StopIteration("empty stream")),
    ],
)
def test_video_processor_handles_narrowed_metadata_and_frame_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    meta_exc: Exception,
    thumb_exc: Exception,
) -> None:
    import av
    import numpy as np

    import photosphere.media.video as video_mod

    clip_path = tmp_path / "clip.mp4"
    with av.open(str(clip_path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=2)
        stream.width = 64
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        arr = np.zeros((64, 64, 3), dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)

    def raise_meta(*_args: Any, **_kwargs: Any) -> Any:
        raise meta_exc

    def raise_thumb(*_args: Any, **_kwargs: Any) -> Any:
        raise thumb_exc

    monkeypatch.setattr(video_mod, "_metadata_from_container", raise_meta)
    monkeypatch.setattr(video_mod, "_first_frame_from_container", raise_thumb)
    meta = VideoProcessor().process(clip_path, tmp_path / "thumbs")
    assert meta.created_at is None
    assert meta.thumbnail_path is None


def test_video_processor_propagates_unexpected_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import av
    import numpy as np

    import photosphere.media.video as video_mod

    clip_path = tmp_path / "clip.mp4"
    with av.open(str(clip_path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=2)
        stream.width = 64
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        arr = np.zeros((64, 64, 3), dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)

    def raise_bug(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("unexpected bug")

    monkeypatch.setattr(video_mod, "_metadata_from_container", raise_bug)
    with pytest.raises(RuntimeError, match="unexpected bug"):
        VideoProcessor().process(clip_path, tmp_path / "thumbs")
