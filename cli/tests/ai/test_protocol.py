"""Unit tests for photosphere.ai.protocol."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from photosphere.ai.protocol import (
    AIInferenceError,
    AINotConfiguredError,
    MediaAnnotation,
    analyze_with_retry,
    configure_hf_cache_env,
    format_hf_load_hint,
    load_optional_ai_provider,
    release_ai_provider,
    resolve_device,
    resolve_dtype,
)
from photosphere.ai.remote import RemoteMoondreamProvider


def test_resolve_device_and_dtype_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_device("cuda") == "cuda"
    assert resolve_device("mps") == "mps"
    assert resolve_device("cpu") == "cpu"
    assert resolve_dtype("mps") == "bfloat16"
    assert resolve_dtype("mps", preferred="float16") == "float16"
    assert resolve_dtype("cpu") == "bfloat16"
    assert resolve_dtype("cpu", preferred="float32") == "float32"

    real_import = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, package=None: (
            (_ for _ in ()).throw(ImportError(name))
            if name == "torch"
            else real_import(name, package)
        ),
    )
    assert resolve_device("auto") == "cpu"
    assert resolve_dtype("cuda") == "float16"


def test_configure_hf_cache_env_and_format_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import os

    for key in (
        "HF_HOME",
        "HF_HUB_CACHE",
        "HF_MODULES_CACHE",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
    ):
        monkeypatch.delenv(key, raising=False)

    hf_dir = tmp_path / "cache" / "huggingface"
    configure_hf_cache_env(hf_dir, offline=True)
    assert os.environ["HF_HOME"] == str(hf_dir)
    assert os.environ["HF_HUB_CACHE"] == str(hf_dir / "hub")
    assert os.environ["HF_MODULES_CACHE"] == str(hf_dir / "modules")
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"

    offline_hint = format_hf_load_hint(
        RuntimeError("missing"), cache_dir=hf_dir, offline=True
    )
    assert "Offline mode is enabled" in offline_hint
    tls_hint = format_hf_load_hint(
        RuntimeError("CERTIFICATE_VERIFY_FAILED"), cache_dir=hf_dir, offline=False
    )
    assert "prefetch-models" in tls_hint
    assert (
        format_hf_load_hint(RuntimeError("other"), cache_dir=hf_dir, offline=False)
        == ""
    )


def test_load_optional_ai_provider_remote_and_missing_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, package=None: (
            (_ for _ in ()).throw(ImportError(name))
            if name in {"torch", "transformers", "einops"}
            else real_import(name, package)
        ),
    )
    remote = load_optional_ai_provider(
        provider_mode="remote",
        api_url="https://cloud-run.example/v1",
        api_key="test-key",
    )
    assert isinstance(remote, RemoteMoondreamProvider)

    with pytest.raises(AINotConfiguredError, match="--no-ai"):
        load_optional_ai_provider("cpu")


def test_load_optional_ai_provider_cpu_logs_10min_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import photosphere.ai.protocol as protocol_mod

    real_import = importlib.import_module
    warnings: list[tuple[str, dict[str, Any]]] = []

    ai_mods = {"torch", "transformers", "einops"}
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, package=None: (
            object() if name in ai_mods else real_import(name, package)
        ),
    )
    monkeypatch.setattr(
        protocol_mod.logger,
        "warning",
        lambda event, **kwargs: warnings.append((event, kwargs)),
    )
    load_optional_ai_provider("cpu")
    assert warnings and warnings[0][0] == "ai_cpu_fallback"
    assert "10+ min" in warnings[0][1]["message"]


def test_analyze_with_retry_and_release(tmp_path: Path) -> None:
    class FlakyProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.released = False

        def analyze(self, image_path: Path) -> MediaAnnotation:
            _ = image_path
            self.calls += 1
            if self.calls == 1:
                raise AIInferenceError("transient")
            return MediaAnnotation(labels=["ok"], caption="Recovered.")

        def release(self) -> None:
            self.released = True

    provider = FlakyProvider()
    ann, retries = analyze_with_retry(provider, tmp_path / "a.jpg", max_retries=1)
    assert ann is not None and ann.caption == "Recovered."
    assert retries == 1
    release_ai_provider(provider)
    assert provider.released is True
    release_ai_provider(None)


def test_analyze_with_retry_prefers_analyze_image_when_supported(
    tmp_path: Path,
) -> None:
    seen: list[tuple[str, Any]] = []

    class InMemoryProvider:
        def analyze(self, image_path: Path) -> MediaAnnotation:
            seen.append(("path", image_path))
            return MediaAnnotation(labels=["path"], caption="From path.")

        def analyze_image(
            self, image: Any, *, source_label: str = "<in-memory>"
        ) -> MediaAnnotation:
            seen.append(("image", (image, source_label)))
            return MediaAnnotation(labels=["mem"], caption="From memory.")

    class PathOnlyProvider:
        def analyze(self, image_path: Path) -> MediaAnnotation:
            seen.append(("path_only", image_path))
            return MediaAnnotation(labels=["path"], caption="From path only.")

    fake_img = object()
    ann_mem, retries_mem = analyze_with_retry(
        InMemoryProvider(), tmp_path / "a.jpg", image=fake_img
    )
    assert ann_mem is not None and ann_mem.labels == ["mem"]
    assert retries_mem == 0

    ann_path, retries_path = analyze_with_retry(
        PathOnlyProvider(), tmp_path / "b.jpg", image=fake_img
    )
    assert ann_path is not None and ann_path.labels == ["path"]
    assert retries_path == 0
    assert seen[0][0] == "image"
    assert seen[1][0] == "path_only"
