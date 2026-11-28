"""Pydantic models and atomic persistence for photosphere.config.json."""

from __future__ import annotations

import json
import os
import re
import socket
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from photosphere import __version__
from photosphere.config import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_PROFILE,
    StorageClass,
    normalize_profile_name,
    profile_root_dir,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BootstrapConfigError(RuntimeError):
    """Raised when photosphere.config.json is missing, invalid, or cannot be written."""


class GcpConfig(BaseModel):
    """Google Cloud Project coordinates."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    location: str = Field(min_length=1)


class StorageConfig(BaseModel):
    """Dual-bucket GCS configuration with per-bucket storage classes."""

    model_config = ConfigDict(extra="forbid")

    media_bucket: str = Field(min_length=1)
    media_storage_class: StorageClass = "ARCHIVE"
    data_bucket: str = Field(min_length=1)
    data_storage_class: StorageClass = "STANDARD"


class FirebaseConfig(BaseModel):
    """Firebase Web App SDK credentials."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    app_id: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    auth_domain: str = Field(min_length=1)
    storage_bucket: str = Field(min_length=1)
    messaging_sender_id: str = Field(min_length=1)


class AuthConfig(BaseModel):
    """Allowed email allowlist and admin identity."""

    model_config = ConfigDict(extra="forbid")

    allowed_emails: list[str] = Field(min_length=1)
    admin_email: str

    @field_validator("allowed_emails")
    @classmethod
    def _normalize_emails(cls, emails: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in emails:
            cleaned = raw.strip().lower()
            if not _EMAIL_RE.match(cleaned):
                raise ValueError(f"Invalid email address: '{raw}'")
            if cleaned not in normalized:
                normalized.append(cleaned)
        if not normalized:
            raise ValueError("allowed_emails must contain at least one email.")
        return normalized

    @field_validator("admin_email")
    @classmethod
    def _normalize_admin(cls, email: str) -> str:
        cleaned = email.strip().lower()
        if not _EMAIL_RE.match(cleaned):
            raise ValueError(f"Invalid admin_email: '{email}'")
        return cleaned


class PipelineConfig(BaseModel):
    """Default language settings."""

    model_config = ConfigDict(extra="forbid")

    default_lang: str = Field(default="en", min_length=2)
    target_lang: str = Field(default="it", min_length=2)


class ConfigMetadata(BaseModel):
    """Debug and provenance metadata recorded in photosphere.config.json."""

    model_config = ConfigDict(extra="allow")

    cli_version: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    hostname: str = Field(min_length=1)


def build_config_metadata() -> ConfigMetadata:
    """Build current CLI/host debug metadata for photosphere.config.json."""
    return ConfigMetadata(
        cli_version=__version__,
        updated_at=datetime.now(UTC).isoformat(),
        hostname=socket.gethostname(),
    )


class PhotosphereConfig(BaseModel):
    """Canonical root configuration stored in photosphere.config.json."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    gcp: GcpConfig
    storage: StorageConfig
    firebase: FirebaseConfig
    auth: AuthConfig
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    profile: str | None = None
    metadata: ConfigMetadata | None = None


def resolve_config_path(
    explicit_path: Path | None = None,
    *,
    profile: str | None = None,
) -> Path:
    """Resolve photosphere.config.json from explicit arg, env, or active profile."""
    if explicit_path is not None:
        return explicit_path.expanduser().resolve()
    env_path = os.getenv("PHOTOSPHERE_CONFIG_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    active_profile = normalize_profile_name(profile)
    if active_profile == DEFAULT_PROFILE:
        cwd_candidate = Path.cwd() / DEFAULT_CONFIG_FILENAME
        if cwd_candidate.exists():
            return cwd_candidate.resolve()
        parent_candidate = Path.cwd().parent / DEFAULT_CONFIG_FILENAME
        if parent_candidate.exists():
            return parent_candidate.resolve()
    return (profile_root_dir(active_profile) / DEFAULT_CONFIG_FILENAME).resolve()


def load_and_validate_config(path: Path) -> PhotosphereConfig:
    """Read and validate photosphere.config.json from disk."""
    if not path.exists():
        raise BootstrapConfigError(
            f"Configuration file not found at {path}. "
            "Run `photosphere init` (or `make init`) first."
        )
    try:
        raw_text = path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
        return PhotosphereConfig.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise BootstrapConfigError(f"Invalid configuration at {path}: {exc}") from exc


def write_config_atomic(path: Path, config: PhotosphereConfig) -> None:
    """Persist validated configuration atomically via temp file + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f"{path.name}.{uuid.uuid4().hex}.tmp"
    serialized = json.dumps(config.model_dump(mode="json"), indent=2) + "\n"
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except OSError as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise BootstrapConfigError(f"Failed to write config to {path}: {exc}") from exc
