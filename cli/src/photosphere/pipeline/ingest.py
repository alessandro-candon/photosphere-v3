"""End-to-end Photosphere v3 ingestion, deduplication, and dual-bucket sync."""

from __future__ import annotations

import mimetypes
import tempfile
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from photosphere.ai.protocol import (
    AIProvider,
    analyze_with_retry,
    load_optional_ai_provider,
    release_ai_provider,
)
from photosphere.ai.translator import EasyNMTTranslator, KeyValueStore
from photosphere.config import PhotosphereSettings, RoutingMode
from photosphere.dedup.hashing import find_similar_annotated_record
from photosphere.dedup.skipped import SkippedManager
from photosphere.media.base import MediaMetadata, classify_media_type, compute_sha1
from photosphere.media.image import ImageProcessor
from photosphere.media.video import VideoProcessor
from photosphere.models.database import (
    FileType,
    MediaDatabase,
    MediaRecord,
)
from photosphere.progress import tqdm_progress, truncate_label
from photosphere.storage.checkpoint import CheckpointEntry, CheckpointStore
from photosphere.storage.gcs_client import GCSStorageClient

logger = structlog.get_logger(__name__)

MEDIA_DB_FILENAME = "photosphere_database_cloud.json"
LABELS_DB_SUFFIX = "photosphere_image_labelling_database_cloud.json"
CAPTIONS_DB_SUFFIX = "photosphere_image_caption_database_cloud.json"


class PlannedUpload(BaseModel):
    """Planned action and destination key emitted during --dry-run."""

    source_path: str
    target_key: str | None = None
    action: Literal["upload", "skip_unsupported", "skip_duplicate", "skip_collision"]
    labels: list[str] | None = None
    caption: str | None = None


class IngestSummary(BaseModel):
    """Execution counters and dry-run preview returned by IngestPipeline.run."""

    routing_mode: RoutingMode = "chronological"
    dry_run: bool = False
    scanned: int = 0
    ingested: int = 0
    skipped_unsupported: int = 0
    skipped_duplicate: int = 0
    skipped_collision: int = 0
    reused_annotations: int = 0
    ai_annotated: int = 0
    ai_retried: int = 0
    ai_failed: int = 0
    resumed_from_checkpoint: int = 0
    periodic_commits: int = 0
    translated_entries: int = 0
    planned_uploads: list[PlannedUpload] = Field(default_factory=list)


def _build_remote_object_key(
    metadata: MediaMetadata,
    input_dir: Path,
    settings: PhotosphereSettings,
    routing_mode: RoutingMode = "chronological",
) -> str:
    if routing_mode == "preserve":
        try:
            return (
                metadata.source_path.resolve()
                .relative_to(input_dir.resolve())
                .as_posix()
            )
        except ValueError:
            # Fall back to logical path when symlinks point outside input_dir.
            return metadata.source_path.relative_to(input_dir).as_posix()
    if metadata.created_at is None:
        return f"{settings.missing_date_prefix}/{metadata.source_path.name}"
    dt = metadata.created_at
    return f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{metadata.source_path.name}"


def _build_record_from_checkpoint(
    metadata: MediaMetadata,
    entry: CheckpointEntry,
) -> MediaRecord:
    return MediaRecord(
        hash=metadata.sha1,
        average_hash=metadata.average_hash,
        source_bucket_uri=entry.source_bucket_uri,
        thumbnail_bucket_uri=entry.thumbnail_bucket_uri,
        file_type=metadata.file_type,
        created_at=metadata.created_at.isoformat() if metadata.created_at else None,
        created_at_timestamp=metadata.created_at_timestamp,
        latitude=metadata.latitude,
        longitude=metadata.longitude,
        geohash=metadata.geohash,
        label_indexes=entry.label_indexes,
        caption_index=entry.caption_index,
    )


