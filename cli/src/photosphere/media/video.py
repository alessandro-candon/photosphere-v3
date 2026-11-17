"""Video metadata extraction, hashing, and first-frame JPEG thumbnail generation."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from pathlib import Path

import av
import imagehash
import structlog
from PIL import Image

from photosphere.media.base import MediaMetadata, compute_sha1
from photosphere.media.image import create_jpeg_thumbnail_from_pil
from photosphere.models.database import FileType

logger = structlog.get_logger(__name__)

_ISO6709_RE = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)")
_COLLAGE_TILE_SIZE = 144
_MAX_SAMPLED_FRAMES = 64


def _parse_timestamp(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    normalized = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed
    except ValueError:
        return None


def _parse_iso6709_location(raw: object) -> tuple[float | None, float | None]:
    if not isinstance(raw, str):
        return None, None
    match = _ISO6709_RE.match(raw.strip())
    if not match:
        return None, None
    try:
        return float(match.group(1)), float(match.group(2))
    except ValueError:
        return None, None


def _apply_frame_rotation(
    img: Image.Image, frame: av.VideoFrame, stream_rotate: str | None
) -> Image.Image:
    """Apply container/frame rotation metadata so portrait videos stay upright."""
    rotation = getattr(frame, "rotation", 0) or 0
    if rotation == 0 and stream_rotate:
        try:
            rotation = int(stream_rotate)
        except ValueError:
            rotation = 0
    normalized = rotation % 360
    if normalized == 0:
        return img
    return img.rotate(-normalized, expand=True)


def _extract_video_metadata(
    video_path: Path,
) -> tuple[datetime | None, float | None, float | None]:
    """Read creation timestamp and ISO-6709 GPS coordinates via PyAV."""
    try:
        with av.open(str(video_path)) as container:
            tags: dict[str, str] = {}
            if container.streams.video:
                tags.update(dict(container.streams.video[0].metadata))
            tags.update(dict(container.metadata))

            raw_ts = tags.get("com.apple.quicktime.creationdate") or tags.get(
                "creation_time"
            )
            raw_loc = tags.get("com.apple.quicktime.location.ISO6709") or tags.get(
                "location"
            )
            created_at = _parse_timestamp(raw_ts)
            lat, lon = _parse_iso6709_location(raw_loc)
            return created_at, lat, lon
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.warning("video_metadata_failed", path=str(video_path), error=str(exc))
        return None, None, None


def _extract_first_frame_jpeg(video_path: Path, destination: Path) -> Path | None:
    """Decode frame at t=0 via PyAV and process identically to image thumbnails."""
    try:
        with av.open(str(video_path)) as container:
            if not container.streams.video:
                return None
            stream = container.streams.video[0]
            stream_rotate = stream.metadata.get("rotate")
            for frame in container.decode(stream):
                img = _apply_frame_rotation(frame.to_image(), frame, stream_rotate)
                return create_jpeg_thumbnail_from_pil(img, destination)
            return None
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.warning("video_thumbnail_failed", path=str(video_path), error=str(exc))
        return None


def _build_collage(frames: list[Image.Image]) -> Image.Image:
    """Tile 144x144 sampled frames into a square grid matching videohash2 layout."""
    count = len(frames)
    cols = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / cols))
    canvas = Image.new(
        "RGB", (cols * _COLLAGE_TILE_SIZE, rows * _COLLAGE_TILE_SIZE), (0, 0, 0)
    )
    for idx, frame in enumerate(frames):
        resized = frame.convert("RGB").resize(
            (_COLLAGE_TILE_SIZE, _COLLAGE_TILE_SIZE), Image.Resampling.BILINEAR
        )
        col = idx % cols
        row = idx // cols
        canvas.paste(resized, (col * _COLLAGE_TILE_SIZE, row * _COLLAGE_TILE_SIZE))
    return canvas


def _sample_video_frames(video_path: Path) -> list[Image.Image]:
    """Sample 1 frame per second across the video using container.seek()."""
    frames: list[Image.Image] = []
    with av.open(str(video_path)) as container:
        if not container.streams.video:
            return frames
        stream = container.streams.video[0]
        stream_rotate = stream.metadata.get("rotate")
        duration_sec = (
            float(container.duration) / av.time_base
            if container.duration is not None and container.duration > 0
            else 0.0
        )
        total_seconds = max(1, int(math.floor(duration_sec)))
        step = max(1, math.ceil(total_seconds / _MAX_SAMPLED_FRAMES))
        timestamps = list(range(0, total_seconds, step))

        for sec in timestamps:
            try:
                if sec > 0:
                    container.seek(int(sec * av.time_base), any_frame=False)
                for frame in container.decode(stream):
                    img = _apply_frame_rotation(frame.to_image(), frame, stream_rotate)
                    frames.append(img)
                    break
            except Exception:
                continue
    return frames


def _compute_video_hash(video_path: Path, thumbnail_path: Path | None) -> str | None:
    """Compute binary-prefixed (`0b...`) 64-bit wavelet hash via PyAV collage."""
    try:
        frames = _sample_video_frames(video_path)
        if frames:
            collage = _build_collage(frames)
            whash = imagehash.whash(collage, hash_size=8)
            bits = "".join("1" if bit else "0" for bit in whash.hash.flatten())
            return f"0b{bits}"
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.warning("video_hash_failed", path=str(video_path), error=str(exc))

    if thumbnail_path is None or not thumbnail_path.exists():
        return None
    with Image.open(thumbnail_path) as thumb:
        whash = imagehash.whash(thumb, hash_size=8)
        bits = "".join("1" if bit else "0" for bit in whash.hash.flatten())
        return f"0b{bits}"


class VideoProcessor:
    """Extract video metadata, perceptual VideoHash, and 280x280 JPEG thumbnails."""

    def process(self, video_path: Path, thumbnail_dir: Path) -> MediaMetadata:
        """Process a video file and generate its local first-frame JPEG thumbnail."""
        sha1 = compute_sha1(video_path)
        thumb_path = thumbnail_dir / f"{video_path.name}.{sha1}.thumbnail.jpg"
        created_at, lat, lon = _extract_video_metadata(video_path)
        generated_thumb = _extract_first_frame_jpeg(video_path, thumb_path)
        avg_hash = _compute_video_hash(video_path, generated_thumb)

        return MediaMetadata(
            source_path=video_path,
            file_type=FileType.VIDEO,
            sha1=sha1,
            average_hash=avg_hash,
            created_at=created_at,
            latitude=lat,
            longitude=lon,
            thumbnail_path=generated_thumb,
        )
