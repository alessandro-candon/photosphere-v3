"""Local write-ahead NDJSON checkpoint for crash-safe batch ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from photosphere.config import RoutingMode


class CheckpointModeMismatchError(RuntimeError):
    """Raised when resuming a checkpoint created under a different routing_mode."""


class CheckpointEntry(BaseModel):
    """Completed item recorded in ingest_checkpoint.ndjson."""

    sha1: str
    routing_mode: RoutingMode = "chronological"
    source_bucket_uri: str
    thumbnail_bucket_uri: str | None = None
    label_indexes: list[int] = Field(default_factory=list)
    caption_index: int | None = None
    recorded_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CheckpointStore:
    """Append-only NDJSON log used to skip already-uploaded files after interruption."""

    def __init__(self, checkpoint_path: Path) -> None:
        self.checkpoint_path = checkpoint_path
        self.entries: dict[str, CheckpointEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.checkpoint_path.exists():
            return
        for raw_line in self.checkpoint_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            entry = CheckpointEntry.model_validate_json(line)
            self.entries[entry.sha1] = entry

    def validate_routing_mode(self, routing_mode: RoutingMode) -> None:
        """Fail fast if existing checkpoint entries were recorded under another mode."""
        mismatched = {
            entry.routing_mode
            for entry in self.entries.values()
            if entry.routing_mode != routing_mode
        }
        if mismatched:
            modes = ", ".join(sorted(mismatched))
            raise CheckpointModeMismatchError(
                f"Existing checkpoint {self.checkpoint_path} uses "
                f"routing_mode={modes}, "
                f"which conflicts with --routing-mode {routing_mode}. "
                "Resume with the matching mode or remove the checkpoint file."
            )

    def is_completed(self, sha1: str) -> bool:
        """Return True if SHA-1 hash is already recorded in checkpoint."""
        return sha1 in self.entries

    def record(self, entry: CheckpointEntry) -> None:
        """Append a completed entry to the NDJSON log and flush to disk."""
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with self.checkpoint_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")
            handle.flush()
        self.entries[entry.sha1] = entry

    def clear(self) -> None:
        """Remove checkpoint file after databases are committed to GCS."""
        self.entries.clear()
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
