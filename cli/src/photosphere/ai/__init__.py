"""Modular AI provider contracts and deterministic KeyValue / EasyNMT translation."""

from photosphere.ai.moondream2 import Moondream2Provider
from photosphere.ai.normalize import (
    normalize_caption,
    normalize_tags,
    parse_tags_response,
)
from photosphere.ai.protocol import (
    AIInferenceError,
    AINotConfiguredError,
    AIProvider,
    MediaAnnotation,
    configure_hf_cache_env,
    load_optional_ai_provider,
    resolve_device,
    resolve_dtype,
)
from photosphere.ai.translator import EasyNMTTranslator, KeyValueStore, translate_text

__all__ = [
    "AIInferenceError",
    "AINotConfiguredError",
    "AIProvider",
    "EasyNMTTranslator",
    "KeyValueStore",
    "MediaAnnotation",
    "Moondream2Provider",
    "configure_hf_cache_env",
    "load_optional_ai_provider",
    "normalize_caption",
    "normalize_tags",
    "parse_tags_response",
    "resolve_device",
    "resolve_dtype",
    "translate_text",
]
