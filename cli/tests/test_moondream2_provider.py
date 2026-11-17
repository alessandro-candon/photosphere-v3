"""Unit tests for Moondream2Provider, resolve_dtype, and 1024px image loading."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from photosphere.ai.moondream2 import (
    MOONDREAM2_MODEL_ID,
    MOONDREAM2_REVISION,
    MOONDREAM2_TOKENIZER_ID,
    MOONDREAM2_TOKENIZER_REVISION,
    Moondream2Provider,
)
from photosphere.ai.protocol import (
    AIInferenceError,
    AINotConfiguredError,
    load_optional_ai_provider,
    resolve_dtype,
)
from photosphere.media.image import load_capped_rgb_image
from tests.conftest import create_sample_jpeg, create_sample_rgba_png


def test_load_capped_rgb_image_applies_exif_and_caps_max_edge(tmp_path: Path) -> None:
    # 2000x1000 with EXIF orientation 6 (90 deg CW -> 1000x2000)
    img_path = create_sample_jpeg(
        tmp_path / "portrait.jpg", size=(2000, 1000), orientation=6
    )
    loaded = load_capped_rgb_image(img_path, max_size=1024)
    assert loaded.mode == "RGB"
    assert loaded.size == (512, 1024)

    rgba_path = create_sample_rgba_png(tmp_path / "alpha.png", size=(400, 200))
    loaded_rgba = load_capped_rgb_image(rgba_path, max_size=1024)
    assert loaded_rgba.mode == "RGB"
    assert loaded_rgba.size == (400, 200)


def test_resolve_dtype_defaults() -> None:
    assert resolve_dtype("mps") == "bfloat16"
    assert resolve_dtype("cpu") == "bfloat16"


def _install_fake_torch_and_transformers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    caption_text: str = "A red car parked on a street.",
    tags_text: str = '["car", "street", "red"]',
    fail_on_answer: bool = False,
) -> dict[str, Any]:
    calls: dict[str, Any] = {"model_kwargs": None, "tok_kwargs": None, "released": 0}

    class FakeModel:
        def to(self, device: str | None = None, dtype: Any = None) -> FakeModel:
            calls["to_device"] = device
            calls["to_dtype"] = dtype
            return self

        def eval(self) -> FakeModel:
            return self

        def encode_image(self, image: Any) -> str:
            calls["encoded_size"] = image.size
            return "encoded"

        def answer_question(self, enc: str, prompt: str, tokenizer: Any) -> str:
            if fail_on_answer:
                raise RuntimeError("CUDA out of memory")
            if "JSON array" in prompt:
                return tags_text
            return caption_text

    fake_torch = ModuleType("torch")
    fake_torch.bfloat16 = "bf16"  # type: ignore[attr-defined]
    fake_torch.float16 = "f16"  # type: ignore[attr-defined]
    fake_torch.float32 = "f32"  # type: ignore[attr-defined]
    fake_torch.inference_mode = contextlib.nullcontext  # type: ignore[attr-defined]
    fake_torch.cuda = SimpleNamespace(  # type: ignore[attr-defined]
        is_available=lambda: False,
        is_bf16_supported=lambda: False,
        empty_cache=lambda: None,
    )
    fake_torch.backends = SimpleNamespace(  # type: ignore[attr-defined]
        mps=SimpleNamespace(is_available=lambda: False)
    )
    fake_torch.mps = SimpleNamespace(empty_cache=lambda: None)  # type: ignore[attr-defined]

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(model_id: str, **kwargs: Any) -> str:
            calls["tok_id"] = model_id
            calls["tok_kwargs"] = kwargs
            return "fake-tokenizer"

    class FakeAutoModel:
        @staticmethod
        def from_pretrained(model_id: str, **kwargs: Any) -> FakeModel:
            calls["model_id"] = model_id
            calls["model_kwargs"] = kwargs
            return FakeModel()

    fake_transformers = ModuleType("transformers")
    fake_transformers.AutoTokenizer = FakeAutoTokenizer  # type: ignore[attr-defined]
    fake_transformers.AutoModelForCausalLM = FakeAutoModel  # type: ignore[attr-defined]

    fake_einops = ModuleType("einops")

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "einops", fake_einops)
    return calls


def test_moondream2_provider_pins_revisions_and_normalizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _install_fake_torch_and_transformers(monkeypatch)
    img_path = create_sample_jpeg(tmp_path / "photo.jpg", size=(1600, 800))

    provider = load_optional_ai_provider("cpu", cache_dir=tmp_path / "cache")
    assert isinstance(provider, Moondream2Provider)

    ann = provider.analyze(img_path)
    assert ann.caption == "A red car parked on a street."
    assert ann.labels == ["car", "street", "red"]
    assert calls["model_id"] == MOONDREAM2_MODEL_ID
    assert calls["model_kwargs"]["revision"] == MOONDREAM2_REVISION
    assert calls["model_kwargs"]["trust_remote_code"] is True
    assert calls["tok_id"] == MOONDREAM2_TOKENIZER_ID
    assert calls["tok_kwargs"]["revision"] == MOONDREAM2_TOKENIZER_REVISION
    assert calls["encoded_size"] == (1024, 512)

    provider.release()
    assert provider._model is None


def test_moondream2_provider_raises_inference_error_on_runtime_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_torch_and_transformers(monkeypatch, fail_on_answer=True)
    img_path = create_sample_jpeg(tmp_path / "photo.jpg")
    provider = Moondream2Provider(device="cpu", cache_dir=tmp_path / "cache")
    with pytest.raises(AIInferenceError, match="Moondream2 inference failed"):
        provider.analyze(img_path)


def test_load_optional_ai_provider_missing_extras_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    real_import = importlib.import_module

    def fake_import(name: str, package: str | None = None) -> Any:
        if name in {"torch", "transformers", "einops"}:
            raise ImportError(name)
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    with pytest.raises(AINotConfiguredError, match="uv sync --extra ai"):
        load_optional_ai_provider("cpu")


def test_moondream2_provider_cpu_matches_bfloat16_vision_crops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reproduce mat1/mat2 dtype mismatch when moondream2 vision crops are bfloat16."""
    calls = _install_fake_torch_and_transformers(monkeypatch)
    fake_transformers = sys.modules["transformers"]

    class StrictDtypeModel:
        def __init__(self) -> None:
            self.weight_dtype = "bf16"

        def to(
            self, device: str | None = None, dtype: Any = None
        ) -> StrictDtypeModel:
            calls["to_device"] = device
            calls["to_dtype"] = dtype
            if dtype is not None:
                self.weight_dtype = dtype
            return self

        def eval(self) -> StrictDtypeModel:
            return self

        def encode_image(self, image: Any) -> str:
            # vikhyatk/moondream2's vision.prepare_crops hardcodes torch.bfloat16
            if self.weight_dtype != "bf16":
                raise RuntimeError(
                    "mat1 and mat2 must have the same dtype, but got BFloat16 and Float"
                )
            return "encoded"

        def answer_question(self, enc: str, prompt: str, tokenizer: Any) -> str:
            if "JSON array" in prompt:
                return '["bust", "marble", "sculpture"]'
            return "A marble bust of Victor Hugo."

    class StrictAutoModel:
        @staticmethod
        def from_pretrained(model_id: str, **kwargs: Any) -> StrictDtypeModel:
            return StrictDtypeModel()

    monkeypatch.setattr(fake_transformers, "AutoModelForCausalLM", StrictAutoModel)

    img_path = create_sample_rgba_png(tmp_path / "Victor_Hugo.png", size=(400, 400))
    provider = Moondream2Provider(device="cpu", cache_dir=tmp_path / "cache")
    ann = provider.analyze(img_path)
    assert ann.caption == "A marble bust of Victor Hugo."
    assert ann.labels == ["bust", "marble", "sculpture"]
