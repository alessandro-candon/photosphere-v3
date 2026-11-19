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

        def to(self, device: str | None = None, dtype: Any = None) -> StrictDtypeModel:
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


def test_default_cache_dir_uses_home_photosphere_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from photosphere.config import PhotosphereSettings

    monkeypatch.delenv("PHOTOSPHERE_CACHE_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_AI_OFFLINE", raising=False)
    settings = PhotosphereSettings()
    assert settings.cache_dir == Path.home() / ".photosphere" / "cache"
    assert settings.ai_offline is False

    custom_cache = tmp_path / "custom-cache"
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(custom_cache))
    monkeypatch.setenv("PHOTOSPHERE_AI_OFFLINE", "1")
    overridden = PhotosphereSettings()
    assert overridden.cache_dir == custom_cache
    assert overridden.ai_offline is True


def test_configure_hf_cache_env_and_offline_local_files_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import os

    from photosphere.ai.protocol import configure_hf_cache_env

    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HF_MODULES_CACHE", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    hf_dir = tmp_path / "cache" / "huggingface"
    configure_hf_cache_env(hf_dir, offline=True)
    assert os.environ["HF_HOME"] == str(hf_dir)
    assert os.environ["HF_HUB_CACHE"] == str(hf_dir / "hub")
    assert os.environ["HF_MODULES_CACHE"] == str(hf_dir / "modules")
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert (hf_dir / "hub").is_dir()
    assert (hf_dir / "modules").is_dir()

    local_tok_dir = (
        hf_dir
        / "models--moondream--starmie-v1"
        / "snapshots"
        / MOONDREAM2_TOKENIZER_REVISION
    )
    local_tok_dir.mkdir(parents=True)

    calls = _install_fake_torch_and_transformers(monkeypatch)
    provider = Moondream2Provider(
        device="cpu", cache_dir=tmp_path / "cache", offline=True
    )
    img_path = create_sample_rgba_png(tmp_path / "offline.png", size=(300, 300))
    ann = provider.analyze(img_path)
    assert ann.labels
    assert calls["tok_id"] == str(local_tok_dir)
    assert calls["tok_kwargs"]["local_files_only"] is True
    assert calls["model_kwargs"]["local_files_only"] is True


def test_translator_offline_flag_and_error_wrapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from photosphere.ai.translator import EasyNMTTranslator

    fake_torch = ModuleType("torch")
    fake_torch.cuda = SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    fake_torch.backends = SimpleNamespace(  # type: ignore[attr-defined]
        mps=SimpleNamespace(is_available=lambda: False)
    )
    fake_transformers = ModuleType("transformers")

    seen: dict[str, Any] = {}

    class FailingTokenizer:
        @staticmethod
        def from_pretrained(model_id: str, **kwargs: Any) -> Any:
            seen["model_id"] = model_id
            seen["kwargs"] = kwargs
            raise OSError("CERTIFICATE_VERIFY_FAILED contacting huggingface.co")

    fake_transformers.MarianTokenizer = FailingTokenizer  # type: ignore[attr-defined]
    fake_transformers.MarianMTModel = FailingTokenizer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    translator = EasyNMTTranslator(tmp_path / "easynmt", offline=True)
    with pytest.raises(AINotConfiguredError, match="Offline mode is enabled"):
        translator.prefetch("it")
    assert seen["model_id"] == "Helsinki-NLP/opus-mt-en-it"
    assert seen["kwargs"]["local_files_only"] is True


def test_doctor_reports_cached_models_and_offline_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import json

    from click.testing import CliRunner

    from photosphere.main import cli

    cache_dir = tmp_path / "cache"
    (cache_dir / "huggingface" / "models--vikhyatk--moondream2").mkdir(parents=True)
    (cache_dir / "huggingface" / "models--moondream--starmie-v1").mkdir(parents=True)
    (cache_dir / "huggingface" / "modules" / "transformers_modules").mkdir(parents=True)
    (cache_dir / "easynmt" / "models--Helsinki-NLP--opus-mt-en-it").mkdir(parents=True)

    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("PHOTOSPHERE_AI_OFFLINE", "1")
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    payload = json.loads(result.output)
    assert payload["cache_dir"] == str(cache_dir)
    assert payload["ai_offline"] is True
    assert payload["cached_models"] == {
        "moondream2": True,
        "moondream2_tokenizer": True,
        "moondream2_modules": True,
        "easynmt_models": ["models--Helsinki-NLP--opus-mt-en-it"],
    }
