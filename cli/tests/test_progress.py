"""Unit tests for tqdm progress bar helpers and translator/CLI wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from photosphere import progress as progress_mod
from photosphere.ai.translator import EasyNMTTranslator, KeyValueStore
from photosphere.progress import TqdmPrintLogger, tqdm_progress, truncate_label


def test_truncate_label_keeps_short_and_truncates_long() -> None:
    assert truncate_label("photo.jpg", max_len=32) == "photo.jpg"
    long_name = "Victor_Hugo_buste_marbre_Musee_Rodin_S.00464_Paris.png"
    truncated = truncate_label(long_name, max_len=20)
    assert len(truncated) == 20
    assert truncated.startswith("...")
    assert truncated.endswith("_Paris.png")


def test_tqdm_print_logger_writes_via_tqdm(monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[str] = []
    monkeypatch.setattr(
        progress_mod.tqdm,
        "write",
        lambda msg, file=None: written.append(msg),
    )
    logger = TqdmPrintLogger()
    logger.info('{"event": "test"}')
    logger.warning('{"event": "warn"}')
    assert written == ['{"event": "test"}', '{"event": "warn"}']


def test_tqdm_progress_respects_enabled_flag() -> None:
    bar_disabled = tqdm_progress([1, 2, 3], desc="Test", unit="item", enabled=False)
    assert bar_disabled.disable is True
    assert list(bar_disabled) == [1, 2, 3]
    bar_disabled.close()


def test_translator_progress_tracks_only_missing_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    real_tqdm_progress = progress_mod.tqdm_progress

    def spy_progress(
        iterable: Any,
        *,
        desc: str,
        unit: str,
        total: int | None = None,
        enabled: bool = True,
    ) -> Any:
        captured["desc"] = desc
        captured["unit"] = unit
        captured["total"] = total
        captured["enabled"] = enabled
        return real_tqdm_progress(
            iterable, desc=desc, unit=unit, total=total, enabled=False
        )

    import photosphere.ai.translator as translator_mod

    monkeypatch.setattr(translator_mod, "tqdm_progress", spy_progress)

    en_store = KeyValueStore(tmp_path / "en_labels.json")
    en_store.store = {"0": "cat", "1": "dog", "2": "tree"}
    it_store = KeyValueStore(tmp_path / "it_labels.json")
    it_store.store = {"0": "gatto"}

    translator = EasyNMTTranslator(
        tmp_path / "cache", translator_fn=lambda text, lang: f"{lang}:{text}"
    )
    count = translator.translate_missing_entries(
        en_store, it_store, "it", show_progress=True
    )
    assert count == 2
    assert captured == {
        "desc": "Translate (it)",
        "unit": "entry",
        "total": 2,
        "enabled": True,
    }
