"""Unit tests for semantic and topology validation rules."""

from __future__ import annotations

from copy import deepcopy

from home_design.json_types import JsonObject
from home_design.validation import ModelValidator


def test_reference_model_passes_all_layers(
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()


def test_non_unit_roof_direction_is_rejected(
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    roof = _element(reference_model, "roof.main")
    geometry = roof["geometry"]
    assert isinstance(geometry, dict)
    geometry["ridgeDirection"] = [2, 0]
    report = validator.validate(reference_model)
    assert any(item.code == "geometry.non-unit-vector" for item in report.errors)


def test_overlapping_openings_are_rejected(
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    elements = reference_model["elements"]
    relationships = reference_model["relationships"]
    assert isinstance(elements, dict) and isinstance(relationships, dict)
    duplicate = deepcopy(elements["opening.window.north"])
    assert isinstance(duplicate, dict)
    duplicate["name"] = "Overlapping test opening"
    elements["opening.window.overlap"] = duplicate
    relationships["rel.voids.overlap"] = {
        "kind": "voids",
        "host": "wall.north",
        "opening": "opening.window.overlap",
    }
    report = validator.validate(reference_model)
    assert any(item.code == "opening.overlap" for item in report.errors)


def test_disconnected_declared_join_is_rejected(
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    relationship = _relationship(reference_model, "rel.joins.north-east")
    endpoint = relationship["a"]
    assert isinstance(endpoint, dict)
    endpoint["at"] = "start"
    report = validator.validate(reference_model)
    assert any(item.code == "join.disconnected" for item in report.errors)


def test_fill_larger_than_opening_is_rejected(
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    opening = _element(reference_model, "opening.window.north")
    geometry = opening["geometry"]
    assert isinstance(geometry, dict)
    geometry["width"] = 1000
    report = validator.validate(reference_model)
    assert any(item.code == "fill.exceeds-opening" for item in report.errors)


def test_opening_outside_host_path_is_rejected(
    validator: ModelValidator,
    reference_model: JsonObject,
) -> None:
    opening = _element(reference_model, "opening.window.north")
    placement = opening["placement"]
    assert isinstance(placement, dict)
    placement["station"] = 10000
    report = validator.validate(reference_model)
    assert any(item.code == "opening.outside-host-path" for item in report.errors)


def _element(model: JsonObject, element_id: str) -> JsonObject:
    elements = model["elements"]
    assert isinstance(elements, dict)
    element = elements[element_id]
    assert isinstance(element, dict)
    return element


def _relationship(model: JsonObject, relationship_id: str) -> JsonObject:
    relationships = model["relationships"]
    assert isinstance(relationships, dict)
    relationship = relationships[relationship_id]
    assert isinstance(relationship, dict)
    return relationship
