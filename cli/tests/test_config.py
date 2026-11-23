"""Unit tests for photosphere.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from photosphere.config import (
    ConfigFileError,
    PhotosphereSettings,
    resolve_photosphere_config_path,
)


def test_default_cache_dir_uses_home_photosphere_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PHOTOSPHERE_CACHE_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_AI_OFFLINE", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_AI_MAX_IMAGE_SIZE", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_AI_DTYPE", raising=False)
    settings = PhotosphereSettings()
    assert settings.cache_dir == Path.home() / ".photosphere" / "cache"
    assert settings.ai_offline is False
    assert settings.ai_max_image_size == 378
    assert settings.ai_dtype == "auto"

    custom_cache = tmp_path / "custom-cache"
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(custom_cache))
    monkeypatch.setenv("PHOTOSPHERE_AI_OFFLINE", "1")
    monkeypatch.setenv("PHOTOSPHERE_AI_DTYPE", "bfloat16")
    overridden = PhotosphereSettings()
    assert overridden.cache_dir == custom_cache
    assert overridden.ai_offline is True
    assert overridden.ai_dtype == "bfloat16"


def test_require_runtime_config_missing_and_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_CONFIG_PATH", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigFileError, match="Missing photosphere.config.json"):
        PhotosphereSettings.require_runtime_config()

    bad_cfg = tmp_path / "bad.json"
    bad_cfg.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(ConfigFileError, match="Missing required section 'gcp'"):
        PhotosphereSettings.require_runtime_config(config_path=bad_cfg)

    with pytest.raises(ConfigFileError, match="Config file not found"):
        resolve_photosphere_config_path(tmp_path / "missing.json")


def test_require_runtime_config_reads_explicit_and_home_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_CONFIG_PATH", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)

    home_cfg_dir = tmp_path / ".photosphere"
    home_cfg_dir.mkdir(parents=True)
    home_cfg = home_cfg_dir / "photosphere.config.json"
    home_cfg.write_text(
        json.dumps(
            {
                "version": 1,
                "gcp": {"project_id": "home-proj", "location": "europe-west1"},
                "storage": {
                    "media_bucket": "m-bkt",
                    "media_storage_class": "ARCHIVE",
                    "data_bucket": "d-bkt",
                    "data_storage_class": "STANDARD",
                },
                "firebase": {},
                "auth": {},
                "pipeline": {"default_lang": "en", "target_lang": "fr"},
            }
        ),
        encoding="utf-8",
    )
    loaded = PhotosphereSettings.require_runtime_config()
    assert loaded.gcp_project_id == "home-proj"
    assert loaded.target_lang == "fr"
