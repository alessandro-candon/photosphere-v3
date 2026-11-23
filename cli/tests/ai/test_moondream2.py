"""Unit tests for photosphere.ai.moondream2."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from photosphere.ai.moondream2 import (
    MOONDREAM2_COMMIT_SHA,
    MOONDREAM2_MODEL_ID,
    MOONDREAM2_REVISION,
    Moondream2Provider,
)
from photosphere.ai.protocol import (
    AIInferenceError,
    load_optional_ai_provider,
)
from tests.conftest import create_sample_jpeg, create_sample_rgba_png


def _install_fake_torch_and_transformers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    raise_on_answer: bool = False,
) -> dict[str, Any]:
    calls: dict[str, Any] = {}

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

        def caption(
            self,
            enc: str,
            *,
            length: str = "normal",
            settings: dict[str, Any] | None = None,
        ) -> dict[str, str]:
            _ = enc
            calls["caption_length"] = length
            calls["caption_settings"] = settings
            if raise_on_answer:
                raise RuntimeError("MPS OOM")
            return {"caption": "A red car parked on a street."}

        def query(
            self,
            enc: str,
            prompt: str,
            *,
            settings: dict[str, Any] | None = None,
        ) -> dict[str, str]:
            _ = enc
            calls["tags_settings"] = settings
            if raise_on_answer:
                raise RuntimeError("MPS OOM")
            assert "JSON array" in prompt
            return {"answer": '["car", "street", "red"]'}

    fake_torch = ModuleType("torch")
    fake_torch.float16 = "fp16"  # type: ignore[attr-defined]
    fake_torch.bfloat16 = "bf16"  # type: ignore[attr-defined]
    fake_torch.float32 = "fp32"  # type: ignore[attr-defined]
    fake_torch.inference_mode = contextlib.nullcontext  # type: ignore[attr-defined]
    fake_torch.cuda = SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
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
    assert MOONDREAM2_REVISION == "2025-06-21"
    assert calls["model_kwargs"]["revision"] == MOONDREAM2_COMMIT_SHA
    assert calls["model_kwargs"]["trust_remote_code"] is True
    assert calls["caption_length"] == "short"
    assert calls["caption_settings"]["max_tokens"] == 55
    assert calls["tags_settings"]["max_tokens"] == 35
    assert calls["encoded_size"] == (378, 189)

    provider.release()
    assert provider._model is None


def test_moondream2_provider_raises_inference_error_on_runtime_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_torch_and_transformers(monkeypatch, raise_on_answer=True)
    img_path = create_sample_jpeg(tmp_path / "photo.jpg")
    provider = Moondream2Provider(device="cpu", cache_dir=tmp_path / "cache")
    with pytest.raises(AIInferenceError, match="MPS OOM"):
        provider.analyze(img_path)


def test_moondream2_provider_cpu_matches_bfloat16_vision_crops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _install_fake_torch_and_transformers(monkeypatch)
    fake_transformers = sys.modules["transformers"]

    class StrictDtypeModel:
        def __init__(self) -> None:
            self.weight_dtype: Any = None

        def to(self, device: str | None = None, dtype: Any = None) -> StrictDtypeModel:
            calls["to_device"] = device
            calls["to_dtype"] = dtype
            if dtype is not None:
                self.weight_dtype = dtype
            return self

        def eval(self) -> StrictDtypeModel:
            return self

        def encode_image(self, image: Any) -> str:
            _ = image
            if self.weight_dtype != "bf16":
                raise RuntimeError("dtype mismatch")
            return "encoded"

        def caption(
            self,
            enc: str,
            *,
            length: str = "normal",
            settings: dict[str, Any] | None = None,
        ) -> dict[str, str]:
            _ = enc, length, settings
            return {"caption": "A marble bust of Victor Hugo."}

        def query(
            self,
            enc: str,
            prompt: str,
            *,
            settings: dict[str, Any] | None = None,
        ) -> dict[str, str]:
            _ = enc, settings
            assert "JSON array" in prompt
            return {"answer": '["bust", "marble", "sculpture"]'}

    class StrictAutoModel:
        @staticmethod
        def from_pretrained(model_id: str, **kwargs: Any) -> StrictDtypeModel:
            _ = model_id, kwargs
            return StrictDtypeModel()

    monkeypatch.setattr(fake_transformers, "AutoModelForCausalLM", StrictAutoModel)

    img_path = create_sample_rgba_png(tmp_path / "Victor_Hugo.png", size=(400, 400))
    provider = Moondream2Provider(device="cpu", cache_dir=tmp_path / "cache")
    ann = provider.analyze(img_path)
    assert ann.caption == "A marble bust of Victor Hugo."
    assert ann.labels == ["bust", "marble", "sculpture"]


def test_moondream2_offline_uses_local_tokenizer_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from photosphere.ai.moondream2 import (
        moondream2_snapshot_dir,
        moondream2_tokenizer_snapshot_dir,
    )

    cache_root = tmp_path / "cache"
    local_tok_dir = moondream2_tokenizer_snapshot_dir(cache_root)
    local_tok_dir.mkdir(parents=True)
    local_model_dir = moondream2_snapshot_dir(cache_root)
    local_model_dir.mkdir(parents=True)
    (local_model_dir / "config.json").write_text("{}", encoding="utf-8")
    (local_model_dir / "model.safetensors").write_bytes(b"weights")

    calls = _install_fake_torch_and_transformers(monkeypatch)
    provider = Moondream2Provider(device="cpu", cache_dir=cache_root, offline=True)
    img_path = create_sample_rgba_png(tmp_path / "offline.png", size=(300, 300))
    ann = provider.analyze(img_path)
    assert ann.labels
    assert calls["model_id"] == MOONDREAM2_MODEL_ID
    assert calls["model_kwargs"]["revision"] == MOONDREAM2_COMMIT_SHA
    assert calls["model_kwargs"]["cache_dir"] == str(cache_root / "huggingface" / "hub")
    assert calls["model_kwargs"]["local_files_only"] is True


def test_moondream2_analyze_image_skips_disk_decode_and_logs_stage_timings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image

    import photosphere.ai.moondream2 as md_mod

    calls = _install_fake_torch_and_transformers(monkeypatch)
    debug_events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        md_mod.logger,
        "debug",
        lambda event, **kwargs: debug_events.append((event, kwargs)),
    )
    monkeypatch.setattr(
        md_mod,
        "load_capped_rgb_image",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("should not decode")),
    )

    provider = Moondream2Provider(device="mps", dtype="auto")
    assert provider.dtype_name == "bfloat16"
    img = Image.new("RGB", (378, 252), color=(40, 80, 120))
    try:
        ann = provider.analyze_image(img, source_label="mem.jpg")
    finally:
        img.close()

    assert ann.caption == "A red car parked on a street."
    assert ann.labels == ["car", "street", "red"]
    assert calls["encoded_size"] == (378, 252)
    assert debug_events and debug_events[-1][0] == "ai_inference_completed"
    payload = debug_events[-1][1]
    for key in ("decode_ms", "encode_ms", "caption_ms", "tags_ms", "duration_ms"):
        assert key in payload
