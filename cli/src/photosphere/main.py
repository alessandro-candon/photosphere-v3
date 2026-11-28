"""Photosphere v3 Click CLI entrypoint."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, cast

import click
import structlog

from photosphere import __version__
from photosphere.ai.moondream2 import Moondream2Provider
from photosphere.ai.protocol import (
    AINotConfiguredError,
    configure_hf_cache_env,
    resolve_device,
)
from photosphere.ai.translator import EasyNMTTranslator
from photosphere.config import (
    DEFAULT_PROFILE,
    ConfigFileError,
    PhotosphereSettings,
    RoutingMode,
    normalize_profile_name,
    profile_display_name,
    resolve_photosphere_config_path,
)
from photosphere.init.command import init_command
from photosphere.models.database import AlbumRecord, KeyValueDictionary, MediaDatabase
from photosphere.pipeline.annotate import AnnotatePipeline
from photosphere.pipeline.common import (
    ALBUMS_DB_FILENAME,
    CAPTIONS_DB_SUFFIX,
    LABELS_DB_SUFFIX,
    MEDIA_DB_FILENAME,
    load_remote_kv_store,
)
from photosphere.pipeline.ingest import IngestPipeline
from photosphere.progress import tqdm_logger_factory
from photosphere.storage.checkpoint import CheckpointModeMismatchError
from photosphere.storage.gcs_client import (
    GCSStorageClient,
    StorageSyncError,
    resolve_credentials_source,
)


def _configure_logging(*, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=tqdm_logger_factory(file=sys.__stderr__),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
    )


_SKIP_PROFILE_PROMPT_COMMANDS = {"version", "prefetch-models"}


def _is_interactive_tty() -> bool:
    """Return True when stdin is attached to an interactive terminal."""
    return sys.stdin.isatty()


@click.group()
@click.option(
    "--profile",
    default=DEFAULT_PROFILE,
    envvar="PHOTOSPHERE_PROFILE",
    show_default=True,
    help="Profile name for isolated config, thumbnails, checkpoints, and DB snapshots.",
)
@click.option(
    "-y",
    "--yes",
    "assume_yes",
    is_flag=True,
    help="Auto-confirm the active profile prompt.",
)
@click.option(
    "--config-file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to photosphere.config.json (overrides default discovery).",
)
@click.option(
    "--creds",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to GCP service-account or authorized-user JSON credentials.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable debug logging.",
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Disable tqdm progress bars on stderr.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    profile: str,
    assume_yes: bool,
    config_file: Path | None,
    creds: Path | None,
    verbose: bool,
    no_progress: bool,
) -> None:
    """Photosphere v3 CLI for project bootstrap, media ingestion, AI, and DB checks."""
    _configure_logging(verbose=verbose)
    try:
        normalized_profile = normalize_profile_name(profile)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="'--profile'") from exc
    ctx.ensure_object(dict)
    ctx.obj["profile"] = normalized_profile
    ctx.obj["assume_yes"] = assume_yes
    ctx.obj["config_path"] = config_file
    ctx.obj["credentials_path"] = creds
    ctx.obj["show_progress"] = not no_progress

    subcommand = ctx.invoked_subcommand
    is_non_interactive_init = (
        subcommand == "init" and "--non-interactive" in sys.argv[1:]
    )
    if (
        subcommand is not None
        and subcommand not in _SKIP_PROFILE_PROMPT_COMMANDS
        and not assume_yes
        and not is_non_interactive_init
        and _is_interactive_tty()
    ):
        display = profile_display_name(normalized_profile)
        if not click.confirm(
            f'Do you want to continue with profile "{display}"?', default=True
        ):
            raise click.Abort()


cli.add_command(init_command, name="init")


@cli.command()
def version() -> None:
    """Print the installed Photosphere CLI version."""
    click.echo(f"photosphere {__version__}")


def _require_settings(
    ctx: click.Context | None = None, **overrides: Any
) -> PhotosphereSettings:
    config_path: Path | None = (
        ctx.obj.get("config_path") if ctx is not None and ctx.obj else None
    )
    profile: str | None = (
        ctx.obj.get("profile") if ctx is not None and ctx.obj else None
    )
    try:
        return PhotosphereSettings.require_runtime_config(
            config_path=config_path, profile=profile, **overrides
        )
    except ConfigFileError as exc:
        raise click.ClickException(str(exc)) from exc


_F = TypeVar("_F", bound=Callable[..., Any])


def _ai_runtime_options(func: _F) -> _F:
    """Attach shared AI runtime Click options to ingest and annotate commands."""
    for decorator in (
        click.option(
            "--offline",
            is_flag=True,
            help=(
                "Load AI and translation models strictly from local cache "
                "without contacting huggingface.co."
            ),
        ),
        click.option(
            "--ai-api-url",
            default=None,
            help=(
                "Base URL for remote Moondream HTTP API "
                "(overrides PHOTOSPHERE_AI_API_URL)."
            ),
        ),
        click.option(
            "--ai-provider",
            type=click.Choice(["local", "remote"], case_sensitive=False),
            default=None,
            help="Vision AI backend: local (MPS/CUDA/CPU) or remote HTTP API.",
        ),
        click.option(
            "--device",
            type=click.Choice(["auto", "cuda", "mps", "cpu"], case_sensitive=False),
            default=None,
            help=(
                "Compute device override for local AI inference (auto, cuda, mps, cpu)."
            ),
        ),
    ):
        func = decorator(func)
    return func


def _build_ai_overrides(
    *,
    device: str | None,
    ai_provider: str | None,
    ai_api_url: str | None,
    offline: bool,
) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if device is not None:
        overrides["device"] = device.lower()
    if ai_provider is not None:
        overrides["ai_provider"] = ai_provider.lower()
    if ai_api_url is not None:
        overrides["ai_api_url"] = ai_api_url
    if offline:
        overrides["ai_offline"] = True
    return overrides


def _build_gcs_client(
    ctx: click.Context | None, settings: PhotosphereSettings
) -> GCSStorageClient:
    credentials_path: Path | None = (
        ctx.obj.get("credentials_path") if ctx is not None and ctx.obj else None
    )
    try:
        return GCSStorageClient(
            project=settings.gcp_project_id,
            credentials_path=credentials_path,
        )
    except StorageSyncError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.argument(
    "input_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--routing-mode",
    type=click.Choice(["chronological", "preserve"], case_sensitive=False),
    default="chronological",
    show_default=True,
    help=(
        "Cloud path layout: chronological (result/YYYY/MM/DD/<file> or "
        "no_datetime/<file>) or preserve (relative path)."
    ),
)
@click.option(
    "--commit-every",
    type=click.IntRange(min=1),
    default=100,
    show_default=True,
    help="Commit media and English label/caption DBs to GCS every N new uploads.",
)
@click.option(
    "--init-db",
    is_flag=True,
    help="Allow initializing empty JSON databases on 404.",
)
@click.option(
    "--no-ai",
    is_flag=True,
    help="Skip AI labeling/captioning during ingestion.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help=(
        "Preview planned GCS keys and collisions without uploading, "
        "moving files, or running AI."
    ),
)
@click.option(
    "--preview-ai",
    is_flag=True,
    help="Run AI tagging/captioning during --dry-run and show results in JSON output.",
)
@_ai_runtime_options
@click.pass_context
def ingest(
    ctx: click.Context,
    input_dir: Path,
    routing_mode: str,
    commit_every: int,
    init_db: bool,
    no_ai: bool,
    device: str | None,
    ai_provider: str | None,
    ai_api_url: str | None,
    dry_run: bool,
    preview_ai: bool,
    offline: bool,
) -> None:
    """Scan INPUT_DIR, isolate skipped/ duplicates, and sync to GCS."""
    overrides = _build_ai_overrides(
        device=device,
        ai_provider=ai_provider,
        ai_api_url=ai_api_url,
        offline=offline,
    )
    settings = _require_settings(ctx, **overrides)
    gcs_client = _build_gcs_client(ctx, settings)
    pipeline = IngestPipeline(settings, gcs_client)
    show_progress = bool(ctx.obj.get("show_progress", True)) if ctx.obj else True
    try:
        summary = pipeline.run(
            input_dir,
            routing_mode=cast(RoutingMode, routing_mode.lower()),
            commit_every=commit_every,
            init_db=init_db,
            no_ai=no_ai,
            dry_run=dry_run,
            preview_ai=preview_ai,
            show_progress=show_progress,
        )
    except (CheckpointModeMismatchError, AINotConfiguredError, StorageSyncError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(summary.model_dump(), indent=2))


@cli.command()
@click.option(
    "--local-media-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Local media directory to read original photos before falling back to GCS.",
)
@click.option(
    "--use-source-bucket",
    is_flag=True,
    help=(
        "Download original photos from the Archive media bucket instead of "
        "thumbnails when local originals are absent (incurs Archive retrieval cost)."
    ),
)
@click.option(
    "--include-partial",
    is_flag=True,
    help="Also annotate records missing only tags or only a caption.",
)
@click.option(
    "--commit-every",
    type=click.IntRange(min=1),
    default=100,
    show_default=True,
    help="Commit media and English label/caption DBs to GCS every N updates.",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=None,
    help="Maximum number of unannotated records to process in this run.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Count unannotated candidate records without running AI or modifying GCS.",
)
@_ai_runtime_options
@click.pass_context
def annotate(
    ctx: click.Context,
    local_media_dir: Path | None,
    use_source_bucket: bool,
    include_partial: bool,
    commit_every: int,
    limit: int | None,
    device: str | None,
    ai_provider: str | None,
    ai_api_url: str | None,
    dry_run: bool,
    offline: bool,
) -> None:
    """Backfill AI tags and captions onto unannotated media records in GCS."""
    overrides = _build_ai_overrides(
        device=device,
        ai_provider=ai_provider,
        ai_api_url=ai_api_url,
        offline=offline,
    )
    settings = _require_settings(ctx, **overrides)
    gcs_client = _build_gcs_client(ctx, settings)
    pipeline = AnnotatePipeline(settings, gcs_client)
    show_progress = bool(ctx.obj.get("show_progress", True)) if ctx.obj else True
    try:
        summary = pipeline.run(
            local_media_dir=local_media_dir,
            use_source_bucket=use_source_bucket,
            include_partial=include_partial,
            commit_every=commit_every,
            limit=limit,
            dry_run=dry_run,
            show_progress=show_progress,
        )
    except (AINotConfiguredError, StorageSyncError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(summary.model_dump(), indent=2))


@cli.command()
@click.option(
    "--target-lang",
    required=True,
    help="Target language code (e.g. it, es, fr).",
)
@click.option(
    "--offline",
    is_flag=True,
    help=(
        "Load translation models strictly from local cache "
        "without contacting huggingface.co."
    ),
)
@click.pass_context
def translate(ctx: click.Context, target_lang: str, offline: bool) -> None:
    """Translate missing en_ label/caption dictionary entries into TARGET_LANG."""
    overrides: dict[str, Any] = {"target_lang": target_lang}
    if offline:
        overrides["ai_offline"] = True
    settings = _require_settings(ctx, **overrides)
    gcs_client = _build_gcs_client(ctx, settings)
    translator = EasyNMTTranslator(
        settings.models_dir / "easynmt",
        offline=settings.ai_offline,
    )
    show_progress = bool(ctx.obj.get("show_progress", True)) if ctx.obj else True

    try:
        gcs_client.verify_bucket_classes(
            settings.media_bucket,
            settings.data_bucket,
            expected_media_class=settings.media_storage_class,
            expected_data_class=settings.data_storage_class,
        )
        for suffix in (LABELS_DB_SUFFIX, CAPTIONS_DB_SUFFIX):
            en_store, _ = load_remote_kv_store(
                gcs_client, settings, f"en_{suffix}", allow_missing=False
            )
            tgt_name = f"{target_lang}_{suffix}"
            tgt_store, tgt_gen = load_remote_kv_store(
                gcs_client, settings, tgt_name, allow_missing=True, flush=False
            )
            count = translator.translate_missing_entries(
                en_store, tgt_store, target_lang, show_progress=show_progress
            )
            tgt_store.flush_to_disk()
            gcs_client.upload_json_atomic(
                settings.data_bucket,
                tgt_name,
                tgt_store.store,
                if_generation_match=tgt_gen if tgt_gen is not None else 0,
            )
            click.echo(f"{tgt_name}: translated {count} new entries")
    except (AINotConfiguredError, StorageSyncError) as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command("verify-db")
@click.option(
    "--lang",
    default="en",
    show_default=True,
    help="Language dictionary prefix to check.",
)
@click.pass_context
def verify_db(ctx: click.Context, lang: str) -> None:
    """Download and validate all four JSON databases from the Standard bucket."""
    settings = _require_settings(ctx)
    gcs_client = _build_gcs_client(ctx, settings)
    try:
        gcs_client.verify_bucket_classes(
            settings.media_bucket,
            settings.data_bucket,
            expected_media_class=settings.media_storage_class,
            expected_data_class=settings.data_storage_class,
        )

        media_raw, _ = gcs_client.download_json(settings.data_bucket, MEDIA_DB_FILENAME)
        labels_store, _ = load_remote_kv_store(
            gcs_client,
            settings,
            f"{lang}_{LABELS_DB_SUFFIX}",
            allow_missing=False,
            flush=False,
        )
        captions_store, _ = load_remote_kv_store(
            gcs_client,
            settings,
            f"{lang}_{CAPTIONS_DB_SUFFIX}",
            allow_missing=False,
            flush=False,
        )
        albums_raw, _ = gcs_client.download_json(
            settings.data_bucket, ALBUMS_DB_FILENAME, init_db=True
        )
    except StorageSyncError as exc:
        raise click.ClickException(str(exc)) from exc

    media_db = MediaDatabase.model_validate(media_raw)
    labels_db = KeyValueDictionary.model_validate(labels_store.store)
    captions_db = KeyValueDictionary.model_validate(captions_store.store)
    albums = [AlbumRecord.model_validate(item) for item in (albums_raw or [])]
    click.echo(
        json.dumps(
            {
                "media_count": len(media_db.root),
                "labels_count": len(labels_db.root),
                "captions_count": len(captions_db.root),
                "albums_count": len(albums),
            },
            indent=2,
        )
    )


def _inspect_cached_models(cache_dir: Path) -> dict[str, Any]:
    """Inspect local Hugging Face and EasyNMT model caches under cache_dir."""
    from photosphere.ai.moondream2 import (
        moondream2_snapshot_dir,
        moondream2_tokenizer_snapshot_dir,
    )

    hf_dir = cache_dir / "huggingface"
    easynmt_dir = cache_dir / "easynmt"
    easynmt_models = (
        sorted(
            p.name
            for p in easynmt_dir.iterdir()
            if p.is_dir() and p.name.startswith("models--Helsinki-NLP--")
        )
        if easynmt_dir.exists()
        else []
    )
    model_snap = moondream2_snapshot_dir(cache_dir)
    tok_snap = moondream2_tokenizer_snapshot_dir(cache_dir)
    return {
        "moondream2": (model_snap / "config.json").is_file()
        and any(model_snap.glob("*.safetensors")),
        "moondream2_tokenizer": (tok_snap / "tokenizer.json").is_file(),
        "moondream2_modules": (hf_dir / "modules" / "transformers_modules").exists(),
        "easynmt_models": easynmt_models,
    }


@cli.command("prefetch-models")
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help=(
        "Target cache directory "
        "(defaults to PHOTOSPHERE_CACHE_DIR or ~/.photosphere/cache)."
    ),
)
@click.option(
    "--lang",
    "langs",
    multiple=True,
    default=("it",),
    show_default=True,
    help="Target language code(s) for Opus-MT translation models (repeatable).",
)
@click.option(
    "--no-vision",
    is_flag=True,
    help="Skip downloading Moondream2 vision weights, tokenizer, and modules.",
)
@click.option(
    "--no-translate",
    is_flag=True,
    help="Skip downloading Helsinki-NLP Opus-MT translation models.",
)
@click.option(
    "--device",
    type=click.Choice(["auto", "cuda", "mps", "cpu"], case_sensitive=False),
    default="cpu",
    show_default=True,
    help="Compute device used while verifying downloaded weights.",
)
def prefetch_models(
    cache_dir: Path | None,
    langs: tuple[str, ...],
    no_vision: bool,
    no_translate: bool,
    device: str,
) -> None:
    """Pre-download Moondream2 and Opus-MT models into the shared cache directory."""
    defaults = PhotosphereSettings()
    target_cache_dir = cache_dir if cache_dir is not None else defaults.models_dir
    target_cache_dir.mkdir(parents=True, exist_ok=True)
    configure_hf_cache_env(target_cache_dir / "huggingface", offline=False)

    downloaded: dict[str, Any] = {
        "cache_dir": str(target_cache_dir),
        "vision": False,
        "languages": [],
    }
    try:
        if not no_vision:
            provider = Moondream2Provider(
                device=device.lower(),
                cache_dir=target_cache_dir,
                offline=False,
            )
            provider.prefetch()
            downloaded["vision"] = True

        if not no_translate:
            translator = EasyNMTTranslator(
                target_cache_dir / "easynmt",
                offline=False,
            )
            for lang in langs:
                normalized = lang.strip().lower()
                if not normalized or normalized == "en":
                    continue
                translator.prefetch(normalized)
                downloaded["languages"].append(normalized)
    except AINotConfiguredError as exc:
        raise click.ClickException(str(exc)) from exc

    downloaded["cached_models"] = _inspect_cached_models(target_cache_dir)
    click.echo(json.dumps(downloaded, indent=2))


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Diagnose config, GCP credentials, media libraries, and compute device."""
    config_path: Path | None = ctx.obj.get("config_path") if ctx.obj else None
    credentials_path: Path | None = ctx.obj.get("credentials_path") if ctx.obj else None
    profile: str = (
        ctx.obj.get("profile", DEFAULT_PROFILE) if ctx.obj else DEFAULT_PROFILE
    )
    errors: list[str] = []
    report: dict[str, Any] = {"profile": profile}

    try:
        resolved_cfg = resolve_photosphere_config_path(config_path, profile=profile)
        report["config_path"] = str(resolved_cfg) if resolved_cfg else None
        settings = PhotosphereSettings.require_runtime_config(
            config_path=config_path, profile=profile
        )
        report["gcp_project_id"] = settings.gcp_project_id
        report["media_bucket"] = settings.media_bucket
        report["data_bucket"] = settings.data_bucket
        report["skipped_dir"] = str(settings.skipped_dir)
        report["cache_dir"] = str(settings.cache_dir)
        report["models_dir"] = str(settings.models_dir)
        report["ai_offline"] = settings.ai_offline
        report["cached_models"] = _inspect_cached_models(settings.models_dir)
        report["compute_device"] = resolve_device(settings.device)
    except ConfigFileError as exc:
        errors.append(f"config: {exc}")
        report["config_path"] = None
        fallback_settings = PhotosphereSettings(profile=profile)
        report["skipped_dir"] = str(fallback_settings.skipped_dir)
        report["cache_dir"] = str(fallback_settings.cache_dir)
        report["models_dir"] = str(fallback_settings.models_dir)
        report["ai_offline"] = fallback_settings.ai_offline
        report["cached_models"] = _inspect_cached_models(fallback_settings.models_dir)
        report["compute_device"] = resolve_device()

    try:
        cred_source, _ = resolve_credentials_source(credentials_path)
        report["credentials_source"] = cred_source
    except StorageSyncError as exc:
        errors.append(f"credentials: {exc}")
        report["credentials_source"] = None

    try:
        import av  # noqa: PLC0415

        report["av_version"] = av.__version__
    except ImportError as exc:
        errors.append(f"av: {exc}")
        report["av_version"] = None

    try:
        import pillow_heif  # noqa: PLC0415

        report["pillow_heif_version"] = pillow_heif.__version__
    except ImportError as exc:
        errors.append(f"pillow_heif: {exc}")
        report["pillow_heif_version"] = None

    report["errors"] = errors
    click.echo(json.dumps(report, indent=2))
    if errors:
        raise SystemExit(1)
