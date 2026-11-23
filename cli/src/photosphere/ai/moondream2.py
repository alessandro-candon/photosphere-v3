"""Moondream2 local vision AI provider for image captioning and tagging."""

from __future__ import annotations

import gc
import importlib
import time
from pathlib import Path
from typing import Any

import structlog
from PIL import Image

from photosphere.ai.normalize import normalize_caption, parse_tags_response
from photosphere.ai.protocol import (
    AIInferenceError,
    AINotConfiguredError,
    MediaAnnotation,
    configure_hf_cache_env,
    empty_device_cache,
    format_hf_load_hint,
    resolve_device,
    resolve_dtype,
)
from photosphere.media.image import load_capped_rgb_image

logger = structlog.get_logger(__name__)

MOONDREAM2_MODEL_ID = "vikhyatk/moondream2"
MOONDREAM2_REVISION = "2025-06-21"
MOONDREAM2_COMMIT_SHA = "9a7d4024050840e001defacec2b00727e89149e6"
MOONDREAM2_TOKENIZER_ID = "moondream/starmie-v1"
MOONDREAM2_TOKENIZER_REVISION = "35192e10a54e36eabe0a7cc57a2c1aab371cafc5"

TAGS_PROMPT = (
    "Return 3 to 5 concise (1-2 word) descriptive tags for this image "
    "as a JSON array of strings, with no extra text."
)
CAPTION_SETTINGS: dict[str, Any] = {
    "max_tokens": 55,
    "temperature": 0.1,
    "top_p": 0.1,
}
TAGS_SETTINGS: dict[str, Any] = {
    "max_tokens": 35,
    "temperature": 0.3,
    "top_p": 0.2,
}
_CACHE_CLEAR_INTERVAL = 25


def moondream2_snapshot_dir(cache_dir: Path) -> Path:
    """Return the canonical local snapshot directory for pinned Moondream2."""
    return (
        cache_dir
        / "huggingface"
        / "hub"
        / "models--vikhyatk--moondream2"
        / "snapshots"
        / MOONDREAM2_COMMIT_SHA
    )


def moondream2_tokenizer_snapshot_dir(cache_dir: Path) -> Path:
    """Return the canonical local snapshot directory for the Moondream2 tokenizer."""
    return (
        cache_dir
        / "huggingface"
        / "hub"
        / "models--moondream--starmie-v1"
        / "snapshots"
        / MOONDREAM2_TOKENIZER_REVISION
    )


