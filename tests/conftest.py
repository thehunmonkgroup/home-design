"""Shared fixtures for home design tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import pytest

from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.validation import ModelValidator

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_MODEL = ROOT / "tests" / "fixtures" / "basic-shell.json"
CONSTRUCTION_MODEL = ROOT / "examples" / "hillside-deck-house.json"


@pytest.fixture
def loader() -> ModelLoader:
    """Return a schema-aware model loader.

    :returns: Model loader for the project schema.
    """
    return ModelLoader()


@pytest.fixture
def validator(loader: ModelLoader) -> ModelValidator:
    """Return the coordinated validator.

    :param loader: Schema-aware loader fixture.
    :returns: Complete model validator.
    """
    return ModelValidator(loader)


@pytest.fixture
def reference_model() -> JsonObject:
    """Return a fresh reference-model copy.

    :returns: Mutable canonical model fixture.
    """
    value = json.loads(REFERENCE_MODEL.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return deepcopy(value)


@pytest.fixture
def construction_model(loader: ModelLoader) -> JsonObject:
    """Load the complete metric construction-system example."""
    return loader.load(CONSTRUCTION_MODEL)


@pytest.fixture
def model_file(tmp_path: Path, reference_model: JsonObject) -> Path:
    """Write a disposable canonical model.

    :param tmp_path: Pytest temporary directory.
    :param reference_model: Reference model fixture.
    :returns: Temporary model path.
    """
    path = tmp_path / "home.json"
    path.write_text(json.dumps(reference_model, indent=2) + "\n", encoding="utf-8")
    return path
