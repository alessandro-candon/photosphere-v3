"""Unit tests for photosphere.storage.checkpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from photosphere.storage.checkpoint import (
    CheckpointEntry,
    CheckpointModeMismatchError,
    CheckpointStore,
)


def test_checkpoint_store_survives_trailing_truncated_line(tmp_path: Path) -> None:
    cp_path = tmp_path / "ingest_checkpoint.ndjson"
    store = CheckpointStore(cp_path)
    entry = CheckpointEntry(
        sha1="a" * 40,
        routing_mode="chronological",
        source_bucket_uri="gs://media/2024/01/01/a.jpg",
    )
    store.record(entry)
    # Append a truncated trailing line simulating power loss mid-write.
    with cp_path.open("a", encoding="utf-8") as handle:
        handle.write('{"sha1": "partial-truncated\n')

    reloaded = CheckpointStore(cp_path)
    assert reloaded.is_completed("a" * 40)
    assert len(reloaded.entries) == 1


def test_checkpoint_store_fails_fast_on_mid_file_corruption(tmp_path: Path) -> None:
    cp_path = tmp_path / "ingest_checkpoint.ndjson"
    valid_line = CheckpointEntry(
        sha1="b" * 40,
        routing_mode="chronological",
        source_bucket_uri="gs://media/2024/01/01/b.jpg",
    ).model_dump_json()
    cp_path.write_text(
        f'{{"sha1":"corrupt-mid-line"}}\n{valid_line}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        CheckpointStore(cp_path)


def test_checkpoint_store_validates_routing_mode_and_clears(tmp_path: Path) -> None:
    cp_path = tmp_path / "ingest_checkpoint.ndjson"
    store = CheckpointStore(cp_path)
    store.record(
        CheckpointEntry(
            sha1="c" * 40,
            routing_mode="preserve",
            source_bucket_uri="gs://media/album/c.jpg",
        )
    )
    with pytest.raises(CheckpointModeMismatchError, match="preserve"):
        store.validate_routing_mode("chronological")

    store.clear()
    assert not cp_path.exists()
    assert not store.entries
