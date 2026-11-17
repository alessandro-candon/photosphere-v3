"""Shared fixtures for photosphere CLI unit and pipeline tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from photosphere.ai.protocol import MediaAnnotation
from photosphere.ai.translator import EasyNMTTranslator
from photosphere.config import PhotosphereSettings

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"


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
