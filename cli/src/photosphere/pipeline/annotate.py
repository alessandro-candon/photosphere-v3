"""Backfill AI tags and captions for unannotated Photosphere media records."""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from pydantic import BaseModel

from photosphere.ai.protocol import (
    AIProvider,
    analyze_with_retry,
    release_ai_provider,
)
from photosphere.ai.translator import EasyNMTTranslator, KeyValueStore
from photosphere.config import PhotosphereSettings
from photosphere.dedup.hashing import find_similar_annotated_record
from photosphere.models.database import FileType, MediaRecord
from photosphere.pipeline.common import (
    CAPTIONS_DB_SUFFIX,
    LABELS_DB_SUFFIX,
    commit_media_and_english_dbs,
    create_ai_provider,
    load_remote_kv_store,
    load_remote_media_db,
    sync_target_language_dictionaries,
)
from photosphere.progress import tqdm_progress
from photosphere.storage.gcs_client import GCSStorageClient

logger = structlog.get_logger(__name__)


class AnnotateSummary(BaseModel):
    """Execution counters returned by AnnotatePipeline.run."""

    dry_run: bool = False
    total_records: int = 0
    candidates: int = 0
    reused_annotations: int = 0
    ai_annotated: int = 0
    ai_retried: int = 0
    ai_failed: int = 0
    skipped_missing_media: int = 0
    periodic_commits: int = 0
    translated_entries: int = 0


def _parse_gs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got {uri!r}")
    bucket, _, object_name = uri[5:].partition("/")
    if not bucket or not object_name:
        raise ValueError(f"Malformed gs:// URI: {uri!r}")
    return bucket, object_name


def _needs_annotation(record: MediaRecord, *, include_partial: bool) -> bool:
    if include_partial:
        return not record.label_indexes or record.caption_index is None
    return not record.label_indexes and record.caption_index is None


