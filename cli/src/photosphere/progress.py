"""Shared tqdm progress bar helpers and structlog-safe terminal output."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import Any, TextIO, TypeVar

from tqdm import tqdm

_T = TypeVar("_T")


class TqdmPrintLogger:
    """Minimal structlog logger that writes through ``tqdm.write``."""

    def __init__(self, file: TextIO | None = None) -> None:
        self._file = file or sys.__stderr__

    def msg(self, message: str) -> None:
        tqdm.write(message, file=self._file)

    log = debug = info = warn = warning = error = fatal = exception = critical = msg


def tqdm_logger_factory(file: TextIO | None = None) -> Any:
    """Return a structlog logger_factory compatible with active tqdm bars."""

    def _factory(*_args: Any) -> TqdmPrintLogger:
        return TqdmPrintLogger(file=file)

    return _factory


def truncate_label(label: str, max_len: int = 32) -> str:
    """Truncate long filenames/labels for compact tqdm postfix display."""
    if len(label) <= max_len:
        return label
    return f"...{label[-(max_len - 3) :]}"


def tqdm_progress(
    iterable: Iterable[_T],
    *,
    desc: str,
    unit: str,
    total: int | None = None,
    enabled: bool = True,
) -> tqdm[_T]:
    """Create a stderr tqdm progress bar that auto-disables on non-TTY streams."""
    return tqdm(
        iterable,
        desc=desc,
        unit=unit,
        total=total,
        file=sys.stderr,
        dynamic_ncols=True,
        disable=None if enabled else True,
    )
