"""Image metadata extraction, perceptual hashing, and shared JPEG thumbnail builder."""

from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import imagehash
from PIL import ExifTags, Image, ImageOps
from pillow_heif import register_heif_opener

from photosphere.media.base import MediaMetadata, compute_sha1
from photosphere.media.gps import dms_to_decimal
from photosphere.models.database import FileType

register_heif_opener()

THUMBNAIL_PIXEL_SIZE = 280
THUMBNAIL_JPEG_QUALITY = 75
AVERAGE_HASH_SIZE = 16


def create_jpeg_thumbnail_from_pil(
    image: Image.Image,
    destination: Path,
    max_size: int = THUMBNAIL_PIXEL_SIZE,
    quality: int = THUMBNAIL_JPEG_QUALITY,
) -> Path:
    """Create a scaled RGB JPEG thumbnail without mutating the source Image instance."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    thumb = image.copy()
    thumb.thumbnail((max_size, max_size))
    if thumb.mode != "RGB":
        thumb = thumb.convert("RGB")
    thumb.save(destination, format="JPEG", quality=quality)
    return destination


def load_capped_rgb_image(image_path: Path, max_size: int = 1024) -> Image.Image:
    """Open an image with EXIF orientation applied, convert to RGB, and cap max edge."""
    with Image.open(image_path) as opened:
        oriented = ImageOps.exif_transpose(opened)
        rgb = oriented.convert("RGB") if oriented.mode != "RGB" else oriented.copy()
    if max(rgb.size) > max_size:
        rgb.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return rgb


def _parse_exif_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str) or "0000:00:00" in raw:
        return None
    text = raw.strip()
    patterns = (
        (
            r"^\d{2}/\d{2}/\d{4}\d:\d{2}$",
            lambda s: f"{s[6:10]}-{s[3:5]}-{s[0:2]} 0{s[10:]}:00",
        ),
        (
            r"^\d{2}/\d{2}/\d{4}\d{2}:\d{2}$",
            lambda s: f"{s[6:10]}-{s[3:5]}-{s[0:2]} {s[10:]}:00",
        ),
        (
            r"^\d{4}:\d{2}:\d{2}\d{2}:\d{2}:\d{2}$",
            lambda s: f"{s[0:4]}-{s[5:7]}-{s[8:10]} {s[10:]}",
        ),
        (
            r"^\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}$",
            lambda s: f"{s[0:4]}-{s[5:7]}-{s[8:10]} {s[11:]}",
        ),
    )
    for pattern, transform in patterns:
        if re.match(pattern, text):
            text = transform(text)
            break
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _extract_gps_pair(gps_info: object) -> tuple[float | None, float | None]:
    if not isinstance(gps_info, dict):
        return None, None
    required = (1, 2, 3, 4)
    if not all(key in gps_info for key in required):
        return None, None
    try:
        lat_dms = gps_info[2]
        lon_dms = gps_info[4]
        lat = dms_to_decimal(lat_dms[0], lat_dms[1], lat_dms[2], str(gps_info[1]))
        lon = dms_to_decimal(lon_dms[0], lon_dms[1], lon_dms[2], str(gps_info[3]))
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None, None
    if math.isnan(lat) or math.isnan(lon):
        return None, None
    return lat, lon


def _extract_exif_metadata(
    image: Image.Image,
) -> tuple[datetime | None, float | None, float | None]:
    exif_raw: Any = image.getexif()
    if not exif_raw:
        return None, None, None

    created_at: datetime | None = None
    fallback_dt: datetime | None = None
    lat: float | None = None
    lon: float | None = None

    for tag_id, value in exif_raw.items():
        tag = ExifTags.TAGS.get(tag_id, tag_id)
        if tag == "DateTimeOriginal":
            created_at = _parse_exif_datetime(value) or created_at
        elif tag == "DateTime":
            fallback_dt = _parse_exif_datetime(value) or fallback_dt
        elif tag == "GPSInfo":
            if hasattr(exif_raw, "get_ifd") and isinstance(value, int):
                gps_ifd = exif_raw.get_ifd(tag_id)
                lat, lon = _extract_gps_pair(gps_ifd)
            else:
                lat, lon = _extract_gps_pair(value)

    return created_at or fallback_dt, lat, lon


class ImageProcessor:
    """Extract metadata, 16x16 average_hash, and 280x280 JPEG thumbnails."""

    def process(self, image_path: Path, thumbnail_dir: Path) -> MediaMetadata:
        """Process an image file and generate its local thumbnail."""
        sha1 = compute_sha1(image_path)
        thumb_path = thumbnail_dir / f"{image_path.name}.{sha1}.thumbnail.jpg"

        with Image.open(image_path) as opened:
            created_at, lat, lon = _extract_exif_metadata(opened)
            oriented = ImageOps.exif_transpose(opened)
            avg_hash = str(imagehash.average_hash(oriented, AVERAGE_HASH_SIZE))
            create_jpeg_thumbnail_from_pil(oriented, thumb_path)

        return MediaMetadata(
            source_path=image_path,
            file_type=FileType.IMAGE,
            sha1=sha1,
            average_hash=avg_hash,
            created_at=created_at,
            latitude=lat,
            longitude=lon,
            thumbnail_path=thumb_path,
        )
