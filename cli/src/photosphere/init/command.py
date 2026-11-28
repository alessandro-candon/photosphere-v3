"""Click CLI command for `photosphere init`."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal, cast

import click

from photosphere.config import StorageClass, normalize_profile_name
from photosphere.init.models import (
    BootstrapConfigError,
    build_config_metadata,
    load_and_validate_config,
    resolve_config_path,
    write_config_atomic,
)
from photosphere.init.provisioner import BootstrapOptions, BootstrapProvisioner
from photosphere.init.rest_client import (
    GoogleRestClient,
    RestApiError,
    prompt_console_step,
)


def _resolve_templates_dir(explicit_infra_dir: Path | None) -> Path | None:
    if explicit_infra_dir is not None:
        return explicit_infra_dir
    cwd_infra = Path.cwd() / "infra"
    if (cwd_infra / "cors.json").is_file() and (cwd_infra / "storage.rules").is_file():
        return cwd_infra
    return None


def _prompt_if_missing(
    value: str | None,
    prompt_text: str,
    *,
    default: str | None = None,
    non_interactive: bool = False,
) -> str:
    if value is not None and value.strip():
        return value.strip()
    if non_interactive:
        raise BootstrapConfigError(
            f"Missing required option for '{prompt_text}' in --non-interactive mode."
        )
    return str(click.prompt(prompt_text, default=default, type=str)).strip()


def _resolve_storage_classes(
    mode: Literal["dev", "prod"],
    media_storage_class: str | None,
    data_storage_class: str | None,
) -> tuple[StorageClass, StorageClass]:
    default_media: StorageClass = "STANDARD" if mode == "dev" else "ARCHIVE"
    media_cls = cast(StorageClass, media_storage_class or default_media)
    data_cls = cast(StorageClass, data_storage_class or "STANDARD")
    return media_cls, data_cls


def _parse_emails(raw_emails: str) -> list[str]:
    emails = [item.strip().lower() for item in raw_emails.split(",") if item.strip()]
    if not emails:
        raise BootstrapConfigError("At least one allowed email is required.")
    return emails


def _build_options(
    *,
    project_id: str | None,
    location: str | None,
    mode: str | None,
    media_bucket: str | None,
    data_bucket: str | None,
    media_storage_class: str | None,
    data_storage_class: str | None,
    allowed_emails: str | None,
    admin_email: str | None,
    target_lang: str,
    non_interactive: bool,
    google_oauth_client_id: str | None,
    google_oauth_client_secret: str | None,
    profile: str = "default",
) -> BootstrapOptions:
    resolved_project = _prompt_if_missing(
        project_id, "Firebase / GCP Project ID", non_interactive=non_interactive
    )
    resolved_location = _prompt_if_missing(
        location,
        "GCS Bucket Location",
        default="europe-west8",
        non_interactive=non_interactive,
    )
    resolved_mode = cast(
        Literal["dev", "prod"],
        mode
        or (
            "dev"
            if non_interactive
            else click.prompt(
                "Environment mode",
                type=click.Choice(["dev", "prod"], case_sensitive=False),
                default="dev",
            ).lower()
        ),
    )
    media_cls, data_cls = _resolve_storage_classes(
        resolved_mode, media_storage_class, data_storage_class
    )
    resolved_media = _prompt_if_missing(
        media_bucket,
        "Media GCS Bucket",
        default=f"{resolved_project}-photosphere-media",
        non_interactive=non_interactive,
    )
    resolved_data = _prompt_if_missing(
        data_bucket,
        "Data GCS Bucket",
        default=f"{resolved_project}-photosphere-data",
        non_interactive=non_interactive,
    )
    raw_emails = _prompt_if_missing(
        allowed_emails,
        "Allowed user email(s) (comma-separated)",
        non_interactive=non_interactive,
    )
    parsed_emails = _parse_emails(raw_emails)
    resolved_admin = _prompt_if_missing(
        admin_email,
        "Admin email",
        default=parsed_emails[0],
        non_interactive=non_interactive,
    ).lower()
    return BootstrapOptions(
        project_id=resolved_project,
        location=resolved_location,
        media_bucket=resolved_media,
        data_bucket=resolved_data,
        media_storage_class=media_cls,
        data_storage_class=data_cls,
        allowed_emails=parsed_emails,
        admin_email=resolved_admin,
        target_lang=target_lang,
        google_oauth_client_id=google_oauth_client_id,
        google_oauth_client_secret=google_oauth_client_secret,
        profile=profile,
    )


@click.command("init")
@click.option("--config-path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--infra-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory containing cors.json and storage.rules templates.",
)
@click.option("--project-id", default=None, help="Existing GCP/Firebase Project ID.")
@click.option("--location", default=None, help="GCS bucket region (e.g. europe-west1).")
@click.option(
    "--mode",
    type=click.Choice(["dev", "prod"], case_sensitive=False),
    default=None,
    help="dev defaults both buckets to STANDARD; prod defaults media to ARCHIVE.",
)
@click.option("--media-bucket", default=None, help="Media GCS bucket name.")
@click.option("--data-bucket", default=None, help="Data GCS bucket name.")
@click.option(
    "--media-storage-class",
    type=click.Choice(["STANDARD", "ARCHIVE"], case_sensitive=False),
    default=None,
    help="Override media bucket storage class.",
)
@click.option(
    "--data-storage-class",
    type=click.Choice(["STANDARD", "ARCHIVE"], case_sensitive=False),
    default=None,
    help="Override data bucket storage class.",
)
@click.option("--allowed-emails", default=None, help="Comma-separated allowed emails.")
@click.option("--admin-email", default=None, help="Admin email address.")
@click.option("--target-lang", default="it", show_default=True)
@click.option("--google-oauth-client-id", default=None)
@click.option("--google-oauth-client-secret", default=None)
@click.option("--non-interactive", is_flag=True, help="Fail instead of prompting.")
@click.option("--force", is_flag=True, help="Re-run provisioning if config exists.")
@click.pass_context
def init_command(
    ctx: click.Context,
    config_path: Path | None,
    infra_dir: Path | None,
    project_id: str | None,
    location: str | None,
    mode: str | None,
    media_bucket: str | None,
    data_bucket: str | None,
    media_storage_class: str | None,
    data_storage_class: str | None,
    allowed_emails: str | None,
    admin_email: str | None,
    target_lang: str,
    google_oauth_client_id: str | None,
    google_oauth_client_secret: str | None,
    non_interactive: bool,
    force: bool,
) -> None:
    """Provision GCP/Firebase infra and write photosphere.config.json."""
    ctx_obj = ctx.obj or {}
    effective_config_path = config_path or ctx_obj.get("config_path")
    credentials_path: Path | None = ctx_obj.get("credentials_path")
    profile: str | None = ctx_obj.get("profile")
    active_profile = normalize_profile_name(profile)
    assume_yes = bool(ctx_obj.get("assume_yes", False))

    target_path = resolve_config_path(effective_config_path, profile=active_profile)
    if target_path.exists() and not force:
        existing = load_and_validate_config(target_path)
        click.echo(json.dumps(existing.model_dump(mode="json"), indent=2))
        return

    try:
        resolved_project = _prompt_if_missing(
            project_id, "Firebase / GCP Project ID", non_interactive=non_interactive
        )
        resolved_data = _prompt_if_missing(
            data_bucket,
            "Data GCS Bucket",
            default=f"{resolved_project}-photosphere-data",
            non_interactive=non_interactive,
        )
        rest_client = GoogleRestClient(
            resolved_project, credentials_path=credentials_path
        )
        provisioner = BootstrapProvisioner(
            rest_client,
            lambda url, step: prompt_console_step(
                url, step, non_interactive=non_interactive
            ),
            templates_dir=_resolve_templates_dir(infra_dir),
        )
        if not target_path.exists() and not force:
            remote_cfg = provisioner.download_config_backup(resolved_data)
            if remote_cfg is not None and (
                non_interactive
                or assume_yes
                or not sys.stdin.isatty()
                or click.confirm(
                    f"Found existing photosphere.config.json in gs://{resolved_data}. "
                    f"Download and restore it for profile '{active_profile}'?",
                    default=True,
                )
            ):
                restored = remote_cfg.model_copy(
                    update={
                        "profile": active_profile,
                        "metadata": build_config_metadata(),
                    }
                )
                write_config_atomic(target_path, restored)
                click.echo(json.dumps(restored.model_dump(mode="json"), indent=2))
                return

        options = _build_options(
            project_id=resolved_project,
            location=location,
            mode=mode.lower() if mode else None,
            media_bucket=media_bucket,
            data_bucket=resolved_data,
            media_storage_class=(
                media_storage_class.upper() if media_storage_class else None
            ),
            data_storage_class=(
                data_storage_class.upper() if data_storage_class else None
            ),
            allowed_emails=allowed_emails,
            admin_email=admin_email,
            target_lang=target_lang,
            non_interactive=non_interactive,
            google_oauth_client_id=google_oauth_client_id,
            google_oauth_client_secret=google_oauth_client_secret,
            profile=active_profile,
        )
        config = provisioner.run(options)
        write_config_atomic(target_path, config)
        provisioner.upload_config_backup(options.data_bucket, config)
        click.echo(json.dumps(config.model_dump(mode="json"), indent=2))
    except (BootstrapConfigError, RestApiError) as exc:
        raise click.ClickException(str(exc)) from exc
