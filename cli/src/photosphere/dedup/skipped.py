"""Collision-safe isolation of unsupported and duplicate files into skipped/."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from photosphere.models.database import SkippedEntry, SkippedManifest

SkipReason = Literal[
    "duplicate_sha1",
    "unsupported_extension",
    "processing_error",
    "target_key_collision",
]


class SkippedManager:
    """Moves rejected/duplicate files into skipped/ and logs skipped_manifest.json."""

    def __init__(self, skipped_dir: Path, manifest_path: Path | None = None) -> None:
        self.skipped_dir = skipped_dir
        self.manifest_path = manifest_path or (skipped_dir / "skipped_manifest.json")
        self.skipped_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> SkippedManifest:
        if not self.manifest_path.exists():
            return SkippedManifest()
        raw = self.manifest_path.read_text(encoding="utf-8")
        return SkippedManifest.model_validate_json(raw)

    def _resolve_unique_destination(
        self, source_path: Path, source_root: Path | None
    ) -> Path:
        if source_root is not None:
            try:
                rel = source_path.resolve().relative_to(source_root.resolve())
            except ValueError:
                rel = Path(source_path.name)
        else:
            rel = Path(source_path.name)

        candidate = self.skipped_dir / rel
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if not candidate.exists():
            return candidate

        counter = 1
        while True:
            numbered = candidate.with_name(
                f"{candidate.stem}.{counter}{candidate.suffix}"
            )
            if not numbered.exists():
                return numbered
            counter += 1

    def move_to_skipped(
        self,
        source_path: Path,
        reason: SkipReason,
        sha1: str,
        average_hash: str | None = None,
        source_root: Path | None = None,
    ) -> SkippedEntry:
        """Move source_path into skipped/ safely and record audit entry."""
        destination = self._resolve_unique_destination(source_path, source_root)
        shutil.move(str(source_path), str(destination))
        entry = SkippedEntry(
            source_path=str(source_path),
            skipped_path=str(destination),
            reason=reason,
            sha1=sha1,
            average_hash=average_hash,
            moved_at=datetime.now(UTC).isoformat(),
        )
        self.manifest.entries.append(entry)
        self.flush()
        return entry

    def flush(self) -> None:
        """Atomically persist skipped_manifest.json to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.manifest_path.with_suffix(".json.tmp")
        payload = json.dumps(self.manifest.model_dump(mode="json"), indent=2)
        tmp_path.write_text(payload + "\n", encoding="utf-8")
        tmp_path.replace(self.manifest_path)
