"""Vision AI provider protocol and compute device/dtype resolution."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class AINotConfiguredError(RuntimeError):
    """Raised when AI inference runs without [ai] extras or backend."""


class AIInferenceError(RuntimeError):
    """Raised when per-item AI inference fails and may be retried or skipped."""


class MediaAnnotation(BaseModel):
    """Normalized output from any image tagging/captioning provider."""

    labels: list[str] = Field(default_factory=list)
    caption: str | None = None


@runtime_checkable
class AIProvider(Protocol):
    """Protocol implemented by local vision models (e.g. Moondream2)."""

    def analyze(self, image_path: Path) -> MediaAnnotation:
        """Return tags and a natural-language caption for a thumbnail or image."""
        ...


def resolve_device(preferred: str = "auto") -> str:
    """Resolve compute device without requiring torch for core CLI runs."""
    if preferred in {"cuda", "mps", "cpu"}:
        return preferred
    try:
        torch = importlib.import_module("torch")
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        return "cpu"
    return "cpu"


def resolve_dtype(device: str) -> str:
    """Resolve optimal floating-point dtype name for the given compute device."""
    if device == "mps":
        return "bfloat16"
    if device == "cuda":
        try:
            torch = importlib.import_module("torch")
            if (
                hasattr(torch.cuda, "is_bf16_supported")
                and torch.cuda.is_bf16_supported()
            ):
                return "bfloat16"
        except ImportError:
            pass
        return "float16"
    return "bfloat16"


def empty_device_cache(device: str | None = None) -> None:
    """Release unused accelerator cache memory when running on MPS or CUDA."""
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return
    target = device or resolve_device("auto")
    if target == "mps" and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
        torch.mps.empty_cache()
    elif target == "cuda" and torch.cuda.is_available():
        torch.cuda.empty_cache()


def load_optional_ai_provider(
    device: str = "auto",
    *,
    cache_dir: Path | None = None,
    max_image_size: int = 1024,
    provider_mode: Literal["local", "remote"] = "local",
    api_url: str | None = None,
    api_key: str | None = None,
    api_timeout: float = 60.0,
) -> AIProvider:
    """Instantiate either the remote Moondream HTTP provider or local Moondream2."""
    if provider_mode == "remote":
        from photosphere.ai.remote import (
            DEFAULT_MOONDREAM_API_URL,
            RemoteMoondreamProvider,
        )

        return RemoteMoondreamProvider(
            api_url=api_url or DEFAULT_MOONDREAM_API_URL,
            api_key=api_key or "",
            max_image_size=max_image_size,
            timeout=api_timeout,
        )

    resolved = resolve_device(device)
    try:
        importlib.import_module("torch")
        importlib.import_module("transformers")
        importlib.import_module("einops")
    except ImportError as exc:
        raise AINotConfiguredError(
            "Vision AI extras are not installed. Re-run with `--no-ai`, use "
            "`--ai-provider remote`, or install optional dependencies via "
            "`uv sync --extra ai`."
        ) from exc

    if resolved == "cpu":
        logger.warning(
            "ai_cpu_fallback",
            device=resolved,
            dtype=resolve_dtype(resolved),
            message=(
                "CPU-only Moondream2 inference is very slow (~10+ min per photo). "
                "Use macOS MPS, CUDA, `--ai-provider remote` "
                "(Cloud Run / Moondream API), or `--no-ai`."
            ),
        )

    from photosphere.ai.moondream2 import Moondream2Provider

    return Moondream2Provider(
        device=resolved,
        cache_dir=cache_dir,
        max_image_size=max_image_size,
    )


def release_ai_provider(provider: AIProvider | None) -> None:
    """Release model weights if the provider implements a release() hook."""
    if provider is None:
        return
    release_fn = getattr(provider, "release", None)
    if callable(release_fn):
        release_fn()


def analyze_with_retry(
    provider: AIProvider,
    image_path: Path,
    *,
    max_retries: int = 1,
    device: str | None = None,
    sha1: str | None = None,
    file_type: str | None = None,
) -> tuple[MediaAnnotation | None, int]:
    """Run AIProvider.analyze with bounded retries on AIInferenceError.

    AINotConfiguredError propagates immediately. Returns (None, retries_used)
    when all attempts fail with AIInferenceError.
    """
    attempts = max(0, max_retries) + 1
    retries_used = 0
    for attempt in range(1, attempts + 1):
        try:
            return provider.analyze(image_path), retries_used
        except AIInferenceError as exc:
            if attempt < attempts:
                retries_used += 1
                logger.warning(
                    "ai_inference_retry",
                    sha1=sha1,
                    image_path=str(image_path),
                    file_type=file_type,
                    attempt=attempt,
                    max_attempts=attempts,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                empty_device_cache(device)
            else:
                logger.error(
                    "ai_inference_failed",
                    sha1=sha1,
                    image_path=str(image_path),
                    file_type=file_type,
                    attempts=attempts,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
    return None, retries_used
