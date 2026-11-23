"""Contract parity tests aligning photosphere.models.database with contracts/."""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError

from photosphere.init.models import PhotosphereConfig
from photosphere.models.database import (
    AlbumRecord,
    KeyValueDictionary,
    MediaDatabase,
    validate_against_contract,
)
from tests.conftest import CONTRACTS_DIR


def _load(rel_path: str) -> Any:
    return json.loads((CONTRACTS_DIR / rel_path).read_text(encoding="utf-8"))


def test_fixtures_pass_json_schemas_and_pydantic_models() -> None:
    media_fixture = _load("fixtures/valid_media_db.json")
    labels_fixture = _load("fixtures/valid_en_labels.json")
    captions_fixture = _load("fixtures/valid_en_captions.json")
    albums_fixture = _load("fixtures/valid_albums.json")

    jsonschema.validate(media_fixture, _load("media_database.schema.json"))
    jsonschema.validate(labels_fixture, _load("kv_dictionary.schema.json"))
    jsonschema.validate(captions_fixture, _load("kv_dictionary.schema.json"))
    jsonschema.validate(albums_fixture, _load("albums.schema.json"))

    validate_against_contract(media_fixture, "media")
    validate_against_contract(labels_fixture, "kv")
    validate_against_contract(captions_fixture, "kv")
    validate_against_contract(albums_fixture, "albums")


def test_schema_and_models_reject_tinydb_wrapper_and_local_file_path() -> None:
    legacy = _load("fixtures/legacy_v2_tinydb.json")
    media_schema = _load("media_database.schema.json")

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(legacy, media_schema)
    with pytest.raises(ValidationError):
        MediaDatabase.model_validate(legacy)

    valid_with_local_path = _load("fixtures/valid_media_db.json")
    first_key = next(iter(valid_with_local_path))
    valid_with_local_path[first_key]["local_file_path"] = "/Users/dev/photo.jpg"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_with_local_path, media_schema)
    with pytest.raises(ValidationError):
        MediaDatabase.model_validate(valid_with_local_path)


def test_models_reject_mismatched_key_or_invalid_dictionary_index() -> None:
    media_fixture = _load("fixtures/valid_media_db.json")
    first_key = next(iter(media_fixture))
    mismatched = {"b" * 40: media_fixture[first_key]}
    with pytest.raises(ValidationError):
        MediaDatabase.model_validate(mismatched)

    with pytest.raises(ValidationError):
        KeyValueDictionary.model_validate({"not_an_int": "dog"})

    with pytest.raises(ValidationError):
        AlbumRecord.model_validate({"name": "Trips", "hashes": ["bad-hash"]})


def test_photosphere_config_fixture_matches_schema_and_model() -> None:
    config_fixture = _load("fixtures/valid_photosphere_config.json")
    config_schema = _load("photosphere_config.schema.json")
    jsonschema.validate(config_fixture, config_schema)
    parsed = PhotosphereConfig.model_validate(config_fixture)
    assert parsed.storage.media_storage_class == "STANDARD"
    assert parsed.storage.data_storage_class == "STANDARD"
