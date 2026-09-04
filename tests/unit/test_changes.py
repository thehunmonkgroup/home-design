"""Unit tests for atomic AI-directed model changes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from home_design.changes import ChangeEngine
from home_design.errors import ChangeConflictError, ModelValidationError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


def test_valid_change_increments_revision_and_preserves_input(
    loader: ModelLoader,
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    engine = ChangeEngine(loader, validator)
    revision = _revision(reference_model)
    change = _move_change(4500, revision)
    result = engine.apply(reference_model, change)
    assert reference_model["revision"] == revision
    assert result["revision"] == revision + 1
    assert _station(result) == 4500


def test_revision_and_value_preconditions_prevent_stale_changes(
    loader: ModelLoader,
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    engine = ChangeEngine(loader, validator)
    revision = _revision(reference_model)
    stale_revision = _move_change(4500, revision)
    stale_revision["baseRevision"] = revision + 1
    with pytest.raises(ChangeConflictError, match="expects revision"):
        engine.apply(reference_model, stale_revision)
    stale_value = _move_change(4500, revision)
    preconditions = stale_value["preconditions"]
    assert isinstance(preconditions, list) and isinstance(preconditions[0], dict)
    preconditions[0]["equals"] = 3900
    with pytest.raises(ChangeConflictError, match="Precondition failed"):
        engine.apply(reference_model, stale_value)


def test_invalid_geometry_change_is_rejected_without_writing(
    loader: ModelLoader,
    validator: ModelValidator,
    model_file: Path,
    reference_model: JsonObject,
    tmp_path: Path,
) -> None:
    change_path = tmp_path / "invalid-change.json"
    change_path.write_text(
        json.dumps(_move_change(20000, _revision(reference_model))), encoding="utf-8"
    )
    original = model_file.read_bytes()
    with pytest.raises(ModelValidationError, match="opening.outside-host-path"):
        ChangeEngine(loader, validator).apply_to_file(model_file, change_path)
    assert model_file.read_bytes() == original


def test_successful_file_change_commits_atomically_to_new_path(
    loader: ModelLoader,
    validator: ModelValidator,
    model_file: Path,
    reference_model: JsonObject,
    tmp_path: Path,
) -> None:
    change_path = tmp_path / "change.json"
    output_path = tmp_path / "next.json"
    change_path.write_text(
        json.dumps(_move_change(4500, _revision(reference_model))), encoding="utf-8"
    )
    result = ChangeEngine(loader, validator).apply_to_file(
        model_file, change_path, output_path
    )
    assert output_path.is_file()
    assert loader.load(output_path) == result
    assert _station(result) == 4500


def test_generic_registry_and_pointer_operations_remain_transactional(
    loader: ModelLoader,
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": "change.material-and-description",
        "description": "Add a material and update the project description",
        "baseRevision": _revision(reference_model),
        "operations": [
            {
                "op": "putObject",
                "registry": "materials",
                "objectId": "material.test",
                "value": {"name": "Test material", "category": "test"},
            },
            {
                "op": "set",
                "path": "/project/description",
                "value": "Updated through a transaction",
            },
        ],
    }
    result = ChangeEngine(loader, validator).apply(reference_model, change)
    materials = result["materials"]
    project = result["project"]
    assert isinstance(materials, dict) and isinstance(project, dict)
    assert materials["material.test"] == {"name": "Test material", "category": "test"}
    assert project["description"] == "Updated through a transaction"


def test_removing_a_referenced_object_is_rejected(
    loader: ModelLoader,
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": "change.remove-used-material",
        "description": "Attempt to remove a referenced material",
        "baseRevision": _revision(reference_model),
        "operations": [
            {
                "op": "removeObject",
                "registry": "materials",
                "objectId": "material.timber",
            }
        ],
    }
    with pytest.raises(ModelValidationError, match="reference.missing"):
        ChangeEngine(loader, validator).apply(reference_model, change)


def test_move_anchor_operation_propagates_to_connected_components(
    loader: ModelLoader,
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": "change.widen-house",
        "description": "Move both east anchors to widen the house",
        "baseRevision": _revision(reference_model),
        "operations": [
            {"op": "moveAnchor", "anchorId": "anchor.house.se", "position": [11000, 0]},
            {
                "op": "moveAnchor",
                "anchorId": "anchor.house.ne",
                "position": [11000, 8000],
            },
        ],
    }
    result = ChangeEngine(loader, validator).apply(reference_model, change)
    elements = result["elements"]
    assert isinstance(elements, dict)
    resolved = ModelResolver(result).resolve()
    east_axis = resolved.element("wall.east").data["axis"]
    ground = resolved.element("slab.ground").data["footprint"]
    assert east_axis == [[11000.0, 8000.0], [11000.0, 0.0]]
    assert isinstance(ground, dict)
    outer = ground["outer"]
    assert isinstance(outer, list)
    assert [11000.0, 0.0] in outer


def _move_change(station: float, base_revision: int) -> JsonObject:
    return {
        "changeVersion": "0.1",
        "id": "change.test-window",
        "description": "Move a test window",
        "baseRevision": base_revision,
        "preconditions": [
            {
                "path": "/elements/opening.window.north/placement/station",
                "equals": 4000,
            }
        ],
        "operations": [
            {
                "op": "moveOpening",
                "openingId": "opening.window.north",
                "station": station,
            }
        ],
    }


def _station(model: JsonObject) -> object:
    elements = model["elements"]
    assert isinstance(elements, dict)
    opening = elements["opening.window.north"]
    assert isinstance(opening, dict)
    placement = opening["placement"]
    assert isinstance(placement, dict)
    return placement["station"]


def _revision(model: JsonObject) -> int:
    revision = model["revision"]
    assert isinstance(revision, int) and not isinstance(revision, bool)
    return revision
