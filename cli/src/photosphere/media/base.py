"""Base media primitives: SHA-1 computation, extension routing, and metadata carrier."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from photosphere.media.gps import encode_geohash
from photosphere.models.database import FileType

IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".heic", ".webp"}
)
VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".m4v", ".mov", ".avi", ".mpg"})


def compute_sha1(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return lowercase hex SHA-1 digest computed over raw file bytes."""
    hasher = hashlib.sha1()
    with file_path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def classify_media_type(file_path: Path) -> FileType | None:
    """Classify supported extensions; return None for unsupported files."""
    suffix = file_path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return FileType.IMAGE
    if suffix in VIDEO_EXTENSIONS:
        return FileType.VIDEO
    return None


@dataclass(slots=True)
class MediaMetadata:
    """Extracted metadata, hashes, and generated thumbnail path for one local file."""

    source_path: Path
    file_type: FileType
    sha1: str
    average_hash: str | None
    created_at: datetime | None
    latitude: float | None
    longitude: float | None
    thumbnail_path: Path | None = None

    @property
    def created_at_timestamp(self) -> int | None:
        """Return Unix epoch seconds for created_at when available."""
        return int(self.created_at.timestamp()) if self.created_at is not None else None

    @property
    def geohash(self) -> str | None:
        """Return precision-9 base-32 geohash when GPS coordinates exist."""
        if self.latitude is not None and self.longitude is not None:
            return encode_geohash(self.latitude, self.longitude)
        return None
