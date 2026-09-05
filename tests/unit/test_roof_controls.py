"""Regression checks tying roof placements and clearances to physical solids."""

from __future__ import annotations

import math
from copy import deepcopy

import pytest

from home_design.json_types import JsonObject
from home_design.construction import Authoring
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class RoofFixture:
    """Author isolated roof variants without changing the reference model file."""

    @staticmethod
    def elements(model: JsonObject) -> dict[str, JsonObject]:
        registry = model["elements"]
        assert isinstance(registry, dict)
        return {
            key: value for key, value in registry.items() if isinstance(value, dict)
        }

    @classmethod
    def shed(cls, model: JsonObject) -> JsonObject:
        elements = cls.elements(model)
        roof = elements["roof.main"]
        geometry = roof["geometry"]
        assert isinstance(geometry, dict)
        geometry.update(
            {
                "form": "shed",
                "pitch": math.degrees(math.atan(8 / 12)),
                "slopeDirection": [0, 1],
            }
        )
        geometry.pop("ridgeDirection", None)
        for element in elements.values():
            if element.get("kind") == "wall":
                element["top"] = {"kind": "height", "height": 2400}
        return geometry


@pytest.mark.parametrize("explicit", [False, True])
def test_roof_underside_queries_match_extruded_bottom_plane(
    reference_model: JsonObject, explicit: bool
) -> None:
    geometry = RoofFixture.shed(reference_model)
    if explicit:
        geometry.clear()
        geometry.update(
            {
                "kind": "faceSet",
                "faces": [
                    {
                        "id": "face.shed",
                        "boundary": {
                            "outer": [
                                [-600, -600, 3000],
                                [10600, -600, 3000],
                                [10600, 8600, 3000 + 9200 * 8 / 12],
                                [-600, 8600, 3000 + 9200 * 8 / 12],
                            ]
                        },
                    }
                ],
            }
        )
    resolver = ModelResolver(reference_model)
    roof = resolver.resolve().element("roof.main")
    mesh = roof.meshes[-1]
    lower = mesh.vertices[len(mesh.vertices) // 2 :]
    center = tuple(
        sum(vertex[axis] for vertex in lower) / len(lower) for axis in range(3)
    )
    datum: JsonObject = {
        "kind": "surface",
        "element": "roof.main",
        "surface": "underside",
        "point": [center[0], center[1]],
        "offset": 0,
    }
    assert resolver.elevation(datum) == pytest.approx(center[2], abs=1e-6)


def test_bearing_datum_keeps_ridge_fixed_under_asymmetric_overhang_changes(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    elements = RoofFixture.elements(reference_model)
    geometry = elements["roof.main"]["geometry"]
    assert isinstance(geometry, dict)
    geometry.update(
        {
            "datumReference": "bearing",
            "datumSurface": "underside",
            "edgeOverhangs": [300, 600, 900, 1200],
        }
    )
    assert validator.validate(reference_model).is_valid
    first = ModelResolver(reference_model)
    first.resolve()
    original = first.roof_surfaces["roof.main"]
    geometry["edgeOverhangs"] = [1200, 900, 300, 600]
    second = ModelResolver(reference_model)
    second.resolve()
    changed = second.roof_surfaces["roof.main"]
    assert changed.top_height(5000, 4000) == pytest.approx(
        original.top_height(5000, 4000)
    )
    assert changed.underside_height(5000, 0) == pytest.approx(2700)
    assert changed.footprint.bounds != original.footprint.bounds


def test_asymmetric_hip_overhangs_preserve_planar_faces_and_bearing_heights(
    reference_model: JsonObject,
) -> None:
    geometry = RoofFixture.shed(reference_model)
    geometry.update(
        {
            "form": "hip",
            "datumReference": "bearing",
            "datumSurface": "underside",
            "edgeOverhangs": [300, 600, 900, 1200],
        }
    )
    geometry.pop("slopeDirection", None)
    resolver = ModelResolver(reference_model)
    roof = resolver.resolve().element("roof.main")
    assert len(Authoring.array(roof.data["faceIds"])) == 4
    assert resolver.roof_surfaces["roof.main"].underside_height(
        5000, 0
    ) == pytest.approx(2700)
    for mesh in roof.meshes:
        if not mesh.role.endswith(":layer:2"):
            continue
        lower = mesh.vertices[len(mesh.vertices) // 2 :]
        center = [sum(point[axis] for point in lower) / len(lower) for axis in range(3)]
        actual = resolver.roof_surfaces["roof.main"].underside_height(
            center[0], center[1]
        )
        assert actual == pytest.approx(center[2], abs=1e-6)


def test_attached_roof_tracks_host_and_rejects_insufficient_headroom(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    geometry = RoofFixture.shed(reference_model)
    elements = reference_model["elements"]
    assert isinstance(elements, dict)
    original = elements["roof.main"]
    assert isinstance(original, dict)
    porch: JsonObject = deepcopy(original)
    porch_geometry: JsonObject = {
        "kind": "parametric",
        "form": "shed",
        "pitch": math.degrees(math.atan(1 / 12)),
        "slopeDirection": [0, 1],
        "footprint": {
            "outer": [
                {"point": [0, -3000]},
                {"point": [7000, -3000]},
                {"point": [7000, 0]},
                {"point": [0, 0]},
            ]
        },
        "overhang": 0,
        "datumPoint": [3500, 0],
        "eaveDatum": {
            "kind": "surface",
            "element": "roof.main",
            "surface": "underside",
            "point": [3500, 0],
            "offset": -100,
        },
    }
    porch["geometry"] = porch_geometry
    porch["clearances"] = [
        {
            "name": "Outer porch headroom",
            "lower": {"kind": "level", "level": "level.ground", "offset": 0},
            "upper": {
                "kind": "surface",
                "element": "roof.porch",
                "surface": "underside",
                "point": [3500, -3000],
                "offset": 0,
            },
            "minimum": 2000,
        }
    ]
    elements["roof.porch"] = porch
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    before = ModelResolver(reference_model)
    before.resolve()
    datum = geometry["eaveDatum"]
    assert isinstance(datum, dict)
    datum["offset"] = -1500
    after = ModelResolver(reference_model)
    after.resolve()
    assert after.roof_surfaces["roof.porch"].eave_z == pytest.approx(
        before.roof_surfaces["roof.porch"].eave_z - 1500
    )
    assert "clearance.insufficient" in {
        diagnostic.code for diagnostic in validator.validate(reference_model).errors
    }
