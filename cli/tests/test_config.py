"""Unit tests for photosphere.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from photosphere.config import (
    ConfigFileError,
    PhotosphereSettings,
    normalize_profile_name,
    resolve_photosphere_config_path,
)


def test_default_cache_dir_uses_home_photosphere_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PHOTOSPHERE_CACHE_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_MODELS_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_SKIPPED_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_AI_OFFLINE", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_AI_MAX_IMAGE_SIZE", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_AI_DTYPE", raising=False)
    settings = PhotosphereSettings()
    assert (
        settings.cache_dir
        == Path.home() / ".photosphere" / "profiles" / "default" / "cache"
    )
    assert (
        settings.skipped_dir
        == Path.home() / ".photosphere" / "profiles" / "default" / "skipped"
    )
    assert settings.models_dir == Path.home() / ".photosphere" / "cache"
    assert settings.ai_offline is False
    assert settings.ai_max_image_size == 378
    assert settings.ai_dtype == "auto"

    custom_cache = tmp_path / "custom-cache"
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(custom_cache))
    monkeypatch.setenv("PHOTOSPHERE_AI_OFFLINE", "1")
    monkeypatch.setenv("PHOTOSPHERE_AI_DTYPE", "bfloat16")
    overridden = PhotosphereSettings()
    assert overridden.cache_dir == custom_cache
    assert overridden.models_dir == custom_cache
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


def test_profile_isolation_shared_models_and_emulator_safety(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_CONFIG_PATH", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_CACHE_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_MODELS_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_SKIPPED_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)

    def _cfg_payload(project_id: str) -> str:
        return json.dumps(
            {
                "version": 1,
                "gcp": {"project_id": project_id, "location": "europe-west1"},
                "storage": {
                    "media_bucket": f"{project_id}-media",
                    "media_storage_class": "ARCHIVE",
                    "data_bucket": f"{project_id}-data",
                    "data_storage_class": "STANDARD",
                },
                "firebase": {},
                "auth": {},
                "pipeline": {"default_lang": "en", "target_lang": "it"},
            }
        )

    # CWD config should not shadow an explicit non-default profile.
    (tmp_path / "photosphere.config.json").write_text(
        _cfg_payload("cwd-proj"), encoding="utf-8"
    )
    work_dir = tmp_path / ".photosphere" / "profiles" / "work"
    work_dir.mkdir(parents=True)
    (work_dir / "photosphere.config.json").write_text(
        _cfg_payload("work-proj"), encoding="utf-8"
    )

    default_settings = PhotosphereSettings.require_runtime_config(profile="default")
    work_settings = PhotosphereSettings.require_runtime_config(profile="Work")
    assert default_settings.gcp_project_id == "cwd-proj"
    assert work_settings.gcp_project_id == "work-proj"
    assert work_settings.profile == "work"
    assert work_settings.cache_dir == work_dir / "cache"
    assert work_settings.skipped_dir == work_dir / "skipped"
    assert (
        work_settings.checkpoint_path
        == work_dir / "cache" / "ingest_checkpoint.ndjson"
    )
    assert default_settings.models_dir == tmp_path / ".photosphere" / "cache"
    assert work_settings.models_dir == default_settings.models_dir

    # Under STORAGE_EMULATOR_HOST, non-default profile must not bleed CWD config.
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    emu_other = PhotosphereSettings.require_runtime_config(profile="other")
    assert emu_other.gcp_project_id is None
    assert (
        emu_other.cache_dir
        == tmp_path / ".photosphere" / "profiles" / "other" / "cache"
    )

    with pytest.raises(ValueError, match="Invalid profile name"):
        normalize_profile_name("../bad")
