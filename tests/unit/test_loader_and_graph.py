"""Unit tests for schema loading and reference analysis."""

from __future__ import annotations

from home_design.graph import ModelIndex
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader


def test_reference_model_satisfies_schema(
    loader: ModelLoader, reference_model: JsonObject
) -> None:
    report = loader.validate_schema(reference_model)
    assert report.is_valid
    assert report.diagnostics == ()


def test_schema_rejects_unknown_fields(
    loader: ModelLoader, reference_model: JsonObject
) -> None:
    reference_model["inventedMeshCache"] = {}
    report = loader.validate_schema(reference_model)
    assert not report.is_valid
    assert any(item.code == "schema.additionalProperties" for item in report.errors)


def test_index_reports_missing_and_wrong_kind_references(
    reference_model: JsonObject,
) -> None:
    elements = reference_model["elements"]
    assert isinstance(elements, dict)
    wall = elements["wall.north"]
    window = elements["window.north"]
    assert isinstance(wall, dict) and isinstance(window, dict)
    wall["storey"] = "level.missing"
    window["type"] = "doorType.entry-900x2100"
    diagnostics = ModelIndex(reference_model).diagnostics()
    assert {item.code for item in diagnostics} >= {
        "reference.missing",
        "reference.kind-mismatch",
    }


def test_index_detects_geometry_dependency_cycle(reference_model: JsonObject) -> None:
    elements = reference_model["elements"]
    assert isinstance(elements, dict)
    east = elements["wall.east"]
    south = elements["wall.south"]
    assert isinstance(east, dict) and isinstance(south, dict)
    east["top"] = {
        "kind": "surface",
        "element": "wall.south",
        "surface": "top",
        "offset": 0,
    }
    south["top"] = {
        "kind": "surface",
        "element": "wall.east",
        "surface": "top",
        "offset": 0,
    }
    diagnostics = ModelIndex(reference_model).diagnostics()
    assert any(item.code == "dependency.cycle" for item in diagnostics)


def test_opening_and_fill_relationship_lookups(reference_model: JsonObject) -> None:
    index = ModelIndex(reference_model)
    assert index.host_for_opening("opening.window.north") == "wall.north"
    assert index.opening_for_fill("window.north") == "opening.window.north"
