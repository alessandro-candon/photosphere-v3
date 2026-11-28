"""Unit tests for photosphere.main Click CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from photosphere.main import cli
from photosphere.storage.gcs_client import GCSStorageClient, StorageSyncError
from tests.conftest import create_sample_jpeg, make_gcs


def test_version_and_doctor_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    ver = runner.invoke(cli, ["-v", "version"])
    assert ver.exit_code == 0
    assert "photosphere 0.1.0" in ver.output

    from photosphere.ai.moondream2 import (
        moondream2_snapshot_dir,
        moondream2_tokenizer_snapshot_dir,
    )

    cache_dir = tmp_path / "cache"
    md_snap = moondream2_snapshot_dir(cache_dir)
    md_snap.mkdir(parents=True)
    (md_snap / "config.json").write_text("{}", encoding="utf-8")
    (md_snap / "model.safetensors").write_bytes(b"weights")
    tok_snap = moondream2_tokenizer_snapshot_dir(cache_dir)
    tok_snap.mkdir(parents=True)
    (tok_snap / "tokenizer.json").write_text("{}", encoding="utf-8")
    (cache_dir / "huggingface" / "modules" / "transformers_modules").mkdir(parents=True)
    (cache_dir / "easynmt" / "models--Helsinki-NLP--opus-mt-en-it").mkdir(parents=True)

    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("PHOTOSPHERE_AI_OFFLINE", "1")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)

    doc = runner.invoke(cli, ["doctor"])
    assert doc.exit_code == 1
    payload = json.loads(doc.output)
    assert payload["cache_dir"] == str(cache_dir)
    assert payload["ai_offline"] is True
    assert payload["cached_models"] == {
        "moondream2": True,
        "moondream2_tokenizer": True,
        "moondream2_modules": True,
        "easynmt_models": ["models--Helsinki-NLP--opus-mt-en-it"],
    }


def test_translate_and_verify_db_catch_storage_sync_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    monkeypatch.setenv("PHOTOSPHERE_MEDIA_BUCKET", "test-media-archive")
    monkeypatch.setenv("PHOTOSPHERE_DATA_BUCKET", "test-data-standard")
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        GCSStorageClient,
        "verify_bucket_classes",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            StorageSyncError("bucket class mismatch")
        ),
    )

    runner = CliRunner()
    res_t = runner.invoke(cli, ["translate", "--target-lang", "it"])
    assert res_t.exit_code != 0
    assert "bucket class mismatch" in res_t.output

    res_v = runner.invoke(cli, ["verify-db"])
    assert res_v.exit_code != 0
    assert "bucket class mismatch" in res_v.output


def test_ingest_cli_dry_run_and_routing_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media_dir = tmp_path / "media"
    (media_dir / "album").mkdir(parents=True)
    create_sample_jpeg(
        media_dir / "album" / "pic.jpg", size=(32, 32), color=(90, 90, 90)
    )
    gcs, _, _ = make_gcs(media_class="ARCHIVE", data_class="STANDARD")
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    monkeypatch.setenv("PHOTOSPHERE_MEDIA_BUCKET", "test-media-archive")
    monkeypatch.setenv("PHOTOSPHERE_DATA_BUCKET", "test-data-standard")
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PHOTOSPHERE_SKIPPED_DIR", str(tmp_path / "skipped"))
    monkeypatch.setattr(
        "photosphere.storage.gcs_client._build_storage_client",
        lambda *args, **kwargs: gcs._client,
    )

    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            "ingest",
            str(media_dir),
            "--routing-mode",
            "preserve",
            "--init-db",
            "--no-ai",
            "--dry-run",
        ],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["routing_mode"] == "preserve"
    assert payload["planned_uploads"][0]["target_key"] == "album/pic.jpg"


def test_prefetch_models_cli_invokes_provider_and_translator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import photosphere.main as main_mod

    seen: dict[str, Any] = {"vision": False, "langs": []}

    class FakePrefetchProvider:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def prefetch(self) -> None:
            seen["vision"] = True

    class FakePrefetchTranslator:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def prefetch(self, lang: str) -> None:
            seen["langs"].append(lang)

    monkeypatch.setattr(main_mod, "Moondream2Provider", FakePrefetchProvider)
    monkeypatch.setattr(main_mod, "EasyNMTTranslator", FakePrefetchTranslator)

    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            "prefetch-models",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--lang",
            "it",
            "--lang",
            "fr",
        ],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["vision"] is True
    assert payload["languages"] == ["it", "fr"]
    assert seen == {"vision": True, "langs": ["it", "fr"]}


def test_verify_db_uses_load_remote_kv_store_and_handles_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from photosphere.storage.gcs_client import StorageConflictError

    gcs, _, _ = make_gcs(media_class="ARCHIVE", data_class="STANDARD")
    gcs.upload_json_atomic("test-data-standard", "photosphere_database_cloud.json", {})
    gcs.upload_json_atomic(
        "test-data-standard",
        "en_photosphere_image_labelling_database_cloud.json",
        {"0": "sky"},
    )
    gcs.upload_json_atomic(
        "test-data-standard",
        "en_photosphere_image_caption_database_cloud.json",
        {"0": "a clear sky"},
    )
    gcs.upload_json_atomic("test-data-standard", "photosphere_albums.json", [])

    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    monkeypatch.setenv("PHOTOSPHERE_MEDIA_BUCKET", "test-media-archive")
    monkeypatch.setenv("PHOTOSPHERE_DATA_BUCKET", "test-data-standard")
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        "photosphere.storage.gcs_client._build_storage_client",
        lambda *args, **kwargs: gcs._client,
    )

    runner = CliRunner()
    res = runner.invoke(cli, ["verify-db"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload == {
        "media_count": 0,
        "labels_count": 1,
        "captions_count": 1,
        "albums_count": 0,
    }
    assert not (
        tmp_path / "cache" / "en_photosphere_image_labelling_database_cloud.json"
    ).exists()

    monkeypatch.setattr(
        GCSStorageClient,
        "verify_bucket_classes",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            StorageConflictError("concurrent write conflict")
        ),
    )
    res_conflict = runner.invoke(cli, ["verify-db"])
    assert res_conflict.exit_code != 0
    assert "concurrent write conflict" in res_conflict.output


def test_profile_confirmation_prompt_and_doctor_propagation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_CACHE_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_MODELS_DIR", raising=False)
    monkeypatch.delenv("PHOTOSPHERE_SKIPPED_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("photosphere.main._is_interactive_tty", lambda: True)

    runner = CliRunner()

    # Answering 'n' to DEFAULT profile prompt aborts cleanly.
    aborted = runner.invoke(cli, ["doctor"], input="n\n")
    assert aborted.exit_code != 0
    assert 'Do you want to continue with profile "DEFAULT"?' in aborted.output

    # Answering 'y' to explicit profile proceeds and propagates to doctor report.
    confirmed = runner.invoke(cli, ["--profile", "work", "doctor"], input="y\n")
    assert 'Do you want to continue with profile "work"?' in confirmed.output
    json_start = confirmed.output.index("{")
    payload = json.loads(confirmed.output[json_start:])
    assert payload["profile"] == "work"
    assert payload["cache_dir"] == str(
        tmp_path / ".photosphere" / "profiles" / "work" / "cache"
    )
    assert payload["skipped_dir"] == str(
        tmp_path / ".photosphere" / "profiles" / "work" / "skipped"
    )
    assert payload["models_dir"] == str(tmp_path / ".photosphere" / "cache")

    # --yes skips the prompt; version skips the prompt; invalid profile fails.
    auto_yes = runner.invoke(cli, ["--profile", "work", "--yes", "doctor"])
    assert "Do you want to continue" not in auto_yes.output
    ver = runner.invoke(cli, ["version"])
    assert ver.exit_code == 0
    assert "Do you want to continue" not in ver.output
    bad = runner.invoke(cli, ["--profile", "bad/name", "version"])
    assert bad.exit_code != 0
    assert "Invalid profile name" in bad.output
