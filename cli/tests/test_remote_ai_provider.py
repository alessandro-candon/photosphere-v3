"""Unit tests for RemoteMoondreamProvider and CPU fallback warning."""

from __future__ import annotations

import importlib
import io
import json
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from photosphere.ai.protocol import (
    AIInferenceError,
    AINotConfiguredError,
    load_optional_ai_provider,
)
from photosphere.ai.remote import RemoteMoondreamProvider
from tests.conftest import create_sample_jpeg


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


def test_remote_provider_sends_x_api_key_and_normalizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_requests: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def fake_urlopen(req: Any, timeout: float = 0) -> _FakeResponse:
        headers = {k.lower(): v for k, v in req.header_items()}
        body = json.loads(req.data.decode("utf-8"))
        seen_requests.append((req.full_url, headers, body))
        if req.full_url.endswith("/caption"):
            return _FakeResponse({"caption": "A marble bust in a museum."})
        return _FakeResponse({"answer": '["sculpture", "marble", "museum"]'})

    import urllib.error
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    img_path = create_sample_jpeg(tmp_path / "statue.jpg", size=(640, 480))
    provider = RemoteMoondreamProvider(
        api_url="https://my-cloud-run.run.app/v1",
        api_key="secret-key-123",
    )
    ann = provider.analyze(img_path)

    assert ann.caption == "A marble bust in a museum."
    assert ann.labels == ["sculpture", "marble", "museum"]
    assert len(seen_requests) == 2
    assert seen_requests[0][0] == "https://my-cloud-run.run.app/v1/caption"
    assert seen_requests[0][1]["x-api-key"] == "secret-key-123"
    assert seen_requests[0][2]["image_url"].startswith("data:image/jpeg;base64,")
    assert seen_requests[1][0] == "https://my-cloud-run.run.app/v1/query"


def test_remote_provider_adds_moondream_auth_for_official_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_headers: list[dict[str, str]] = []

    def fake_urlopen(req: Any, timeout: float = 0) -> _FakeResponse:
        seen_headers.append({k.lower(): v for k, v in req.header_items()})
        if req.full_url.endswith("/caption"):
            return _FakeResponse({"caption": "Sunset over water."})
        return _FakeResponse({"answer": '["sunset", "water"]'})

    import urllib.error
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    img_path = create_sample_jpeg(tmp_path / "sunset.jpg")
    provider = RemoteMoondreamProvider(
        api_url="https://api.moondream.ai/v1",
        api_key="md-key",
    )
    ann = provider.analyze(img_path)
    assert ann.caption == "Sunset over water."
    assert seen_headers[0]["x-api-key"] == "md-key"
    assert seen_headers[0]["x-moondream-auth"] == "md-key"


def test_remote_provider_auth_and_transient_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(AINotConfiguredError, match="ai_api_key"):
        RemoteMoondreamProvider(api_url="https://example.com/v1", api_key="")

    img_path = create_sample_jpeg(tmp_path / "photo.jpg")
    provider = RemoteMoondreamProvider(
        api_url="https://example.com/v1", api_key="bad-key"
    )

    def raise_401(req: Any, timeout: float = 0) -> None:
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", Message(), io.BytesIO(b"")
        )

    import urllib.error
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", raise_401)
    with pytest.raises(AINotConfiguredError, match="authentication failed"):
        provider.analyze(img_path)

    def raise_503(req: Any, timeout: float = 0) -> None:
        raise urllib.error.HTTPError(
            req.full_url, 503, "Service Unavailable", Message(), io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_503)
    with pytest.raises(AIInferenceError, match="HTTP error 503"):
        provider.analyze(img_path)


def test_load_optional_ai_provider_remote_does_not_require_torch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = importlib.import_module

    def block_torch(name: str, package: str | None = None) -> Any:
        if name in {"torch", "transformers", "einops"}:
            raise ImportError(name)
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", block_torch)
    provider = load_optional_ai_provider(
        provider_mode="remote",
        api_url="https://cloud-run.example/v1",
        api_key="test-key",
    )
    assert isinstance(provider, RemoteMoondreamProvider)


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
    assert warnings
    assert warnings[0][0] == "ai_cpu_fallback"
    assert "10+ min" in warnings[0][1]["message"]
