"""Unit tests for photosphere.pipeline.common."""

from __future__ import annotations

from typing import Any

from photosphere.ai.translator import KeyValueStore
from photosphere.config import PhotosphereSettings
from photosphere.models.database import FileType, MediaRecord
from photosphere.pipeline.common import (
    CAPTIONS_DB_SUFFIX,
    LABELS_DB_SUFFIX,
    MEDIA_DB_FILENAME,
    commit_media_and_english_dbs,
    create_ai_provider,
    load_remote_kv_store,
    load_remote_media_db,
    sync_target_language_dictionaries,
)
from tests.conftest import make_gcs


def test_load_and_commit_media_and_kv_stores(
    cli_settings: PhotosphereSettings, fake_translator: Any
) -> None:
    gcs, _, data_bkt = make_gcs()

    db_records, db_gen = load_remote_media_db(gcs, cli_settings, init_db=True)
    assert db_records == {} and db_gen is None

    en_labels, labels_gen = load_remote_kv_store(
        gcs, cli_settings, f"en_{LABELS_DB_SUFFIX}", allow_missing=True
    )
    en_captions, captions_gen = load_remote_kv_store(
        gcs, cli_settings, f"en_{CAPTIONS_DB_SUFFIX}", allow_missing=True
    )
    assert isinstance(en_labels, KeyValueStore)
    en_labels.add_unique_value("mountain")
    en_captions.add_unique_value("A snowy peak.")

    rec = MediaRecord(
        hash="a" * 40,
        average_hash="0" * 64,
        source_bucket_uri=f"gs://{cli_settings.media_bucket}/a.jpg",
        file_type=FileType.IMAGE,
        label_indexes=[0],
        caption_index=0,
    )
    db_records[rec.hash] = rec

    new_db_gen, new_l_gen, new_c_gen = commit_media_and_english_dbs(
        gcs,
        cli_settings,
        db_records,
        db_gen,
        en_labels,
        labels_gen,
        en_captions,
        captions_gen,
    )
    assert (new_db_gen, new_l_gen, new_c_gen) == (1, 1, 1)
    assert MEDIA_DB_FILENAME in data_bkt.objects

    translated = sync_target_language_dictionaries(
        gcs,
        cli_settings,
        en_labels,
        en_captions,
        translator=fake_translator,
        target_lang="it",
    )
    assert translated == 2
    assert f"it_{LABELS_DB_SUFFIX}" in data_bkt.objects
    assert f"it_{CAPTIONS_DB_SUFFIX}" in data_bkt.objects


def test_create_ai_provider_passes_settings_to_loader(
    cli_settings: PhotosphereSettings,
) -> None:
    called: dict[str, Any] = {}

    def fake_loader(*args: Any, **kwargs: Any) -> Any:
        called["args"] = args
        called["kwargs"] = kwargs
        return "provider"

    res = create_ai_provider(cli_settings, loader=fake_loader)
    assert res == "provider"
    assert called["kwargs"]["cache_dir"] == cli_settings.cache_dir
    assert called["kwargs"]["offline"] is False
