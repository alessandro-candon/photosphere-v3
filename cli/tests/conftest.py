"""Shared fixtures for photosphere CLI unit and pipeline tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from photosphere.ai.protocol import MediaAnnotation
from photosphere.ai.translator import EasyNMTTranslator
from photosphere.config import PhotosphereSettings
from photosphere.storage.gcs_client import GCSStorageClient, StorageSyncError

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"


class FakeBlob:
    """In-memory GCS blob supporting generation checks and JSON/bytes I/O."""

    def __init__(self, bucket: FakeBucket, name: str) -> None:
        self._bucket = bucket
        self.name = name
        self.generation: int | None = bucket.generations.get(name)

    def reload(self) -> None:
        from google.api_core.exceptions import NotFound

        if self.name not in self._bucket.objects:
            raise NotFound(self.name)
        self.generation = self._bucket.generations[self.name]

    def download_as_text(self, encoding: str = "utf-8") -> str:
        from google.api_core.exceptions import NotFound

        if self.name not in self._bucket.objects:
            raise NotFound(self.name)
        return self._bucket.objects[self.name].decode(encoding)

    def download_to_filename(self, filename: str) -> None:
        from google.api_core.exceptions import NotFound

        if self.name not in self._bucket.objects:
            raise NotFound(self.name)
        Path(filename).write_bytes(self._bucket.objects[self.name])

    def upload_from_filename(
        self,
        filename: str,
        content_type: str | None = None,
        if_generation_match: int | None = None,
    ) -> None:
        _ = content_type
        self._check_generation(if_generation_match)
        self._bucket.objects[self.name] = Path(filename).read_bytes()
        self._bump_generation()

    def upload_from_string(
        self,
        data: str | bytes,
        content_type: str | None = None,
        if_generation_match: int | None = None,
    ) -> None:
        _ = content_type
        self._check_generation(if_generation_match)
        raw = data.encode("utf-8") if isinstance(data, str) else data
        self._bucket.objects[self.name] = raw
        self._bump_generation()

    def _check_generation(self, if_generation_match: int | None) -> None:
        current_gen = self._bucket.generations.get(self.name)
        if if_generation_match is not None:
            if if_generation_match == 0 and current_gen is not None:
                raise StorageSyncError(f"Precondition failed on {self.name}")
            if if_generation_match != 0 and current_gen != if_generation_match:
                raise StorageSyncError(f"Generation mismatch on {self.name}")

    def _bump_generation(self) -> None:
        current_gen = self._bucket.generations.get(self.name)
        new_gen = (current_gen or 0) + 1
        self._bucket.generations[self.name] = new_gen
        self.generation = new_gen


class FakeBucket:
    """In-memory GCS bucket."""

    def __init__(self, storage_class: str) -> None:
        self.storage_class = storage_class
        self.objects: dict[str, bytes] = {}
        self.generations: dict[str, int] = {}

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)


class FakeClient:
    """In-memory GCS client."""

    def __init__(self, buckets: dict[str, FakeBucket]) -> None:
        self._buckets = buckets

    def bucket(self, name: str) -> FakeBucket:
        return self._buckets[name]

    def get_bucket(self, name: str) -> FakeBucket:
        return self._buckets[name]


def make_gcs(
    media_class: str = "ARCHIVE", data_class: str = "STANDARD"
) -> tuple[GCSStorageClient, FakeBucket, FakeBucket]:
    """Build an isolated GCSStorageClient backed by in-memory FakeBuckets."""
    media_bkt = FakeBucket(media_class)
    data_bkt = FakeBucket(data_class)
    raw_client: Any = FakeClient(
        {
            "test-media-archive": media_bkt,
            "test-data-standard": data_bkt,
        }
    )
    return GCSStorageClient(client=raw_client), media_bkt, data_bkt


class FakeAIProvider:
    """Deterministic fake vision model implementing AIProvider Protocol."""

    def __init__(
        self, labels: list[str] | None = None, caption: str | None = None
    ) -> None:
        self.calls: list[Path] = []
        self._labels = labels or ["landscape", "outdoor"]
        self._caption = caption or "A colorful synthetic test frame."

    def analyze(self, image_path: Path) -> MediaAnnotation:
        self.calls.append(image_path)
        return MediaAnnotation(labels=list(self._labels), caption=self._caption)


def create_sample_jpeg(
    path: Path,
    size: tuple[int, int] = (640, 480),
    color: tuple[int, int, int] = (20, 120, 200),
    *,
    orientation: int | None = None,
) -> Path:
    """Create a synthetic RGB JPEG with optional EXIF Orientation tag."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=color)
    exif = img.getexif()
    if orientation is not None:
        exif[274] = orientation  # Orientation tag
    img.save(path, format="JPEG", exif=exif)
    return path


def create_sample_rgba_png(
    path: Path,
    size: tuple[int, int] = (800, 400),
    color: tuple[int, int, int, int] = (200, 40, 40, 128),
) -> Path:
    """Create a synthetic RGBA PNG image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", size, color=color)
    img.save(path, format="PNG")
    return path


def create_sample_mp4(path: Path, size: str = "640x480") -> Path | None:
    """Create a tiny 1-second solid-color MP4 video using ffmpeg when available."""
    if shutil.which("ffmpeg") is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=blue:s={size}:d=0.5",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    res = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if res.returncode != 0 or not path.exists():
        return None
    return path


@pytest.fixture
def cli_settings(tmp_path: Path) -> PhotosphereSettings:
    """Return isolated PhotosphereSettings writing to tmp_path."""
    return PhotosphereSettings(
        media_bucket="test-media-archive",
        media_storage_class="ARCHIVE",
        data_bucket="test-data-standard",
        data_storage_class="STANDARD",
        skipped_dir=tmp_path / "skipped",
        cache_dir=tmp_path / "cache",
        target_lang="it",
        device="cpu",
    )


@pytest.fixture
def fake_translator(tmp_path: Path) -> EasyNMTTranslator:
    """Return deterministic offline EasyNMTTranslator for tests."""
    return EasyNMTTranslator(
        cache_dir=tmp_path / "easynmt",
        translator_fn=lambda text, lang: f"[{lang}] {text}",
    )
