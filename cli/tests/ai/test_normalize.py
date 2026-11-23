"""Unit tests for photosphere.ai.normalize."""

from __future__ import annotations

from photosphere.ai.normalize import (
    normalize_caption,
    normalize_tags,
    parse_tags_response,
)


def test_normalize_caption_collapses_whitespace_and_keeps_first_sentence() -> None:
    raw = '  "An   orange train on tracks. It moves right."  '
    assert normalize_caption(raw) == "An orange train on tracks."
    assert normalize_caption("   ") is None
    assert normalize_caption(None) is None
    assert normalize_caption('"."') == "."


def test_normalize_tags_cleans_deduplicates_and_caps_at_five() -> None:
    raw = [
        "1. Train ",
        "  train",
        "- Railway Track!",
        "",
        "   ",
        "Station.",
        "Travel",
        "Orange",
        "Platform",
    ]
    assert normalize_tags(raw, max_tags=5) == [
        "train",
        "railway track",
        "station",
        "travel",
        "orange",
    ]
    assert normalize_tags(raw, max_tags=0) == []


def test_normalize_tags_accepts_fewer_than_three_without_padding() -> None:
    assert normalize_tags(["sunset", "beach"]) == ["sunset", "beach"]


def test_parse_tags_response_handles_json_and_delimited_fallback() -> None:
    json_resp = '```json\n["Mountain", "Snowy Peak", "mountain", ""]\n```'
    assert parse_tags_response(json_resp) == ["mountain", "snowy peak"]

    csv_resp = "1. dog, 2. park, grass"
    assert parse_tags_response(csv_resp) == ["dog", "park", "grass"]
    assert parse_tags_response("   ") == []
    assert parse_tags_response("[invalid json]") == ["invalid json"]
