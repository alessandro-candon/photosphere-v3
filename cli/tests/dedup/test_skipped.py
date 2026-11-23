"""Unit tests for photosphere.dedup.skipped."""

from __future__ import annotations

import json
from pathlib import Path

from photosphere.dedup.skipped import SkippedManager
from photosphere.media.base import compute_sha1
from tests.conftest import create_sample_jpeg


def test_skipped_manager_moves_collision_safely_and_logs_manifest(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "staging"
    skipped_dir = tmp_path / "skipped"
    f1 = create_sample_jpeg(source_root / "nested" / "photo.jpg")
    f2 = create_sample_jpeg(source_root / "nested" / "photo.2.copy.jpg")
    f2_renamed = source_root / "nested" / "photo.jpg"

    mgr = SkippedManager(skipped_dir)
    entry1 = mgr.move_to_skipped(
        f1, reason="duplicate_sha1", sha1=compute_sha1(f1), source_root=source_root
    )
    assert not f1.exists()
    assert Path(entry1.skipped_path).exists()

    f2.rename(f2_renamed)
    entry2 = mgr.move_to_skipped(
        f2_renamed,
        reason="processing_error",
        sha1=compute_sha1(f2_renamed),
        source_root=source_root,
    )
    assert Path(entry2.skipped_path).exists()
    assert entry1.skipped_path != entry2.skipped_path
    assert entry2.reason == "processing_error"

    # Re-opening SkippedManager reloads existing manifest entries from disk.
    reopened = SkippedManager(skipped_dir)
    assert len(reopened.manifest.entries) == 2

    manifest_raw = json.loads(
        (skipped_dir / "skipped_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest_raw["entries"]) == 2