class IngestPipeline:
    """Coordinate scanning, skipped/ isolation, hashing, AI, and GCS sync."""

    def __init__(
        self,
        settings: PhotosphereSettings,
        gcs_client: GCSStorageClient,
        ai_provider: AIProvider | None = None,
        translator: EasyNMTTranslator | None = None,
    ) -> None:
        self.settings = settings
        self.gcs = gcs_client
        self.ai_provider = ai_provider
        self.translator = translator
        self.image_processor = ImageProcessor()
        self.video_processor = VideoProcessor()
        self.skipped = SkippedManager(
            settings.skipped_dir, settings.skipped_manifest_path
        )
        self.checkpoint = CheckpointStore(settings.checkpoint_path)

    def _load_remote_db(
        self, *, init_db: bool
    ) -> tuple[dict[str, MediaRecord], int | None]:
        raw_db, generation = self.gcs.download_json(
            self.settings.data_bucket, MEDIA_DB_FILENAME, init_db=init_db
        )
        if raw_db is None:
            return {}, generation
        validated = MediaDatabase.model_validate(raw_db)
        return dict(validated.root), generation

    def _load_kv_store(
        self, object_name: str, *, allow_missing: bool
    ) -> tuple[KeyValueStore, int | None]:
        local_path = self.settings.cache_dir / object_name
        raw, gen = self.gcs.download_json(
            self.settings.data_bucket, object_name, init_db=allow_missing
        )
        store = KeyValueStore(local_path)
        if isinstance(raw, dict):
            store.store = {str(k): str(v) for k, v in raw.items()}
            store.next_index = max((int(k) for k in store.store), default=-1) + 1
            store.flush_to_disk()
        return store, gen

    def _resolve_ai_provider(self) -> AIProvider:
        if self.ai_provider is None:
            self.ai_provider = load_optional_ai_provider(
                self.settings.device,
                cache_dir=self.settings.cache_dir,
                max_image_size=self.settings.ai_max_image_size,
                provider_mode=self.settings.ai_provider,
                api_url=self.settings.ai_api_url,
                api_key=self.settings.ai_api_key,
                api_timeout=self.settings.ai_api_timeout,
                offline=self.settings.ai_offline,
            )
        return self.ai_provider

    def _annotate_novel_media(
        self,
        metadata: MediaMetadata,
        db_records: dict[str, MediaRecord],
        en_labels: KeyValueStore,
        en_captions: KeyValueStore,
        *,
        no_ai: bool,
        summary: IngestSummary,
    ) -> tuple[list[int], int | None]:
        similar = find_similar_annotated_record(
            metadata.average_hash, db_records.values()
        )
        if similar is not None:
            summary.reused_annotations += 1
            return list(similar.label_indexes), similar.caption_index

        if no_ai:
            return [], None

        provider = self._resolve_ai_provider()
        target_image = (
            metadata.source_path
            if metadata.file_type == FileType.IMAGE
            else (metadata.thumbnail_path or metadata.source_path)
        )
        annotation, retries_used = analyze_with_retry(
            provider,
            target_image,
            max_retries=self.settings.ai_max_retries,
            device=self.settings.device,
            sha1=metadata.sha1,
            file_type=metadata.file_type.value,
        )
        summary.ai_retried += retries_used
        if annotation is None:
            summary.ai_failed += 1
            return [], None

        summary.ai_annotated += 1
        label_indexes = en_labels.add_unique_multiple_values(annotation.labels)
        caption_index = (
            en_captions.add_unique_value(annotation.caption)
            if annotation.caption
            else None
        )
        return label_indexes, caption_index

    def _upload_media_pair(
        self,
        metadata: MediaMetadata,
        source_key: str,
    ) -> tuple[str, str | None]:
        mime, _ = mimetypes.guess_type(metadata.source_path.name)
        source_uri = self.gcs.upload_blob(
            self.settings.media_bucket,
            metadata.source_path,
            source_key,
            content_type=mime,
            if_generation_match=0,
        )
        thumb_uri: str | None = None
        if metadata.thumbnail_path is not None and metadata.thumbnail_path.exists():
            thumb_key = f"thumbnails/{metadata.thumbnail_path.name}"
            thumb_uri = self.gcs.upload_blob(
                self.settings.media_bucket,
                metadata.thumbnail_path,
                thumb_key,
                content_type="image/jpeg",
            )
        return source_uri, thumb_uri

    def _process_single_file(
        self,
        file_path: Path,
        input_dir: Path,
        db_records: dict[str, MediaRecord],
        resumable_sha1s: set[str],
        known_target_uris: set[str],
        en_labels: KeyValueStore,
        en_captions: KeyValueStore,
        *,
        routing_mode: RoutingMode,
        no_ai: bool,
        dry_run: bool,
        preview_ai: bool = False,
        thumb_dir: Path,
        summary: IngestSummary,
    ) -> bool:
        """Process one file; return True when a new upload was performed."""
        media_type = classify_media_type(file_path)
        if media_type is None:
            if dry_run:
                summary.planned_uploads.append(
                    PlannedUpload(source_path=str(file_path), action="skip_unsupported")
                )
            else:
                sha1 = compute_sha1(file_path)
                self.skipped.move_to_skipped(
                    file_path, "unsupported_extension", sha1, source_root=input_dir
                )
            summary.skipped_unsupported += 1
            return False

        metadata = (
            self.image_processor.process(file_path, thumb_dir)
            if media_type == FileType.IMAGE
            else self.video_processor.process(file_path, thumb_dir)
        )

        if not dry_run and metadata.sha1 in resumable_sha1s:
            resumable_sha1s.remove(metadata.sha1)
            entry = self.checkpoint.entries[metadata.sha1]
            db_records[metadata.sha1] = _build_record_from_checkpoint(metadata, entry)
            known_target_uris.add(entry.source_bucket_uri)
            summary.resumed_from_checkpoint += 1
            summary.ingested += 1
            return False

        if metadata.sha1 in db_records:
            if dry_run:
                summary.planned_uploads.append(
                    PlannedUpload(source_path=str(file_path), action="skip_duplicate")
                )
            else:
                self.skipped.move_to_skipped(
                    file_path,
                    "duplicate_sha1",
                    metadata.sha1,
                    average_hash=metadata.average_hash,
                    source_root=input_dir,
                )
            summary.skipped_duplicate += 1
            return False

        source_key = _build_remote_object_key(
            metadata, input_dir, self.settings, routing_mode=routing_mode
        )
        source_uri = f"gs://{self.settings.media_bucket}/{source_key}"
        if source_uri in known_target_uris:
            logger.warning(
                "target_key_collision",
                source_path=str(file_path),
                sha1=metadata.sha1,
                target_key=source_key,
                routing_mode=routing_mode,
            )
            if dry_run:
                summary.planned_uploads.append(
                    PlannedUpload(
                        source_path=str(file_path),
                        target_key=source_key,
                        action="skip_collision",
                    )
                )
            else:
                self.skipped.move_to_skipped(
                    file_path,
                    "target_key_collision",
                    metadata.sha1,
                    average_hash=metadata.average_hash,
                    source_root=input_dir,
                )
            summary.skipped_collision += 1
            return False

        known_target_uris.add(source_uri)
        if dry_run:
            preview_labels: list[str] | None = None
            preview_caption: str | None = None
            if preview_ai and not no_ai:
                label_indexes, caption_index = self._annotate_novel_media(
                    metadata,
                    db_records,
                    en_labels,
                    en_captions,
                    no_ai=False,
                    summary=summary,
                )
                preview_labels = [
                    en_labels.store[str(idx)]
                    for idx in label_indexes
                    if str(idx) in en_labels.store
                ]
                preview_caption = (
                    en_captions.store.get(str(caption_index))
                    if caption_index is not None
                    else None
                )
            summary.planned_uploads.append(
                PlannedUpload(
                    source_path=str(file_path),
                    target_key=source_key,
                    action="upload",
                    labels=preview_labels,
                    caption=preview_caption,
                )
            )
            summary.ingested += 1
            return False

        label_indexes, caption_index = self._annotate_novel_media(
            metadata, db_records, en_labels, en_captions, no_ai=no_ai, summary=summary
        )
        source_uri, thumb_uri = self._upload_media_pair(metadata, source_key)
        en_labels.flush_to_disk()
        en_captions.flush_to_disk()
        self.checkpoint.record(
            CheckpointEntry(
                sha1=metadata.sha1,
                routing_mode=routing_mode,
                source_bucket_uri=source_uri,
                thumbnail_bucket_uri=thumb_uri,
                label_indexes=label_indexes,
                caption_index=caption_index,
            )
        )

        db_records[metadata.sha1] = MediaRecord(
            hash=metadata.sha1,
            average_hash=metadata.average_hash,
            source_bucket_uri=source_uri,
            thumbnail_bucket_uri=thumb_uri,
            file_type=metadata.file_type,
            created_at=metadata.created_at.isoformat() if metadata.created_at else None,
            created_at_timestamp=metadata.created_at_timestamp,
            latitude=metadata.latitude,
            longitude=metadata.longitude,
            geohash=metadata.geohash,
            label_indexes=label_indexes,
            caption_index=caption_index,
        )
        summary.ingested += 1
        return True

    def _commit_databases(
        self,
        db_records: dict[str, MediaRecord],
        db_gen: int | None,
        en_labels: KeyValueStore,
        en_labels_gen: int | None,
        en_captions: KeyValueStore,
        en_captions_gen: int | None,
    ) -> tuple[int | None, int | None, int | None]:
        """Flush en_* dicts before media_db and return updated GCS generations."""
        serialized_db: dict[str, Any] = {
            sha1: rec.model_dump(mode="json") for sha1, rec in db_records.items()
        }
        MediaDatabase.model_validate(serialized_db)
        en_labels.flush_to_disk()
        en_captions.flush_to_disk()
        new_en_labels_gen = self.gcs.upload_json_atomic(
            self.settings.data_bucket,
            f"en_{LABELS_DB_SUFFIX}",
            en_labels.store,
            if_generation_match=en_labels_gen if en_labels_gen is not None else 0,
        )
        new_en_captions_gen = self.gcs.upload_json_atomic(
            self.settings.data_bucket,
            f"en_{CAPTIONS_DB_SUFFIX}",
            en_captions.store,
            if_generation_match=en_captions_gen if en_captions_gen is not None else 0,
        )
        new_db_gen = self.gcs.upload_json_atomic(
            self.settings.data_bucket,
            MEDIA_DB_FILENAME,
            serialized_db,
            if_generation_match=db_gen if db_gen is not None else 0,
        )
        return new_db_gen, new_en_labels_gen, new_en_captions_gen

    def _run_translation(
        self,
        en_labels: KeyValueStore,
        en_captions: KeyValueStore,
        *,
        summary: IngestSummary,
        show_progress: bool = True,
    ) -> None:
        target_lang = self.settings.target_lang
        if target_lang != "en" and (
            self.translator is not None or summary.ai_annotated > 0
        ):
            translator = self.translator or EasyNMTTranslator(
                self.settings.cache_dir / "easynmt",
                offline=self.settings.ai_offline,
            )
            tgt_labels, tgt_l_gen = self._load_kv_store(
                f"{target_lang}_{LABELS_DB_SUFFIX}", allow_missing=True
            )
            tgt_captions, tgt_c_gen = self._load_kv_store(
                f"{target_lang}_{CAPTIONS_DB_SUFFIX}", allow_missing=True
            )
            if isinstance(translator, EasyNMTTranslator):
                summary.translated_entries += translator.translate_missing_entries(
                    en_labels, tgt_labels, target_lang, show_progress=show_progress
                )
                summary.translated_entries += translator.translate_missing_entries(
                    en_captions, tgt_captions, target_lang, show_progress=show_progress
                )
            else:
                summary.translated_entries += translator.translate_missing_entries(
                    en_labels, tgt_labels, target_lang
                )
                summary.translated_entries += translator.translate_missing_entries(
                    en_captions, tgt_captions, target_lang
                )
            tgt_labels.flush_to_disk()
            tgt_captions.flush_to_disk()
            self.gcs.upload_json_atomic(
                self.settings.data_bucket,
                f"{target_lang}_{LABELS_DB_SUFFIX}",
                tgt_labels.store,
                if_generation_match=tgt_l_gen if tgt_l_gen is not None else 0,
            )
            self.gcs.upload_json_atomic(
                self.settings.data_bucket,
                f"{target_lang}_{CAPTIONS_DB_SUFFIX}",
                tgt_captions.store,
                if_generation_match=tgt_c_gen if tgt_c_gen is not None else 0,
            )

    def run(
        self,
        input_dir: Path,
        *,
        routing_mode: RoutingMode = "chronological",
        commit_every: int = 100,
        init_db: bool = False,
        no_ai: bool = False,
        dry_run: bool = False,
        preview_ai: bool = False,
        show_progress: bool = True,
    ) -> IngestSummary:
        """Execute full local-to-GCS ingestion pipeline."""
        self.gcs.verify_bucket_classes(
            self.settings.media_bucket,
            self.settings.data_bucket,
            expected_media_class=self.settings.media_storage_class,
            expected_data_class=self.settings.data_storage_class,
            strict=not dry_run,
        )
        if not dry_run:
            self.checkpoint.validate_routing_mode(routing_mode)
        resumable_sha1s = set(self.checkpoint.entries.keys()) if not dry_run else set()

        db_records, db_gen = self._load_remote_db(init_db=init_db)
        en_labels, en_labels_gen = self._load_kv_store(
            f"en_{LABELS_DB_SUFFIX}", allow_missing=init_db
        )
        en_captions, en_captions_gen = self._load_kv_store(
            f"en_{CAPTIONS_DB_SUFFIX}", allow_missing=init_db
        )
        known_target_uris: set[str] = {
            rec.source_bucket_uri
            for rec in db_records.values()
            if rec.source_bucket_uri
        }

        summary = IngestSummary(routing_mode=routing_mode, dry_run=dry_run)
        files = sorted(path for path in input_dir.rglob("*") if path.is_file())
        uncommitted_uploads = 0
        with tempfile.TemporaryDirectory() as tmp_thumb_dir:
            thumb_dir = (
                Path(tmp_thumb_dir)
                if dry_run
                else (self.settings.cache_dir / "thumbnails")
            )
            with tqdm_progress(
                files,
                desc="Ingest",
                unit="file",
                total=len(files),
                enabled=show_progress,
            ) as pbar:
                for file_path in pbar:
                    pbar.set_postfix_str(truncate_label(file_path.name), refresh=True)
                    summary.scanned += 1
                    uploaded = self._process_single_file(
                        file_path,
                        input_dir,
                        db_records,
                        resumable_sha1s,
                        known_target_uris,
                        en_labels,
                        en_captions,
                        routing_mode=routing_mode,
                        no_ai=no_ai or (dry_run and not preview_ai),
                        dry_run=dry_run,
                        preview_ai=preview_ai,
                        thumb_dir=thumb_dir,
                        summary=summary,
                    )
                    skipped = (
                        summary.skipped_unsupported
                        + summary.skipped_duplicate
                        + summary.skipped_collision
                    )
                    pbar.set_postfix(
                        ing=summary.ingested,
                        skip=skipped,
                        err=summary.ai_failed,
                        refresh=False,
                    )
                    if uploaded and not dry_run:
                        uncommitted_uploads += 1
                        if uncommitted_uploads >= commit_every:
                            db_gen, en_labels_gen, en_captions_gen = (
                                self._commit_databases(
                                    db_records,
                                    db_gen,
                                    en_labels,
                                    en_labels_gen,
                                    en_captions,
                                    en_captions_gen,
                                )
                            )
                            self.checkpoint.clear()
                            uncommitted_uploads = 0
                            summary.periodic_commits += 1

        if dry_run and preview_ai:
            release_ai_provider(self.ai_provider)
        elif not dry_run and (
            uncommitted_uploads > 0 or summary.resumed_from_checkpoint > 0 or init_db
        ):
            db_gen, en_labels_gen, en_captions_gen = self._commit_databases(
                db_records,
                db_gen,
                en_labels,
                en_labels_gen,
                en_captions,
                en_captions_gen,
            )
            self.checkpoint.clear()
            release_ai_provider(self.ai_provider)
            self._run_translation(
                en_labels, en_captions, summary=summary, show_progress=show_progress
            )

        logger.info("ingest_finished", **summary.model_dump())
        return summary
