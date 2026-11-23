"""Unit tests for photosphere.dedup.hashing."""

from __future__ import annotations

import pytest

from photosphere.dedup.hashing import (
    PerceptualHashIndex,
    find_similar_annotated_record,
    hamming_distance_percentage,
)
from photosphere.models.database import FileType, MediaRecord


def test_hamming_distance_percentage_hex_binary_and_edge_cases() -> None:
    dist, _, sim = hamming_distance_percentage("ffff", "ffff")
    assert dist == 0 and sim == 100.0
    dist_bin, _, sim_bin = hamming_distance_percentage("0b11110000", "0b11110000")
    assert dist_bin == 0 and sim_bin == 100.0
    assert hamming_distance_percentage("ffff", "ff")[2] == 0.0
    assert hamming_distance_percentage("0b1010", "abcd")[2] == 0.0
    assert hamming_distance_percentage("zzzz", "ffff")[2] == 0.0
    assert hamming_distance_percentage("0b", "0b")[2] == 0.0
    assert hamming_distance_percentage("", "ffff")[2] == 0.0
    assert hamming_distance_percentage(None, "ffff")[2] == 0.0


def test_find_similar_annotated_record_predecoded_and_malformed_candidates() -> None:
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
    malformed = MediaRecord(
        hash="c" * 40,
        average_hash="zzzz" * 16,
        source_bucket_uri="gs://b/c.jpg",
        file_type=FileType.IMAGE,
        label_indexes=[0],
        caption_index=0,
    )
    assert find_similar_annotated_record(None, [existing]) is None
    assert find_similar_annotated_record("zzzz" * 16, [existing]) is None
    assert find_similar_annotated_record("0b", [existing]) is None
    assert find_similar_annotated_record("ffff" * 16, [unannotated, malformed]) is None

    matched = find_similar_annotated_record(
        "ffff" * 16, [malformed, existing], threshold_pct=90.0
    )
    assert matched is existing
    unmatched = find_similar_annotated_record(
        "0000" * 16, [existing], threshold_pct=90.0
    )
    assert unmatched is None


@pytest.mark.parametrize(
    ("hash1", "hash2", "expected_sim"),
    [
        ("ffff" * 16, "ffff" * 16, 100.0),
        ("ffff" * 16, "0000" * 16, 0.0),
        ("0b" + "1" * 64, "0b" + "1" * 60 + "0000", 93.75),
        ("0b" + "1" * 64, "ffff" * 16, 0.0),
        ("ffff" * 16, "ffff" * 8, 0.0),
        ("zzzz" * 16, "ffff" * 16, 0.0),
        ("", "ffff" * 16, 0.0),
    ],
)
def test_hamming_and_find_similar_share_similarity_behavior(
    hash1: str, hash2: str, expected_sim: float
) -> None:
    _, _, sim = hamming_distance_percentage(hash1, hash2)
    assert sim == expected_sim
    candidate = MediaRecord(
        hash="d" * 40,
        average_hash=hash2,
        source_bucket_uri="gs://b/d.jpg",
        file_type=FileType.IMAGE,
        label_indexes=[0],
        caption_index=0,
    )
    found = find_similar_annotated_record(hash1, [candidate], threshold_pct=90.0)
    index = PerceptualHashIndex.from_records([candidate])
    indexed = index.find_similar(hash1, threshold_pct=90.0)
    if expected_sim >= 90.0:
        assert found is candidate
        assert indexed is candidate
    else:
        assert found is None
        assert indexed is None


def test_perceptual_hash_index_incremental_add() -> None:
    index = PerceptualHashIndex()
    assert index.find_similar("ffff" * 16) is None

    unannotated = MediaRecord(
        hash="a" * 40,
        average_hash="ffff" * 16,
        source_bucket_uri="gs://b/a.jpg",
        file_type=FileType.IMAGE,
    )
    index.add(unannotated)
    assert index.find_similar("ffff" * 16) is None

    annotated = MediaRecord(
        hash="b" * 40,
        average_hash="ffff" * 16,
        source_bucket_uri="gs://b/b.jpg",
        file_type=FileType.IMAGE,
        label_indexes=[1],
        caption_index=0,
    )
    index.add(annotated)
    assert index.find_similar("ffff" * 16) is annotated
