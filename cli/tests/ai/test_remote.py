"""Unit tests for photosphere.ai.remote."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from photosphere.ai.protocol import AIInferenceError, AINotConfiguredError
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
        _ = timeout
        headers = {k.lower(): v for k, v in req.header_items()}
        body = json.loads(req.data.decode("utf-8"))
        seen_requests.append((req.full_url, headers, body))
        if req.full_url.endswith("/caption"):
            return _FakeResponse({"caption": "A marble bust in a museum."})
        return _FakeResponse({"answer": '["sculpture", "marble", "museum"]'})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    img_path = create_sample_jpeg(tmp_path / "statue.jpg", size=(640, 480))
    provider = RemoteMoondreamProvider(
        api_url="https://my-cloud-run.run.app/v1",
        api_key="secret-key-123",
    )
    assert provider.max_image_size == 378
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
        _ = timeout
        seen_headers.append({k.lower(): v for k, v in req.header_items()})
        if req.full_url.endswith("/caption"):
            return _FakeResponse({"caption": "Sunset over water."})
        return _FakeResponse({"answer": '["sunset", "water"]'})

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
    with pytest.raises(AINotConfiguredError, match="ai_api_url"):
        RemoteMoondreamProvider(api_url="  ", api_key="k")
    with pytest.raises(AINotConfiguredError, match="ai_api_key"):
        RemoteMoondreamProvider(api_url="https://example.com/v1", api_key="")

    img_path = create_sample_jpeg(tmp_path / "photo.jpg")
    provider = RemoteMoondreamProvider(
        api_url="https://example.com/v1", api_key="bad-key"
    )

    def raise_401(req: Any, timeout: float = 0) -> None:
        _ = timeout
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", Message(), io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_401)
    with pytest.raises(AINotConfiguredError, match="authentication failed"):
        provider.analyze(img_path)

    def raise_503(req: Any, timeout: float = 0) -> None:
        _ = timeout
        raise urllib.error.HTTPError(
            req.full_url, 503, "Service Unavailable", Message(), io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_503)
    with pytest.raises(AIInferenceError, match="HTTP error 503"):
        provider.analyze(img_path)

    def raise_url_err(req: Any, timeout: float = 0) -> None:
        _ = req, timeout
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr(urllib.request, "urlopen", raise_url_err)
    with pytest.raises(AIInferenceError, match="request failed"):
        provider.analyze(img_path)
