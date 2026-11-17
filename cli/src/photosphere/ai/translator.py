"""Deterministic KeyValueStore and Opus-MT (transformers) dictionary translator."""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from photosphere.ai.protocol import resolve_device
from photosphere.models.database import KeyValueDictionary
from photosphere.progress import tqdm_progress

_META_NOTE_MARKERS = (
    "optional",
    "probably",
    "does not need",
    "doesn't need",
    "no translation",
    "not need a translation",
    "city name",
    "proper noun",
    "keep in english",
    "leave untranslated",
)
_LANG_CODE_RE = re.compile(r"\b[a-z]{2}(-[a-z]{2})?\b", re.IGNORECASE)
_PAREN_INNERMOST_RE = re.compile(r"\([^()]*\)")
_TRAILING_PUNCT_RE = re.compile(r"[\s\-—:;,.|]+$")


class KeyValueStore:
    """Minified integer-key JSON store with deterministic disk persistence."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.store: dict[str, str] = {}
        self.next_index = 0

    def load_file(self) -> None:
        """Load dictionary entries from disk when present and valid."""
        if not self.db_path.exists():
            self.store = {}
            self.next_index = 0
            return
        loaded = json.loads(self.db_path.read_text(encoding="utf-8"))
        validated = KeyValueDictionary.model_validate(loaded)
        self.store = dict(validated.root)
        self.next_index = max((int(key) for key in self.store), default=-1) + 1

    def add_unique_value(self, value: str) -> int:
        """Return existing index for value or allocate a sequential string key."""
        for idx_str, stored in self.store.items():
            if stored == value:
                return int(idx_str)
        assigned = self.next_index
        self.store[str(assigned)] = value
        self.next_index += 1
        return assigned

    def add_unique_multiple_values(self, values: list[str]) -> list[int]:
        """Insert a list of tag values and return their integer dictionary indexes."""
        return [self.add_unique_value(item) for item in values]

    def set_value_at_index(self, index: int | str, value: str) -> None:
        """Set translation entry at an explicit index without altering next_index."""
        key = str(index)
        if key not in self.store:
            self.store[key] = value
            numeric = int(key)
            if numeric >= self.next_index:
                self.next_index = numeric + 1

    def flush_to_disk(self) -> None:
        """Atomically write minified JSON dictionary matching v2 format."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.db_path.with_suffix(".json.tmp")
        serialized = json.dumps(self.store, separators=(",", ":"), ensure_ascii=False)
        tmp_path.write_text(serialized, encoding="utf-8")
        tmp_path.replace(self.db_path)


def _should_drop_parenthetical(content: str) -> bool:
    lowered = content.strip().lower()
    if not lowered or len(lowered) >= 40:
        return True
    if any(marker in lowered for marker in _META_NOTE_MARKERS):
        return True
    return "->" in lowered and _LANG_CODE_RE.search(lowered) is not None


def _strip_meta_parenthetical_notes(text: str) -> str:
    cleaned = text
    removed_any = False
    while True:
        changed = False

        def _replace(match: re.Match[str]) -> str:
            nonlocal changed, removed_any
            inner = match.group(0)[1:-1]
            if _should_drop_parenthetical(inner):
                changed = True
                removed_any = True
                return ""
            return match.group(0)

        cleaned = _PAREN_INNERMOST_RE.sub(_replace, cleaned)
        if not changed:
            break

    if removed_any:
        cleaned = cleaned.replace("()", "").strip(" )(")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _strip_trailing_meta_note(text: str) -> str:
    lowered = text.lower()
    earliest_idx: int | None = None
    for marker in _META_NOTE_MARKERS:
        idx = lowered.find(marker)
        if idx >= 2 and (earliest_idx is None or idx < earliest_idx):
            earliest_idx = idx
    if earliest_idx is None:
        return text.strip()
    return _TRAILING_PUNCT_RE.sub("", text[:earliest_idx]).strip()


def _normalize_whitespace(text: str) -> str:
    single_line = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return re.sub(r"\s{2,}", " ", single_line).strip()


def translate_text(
    text: str,
    target_lang: str,
    *,
    translator_fn: Callable[[str, str], str],
    clean_meta_notes: bool = True,
) -> str:
    """Translate text and remove hallucinated MT meta-notes."""
    translated = _normalize_whitespace(translator_fn(text, target_lang))
    if not clean_meta_notes:
        return translated
    translated = _strip_meta_parenthetical_notes(translated)
    translated = _strip_trailing_meta_note(translated)
    return _normalize_whitespace(translated)


class EasyNMTTranslator:
    """Translates missing canonical en_ entries into a target language via Opus-MT."""

    def __init__(
        self,
        cache_dir: Path,
        translator_fn: Callable[[str, str], str] | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self._translator_fn = translator_fn
        self._models: dict[str, tuple[Any, Any, Any, str]] = {}

    def _load_opus_mt(self, target_lang: str) -> tuple[Any, Any, Any, str]:
        if target_lang in self._models:
            return self._models[target_lang]
        try:
            torch = importlib.import_module("torch")
            transformers = importlib.import_module("transformers")
        except ImportError as exc:
            raise RuntimeError(
                "Translation requires `[ai]` extras. Run `uv sync --extra ai`."
            ) from exc

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        model_id = f"Helsinki-NLP/opus-mt-en-{target_lang}"
        device = resolve_device("auto")
        tokenizer = transformers.MarianTokenizer.from_pretrained(
            model_id, cache_dir=str(self.cache_dir)
        )
        model = transformers.MarianMTModel.from_pretrained(
            model_id, cache_dir=str(self.cache_dir)
        )
        model = model.to(device)
        model.eval()
        bundle = (tokenizer, model, torch, device)
        self._models[target_lang] = bundle
        return bundle

    def _translate_opus_mt(self, text: str, target_lang: str) -> str:
        tokenizer, model, torch, device = self._load_opus_mt(target_lang)
        encoded = tokenizer(
            [text], return_tensors="pt", padding=True, truncation=True
        )
        encoded = {k: v.to(device) for k, v in encoded.items()}
        with torch.inference_mode():
            generated = model.generate(**encoded)
        return str(tokenizer.decode(generated[0], skip_special_tokens=True))

    def _get_translator_fn(self) -> Callable[[str, str], str]:
        if self._translator_fn is not None:
            return self._translator_fn
        return self._translate_opus_mt

    def translate_missing_entries(
        self,
        source_store: KeyValueStore,
        target_store: KeyValueStore,
        target_lang: str,
        *,
        show_progress: bool = True,
    ) -> int:
        """Translate keys present in source_store missing from target_store."""
        missing_items = [
            (key, value)
            for key, value in source_store.store.items()
            if key not in target_store.store
        ]
        if not missing_items:
            return 0
        fn = self._get_translator_fn()
        translated_count = 0
        with tqdm_progress(
            missing_items,
            desc=f"Translate ({target_lang})",
            unit="entry",
            total=len(missing_items),
            enabled=show_progress,
        ) as pbar:
            for key, value in pbar:
                cleaned = translate_text(value, target_lang, translator_fn=fn)
                if cleaned:
                    target_store.set_value_at_index(key, cleaned)
                    translated_count += 1
        return translated_count
