"""Unit tests for photosphere.ai.translator."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from photosphere.ai.protocol import AINotConfiguredError
from photosphere.ai.translator import EasyNMTTranslator, KeyValueStore, translate_text


def test_key_value_store_o1_index_from_mapping_and_load_file(tmp_path: Path) -> None:
    db_path = tmp_path / "en_labels.json"
    store = KeyValueStore(db_path)
    idx0 = store.add_unique_value("dog")
    idx1 = store.add_unique_value("park")
    idx0_again = store.add_unique_value("dog")
    assert (idx0, idx1, idx0_again) == (0, 1, 0)
    store.set_value_at_index(5, "river")
    assert store.add_unique_value("river") == 5
    assert store.next_index == 6
    store.flush_to_disk()

    reloaded = KeyValueStore(db_path)
    reloaded.load_file()
    assert reloaded.add_unique_value("dog") == 0
    assert reloaded.add_unique_value("river") == 5
    assert reloaded.add_unique_value("forest") == 6

    mapped = KeyValueStore.from_mapping(
        tmp_path / "mapped.json", {"0": "alpha", "2": "beta"}, flush=True
    )
    assert mapped.db_path.exists()
    assert mapped.add_unique_value("beta") == 2
    assert mapped.add_unique_value("gamma") == 3


def test_translate_text_cleans_meta_notes() -> None:
    cleaned = translate_text(
        "cane",
        "it",
        translator_fn=lambda t, _: f"{t} (proper noun - keep in english)",
    )
    assert cleaned == "cane"

    cleaned_trailing = translate_text(
        "Milano",
        "it",
        translator_fn=lambda t, _: f"{t} city name optional",
    )
    assert cleaned_trailing == "Milano"


def test_translator_offline_flag_and_error_wrapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_torch = ModuleType("torch")
    fake_torch.cuda = SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    fake_torch.backends = SimpleNamespace(  # type: ignore[attr-defined]
        mps=SimpleNamespace(is_available=lambda: False)
    )
    fake_transformers = ModuleType("transformers")

    seen: dict[str, Any] = {}

    class FailingTokenizer:
        @staticmethod
        def from_pretrained(model_id: str, **kwargs: Any) -> Any:
            seen["model_id"] = model_id
            seen["kwargs"] = kwargs
            raise OSError("CERTIFICATE_VERIFY_FAILED contacting huggingface.co")

    fake_transformers.MarianTokenizer = FailingTokenizer  # type: ignore[attr-defined]
    fake_transformers.MarianMTModel = FailingTokenizer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    translator = EasyNMTTranslator(tmp_path / "easynmt", offline=True)
    with pytest.raises(AINotConfiguredError, match="Offline mode is enabled"):
        translator.prefetch("it")
    assert seen["model_id"] == "Helsinki-NLP/opus-mt-en-it"
    assert seen["kwargs"]["local_files_only"] is True


def test_key_value_store_index_consistency_across_all_mutations(tmp_path: Path) -> None:
    def assert_synced(kv: KeyValueStore) -> None:
        expected = {v: int(k) for k, v in kv.store.items()}
        assert kv._value_to_index == expected  # noqa: SLF001

    store = KeyValueStore(tmp_path / "labels.json")
    store.add_unique_value("sky")
    assert_synced(store)
    store.add_unique_multiple_values(["tree", "sky", "lake"])
    assert_synced(store)
    store.set_value_at_index(10, "mountain")
    assert_synced(store)
    store.flush_to_disk()

    reloaded = KeyValueStore(tmp_path / "labels.json")
    reloaded.load_file()
    assert_synced(reloaded)

    mapped = KeyValueStore.from_mapping(
        tmp_path / "mapped.json", {"0": "a", "3": "b"}, flush=False
    )
    assert_synced(mapped)
