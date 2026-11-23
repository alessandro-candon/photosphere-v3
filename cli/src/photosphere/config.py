"""Runtime configuration loaded via pydantic-settings and photosphere.config.json."""

from __future__ import annotations

import contextvars
import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

DEFAULT_CONFIG_FILENAME = "photosphere.config.json"
StorageClass = Literal["ARCHIVE", "STANDARD"]
RoutingMode = Literal["chronological", "preserve"]
AIProviderMode = Literal["local", "remote"]
_CONFIG_PATH_OVERRIDE: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "_CONFIG_PATH_OVERRIDE", default=None
)


class ConfigFileError(RuntimeError):
    """Raised when photosphere.config.json is missing or invalid at runtime."""


def resolve_photosphere_config_path(explicit_path: Path | None = None) -> Path | None:
    """Locate photosphere.config.json from explicit, env, cwd, or ~/.photosphere."""
    if explicit_path is not None:
        resolved = explicit_path.expanduser().resolve()
        if not resolved.exists():
            raise ConfigFileError(f"Config file not found: {resolved}")
        return resolved
    env_path = os.getenv("PHOTOSPHERE_CONFIG_PATH")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if not candidate.exists():
            raise ConfigFileError(f"PHOTOSPHERE_CONFIG_PATH not found: {candidate}")
        return candidate
    for candidate in (
        Path.cwd() / DEFAULT_CONFIG_FILENAME,
        Path.cwd().parent / DEFAULT_CONFIG_FILENAME,
        Path.home() / ".photosphere" / DEFAULT_CONFIG_FILENAME,
    ):
        if candidate.exists():
            return candidate.resolve()
    return None


def _extract_settings_from_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigFileError(f"Expected JSON object in {path}")
    for key in ("version", "gcp", "storage", "firebase", "auth", "pipeline"):
        if key not in raw:
            raise ConfigFileError(f"Missing required section '{key}' in {path}")
    gcp = raw["gcp"]
    storage = raw["storage"]
    pipeline = raw["pipeline"]
    return {
        "gcp_project_id": gcp["project_id"],
        "media_bucket": storage["media_bucket"],
        "media_storage_class": storage["media_storage_class"],
        "data_bucket": storage["data_bucket"],
        "data_storage_class": storage["data_storage_class"],
        "target_lang": pipeline["target_lang"],
    }


class _PhotosphereJsonSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        path = _CONFIG_PATH_OVERRIDE.get() or resolve_photosphere_config_path()
        self._data: dict[str, Any] = (
            _extract_settings_from_json(path) if path is not None else {}
        )

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        value = self._data.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        return dict(self._data)


class PhotosphereSettings(BaseSettings):
    """Configuration settings for Photosphere v3 CLI operations."""

    model_config = SettingsConfigDict(
        env_prefix="PHOTOSPHERE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gcp_project_id: str | None = Field(
        default=None,
        description="GCP project ID loaded from photosphere.config.json.",
    )
    media_bucket: str = Field(
        default="photosphere-media-archive",
        description="Media GCS bucket holding original media and thumbnails.",
    )
    media_storage_class: StorageClass = Field(
        default="ARCHIVE",
        description="Expected GCS storage class for the media bucket.",
    )
    data_bucket: str = Field(
        default="photosphere-data-standard",
        description="Data GCS bucket holding the four JSON databases.",
    )
    data_storage_class: StorageClass = Field(
        default="STANDARD",
        description="Expected GCS storage class for the data bucket.",
    )
    skipped_dir: Path = Field(
        default=Path("./skipped"),
        description="Local directory for unsupported and duplicate files.",
    )
    cache_dir: Path = Field(
        default_factory=lambda: Path.home() / ".photosphere" / "cache",
        description=(
            "Local cache for checkpoints, DB snapshots, thumbnails, and AI models."
        ),
    )
    missing_date_prefix: str = Field(
        default="no_datetime",
        description="Object key prefix used when media lacks creation timestamp.",
    )
    target_lang: str = Field(
        default="it",
        description="Target ISO language code for dictionary translation.",
    )
    device: Literal["auto", "cuda", "mps", "cpu"] = Field(
        default="auto",
        description="Compute device preference for optional AI inference.",
    )
    ai_dtype: Literal["auto", "float16", "bfloat16", "float32"] = Field(
        default="auto",
        description="Floating-point dtype override for local AI inference.",
    )
    ai_max_image_size: int = Field(
        default=378,
        ge=256,
        description="Max pixel dimension for in-memory photo resizing before AI.",
    )
    ai_max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        description="Maximum retry attempts on transient AI inference failures.",
    )
    ai_provider: AIProviderMode = Field(
        default="local",
        description="Vision AI backend: local (MPS/CUDA/CPU) or remote HTTP API.",
    )
    ai_offline: bool = Field(
        default=False,
        description=(
            "Load local AI and translation models strictly from cache "
            "without contacting huggingface.co."
        ),
    )
    ai_api_url: str | None = Field(
        default=None,
        description="Base URL for remote Moondream HTTP API (Cloud Run or Moondream).",
    )
    ai_api_key: str | None = Field(
        default=None,
        description="API key sent as x-api-key header for remote AI inference.",
    )
    ai_api_timeout: float = Field(
        default=60.0,
        gt=0,
        description="HTTP timeout in seconds for remote AI requests.",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Prioritize init kwargs, env vars, photosphere.config.json, then dotenv."""
        return (
            init_settings,
            env_settings,
            _PhotosphereJsonSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @classmethod
    def require_runtime_config(
        cls,
        config_path: Path | None = None,
        **overrides: Any,
    ) -> PhotosphereSettings:
        """Load settings and fail fast if photosphere.config.json is absent."""
        if os.getenv("STORAGE_EMULATOR_HOST"):
            return cls(**overrides)
        resolved = resolve_photosphere_config_path(config_path)
        if resolved is None:
            raise ConfigFileError(
                "Missing photosphere.config.json. Place it at "
                "~/.photosphere/photosphere.config.json, pass --config-file <path>, "
                "or run `photosphere init` (or `make init` in the repository)."
            )
        try:
            _extract_settings_from_json(resolved)
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise ConfigFileError(
                f"Invalid photosphere.config.json at {resolved}: {exc}"
            ) from exc
        token = _CONFIG_PATH_OVERRIDE.set(resolved)
        try:
            return cls(**overrides)
        finally:
            _CONFIG_PATH_OVERRIDE.reset(token)

    @property
    def skipped_manifest_path(self) -> Path:
        """Return path to the local skipped audit manifest JSON."""
        return self.skipped_dir / "skipped_manifest.json"

    @property
    def checkpoint_path(self) -> Path:
        """Return path to the local NDJSON ingest write-ahead checkpoint."""
        return self.cache_dir / "ingest_checkpoint.ndjson"
