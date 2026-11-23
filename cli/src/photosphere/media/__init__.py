"""Media classification, hashing, GPS encoding, and thumbnail processors."""

from photosphere.media.base import MediaMetadata, classify_media_type, compute_sha1
from photosphere.media.gps import dms_to_decimal, encode_geohash
from photosphere.media.image import (
    THUMBNAIL_PIXEL_SIZE,
    ImageProcessor,
    create_jpeg_thumbnail_from_pil,
)
from photosphere.media.video import VideoProcessor

__all__ = [
    "ImageProcessor",
    "MediaMetadata",
    "THUMBNAIL_PIXEL_SIZE",
    "VideoProcessor",
    "classify_media_type",
    "compute_sha1",
    "create_jpeg_thumbnail_from_pil",
    "dms_to_decimal",
    "encode_geohash",
]
