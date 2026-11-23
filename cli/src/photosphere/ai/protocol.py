"""Vision AI provider protocol and compute device/dtype resolution."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any, Literal, Protocol, cast, runtime_checkable

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


def resolve_dtype(device: str, preferred: str = "auto") -> str:
    """Resolve optimal floating-point dtype name for the given compute device."""
    if preferred in {"float16", "bfloat16", "float32"}:
        return preferred
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


def configure_hf_cache_env(hf_cache_dir: Path | None, *, offline: bool = False) -> None:
    """Configure Hugging Face cache and offline env vars before transformers import."""
    if hf_cache_dir is not None:
        hf_cache_dir.mkdir(parents=True, exist_ok=True)
        hub_dir = hf_cache_dir / "hub"
        hub_dir.mkdir(parents=True, exist_ok=True)
        modules_dir = hf_cache_dir / "modules"
        modules_dir.mkdir(parents=True, exist_ok=True)
        if offline:
            os.environ["HF_HOME"] = str(hf_cache_dir)
            os.environ["HF_HUB_CACHE"] = str(hub_dir)
            os.environ["HF_MODULES_CACHE"] = str(modules_dir)
        else:
            os.environ.setdefault("HF_HOME", str(hf_cache_dir))
            os.environ.setdefault("HF_HUB_CACHE", str(hub_dir))
            os.environ.setdefault("HF_MODULES_CACHE", str(modules_dir))
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"


def format_hf_load_hint(
    exc: Exception, *, cache_dir: Path | None, offline: bool
) -> str:
    """Return offline/cache guidance when Hugging Face model loading fails."""
    text = str(exc)
    is_network_or_tls = any(
        marker in text
        for marker in (
            "CERTIFICATE_VERIFY_FAILED",
            "SSLError",
            "huggingface.co",
            "ConnectionError",
            "MaxRetryError",
        )
    )
    cache_hint = str(cache_dir) if cache_dir is not None else "~/.photosphere/cache"
    if offline:
        return (
            f" Offline mode is enabled (`--offline` / `PHOTOSPHERE_AI_OFFLINE=1`); "
            f"ensure the model cache is present under `{cache_hint}` "
            f"(run `photosphere prefetch-models` on a machine with Hugging Face access "
            f"and copy the cache directory)."
        )
    if is_network_or_tls:
        return (
            f" If `huggingface.co` is blocked on this network, run "
            f"`photosphere prefetch-models` on a machine with access, copy "
            f"`~/.photosphere/cache` into `{cache_hint}`, and re-run with `--offline`."
        )
    return ""


def load_optional_ai_provider(
    device: str = "auto",
    *,
    dtype: str = "auto",
    cache_dir: Path | None = None,
    max_image_size: int = 378,
    provider_mode: Literal["local", "remote"] = "local",
    api_url: str | None = None,
    api_key: str | None = None,
    api_timeout: float = 60.0,
    offline: bool = False,
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

    hf_cache_dir = (cache_dir / "huggingface") if cache_dir is not None else None
    configure_hf_cache_env(hf_cache_dir, offline=offline)

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
            dtype=resolve_dtype(resolved, preferred=dtype),
            message=(
                "CPU-only Moondream2 inference is very slow (~10+ min per photo). "
                "Use macOS MPS, CUDA, `--ai-provider remote` "
                "(Cloud Run / Moondream API), or `--no-ai`."
            ),
        )

    from photosphere.ai.moondream2 import Moondream2Provider

    return Moondream2Provider(
        device=resolved,
        dtype=dtype,
        cache_dir=cache_dir,
        max_image_size=max_image_size,
        offline=offline,
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
    image: object | None = None,
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
    analyze_image_fn = (
        getattr(provider, "analyze_image", None) if image is not None else None
    )
    use_in_memory = image is not None and callable(analyze_image_fn)
    for attempt in range(1, attempts + 1):
        try:
            if use_in_memory and callable(analyze_image_fn):
                result = cast(
                    MediaAnnotation,
                    cast(Any, analyze_image_fn)(image, source_label=str(image_path)),
                )
                return result, retries_used
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
