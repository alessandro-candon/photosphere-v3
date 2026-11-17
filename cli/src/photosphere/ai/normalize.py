"""Provider-agnostic caption and tag normalization helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*•]+|\d+[.):])\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_EDGE_PUNCT_RE = re.compile(r"^[\s\"'`.,;:!?()\[\]{}]+|[\s\"'`.,;:!?()\[\]{}]+$")
_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def normalize_caption(raw: str | None) -> str | None:
    """Normalize a generated caption to a single clean sentence, or None if empty."""
    if not raw:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", raw).strip().strip("\"'")
    if not cleaned:
        return None
    # Keep only the first sentence when a VLM emits extra trailing sentences.
    parts = _SENTENCE_SPLIT_RE.split(cleaned, maxsplit=1)
    first = parts[0].strip()
    return first or None


def normalize_tags(raw_tags: Sequence[str], max_tags: int = 5) -> list[str]:
    """Lowercase, trim, deduplicate, and cap tags without padding."""
    if max_tags <= 0:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_tags:
        if not isinstance(item, str):
            continue
        cleaned = _LIST_PREFIX_RE.sub("", item)
        cleaned = _EDGE_PUNCT_RE.sub("", cleaned)
        cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
        if len(result) >= max_tags:
            break
    return result


def parse_tags_response(raw_text: str, max_tags: int = 5) -> list[str]:
    """Parse a JSON array or delimited tag string into normalized tags."""
    if not raw_text or not raw_text.strip():
        return []
    match = _JSON_ARRAY_RE.search(raw_text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return normalize_tags([str(x) for x in parsed], max_tags=max_tags)
        except json.JSONDecodeError:
            pass
    # Fallback for comma- or newline-delimited responses.
    stripped = raw_text.strip()
    candidates = (
        stripped.splitlines()
        if "\n" in stripped
        else stripped.split(",")
    )
    return normalize_tags(candidates, max_tags=max_tags)