class Moondream2Provider:
    """Lazy-loaded Moondream2 adapter implementing the AIProvider protocol."""

    def __init__(
        self,
        device: str = "auto",
        *,
        dtype: str = "auto",
        cache_dir: Path | None = None,
        max_image_size: int = 378,
        max_tags: int = 5,
        offline: bool = False,
    ) -> None:
        self.device = resolve_device(device)
        self.dtype_name = resolve_dtype(self.device, preferred=dtype)
        self.cache_dir = (cache_dir / "huggingface") if cache_dir is not None else None
        self.max_image_size = max_image_size
        self.max_tags = max_tags
        self.offline = offline
        self._model: Any | None = None
        self._torch: Any | None = None
        self._processed_count = 0

    def _ensure_loaded(self) -> tuple[Any, Any]:
        if self._model is not None and self._torch is not None:
            return self._model, self._torch

        configure_hf_cache_env(self.cache_dir, offline=self.offline)

        try:
            torch = importlib.import_module("torch")
            transformers = importlib.import_module("transformers")
        except ImportError as exc:
            raise AINotConfiguredError(
                "Moondream2 requires `[ai]` dependencies (`uv sync --extra ai`)."
            ) from exc

        dtype = getattr(torch, self.dtype_name)
        hf_hub_cache: str | None = None
        if self.cache_dir is not None:
            hub_dir = self.cache_dir / "hub"
            hub_dir.mkdir(parents=True, exist_ok=True)
            hf_hub_cache = str(hub_dir)

        started = time.perf_counter()
        try:
            model = transformers.AutoModelForCausalLM.from_pretrained(
                MOONDREAM2_MODEL_ID,
                revision=MOONDREAM2_COMMIT_SHA,
                trust_remote_code=True,
                dtype=dtype,
                cache_dir=hf_hub_cache,
                local_files_only=self.offline,
            )
            model = model.to(device=self.device, dtype=dtype)
            model.eval()
        except Exception as exc:
            short_rev = MOONDREAM2_REVISION[:8]
            hint = format_hf_load_hint(
                exc, cache_dir=self.cache_dir, offline=self.offline
            )
            raise AINotConfiguredError(
                f"Failed to load Moondream2 "
                f"({MOONDREAM2_MODEL_ID}@{short_rev}): {exc}{hint}"
            ) from exc

        load_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "ai_provider_loaded",
            model_id=MOONDREAM2_MODEL_ID,
            revision=MOONDREAM2_REVISION,
            device=self.device,
            dtype=self.dtype_name,
            load_duration_ms=load_ms,
        )
        self._model = model
        self._torch = torch
        return model, torch

    def prefetch(self) -> None:
        """Download and verify Moondream2 weights, tokenizer, and modules in cache."""
        self._ensure_loaded()
        self.release()

    def analyze_image(
        self,
        rgb_image: Image.Image,
        *,
        source_label: str = "<in-memory>",
        decode_ms: float = 0.0,
    ) -> MediaAnnotation:
        """Generate a normalized caption and up to 5 tags from an in-memory image."""
        model, torch = self._ensure_loaded()
        started = time.perf_counter()
        try:
            with torch.inference_mode():
                t0 = time.perf_counter()
                enc_image = model.encode_image(rgb_image)
                t1 = time.perf_counter()
                caption_res: Any = model.caption(
                    enc_image, length="short", settings=CAPTION_SETTINGS
                )
                t2 = time.perf_counter()
                raw_caption: Any = (
                    caption_res.get("caption")
                    if isinstance(caption_res, dict)
                    else caption_res
                )
                tags_res: Any = model.query(
                    enc_image, TAGS_PROMPT, settings=TAGS_SETTINGS
                )
                t3 = time.perf_counter()
                raw_tags: Any = (
                    tags_res.get("answer") if isinstance(tags_res, dict) else tags_res
                )
        except Exception as exc:
            raise AIInferenceError(
                f"Moondream2 inference failed on {source_label}: {exc}"
            ) from exc
        finally:
            self._processed_count += 1
            if self._processed_count % _CACHE_CLEAR_INTERVAL == 0:
                empty_device_cache(self.device)

        caption = normalize_caption(
            str(raw_caption) if raw_caption is not None else None
        )
        labels = parse_tags_response(
            str(raw_tags) if raw_tags is not None else "",
            max_tags=self.max_tags,
        )
        if not labels and caption is None:
            raise AIInferenceError(
                f"Moondream2 returned empty caption and tags for {source_label}"
            )

        logger.debug(
            "ai_inference_completed",
            image_path=source_label,
            decode_ms=round(decode_ms, 1),
            encode_ms=round((t1 - t0) * 1000, 1),
            caption_ms=round((t2 - t1) * 1000, 1),
            tags_ms=round((t3 - t2) * 1000, 1),
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            tag_count=len(labels),
            has_caption=caption is not None,
        )
        return MediaAnnotation(labels=labels, caption=caption)

    def analyze(self, image_path: Path) -> MediaAnnotation:
        """Generate a normalized caption and up to 5 descriptive tags for an image."""
        self._ensure_loaded()
        decode_started = time.perf_counter()
        try:
            rgb_image = load_capped_rgb_image(image_path, max_size=self.max_image_size)
        except Exception as exc:
            raise AIInferenceError(
                f"Failed to decode image for AI inference ({image_path}): {exc}"
            ) from exc
        decode_ms = (time.perf_counter() - decode_started) * 1000
        try:
            return self.analyze_image(
                rgb_image, source_label=str(image_path), decode_ms=decode_ms
            )
        finally:
            rgb_image.close()

    def release(self) -> None:
        """Release model weights and free accelerator cache before translation."""
        if self._model is not None:
            self._model = None
            gc.collect()
            empty_device_cache(self.device)
