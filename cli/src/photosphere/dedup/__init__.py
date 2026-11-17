"""Deduplication and skipped-file isolation utilities."""

from photosphere.dedup.hashing import (
    find_similar_annotated_record,
    hamming_distance_percentage,
)
from photosphere.dedup.skipped import SkippedManager

__all__ = [
    "SkippedManager",
    "find_similar_annotated_record",
    "hamming_distance_percentage",
]
