"""End-to-end Photosphere v3 ingestion, deduplication, and dual-bucket sync."""

from __future__ import annotations

import mimetypes
import tempfile
import time
from pathlib import Path
from typing import Literal

import structlog
from PIL import Image
from pydantic import BaseModel, Field

from photosphere.ai.protocol import (
    AIProvider,
    analyze_with_retry,
    load_optional_ai_provider,
    release_ai_provider,
)
from photosphere.ai.translator import EasyNMTTranslator, KeyValueStore
from photosphere.config import PhotosphereSettings, RoutingMode
from photosphere.dedup.hashing import PerceptualHashIndex, find_similar_annotated_record
from photosphere.dedup.skipped import SkippedManager, SkipReason
from photosphere.media.base import (
    MediaDecodeError,
    MediaMetadata,
    classify_media_type,
    compute_sha1,
)
from photosphere.media.image import ImageProcessor
from photosphere.media.video import VideoProcessor
from photosphere.models.database import (
    FileType,
    MediaRecord,
)
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
from photosphere.progress import tqdm_progress, truncate_label
from photosphere.storage.checkpoint import CheckpointEntry, CheckpointStore
from photosphere.storage.gcs_client import GCSStorageClient

logger = structlog.get_logger(__name__)

__all__ = [
    "CAPTIONS_DB_SUFFIX",
    "LABELS_DB_SUFFIX",
    "MEDIA_DB_FILENAME",
    "IngestPipeline",
    "IngestSummary",
    "PlannedUpload",
]


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


