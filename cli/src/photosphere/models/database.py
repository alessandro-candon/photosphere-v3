"""Canonical Pydantic v2 schemas matching contracts/*.schema.json."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

SHA1_HEX_RE = re.compile(r"^[0-9a-f]{40}$")
GS_URI_RE = re.compile(r"^gs://[^/]+/.+$")
UINT_KEY_RE = re.compile(r"^(0|[1-9][0-9]*)$")


class FileType(StrEnum):
    """Supported cloud catalog media types."""

    FILE = "FILE"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class MediaRecord(BaseModel):
    """Single catalog entry stored in photosphere_database_cloud.json."""

    model_config = ConfigDict(extra="forbid")

    hash: str
    average_hash: str | None = Field(default=None, min_length=1)
    source_bucket_uri: str
    thumbnail_bucket_uri: str | None = None
    file_type: FileType
    created_at: str | None = Field(default=None, min_length=1)
    created_at_timestamp: int | None = Field(default=None, ge=0)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    geohash: str | None = None
    label_indexes: list[int] = Field(default_factory=list)
    caption_index: int | None = Field(default=None, ge=0)

    @field_validator("hash")
    @classmethod
    def _validate_sha1_hash(cls, value: str) -> str:
        if not SHA1_HEX_RE.match(value):
            raise ValueError(f"hash must be 40 lowercase hex chars, got {value!r}")
        return value

    @field_validator("source_bucket_uri")
    @classmethod
    def _validate_source_uri(cls, value: str) -> str:
        if not GS_URI_RE.match(value):
            raise ValueError(
                f"source_bucket_uri must be a valid gs:// URI, got {value!r}"
            )
        return value

    @field_validator("thumbnail_bucket_uri")
    @classmethod
    def _validate_thumbnail_uri(cls, value: str | None) -> str | None:
        if value is not None and not GS_URI_RE.match(value):
            raise ValueError(
                f"thumbnail_bucket_uri must be a valid gs:// URI, got {value!r}"
            )
        return value

    @field_validator("label_indexes")
    @classmethod
    def _validate_label_indexes(cls, values: list[int]) -> list[int]:
        for idx in values:
            if idx < 0:
                raise ValueError(f"label index must be >= 0, got {idx}")
        return values


class MediaDatabase(RootModel[dict[str, MediaRecord]]):
    """Flat dictionary keyed by lowercase SHA-1 digest."""

    @model_validator(mode="after")
    def _verify_keys_match_record_hashes(self) -> MediaDatabase:
        for key, record in self.root.items():
            if not SHA1_HEX_RE.match(key):
                raise ValueError(
                    f"Database key must be a 40-char lowercase SHA-1 digest: {key!r}"
                )
            if key != record.hash:
                raise ValueError(
                    f"Key {key!r} does not match record hash {record.hash!r}"
                )
        return self


class KeyValueDictionary(RootModel[dict[str, str]]):
    """Minified stringified-index dictionary for labels or captions."""

    @model_validator(mode="after")
    def _verify_entries(self) -> KeyValueDictionary:
        for key, val in self.root.items():
            if not UINT_KEY_RE.match(key):
                raise ValueError(
                    f"Dictionary key must be stringified integer >= 0: {key!r}"
                )
            if not val:
                raise ValueError(f"Dictionary value at key {key!r} must be non-empty")
        return self


class AlbumRecord(BaseModel):
    """Album entry stored inside photosphere_albums.json."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    hashes: list[str] = Field(default_factory=list)

    @field_validator("hashes")
    @classmethod
    def _validate_hashes(cls, values: list[str]) -> list[str]:
        for digest in values:
            if not SHA1_HEX_RE.match(digest):
                raise ValueError(
                    f"Album hash must be 40 lowercase hex chars: {digest!r}"
                )
        return values


class SkippedEntry(BaseModel):
    """Audit entry recorded when moving a file into skipped/."""

    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=1)
    skipped_path: str = Field(min_length=1)
    reason: Literal[
        "duplicate_sha1",
        "unsupported_extension",
        "processing_error",
        "target_key_collision",
    ]
    sha1: str
    average_hash: str | None = None
    moved_at: str = Field(min_length=1)


class SkippedManifest(BaseModel):
    """Audit manifest persisted as skipped/skipped_manifest.json."""

    model_config = ConfigDict(extra="forbid")

    entries: list[SkippedEntry] = Field(default_factory=list)


def validate_against_contract(
    payload: object, kind: Literal["media", "kv", "albums"]
) -> None:
    """Validate an already-parsed JSON object against strict v3 Pydantic models."""
    if kind == "media":
        MediaDatabase.model_validate(payload)
    elif kind == "kv":
        KeyValueDictionary.model_validate(payload)
    else:
        for item in payload if isinstance(payload, list) else [payload]:
            AlbumRecord.model_validate(item)
