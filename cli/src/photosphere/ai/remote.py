"""Remote Moondream HTTP API provider (Cloud Run or Moondream Cloud API)."""

from __future__ import annotations

import base64
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog

from photosphere.ai.normalize import normalize_caption, parse_tags_response
from photosphere.ai.protocol import (
    AIInferenceError,
    AINotConfiguredError,
    MediaAnnotation,
)
from photosphere.media.image import load_capped_rgb_image

logger = structlog.get_logger(__name__)

DEFAULT_MOONDREAM_API_URL = "https://api.moondream.ai/v1"
TAGS_PROMPT = (
    "Return 3 to 5 concise descriptive tags for this image as a JSON array of strings."
)


class RemoteMoondreamProvider:
    """HTTP client implementing AIProvider for Cloud Run or Moondream Cloud API."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        *,
        max_image_size: int = 1024,
        max_tags: int = 5,
        timeout: float = 60.0,
    ) -> None:
        cleaned_url = api_url.strip().rstrip("/")
        if not cleaned_url:
            raise AINotConfiguredError(
                "Remote AI provider requires `ai_api_url` "
                "(e.g. --ai-api-url or PHOTOSPHERE_AI_API_URL)."
            )
        if not api_key.strip():
            raise AINotConfiguredError(
                "Remote AI provider requires `ai_api_key` "
                "(set PHOTOSPHERE_AI_API_KEY)."
            )
        self.api_url = cleaned_url
        self.api_key = api_key.strip()
        self.max_image_size = max_image_size
        self.max_tags = max_tags
        self.timeout = timeout

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
        }
        host = urlparse(self.api_url).hostname or ""
        if host.endswith("moondream.ai"):
            headers["X-Moondream-Auth"] = self.api_key
        return headers

    def _encode_image_data_url(self, image_path: Path) -> str:
        try:
            rgb_image = load_capped_rgb_image(image_path, max_size=self.max_image_size)
            buf = io.BytesIO()
            rgb_image.save(buf, format="JPEG", quality=90)
        except Exception as exc:
            raise AIInferenceError(
                f"Failed to decode/encode image for remote AI ({image_path}): {exc}"
            ) from exc
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def _post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers=self._build_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise AINotConfiguredError(
                    f"Remote AI authentication failed ({exc.code}) at {url}."
                ) from exc
            raise AIInferenceError(
                f"Remote AI HTTP error {exc.code} from {url}: {exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AIInferenceError(
                f"Remote AI request failed for {url}: {exc}"
            ) from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIInferenceError(
                f"Remote AI returned invalid JSON from {url}: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise AIInferenceError(
                f"Remote AI returned non-object JSON from {url}."
            )
        return parsed

    def analyze(self, image_path: Path) -> MediaAnnotation:
        """Request caption and tags from the configured remote Moondream API."""
        data_url = self._encode_image_data_url(image_path)
        started = time.perf_counter()

        caption_resp = self._post_json(
            "/caption", {"image_url": data_url, "length": "normal"}
        )
        tags_resp = self._post_json(
            "/query", {"image_url": data_url, "question": TAGS_PROMPT}
        )

        raw_caption = str(caption_resp.get("caption") or "")
        raw_tags = str(tags_resp.get("answer") or tags_resp.get("tags") or "")
        caption = normalize_caption(raw_caption)
        labels = parse_tags_response(raw_tags, max_tags=self.max_tags)

        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.debug(
            "remote_ai_inference_completed",
            image_path=str(image_path),
            api_url=self.api_url,
            duration_ms=elapsed_ms,
            label_count=len(labels),
        )
        return MediaAnnotation(labels=labels, caption=caption)
