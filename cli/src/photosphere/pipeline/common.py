"""Shared database sync, AI provider, and translation helpers for pipelines."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from photosphere.ai.protocol import AIProvider, load_optional_ai_provider
from photosphere.ai.translator import EasyNMTTranslator, KeyValueStore
from photosphere.config import PhotosphereSettings
from photosphere.models.database import MediaDatabase, MediaRecord
from photosphere.storage.gcs_client import GCSStorageClient

MEDIA_DB_FILENAME = "photosphere_database_cloud.json"
LABELS_DB_SUFFIX = "photosphere_image_labelling_database_cloud.json"
CAPTIONS_DB_SUFFIX = "photosphere_image_caption_database_cloud.json"
ALBUMS_DB_FILENAME = "photosphere_albums.json"


def create_ai_provider(
    settings: PhotosphereSettings,
    *,
    loader: Callable[..., AIProvider] = load_optional_ai_provider,
) -> AIProvider:
    """Instantiate the configured vision AI provider from runtime settings."""
    return loader(
        settings.device,
        dtype=settings.ai_dtype,
        cache_dir=settings.models_dir,
        max_image_size=settings.ai_max_image_size,
        provider_mode=settings.ai_provider,
        api_url=settings.ai_api_url,
        api_key=settings.ai_api_key,
        api_timeout=settings.ai_api_timeout,
        offline=settings.ai_offline,
    )


def load_remote_media_db(
    gcs: GCSStorageClient,
    settings: PhotosphereSettings,
    *,
    init_db: bool,
) -> tuple[dict[str, MediaRecord], int | None]:
    """Download and validate photosphere_database_cloud.json from GCS."""
    raw_db, generation = gcs.download_json(
        settings.data_bucket, MEDIA_DB_FILENAME, init_db=init_db
    )
    if raw_db is None:
        return {}, generation
    validated = MediaDatabase.model_validate(raw_db)
    return dict(validated.root), generation


def load_remote_kv_store(
    gcs: GCSStorageClient,
    settings: PhotosphereSettings,
    object_name: str,
    *,
    allow_missing: bool,
    flush: bool = True,
) -> tuple[KeyValueStore, int | None]:
    """Download a JSON dictionary from GCS into a local KeyValueStore."""
    local_path = settings.cache_dir / object_name
    raw, gen = gcs.download_json(
        settings.data_bucket, object_name, init_db=allow_missing
    )
    mapping = raw if isinstance(raw, dict) else None
    store = KeyValueStore.from_mapping(local_path, mapping, flush=flush)
    return store, gen


def commit_media_and_english_dbs(
    gcs: GCSStorageClient,
    settings: PhotosphereSettings,
    db_records: dict[str, MediaRecord],
    db_gen: int | None,
    en_labels: KeyValueStore,
    en_labels_gen: int | None,
    en_captions: KeyValueStore,
    en_captions_gen: int | None,
) -> tuple[int | None, int | None, int | None]:
    """Flush en_* dictionaries, validate media_db, and upload atomically to GCS."""
    serialized_db: dict[str, Any] = {
        sha1: rec.model_dump(mode="json") for sha1, rec in db_records.items()
    }
    MediaDatabase.model_validate(serialized_db)
    en_labels.flush_to_disk()
    en_captions.flush_to_disk()
    new_labels_gen = gcs.upload_json_atomic(
        settings.data_bucket,
        f"en_{LABELS_DB_SUFFIX}",
        en_labels.store,
        if_generation_match=en_labels_gen if en_labels_gen is not None else 0,
    )
    new_captions_gen = gcs.upload_json_atomic(
        settings.data_bucket,
        f"en_{CAPTIONS_DB_SUFFIX}",
        en_captions.store,
        if_generation_match=en_captions_gen if en_captions_gen is not None else 0,
    )
    new_db_gen = gcs.upload_json_atomic(
        settings.data_bucket,
        MEDIA_DB_FILENAME,
        serialized_db,
        if_generation_match=db_gen if db_gen is not None else 0,
    )
    return new_db_gen, new_labels_gen, new_captions_gen


def sync_target_language_dictionaries(
    gcs: GCSStorageClient,
    settings: PhotosphereSettings,
    en_labels: KeyValueStore,
    en_captions: KeyValueStore,
    *,
    translator: EasyNMTTranslator | None = None,
    target_lang: str | None = None,
    show_progress: bool = True,
) -> int:
    """Translate missing en_ label/caption entries into target_lang and upload."""
    lang = target_lang or settings.target_lang
    active_translator = translator or EasyNMTTranslator(
        settings.models_dir / "easynmt",
        offline=settings.ai_offline,
    )
    tgt_labels, tgt_l_gen = load_remote_kv_store(
        gcs, settings, f"{lang}_{LABELS_DB_SUFFIX}", allow_missing=True
    )
    tgt_captions, tgt_c_gen = load_remote_kv_store(
        gcs, settings, f"{lang}_{CAPTIONS_DB_SUFFIX}", allow_missing=True
    )

    translated_count = 0
    if isinstance(active_translator, EasyNMTTranslator):
        translated_count += active_translator.translate_missing_entries(
            en_labels, tgt_labels, lang, show_progress=show_progress
        )
        translated_count += active_translator.translate_missing_entries(
            en_captions, tgt_captions, lang, show_progress=show_progress
        )
    else:
        translated_count += active_translator.translate_missing_entries(
            en_labels, tgt_labels, lang
        )
        translated_count += active_translator.translate_missing_entries(
            en_captions, tgt_captions, lang
        )

    tgt_labels.flush_to_disk()
    tgt_captions.flush_to_disk()
    gcs.upload_json_atomic(
        settings.data_bucket,
        f"{lang}_{LABELS_DB_SUFFIX}",
        tgt_labels.store,
        if_generation_match=tgt_l_gen if tgt_l_gen is not None else 0,
    )
    gcs.upload_json_atomic(
        settings.data_bucket,
        f"{lang}_{CAPTIONS_DB_SUFFIX}",
        tgt_captions.store,
        if_generation_match=tgt_c_gen if tgt_c_gen is not None else 0,
    )
    return translated_count