class AnnotatePipeline:
    """Backfill tags and captions onto existing unannotated GCS media records."""

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

    def _resolve_ai_provider(self) -> AIProvider:
        if self.ai_provider is None:
            self.ai_provider = create_ai_provider(self.settings)
        return self.ai_provider

    def _load_kv_store(
        self, filename: str, *, allow_missing: bool
    ) -> tuple[KeyValueStore, int | None]:
        return load_remote_kv_store(
            self.gcs, self.settings, filename, allow_missing=allow_missing
        )

    def _commit_databases(
        self,
        db_records: dict[str, MediaRecord],
        db_gen: int | None,
        en_labels: KeyValueStore,
        en_labels_gen: int | None,
        en_captions: KeyValueStore,
        en_captions_gen: int | None,
    ) -> tuple[int | None, int | None, int | None]:
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

    def _resolve_input_image(
        self,
        record: MediaRecord,
        temp_dir: Path,
        *,
        local_media_dir: Path | None,
        use_source_bucket: bool,
    ) -> Path | None:
        _, source_obj = _parse_gs_uri(record.source_bucket_uri)
        if local_media_dir is not None and record.file_type == FileType.IMAGE:
            for candidate in (
                local_media_dir / source_obj,
                local_media_dir / Path(source_obj).name,
            ):
                if candidate.is_file():
                    return candidate

        target_uri = (
            record.source_bucket_uri
            if use_source_bucket and record.file_type == FileType.IMAGE
            else (record.thumbnail_bucket_uri or record.source_bucket_uri)
        )
        bucket, obj_name = _parse_gs_uri(target_uri)
        dest = temp_dir / f"{record.hash}_{Path(obj_name).name}"
        try:
            return self.gcs.download_blob(bucket, obj_name, dest)
        except Exception as exc:
            logger.warning(
                "annotate_download_failed",
                sha1=record.hash,
                uri=target_uri,
                error=str(exc),
            )
            return None

    def _run_translation(
        self,
        en_labels: KeyValueStore,
        en_captions: KeyValueStore,
        *,
        summary: AnnotateSummary,
        show_progress: bool = True,
    ) -> None:
        target_lang = self.settings.target_lang
        if target_lang == "en" or (
            self.translator is None and summary.ai_annotated == 0
        ):
            return
        summary.translated_entries += sync_target_language_dictionaries(
            self.gcs,
            self.settings,
            en_labels,
            en_captions,
            translator=self.translator,
            target_lang=target_lang,
            show_progress=show_progress,
        )

    def _annotate_record(
        self,
        record: MediaRecord,
        db_records: dict[str, MediaRecord],
        en_labels: KeyValueStore,
        en_captions: KeyValueStore,
        temp_dir: Path,
        *,
        local_media_dir: Path | None,
        use_source_bucket: bool,
        summary: AnnotateSummary,
    ) -> bool:
        similar = find_similar_annotated_record(
            record.average_hash, db_records.values()
        )
        if similar is not None:
            if not record.label_indexes:
                record.label_indexes = list(similar.label_indexes)
            if record.caption_index is None:
                record.caption_index = similar.caption_index
            summary.reused_annotations += 1
            return True

        input_path = self._resolve_input_image(
            record,
            temp_dir,
            local_media_dir=local_media_dir,
            use_source_bucket=use_source_bucket,
        )
        if input_path is None:
            summary.skipped_missing_media += 1
            return False

        provider = self._resolve_ai_provider()
        annotation, retries_used = analyze_with_retry(
            provider,
            input_path,
            max_retries=self.settings.ai_max_retries,
            device=self.settings.device,
            sha1=record.hash,
            file_type=record.file_type.value,
        )
        summary.ai_retried += retries_used
        if annotation is None:
            summary.ai_failed += 1
            return False

        if not record.label_indexes and annotation.labels:
            record.label_indexes = en_labels.add_unique_multiple_values(
                annotation.labels
            )
        if record.caption_index is None and annotation.caption:
            record.caption_index = en_captions.add_unique_value(annotation.caption)
        summary.ai_annotated += 1
        return True

    def run(
        self,
        *,
        local_media_dir: Path | None = None,
        use_source_bucket: bool = False,
        include_partial: bool = False,
        commit_every: int = 100,
        limit: int | None = None,
        dry_run: bool = False,
        show_progress: bool = True,
    ) -> AnnotateSummary:
        """Backfill AI labels and captions for unannotated records in GCS."""
        self.gcs.verify_bucket_classes(
            self.settings.media_bucket,
            self.settings.data_bucket,
            expected_media_class=self.settings.media_storage_class,
            expected_data_class=self.settings.data_storage_class,
            strict=not dry_run,
        )
        db_records, db_gen = load_remote_media_db(
            self.gcs, self.settings, init_db=False
        )
        en_labels, en_labels_gen = self._load_kv_store(
            f"en_{LABELS_DB_SUFFIX}", allow_missing=True
        )
        en_captions, en_captions_gen = self._load_kv_store(
            f"en_{CAPTIONS_DB_SUFFIX}", allow_missing=True
        )

        candidates = [
            record
            for record in db_records.values()
            if _needs_annotation(record, include_partial=include_partial)
        ]
        if limit is not None:
            candidates = candidates[:limit]

        summary = AnnotateSummary(
            dry_run=dry_run,
            total_records=len(db_records),
            candidates=len(candidates),
        )
        if dry_run or not candidates:
            logger.info("annotate_finished", **summary.model_dump())
            return summary

        uncommitted = 0
        with tempfile.TemporaryDirectory(prefix="photosphere_annotate_") as tmp_dir_str:
            temp_dir = Path(tmp_dir_str)
            with tqdm_progress(
                candidates,
                desc="Annotate",
                unit="item",
                total=len(candidates),
                enabled=show_progress,
            ) as pbar:
                for record in pbar:
                    pbar.set_postfix_str(record.hash[:10], refresh=True)
                    updated = self._annotate_record(
                        record,
                        db_records,
                        en_labels,
                        en_captions,
                        temp_dir,
                        local_media_dir=local_media_dir,
                        use_source_bucket=use_source_bucket,
                        summary=summary,
                    )
                    pbar.set_postfix(
                        ok=summary.ai_annotated,
                        reused=summary.reused_annotations,
                        err=summary.ai_failed,
                        refresh=False,
                    )
                    if not updated:
                        continue
                    uncommitted += 1
                    if uncommitted >= commit_every:
                        db_gen, en_labels_gen, en_captions_gen = self._commit_databases(
                            db_records,
                            db_gen,
                            en_labels,
                            en_labels_gen,
                            en_captions,
                            en_captions_gen,
                        )
                        uncommitted = 0
                        summary.periodic_commits += 1

        if uncommitted > 0:
            db_gen, en_labels_gen, en_captions_gen = self._commit_databases(
                db_records,
                db_gen,
                en_labels,
                en_labels_gen,
                en_captions,
                en_captions_gen,
            )

        release_ai_provider(self.ai_provider)
        self._run_translation(
            en_labels, en_captions, summary=summary, show_progress=show_progress
        )
        logger.info("annotate_finished", **summary.model_dump())
        return summary
