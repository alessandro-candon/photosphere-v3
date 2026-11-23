"""Perceptual hash comparison ported from photosphere-v2."""

from __future__ import annotations

from collections.abc import Iterable

from photosphere.models.database import MediaRecord

DEFAULT_SIMILARITY_THRESHOLD_PCT = 90.0


def _decode_hash_bits(raw_hash: str) -> tuple[int, int] | None:
    if raw_hash.startswith("0b"):
        bit_str = raw_hash[2:]
        if not bit_str:
            return None
        return int(bit_str, 2), len(bit_str)
    if not raw_hash:
        return None
    return int(raw_hash, 16), len(raw_hash) * 4


def _similarity_from_decoded(
    int_1: int,
    int_2: int,
    total_bits: int,
) -> tuple[int, float, float]:
    """Compute (bit_distance, distance_pct, similarity_pct) from decoded bit ints."""
    raw_distance = (int_1 ^ int_2).bit_count()
    distance_pct = (raw_distance / total_bits) * 100.0 if total_bits else 0.0
    similarity_pct = 100.0 - distance_pct
    return raw_distance, distance_pct, similarity_pct


def hamming_distance_percentage(
    hash1: str | None,
    hash2: str | None,
) -> tuple[int, float, float]:
    """Return (bit_distance, distance_pct, similarity_pct) for two hashes."""
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        fallback_bits = max(len(hash1 or ""), len(hash2 or "")) * 4
        return fallback_bits, 100.0, 0.0

    if hash1.startswith("0b") != hash2.startswith("0b"):
        return len(hash1) * 4, 100.0, 0.0

    try:
        decoded_1 = _decode_hash_bits(hash1)
        decoded_2 = _decode_hash_bits(hash2)
    except ValueError:
        return len(hash1) * 4, 100.0, 0.0

    if decoded_1 is None or decoded_2 is None:
        return 0, 100.0, 0.0

    int_1, total_bits = decoded_1
    int_2, _ = decoded_2
    return _similarity_from_decoded(int_1, int_2, total_bits)


def find_similar_annotated_record(
    average_hash: str | None,
    records: Iterable[MediaRecord],
    threshold_pct: float = DEFAULT_SIMILARITY_THRESHOLD_PCT,
) -> MediaRecord | None:
    """Return the closest annotated record meeting similarity threshold, if any."""
    if not average_hash:
        return None
    try:
        target_decoded = _decode_hash_bits(average_hash)
    except ValueError:
        return None
    if target_decoded is None:
        return None

    target_int, total_bits = target_decoded
    target_len = len(average_hash)
    is_binary = average_hash.startswith("0b")

    best_match: MediaRecord | None = None
    best_similarity = threshold_pct
    for record in records:
        cand = record.average_hash
        has_annotations = bool(record.label_indexes or record.caption_index is not None)
        if (
            not cand
            or not has_annotations
            or len(cand) != target_len
            or cand.startswith("0b") != is_binary
        ):
            continue
        try:
            cand_decoded = _decode_hash_bits(cand)
        except ValueError:
            continue
        if cand_decoded is None:
            continue
        cand_int, _ = cand_decoded
        _, _, similarity = _similarity_from_decoded(target_int, cand_int, total_bits)
        if similarity >= best_similarity:
            best_similarity = similarity
            best_match = record
    return best_match


class PerceptualHashIndex:
    """In-memory index of pre-decoded annotated perceptual hashes."""

    def __init__(self) -> None:
        self._entries: list[tuple[int, int, int, bool, MediaRecord]] = []

    @classmethod
    def from_records(cls, records: Iterable[MediaRecord]) -> PerceptualHashIndex:
        """Build an index from an iterable of existing MediaRecord items."""
        index = cls()
        for record in records:
            index.add(record)
        return index

    def add(self, record: MediaRecord) -> None:
        """Decode and store an annotated record's average_hash if valid."""
        cand = record.average_hash
        has_annotations = bool(record.label_indexes or record.caption_index is not None)
        if not cand or not has_annotations:
            return
        try:
            decoded = _decode_hash_bits(cand)
        except ValueError:
            return
        if decoded is None:
            return
        cand_int, total_bits = decoded
        self._entries.append(
            (cand_int, total_bits, len(cand), cand.startswith("0b"), record)
        )

    def find_similar(
        self,
        average_hash: str | None,
        threshold_pct: float = DEFAULT_SIMILARITY_THRESHOLD_PCT,
    ) -> MediaRecord | None:
        """Return the closest annotated record meeting similarity threshold, if any."""
        if not average_hash:
            return None
        try:
            target_decoded = _decode_hash_bits(average_hash)
        except ValueError:
            return None
        if target_decoded is None:
            return None

        target_int, total_bits = target_decoded
        target_len = len(average_hash)
        is_binary = average_hash.startswith("0b")

        best_match: MediaRecord | None = None
        best_similarity = threshold_pct
        for cand_int, _, cand_len, cand_is_binary, record in self._entries:
            if cand_len != target_len or cand_is_binary != is_binary:
                continue
            _, _, similarity = _similarity_from_decoded(
                target_int, cand_int, total_bits
            )
            if similarity >= best_similarity:
                best_similarity = similarity
                best_match = record
        return best_match