CHRONOLOGICAL_RESULT_PREFIX = "result"


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
    return (
        f"{CHRONOLOGICAL_RESULT_PREFIX}/"
        f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{metadata.source_path.name}"
    )


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
        return load_remote_media_db(self.gcs, self.settings, init_db=init_db)

    def _load_kv_store(
        self, object_name: str, *, allow_missing: bool
    ) -> tuple[KeyValueStore, int | None]:
        return load_remote_kv_store(
            self.gcs, self.settings, object_name, allow_missing=allow_missing
        )

    def _resolve_ai_provider(self) -> AIProvider:
        if self.ai_provider is None:
            self.ai_provider = create_ai_provider(
                self.settings, loader=load_optional_ai_provider
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
        hash_index: PerceptualHashIndex | None = None,
        ai_image: Image.Image | None = None,
    ) -> tuple[list[int], int | None]:
        dedup_started = time.perf_counter()
        similar = (
            hash_index.find_similar(metadata.average_hash)
            if hash_index is not None
            else find_similar_annotated_record(
                metadata.average_hash, db_records.values()
            )
        )
        dedup_ms = (time.perf_counter() - dedup_started) * 1000
        if similar is not None:
            summary.reused_annotations += 1
            logger.debug(
                "ingest_annotation_reused",
                source_path=str(metadata.source_path),
                dedup_ms=round(dedup_ms, 1),
            )
            return list(similar.label_indexes), similar.caption_index

        if no_ai:
            return [], None

        provider = self._resolve_ai_provider()
        target_image = (
            metadata.source_path
            if metadata.file_type == FileType.IMAGE
            else (metadata.thumbnail_path or metadata.source_path)
        )
        ai_started = time.perf_counter()
        annotation, retries_used = analyze_with_retry(
            provider,
            target_image,
            image=ai_image if metadata.file_type == FileType.IMAGE else None,
            max_retries=self.settings.ai_max_retries,
            device=self.settings.device,
            sha1=metadata.sha1,
            file_type=metadata.file_type.value,
        )
        ai_ms = (time.perf_counter() - ai_started) * 1000
        logger.debug(
            "ingest_ai_stage_completed",
            source_path=str(metadata.source_path),
            dedup_ms=round(dedup_ms, 1),
            ai_ms=round(ai_ms, 1),
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

    def _extract_media_or_skip(
        self,
        file_path: Path,
        input_dir: Path,
        media_type: FileType,
        thumb_dir: Path,
        *,
        sha1: str,
        dry_run: bool,
        summary: IngestSummary,
        generate_thumbnail: bool = True,
        extract_exif: bool = True,
        ai_max_image_size: int | None = None,
    ) -> tuple[MediaMetadata | None, Image.Image | None]:
        decode_started = time.perf_counter()
        try:
            if media_type == FileType.IMAGE:
                metadata, ai_image = self.image_processor.process_for_ingest(
                    file_path,
                    thumb_dir,
                    sha1=sha1,
                    generate_thumbnail=generate_thumbnail,
                    extract_exif=extract_exif,
                    ai_max_image_size=ai_max_image_size,
                )
            else:
                metadata = self.video_processor.process(file_path, thumb_dir, sha1=sha1)
                ai_image = None
        except MediaDecodeError as exc:
            logger.warning(
                "media_processing_failed",
                source_path=str(file_path),
                sha1=sha1,
                error=str(exc),
            )
            if dry_run:
                summary.planned_uploads.append(
                    PlannedUpload(source_path=str(file_path), action="skip_unsupported")
                )
            else:
                self.skipped.move_to_skipped(
                    file_path, "processing_error", sha1, source_root=input_dir
                )
            summary.skipped_unsupported += 1
            return None, None
        logger.debug(
            "ingest_media_decoded",
            source_path=str(file_path),
            file_type=media_type.value,
            decode_ms=round((time.perf_counter() - decode_started) * 1000, 1),
            generate_thumbnail=generate_thumbnail,
            has_ai_image=ai_image is not None,
        )
        return metadata, ai_image

    def _build_dry_run_preview(
        self,
        metadata: MediaMetadata,
        db_records: dict[str, MediaRecord],
        en_labels: KeyValueStore,
        en_captions: KeyValueStore,
        *,
        preview_ai: bool,
        no_ai: bool,
        summary: IngestSummary,
        hash_index: PerceptualHashIndex | None = None,
        ai_image: Image.Image | None = None,
    ) -> tuple[list[str] | None, str | None]:
        if not preview_ai or no_ai:
            return None, None
        label_indexes, caption_index = self._annotate_novel_media(
            metadata,
            db_records,
            en_labels,
            en_captions,
            no_ai=False,
            summary=summary,
            hash_index=hash_index,
            ai_image=ai_image,
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
        return preview_labels, preview_caption

    def _record_skip_event(
        self,
        file_path: Path,
        input_dir: Path,
        *,
        dry_run: bool,
        action: Literal["skip_unsupported", "skip_duplicate", "skip_collision"],
        reason: SkipReason,
        sha1: str,
        average_hash: str | None = None,
        target_key: str | None = None,
        summary: IngestSummary,
    ) -> None:
        if dry_run:
            summary.planned_uploads.append(
                PlannedUpload(
                    source_path=str(file_path), target_key=target_key, action=action
                )
            )
        else:
            self.skipped.move_to_skipped(
                file_path,
                reason,
                sha1,
                average_hash=average_hash,
                source_root=input_dir,
            )

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
        hash_index: PerceptualHashIndex | None = None,
    ) -> bool:
        """Process one file; return True when a new upload was performed."""
        media_type = classify_media_type(file_path)
        if media_type is None:
            sha1 = "" if dry_run else compute_sha1(file_path)
            self._record_skip_event(
                file_path,
                input_dir,
                dry_run=dry_run,
                action="skip_unsupported",
                reason="unsupported_extension",
                sha1=sha1,
                summary=summary,
            )
            summary.skipped_unsupported += 1
            return False

        sha1 = compute_sha1(file_path)
        is_resumable = not dry_run and sha1 in resumable_sha1s
        is_duplicate = not is_resumable and sha1 in db_records
        need_ai_image = (
            media_type == FileType.IMAGE
            and not is_resumable
            and not is_duplicate
            and not no_ai
        )

        metadata, ai_image = self._extract_media_or_skip(
            file_path,
            input_dir,
            media_type,
            thumb_dir,
            sha1=sha1,
            dry_run=dry_run,
            summary=summary,
            generate_thumbnail=not is_resumable and not is_duplicate,
            extract_exif=not is_duplicate,
            ai_max_image_size=(
                self.settings.ai_max_image_size if need_ai_image else None
            ),
        )
        if metadata is None:
            return False

        try:
            if is_resumable:
                resumable_sha1s.remove(metadata.sha1)
                entry = self.checkpoint.entries[metadata.sha1]
                record = _build_record_from_checkpoint(metadata, entry)
                db_records[metadata.sha1] = record
                if hash_index is not None:
                    hash_index.add(record)
                known_target_uris.add(entry.source_bucket_uri)
                summary.resumed_from_checkpoint += 1
                summary.ingested += 1
                return False

            if is_duplicate:
                self._record_skip_event(
                    file_path,
                    input_dir,
                    dry_run=dry_run,
                    action="skip_duplicate",
                    reason="duplicate_sha1",
                    sha1=metadata.sha1,
                    average_hash=metadata.average_hash,
                    summary=summary,
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
                self._record_skip_event(
                    file_path,
                    input_dir,
                    dry_run=dry_run,
                    action="skip_collision",
                    reason="target_key_collision",
                    sha1=metadata.sha1,
                    average_hash=metadata.average_hash,
                    target_key=source_key,
                    summary=summary,
                )
                summary.skipped_collision += 1
                return False

            known_target_uris.add(source_uri)
            if dry_run:
                preview_labels, preview_caption = self._build_dry_run_preview(
                    metadata,
                    db_records,
                    en_labels,
                    en_captions,
                    preview_ai=preview_ai,
                    no_ai=no_ai,
                    summary=summary,
                    hash_index=hash_index,
                    ai_image=ai_image,
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
                metadata,
                db_records,
                en_labels,
                en_captions,
                no_ai=no_ai,
                summary=summary,
                hash_index=hash_index,
                ai_image=ai_image,
            )
        finally:
            if ai_image is not None:
                ai_image.close()

        source_uri, thumb_uri = self._upload_media_pair(metadata, source_key)
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

        record = MediaRecord(
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
        db_records[metadata.sha1] = record
        if hash_index is not None:
            hash_index.add(record)
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
        return commit_media_and_english_dbs(
            self.gcs,
            self.settings,
            db_records,
            db_gen,
            en_labels,
            en_labels_gen,
            en_captions,
            en_captions_gen,
        )

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
            summary.translated_entries += sync_target_language_dictionaries(
                self.gcs,
                self.settings,
                en_labels,
                en_captions,
                translator=self.translator,
                target_lang=target_lang,
                show_progress=show_progress,
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
        hash_index = PerceptualHashIndex.from_records(db_records.values())

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
                        hash_index=hash_index,
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
