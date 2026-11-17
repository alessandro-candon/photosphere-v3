"""Integration tests for IngestPipeline, checkpoints, GCS guards, and Click CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from photosphere.config import ConfigFileError, PhotosphereSettings
from photosphere.main import cli
from photosphere.media.base import compute_sha1
from photosphere.pipeline.ingest import (
    CAPTIONS_DB_SUFFIX,
    LABELS_DB_SUFFIX,
    MEDIA_DB_FILENAME,
    IngestPipeline,
)
from photosphere.storage.checkpoint import CheckpointEntry
from photosphere.storage.gcs_client import (
    BucketClassError,
    GCSStorageClient,
    StorageSyncError,
)
from tests.conftest import FakeAIProvider, create_sample_jpeg


class _FakeBlob:
    def __init__(self, bucket: _FakeBucket, name: str) -> None:
        self._bucket = bucket
        self.name = name
        self.generation: int | None = bucket.generations.get(name)

    def reload(self) -> None:
        from google.api_core.exceptions import NotFound

        if self.name not in self._bucket.objects:
            raise NotFound(self.name)
        self.generation = self._bucket.generations[self.name]

    def download_as_text(self, encoding: str = "utf-8") -> str:
        from google.api_core.exceptions import NotFound

        if self.name not in self._bucket.objects:
            raise NotFound(self.name)
        return self._bucket.objects[self.name].decode(encoding)

    def upload_from_filename(
        self,
        filename: str,
        content_type: str | None = None,
        if_generation_match: int | None = None,
    ) -> None:
        _ = content_type
        current_gen = self._bucket.generations.get(self.name)
        if if_generation_match is not None:
            if if_generation_match == 0 and current_gen is not None:
                raise StorageSyncError(f"Precondition failed on {self.name}")
            if if_generation_match != 0 and current_gen != if_generation_match:
                raise StorageSyncError(f"Generation mismatch on {self.name}")
        self._bucket.objects[self.name] = Path(filename).read_bytes()
        new_gen = (current_gen or 0) + 1
        self._bucket.generations[self.name] = new_gen
        self.generation = new_gen

    def upload_from_string(
        self,
        data: str | bytes,
        content_type: str | None = None,
        if_generation_match: int | None = None,
    ) -> None:
        _ = content_type
        current_gen = self._bucket.generations.get(self.name)
        if if_generation_match is not None:
            if if_generation_match == 0 and current_gen is not None:
                raise StorageSyncError(f"Precondition failed on {self.name}")
            if if_generation_match != 0 and current_gen != if_generation_match:
                raise StorageSyncError(f"Generation mismatch on {self.name}")
        raw = data.encode("utf-8") if isinstance(data, str) else data
        self._bucket.objects[self.name] = raw
        new_gen = (current_gen or 0) + 1
        self._bucket.generations[self.name] = new_gen
        self.generation = new_gen


class _FakeBucket:
    def __init__(self, storage_class: str) -> None:
        self.storage_class = storage_class
        self.objects: dict[str, bytes] = {}
        self.generations: dict[str, int] = {}

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self, name)


class _FakeClient:
    def __init__(self, buckets: dict[str, _FakeBucket]) -> None:
        self._buckets = buckets

    def bucket(self, name: str) -> _FakeBucket:
        return self._buckets[name]

    def get_bucket(self, name: str) -> _FakeBucket:
        return self._buckets[name]


def _make_gcs(
    media_class: str = "ARCHIVE", data_class: str = "STANDARD"
) -> tuple[GCSStorageClient, _FakeBucket, _FakeBucket]:
    media_bkt = _FakeBucket(media_class)
    data_bkt = _FakeBucket(data_class)
    raw_client: Any = _FakeClient(
        {
            "test-media-archive": media_bkt,
            "test-data-standard": data_bkt,
        }
    )
    return GCSStorageClient(client=raw_client), media_bkt, data_bkt


def test_gcs_storage_client_enforces_bucket_classes_and_aborts_on_missing_db() -> None:
    bad_gcs, _, _ = _make_gcs(media_class="STANDARD", data_class="STANDARD")
    with pytest.raises(BucketClassError, match="ARCHIVE"):
        bad_gcs.verify_bucket_classes(
            "test-media-archive", "test-data-standard", strict=True
        )

    good_gcs, _, _ = _make_gcs()
    good_gcs.verify_bucket_classes(
        "test-media-archive", "test-data-standard", strict=True
    )

    with pytest.raises(StorageSyncError, match="--init-db"):
        good_gcs.download_json("test-data-standard", MEDIA_DB_FILENAME, init_db=False)

    payload, gen = good_gcs.download_json(
        "test-data-standard", MEDIA_DB_FILENAME, init_db=True
    )
    assert payload is None and gen is None


def test_ingest_pipeline_dedup_ai_translation_and_dual_bucket_routing(
    tmp_path: Path,
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
) -> None:
    input_dir = tmp_path / "media_in"
    photo_a = create_sample_jpeg(input_dir / "a.jpg", color=(10, 40, 220))
    photo_a_dup = create_sample_jpeg(
        input_dir / "nested" / "a_dup.jpg", color=(10, 40, 220)
    )
    # Visually similar (>90% average_hash overlap) image reuses existing AI labels
    photo_similar = input_dir / "a_almost_same.jpg"
    create_sample_jpeg(photo_similar, color=(10, 40, 221))
    aux_json = input_dir / "a.jpg.supplemental-metadata.json"
    aux_json.parent.mkdir(parents=True, exist_ok=True)
    aux_json.write_text('{"title": "test"}', encoding="utf-8")

    # Sanity check: photo_a and photo_a_dup have identical bytes & SHA-1
    assert compute_sha1(photo_a) == compute_sha1(photo_a_dup)

    gcs, media_bkt, data_bkt = _make_gcs()
    fake_ai = FakeAIProvider(labels=["sky", "blue"], caption="Deep blue sky frame.")
    pipeline = IngestPipeline(
        cli_settings, gcs, ai_provider=fake_ai, translator=fake_translator
    )
    summary = pipeline.run(input_dir, init_db=True)

    assert summary.scanned == 4
    assert summary.skipped_unsupported == 1
    assert summary.skipped_duplicate == 1
    assert summary.ingested == 2
    assert summary.ai_annotated == 1
    assert summary.reused_annotations == 1
    assert summary.translated_entries == 3  # 2 labels + 1 caption

    # JSON DBs landed in Standard bucket; media & thumbs landed in Archive bucket
    assert MEDIA_DB_FILENAME in data_bkt.objects
    assert f"en_{LABELS_DB_SUFFIX}" in data_bkt.objects
    assert f"it_{LABELS_DB_SUFFIX}" in data_bkt.objects
    assert any(key.startswith("thumbnails/") for key in media_bkt.objects)
    assert any(key.startswith("no_datetime/") for key in media_bkt.objects)
    assert not any(key.endswith(".json") for key in media_bkt.objects)

    manifest = json.loads(
        cli_settings.skipped_manifest_path.read_text(encoding="utf-8")
    )
    assert len(manifest["entries"]) == 2
    reasons = {entry["reason"] for entry in manifest["entries"]}
    assert reasons == {"unsupported_extension", "duplicate_sha1"}


def test_ingest_pipeline_resumes_from_checkpoint_without_ai_or_reupload(
    tmp_path: Path,
    cli_settings: PhotosphereSettings,
) -> None:
    input_dir = tmp_path / "resume_in"
    photo = create_sample_jpeg(input_dir / "resumed.jpg", color=(80, 90, 100))
    sha1 = compute_sha1(photo)

    gcs, media_bkt, data_bkt = _make_gcs()
    data_bkt.objects[f"en_{LABELS_DB_SUFFIX}"] = b'{"0":"street"}'
    data_bkt.generations[f"en_{LABELS_DB_SUFFIX}"] = 1
    data_bkt.objects[f"en_{CAPTIONS_DB_SUFFIX}"] = b'{"0":"Quiet city street"}'
    data_bkt.generations[f"en_{CAPTIONS_DB_SUFFIX}"] = 1

    pipeline = IngestPipeline(cli_settings, gcs)
    pipeline.checkpoint.record(
        CheckpointEntry(
            sha1=sha1,
            source_bucket_uri="gs://test-media-archive/no_datetime/resumed.jpg",
            thumbnail_bucket_uri=f"gs://test-media-archive/thumbnails/resumed.jpg.{sha1}.thumbnail.jpg",
            label_indexes=[0],
            caption_index=0,
        )
    )

    summary = pipeline.run(input_dir, init_db=True, no_ai=True)
    assert summary.resumed_from_checkpoint == 1
    assert summary.ingested == 1
    assert media_bkt.objects == {}  # Did not re-upload already checkpointed file
    db_loaded = json.loads(data_bkt.objects[MEDIA_DB_FILENAME].decode("utf-8"))
    assert sha1 in db_loaded
    assert not cli_settings.checkpoint_path.exists()


def test_click_version_and_no_ai_dry_run_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    res = runner.invoke(cli, ["version"])
    assert res.exit_code == 0
    assert "photosphere 0.1.0" in res.output

    # Verify dry-run with fake client and STORAGE_EMULATOR_HOST
    media_dir = tmp_path / "dry"
    create_sample_jpeg(media_dir / "sample.jpg")
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    monkeypatch.setenv("PHOTOSPHERE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PHOTOSPHERE_SKIPPED_DIR", str(tmp_path / "skipped"))
    monkeypatch.setattr(
        GCSStorageClient,
        "download_json",
        lambda self, bucket, obj, init_db=False: (None, None),
    )

    dry_res = runner.invoke(
        cli, ["ingest", str(media_dir), "--init-db", "--no-ai", "--dry-run"]
    )
    assert dry_res.exit_code == 0
    summary = json.loads(dry_res.output)
    assert summary["ingested"] == 1


def test_dynamic_storage_class_verification_and_required_runtime_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_gcs, _, _ = _make_gcs(media_class="STANDARD", data_class="STANDARD")
    dev_gcs.verify_bucket_classes(
        "test-media-archive",
        "test-data-standard",
        expected_media_class="STANDARD",
        expected_data_class="STANDARD",
        strict=True,
    )

    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("PHOTOSPHERE_CONFIG_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(ConfigFileError, match="PHOTOSPHERE_CONFIG_PATH not found"):
        PhotosphereSettings.require_runtime_config()

    monkeypatch.delenv("PHOTOSPHERE_CONFIG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "empty_home"))
    with pytest.raises(ConfigFileError, match="photosphere.config.json"):
        PhotosphereSettings.require_runtime_config()

    cfg_path = tmp_path / "photosphere.config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "version": 1,
                "gcp": {"project_id": "p-dev", "location": "europe-west1"},
                "storage": {
                    "media_bucket": "p-dev-media",
                    "media_storage_class": "STANDARD",
                    "data_bucket": "p-dev-data",
                    "data_storage_class": "STANDARD",
                },
                "firebase": {
                    "project_id": "p-dev",
                    "app_id": "1:1:web:1",
                    "api_key": "k",
                    "auth_domain": "p-dev.firebaseapp.com",
                    "storage_bucket": "p-dev-media",
                    "messaging_sender_id": "1",
                },
                "auth": {
                    "allowed_emails": ["dev@example.com"],
                    "admin_email": "dev@example.com",
                },
                "pipeline": {
                    "default_lang": "en",
                    "target_lang": "fr",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PHOTOSPHERE_CONFIG_PATH", str(cfg_path))
    loaded = PhotosphereSettings.require_runtime_config()
    assert loaded.media_bucket == "p-dev-media"
    assert loaded.media_storage_class == "STANDARD"
    assert loaded.target_lang == "fr"

    # Explicit config_path overrides env and loads into _PhotosphereJsonSource
    home_dir = tmp_path / "home"
    dot_ps = home_dir / ".photosphere"
    dot_ps.mkdir(parents=True)
    home_cfg = dot_ps / "photosphere.config.json"
    home_cfg.write_text(
        cfg_path.read_text(encoding="utf-8").replace("p-dev-media", "p-home-media"),
        encoding="utf-8",
    )
    override_loaded = PhotosphereSettings.require_runtime_config(config_path=home_cfg)
    assert override_loaded.media_bucket == "p-home-media"

    # ~/.photosphere/photosphere.config.json fallback when CWD & env are absent
    monkeypatch.delenv("PHOTOSPHERE_CONFIG_PATH", raising=False)
    cfg_path.unlink()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home_dir))
    fallback_loaded = PhotosphereSettings.require_runtime_config()
    assert fallback_loaded.media_bucket == "p-home-media"


def test_credentials_resolution_and_doctor_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from photosphere.storage.gcs_client import resolve_credentials_source

    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    src, _ = resolve_credentials_source()
    assert src == "emulator"

    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    with pytest.raises(StorageSyncError, match="Credentials file not found"):
        resolve_credentials_source(tmp_path / "missing-creds.json")

    runner = CliRunner()
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["credentials_source"] == "emulator"
    assert payload["av_version"] is not None
    assert payload["pillow_heif_version"] is not None
    assert payload["errors"] == []
    assert payload["credentials_source"] == "emulator"


def test_dry_run_is_read_only_and_previews_keys_and_collisions(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
) -> None:
    gcs, _, _ = _make_gcs()
    media_dir = tmp_path / "photos"
    (media_dir / "a").mkdir(parents=True)
    (media_dir / "b").mkdir(parents=True)

    create_sample_jpeg(media_dir / "a" / "same.jpg", size=(32, 32), color=(10, 20, 30))
    create_sample_jpeg(media_dir / "b" / "same.jpg", size=(32, 32), color=(40, 50, 60))
    (media_dir / "a" / "notes.json").write_text("{}", encoding="utf-8")

    pipeline = IngestPipeline(cli_settings, gcs, translator=fake_translator)
    summary = pipeline.run(
        media_dir,
        routing_mode="chronological",
        init_db=True,
        dry_run=True,
    )

    assert summary.dry_run is True
    assert summary.routing_mode == "chronological"
    assert summary.ingested == 1
    assert summary.skipped_collision == 1
    assert summary.skipped_unsupported == 1
    assert [p.action for p in summary.planned_uploads] == [
        "skip_unsupported",
        "upload",
        "skip_collision",
    ]
    assert summary.planned_uploads[1].target_key == "no_datetime/same.jpg"
    assert summary.planned_uploads[2].target_key == "no_datetime/same.jpg"

    # Dry-run must not mutate skipped/, thumbnails, checkpoint, or GCS.
    assert (media_dir / "a" / "notes.json").exists()
    assert (media_dir / "b" / "same.jpg").exists()
    assert not (cli_settings.cache_dir / "thumbnails").exists()
    assert not cli_settings.checkpoint_path.exists()
    assert not cli_settings.skipped_manifest_path.exists()


def test_target_key_collision_moves_to_skipped_and_preserves_first_blob(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
) -> None:
    gcs, media_bucket, _ = _make_gcs()
    media_dir = tmp_path / "photos"
    (media_dir / "a").mkdir(parents=True)
    (media_dir / "b").mkdir(parents=True)

    create_sample_jpeg(
        media_dir / "a" / "dupname.jpg", size=(32, 32), color=(11, 22, 33)
    )
    create_sample_jpeg(
        media_dir / "b" / "dupname.jpg", size=(32, 32), color=(44, 55, 66)
    )

    pipeline = IngestPipeline(cli_settings, gcs, translator=fake_translator)
    summary = pipeline.run(
        media_dir,
        routing_mode="chronological",
        init_db=True,
        no_ai=True,
    )

    assert summary.ingested == 1
    assert summary.skipped_collision == 1
    assert "no_datetime/dupname.jpg" in media_bucket.objects
    assert not (media_dir / "b" / "dupname.jpg").exists()
    manifest = json.loads(
        cli_settings.skipped_manifest_path.read_text(encoding="utf-8")
    )
    assert manifest["entries"][0]["reason"] == "target_key_collision"


def test_periodic_commits_and_checkpoint_mode_mismatch(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
) -> None:
    from photosphere.storage.checkpoint import CheckpointModeMismatchError

    gcs, _, data_bucket = _make_gcs()
    media_dir = tmp_path / "photos"
    media_dir.mkdir(parents=True)
    for idx in range(5):
        create_sample_jpeg(
            media_dir / f"img_{idx}.jpg", size=(32, 32), color=(idx * 30, 10, 20)
        )

    pipeline = IngestPipeline(cli_settings, gcs, translator=fake_translator)
    summary = pipeline.run(
        media_dir,
        routing_mode="preserve",
        commit_every=2,
        init_db=True,
        no_ai=True,
    )

    assert summary.ingested == 5
    assert summary.periodic_commits == 2
    assert "photosphere_database_cloud.json" in data_bucket.objects
    db_json = json.loads(
        data_bucket.objects["photosphere_database_cloud.json"].decode("utf-8")
    )
    assert len(db_json) == 5

    # Checkpoint with mismatched routing_mode fails fast.
    pipeline.checkpoint.record(
        CheckpointEntry(
            sha1="a" * 40,
            routing_mode="chronological",
            source_bucket_uri="gs://test-media-archive/no_datetime/x.jpg",
        )
    )
    with pytest.raises(CheckpointModeMismatchError, match="routing_mode=chronological"):
        pipeline.run(media_dir, routing_mode="preserve", no_ai=True)
    pipeline.checkpoint.clear()


def test_ingest_cli_routing_mode_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "photosphere.config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "version": 1,
                "gcp": {"project_id": "p-dev", "location": "europe-west1"},
                "storage": {
                    "media_bucket": "test-media-archive",
                    "media_storage_class": "STANDARD",
                    "data_bucket": "test-data-standard",
                    "data_storage_class": "STANDARD",
                },
                "firebase": {
                    "project_id": "p-dev",
                    "app_id": "1:1:web:1",
                    "api_key": "k",
                    "auth_domain": "p-dev.firebaseapp.com",
                    "storage_bucket": "test-media-archive",
                    "messaging_sender_id": "1",
                },
                "auth": {
                    "allowed_emails": ["dev@example.com"],
                    "admin_email": "dev@example.com",
                },
                "pipeline": {"default_lang": "en", "target_lang": "it"},
            }
        ),
        encoding="utf-8",
    )
    media_dir = tmp_path / "media"
    (media_dir / "album").mkdir(parents=True)
    create_sample_jpeg(
        media_dir / "album" / "pic.jpg", size=(32, 32), color=(90, 90, 90)
    )

    gcs, _, _ = _make_gcs(media_class="STANDARD", data_class="STANDARD")
    monkeypatch.setenv("PHOTOSPHERE_CONFIG_PATH", str(cfg_path))
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")
    monkeypatch.setattr("photosphere.main._build_gcs_client", lambda ctx, settings: gcs)

    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            "ingest",
            str(media_dir),
            "--routing-mode",
            "preserve",
            "--init-db",
            "--dry-run",
        ],
    )
    assert res.exit_code == 0, res.output
    out = json.loads(res.output)
    assert out["routing_mode"] == "preserve"
    assert out["planned_uploads"][0]["target_key"] == "album/pic.jpg"


def test_ingest_caches_provider_uses_source_path_and_handles_retry_fallback(
    cli_settings: PhotosphereSettings,
    fake_translator: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from photosphere.ai.protocol import AIInferenceError, AINotConfiguredError

    media_dir = tmp_path / "media"
    create_sample_jpeg(media_dir / "a.jpg", size=(400, 300), color=(10, 20, 30))
    img2 = create_sample_jpeg(media_dir / "b.jpg", size=(400, 300), color=(240, 10, 10))
    # Make perceptual hashes distinct by drawing a white half on img2
    from PIL import Image, ImageDraw

    with Image.open(img2) as im:
        draw = ImageDraw.Draw(im)
        draw.rectangle([0, 0, 200, 300], fill=(255, 255, 255))
        im.save(img2, format="JPEG")

    gcs, _, _ = _make_gcs()
    load_calls = 0
    analyzed_paths: list[Path] = []
    released = False

    class CountingProvider:
        def analyze(self, image_path: Path) -> Any:
            analyzed_paths.append(image_path)
            if image_path.name == "b.jpg":
                raise AIInferenceError("transient OOM")
            from photosphere.ai.protocol import MediaAnnotation

            return MediaAnnotation(labels=["sky", "blue"], caption="Blue frame.")

        def release(self) -> None:
            nonlocal released
            released = True

    def fake_loader(*args: Any, **kwargs: Any) -> CountingProvider:
        nonlocal load_calls
        load_calls += 1
        return CountingProvider()

    monkeypatch.setattr(
        "photosphere.pipeline.ingest.load_optional_ai_provider", fake_loader
    )

    pipeline = IngestPipeline(cli_settings, gcs, translator=fake_translator)
    summary = pipeline.run(media_dir, init_db=True)

    assert load_calls == 1
    assert released is True
    assert summary.ingested == 2
    assert summary.ai_annotated == 1
    assert summary.ai_retried == 1
    assert summary.ai_failed == 1
    # Photos receive original source_path, not 280x280 thumbnail
    assert all(p.parent == media_dir for p in analyzed_paths)

    # AINotConfiguredError fails fast without swallowing
    class FailingLoader:
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise AINotConfiguredError("missing [ai] extras")

    media_dir_2 = tmp_path / "media2"
    img3 = create_sample_jpeg(
        media_dir_2 / "c.jpg", size=(200, 200), color=(50, 150, 50)
    )
    with Image.open(img3) as im:
        draw = ImageDraw.Draw(im)
        draw.rectangle([0, 100, 200, 200], fill=(10, 10, 10))
        im.save(img3, format="JPEG")
    monkeypatch.setattr(
        "photosphere.pipeline.ingest.load_optional_ai_provider", FailingLoader()
    )
    pipeline2 = IngestPipeline(cli_settings, gcs)
    with pytest.raises(AINotConfiguredError, match="missing \\[ai\\] extras"):
        pipeline2.run(media_dir_2, init_db=True)


def test_dry_run_preview_ai_populates_planned_upload_labels_and_caption(
    cli_settings: PhotosphereSettings,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "media"
    create_sample_jpeg(media_dir / "sample.jpg", size=(300, 200), color=(20, 40, 60))
    gcs, media_bkt, _ = _make_gcs()
    fake_ai = FakeAIProvider(
        labels=["ocean", "blue", "water"],
        caption="A calm blue ocean frame.",
    )
    pipeline = IngestPipeline(cli_settings, gcs, ai_provider=fake_ai)
    summary = pipeline.run(
        media_dir, init_db=True, dry_run=True, preview_ai=True
    )
    assert summary.dry_run is True
    assert summary.ai_annotated == 1
    assert len(media_bkt.objects) == 0
    assert len(summary.planned_uploads) == 1
    planned = summary.planned_uploads[0]
    assert planned.labels == ["ocean", "blue", "water"]
    assert planned.caption == "A calm blue ocean frame."

