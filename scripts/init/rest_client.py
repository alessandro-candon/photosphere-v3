"""Google Auth REST client with LRO polling and interactive console fallback."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterable
from typing import Any

import google.auth
from google.auth.credentials import CredentialsWithQuotaProject
from google.auth.transport.requests import AuthorizedSession
from requests import Response

from scripts.init.models import BootstrapConfigError

CLOUD_PLATFORM_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class RestApiError(RuntimeError):
    """Structured error raised when a Google Cloud or Firebase REST call fails."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        reason: str = "",
        response_body: str = "",
    ) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.reason = reason
        self.message = message
        self.response_body = response_body


def _parse_error_details(response: Response) -> tuple[str, str]:
    try:
        data = response.json()
    except ValueError:
        return "", response.text
    err = data.get("error", {}) if isinstance(data, dict) else {}
    if not isinstance(err, dict):
        return "", response.text
    message = str(err.get("message") or response.text)
    reason = str(err.get("status") or "")
    for detail in err.get("details", []) or []:
        if isinstance(detail, dict) and detail.get("reason"):
            reason = str(detail["reason"])
            break
    return reason, message


def prompt_console_step(
    url: str,
    instruction: str,
    *,
    non_interactive: bool = False,
) -> None:
    """Pause for a manual browser step in the Firebase Console and wait for Enter."""
    if non_interactive or not sys.stdin.isatty():
        raise BootstrapConfigError(
            f"Manual action required in Firebase Console ({url}): {instruction}"
        )
    print(
        f"\nAction required in Firebase Console:\n  URL: {url}\n  Step: {instruction}"
    )
    input("Press Enter once completed...")


class GoogleRestClient:
    """Minimal authenticated REST client for GCP and Firebase APIs."""

    def __init__(
        self,
        project_id: str,
        *,
        session: AuthorizedSession | Any | None = None,
        timeout: int = 30,
    ) -> None:
        self.project_id = project_id
        self.timeout = timeout
        if session is not None:
            self._session = session
        else:
            creds, _ = google.auth.default(scopes=CLOUD_PLATFORM_SCOPES)
            if isinstance(creds, CredentialsWithQuotaProject):
                creds = creds.with_quota_project(project_id)
            self._session = AuthorizedSession(creds)

    def _base_headers(self, *, include_quota: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if include_quota:
            headers["x-goog-user-project"] = self.project_id
        return headers

    def _send(
        self,
        method: str,
        url: str,
        *,
        json_body: Any = None,
        data: bytes | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        include_quota: bool = True,
    ) -> Response:
        req_headers = self._base_headers(include_quota=include_quota)
        if headers:
            req_headers.update(headers)
        return self._session.request(
            method=method,
            url=url,
            json=json_body,
            data=data,
            params=params,
            headers=req_headers,
            timeout=self.timeout,
        )

    def request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: Any = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        allow_statuses: Iterable[int] = (),
        retry_without_quota_header: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        """Send an authenticated JSON request and raise RestApiError on failure."""
        allowed = set(allow_statuses)
        response = self._send(
            method,
            url,
            json_body=json_body,
            params=params,
            headers=headers,
            include_quota=True,
        )
        if (
            retry_without_quota_header
            and response.status_code == 403
            and "x-goog-user-project" not in (headers or {})
        ):
            response = self._send(
                method,
                url,
                json_body=json_body,
                params=params,
                headers=headers,
                include_quota=False,
            )

        if response.status_code >= 400 and response.status_code not in allowed:
            reason, message = _parse_error_details(response)
            raise RestApiError(
                response.status_code,
                message,
                reason=reason,
                response_body=response.text,
            )

        if not response.text.strip():
            return response.status_code, {}
        parsed = response.json()
        return response.status_code, parsed if isinstance(parsed, dict) else {}

    def upload_bytes(
        self,
        url: str,
        payload: bytes,
        *,
        content_type: str,
        if_generation_match: int | None = None,
        allow_statuses: Iterable[int] = (),
    ) -> int:
        """Upload raw bytes (used for ifGenerationMatch=0 database seeding)."""
        params: dict[str, str] = {"uploadType": "media"}
        if if_generation_match is not None:
            params["ifGenerationMatch"] = str(if_generation_match)
        response = self._send(
            "POST",
            url,
            data=payload,
            params=params,
            headers={"Content-Type": content_type},
            include_quota=False,
        )
        allowed = set(allow_statuses)
        if response.status_code >= 400 and response.status_code not in allowed:
            reason, message = _parse_error_details(response)
            raise RestApiError(
                response.status_code,
                message,
                reason=reason,
                response_body=response.text,
            )
        return response.status_code

    def poll_lro(
        self,
        operation_url: str,
        *,
        timeout_seconds: float = 180.0,
        interval_seconds: float = 2.0,
    ) -> dict[str, Any]:
        """Poll a Google Long-Running Operation URL until done=true."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            _, data = self.request_json("GET", operation_url)
            if data.get("done"):
                if "error" in data:
                    err = data["error"]
                    raise RestApiError(
                        int(err.get("code", 500)),
                        json.dumps(err),
                        response_body=json.dumps(err),
                    )
                response_obj = data.get("response")
                return response_obj if isinstance(response_obj, dict) else data
            if time.monotonic() >= deadline:
                raise BootstrapConfigError(
                    f"Timed out waiting for operation {operation_url}"
                )
            time.sleep(interval_seconds)
