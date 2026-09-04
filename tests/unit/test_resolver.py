"""Unit tests for component resolution and integration geometry."""

from __future__ import annotations

import math
from copy import deepcopy

import pytest

from home_design.json_types import JsonObject
from home_design.resolved import MeshData
from home_design.resolver import ModelResolver


def test_reference_model_resolves_every_element(reference_model: JsonObject) -> None:
    resolved = ModelResolver(reference_model).resolve()
    elements = reference_model["elements"]
    assert isinstance(elements, dict)
    assert len(resolved.elements) == len(elements)
    assert {element.kind for element in resolved.elements} == {
        "assembly",
        "door",
        "opening",
        "roof",
        "slab",
        "space",
        "wall",
        "window",
    }
    assert resolved.element("slab.deck.south").data["topElevation"] == -25.0
    assert resolved.element("space.living").data["area"] == pytest.approx(9815 * 7815)


def test_wall_mesh_is_cut_by_hosted_opening(reference_model: JsonObject) -> None:
    with_opening = ModelResolver(reference_model).resolve().element("wall.north")
    relationships = reference_model["relationships"]
    elements = reference_model["elements"]
    assert isinstance(relationships, dict) and isinstance(elements, dict)
    del relationships["rel.voids.north-window"]
    del relationships["rel.fills.north-window"]
    del elements["opening.window.north"]
    del elements["window.north"]
    without_opening = ModelResolver(reference_model).resolve().element("wall.north")
    assert _mesh_area_projection(with_opening.meshes[0]) < _mesh_area_projection(
        without_opening.meshes[0]
    )


def test_roof_surface_drives_sloped_wall_tops(reference_model: JsonObject) -> None:
    resolved = ModelResolver(reference_model).resolve()
    north = resolved.element("wall.north")
    east = resolved.element("wall.east")
    north_range = north.data["topElevationRange"]
    east_range = east.data["topElevationRange"]
    assert isinstance(north_range, list) and isinstance(east_range, list)
    assert all(isinstance(value, (int, float)) for value in (*north_range, *east_range))
    north_values = [
        float(value) for value in north_range if isinstance(value, (int, float))
    ]
    east_values = [
        float(value) for value in east_range if isinstance(value, (int, float))
    ]
    assert north_values[0] == pytest.approx(north_values[1])
    assert east_values[1] - east_values[0] > 1500


@pytest.mark.parametrize(
    ("geometry", "expected_faces"),
    [
        (
            {
                "kind": "parametric",
                "form": "flat",
                "footprint": None,
                "eaveDatum": None,
                "overhang": 300,
            },
            1,
        ),
        (
            {
                "kind": "parametric",
                "form": "shed",
                "footprint": None,
                "eaveDatum": None,
                "pitch": 12,
                "slopeDirection": [0, 1],
                "overhang": 300,
            },
            1,
        ),
        (
            {
                "kind": "parametric",
                "form": "gable",
                "footprint": None,
                "eaveDatum": None,
                "pitch": 30,
                "ridgeDirection": [1, 0],
                "overhang": 300,
            },
            2,
        ),
        (
            {
                "kind": "parametric",
                "form": "hip",
                "footprint": None,
                "eaveDatum": None,
                "pitch": 25,
                "overhang": 300,
            },
            4,
        ),
    ],
)
def test_all_parametric_roof_forms_resolve(
    reference_model: JsonObject,
    geometry: JsonObject,
    expected_faces: int,
) -> None:
    roof = _element(reference_model, "roof.main")
    original = roof["geometry"]
    assert isinstance(original, dict)
    geometry = deepcopy(geometry)
    geometry["footprint"] = deepcopy(original["footprint"])
    geometry["eaveDatum"] = deepcopy(original["eaveDatum"])
    roof["geometry"] = geometry
    _set_wall_heights(reference_model)
    resolved = ModelResolver(reference_model).resolve().element("roof.main")
    assert len(resolved.meshes) == expected_faces
    assert all(mesh.vertices and mesh.faces for mesh in resolved.meshes)


def test_explicit_roof_face_set_resolves(reference_model: JsonObject) -> None:
    roof = _element(reference_model, "roof.main")
    roof["geometry"] = {
        "kind": "faceSet",
        "faces": [
            {
                "id": "roof-face.test",
                "boundary": {
                    "outer": [
                        [-500, -500, 3000],
                        [10500, -500, 3000],
                        [10500, 8500, 3500],
                        [-500, 8500, 3500],
                    ]
                },
            }
        ],
    }
    _set_wall_heights(reference_model)
    resolved = ModelResolver(reference_model).resolve().element("roof.main")
    assert len(resolved.meshes) == 1
    assert resolved.data["form"] == "faceSet"


def test_explicit_roof_faces_continue_to_drive_wall_tops(
    reference_model: JsonObject,
) -> None:
    roof = _element(reference_model, "roof.main")
    roof["geometry"] = {
        "kind": "faceSet",
        "faces": [
            {
                "id": "north-slope",
                "boundary": {
                    "outer": [
                        [-600, 8600, 2700],
                        [10600, 8600, 2700],
                        [10600, 4000, 5355],
                        [-600, 4000, 5355],
                    ]
                },
            },
            {
                "id": "south-slope",
                "boundary": {
                    "outer": [
                        [-600, 4000, 5355],
                        [10600, 4000, 5355],
                        [10600, -600, 2700],
                        [-600, -600, 2700],
                    ]
                },
            },
        ],
    }
    resolved = ModelResolver(reference_model).resolve()
    east = resolved.element("wall.east")
    elevations = east.data["topElevationRange"]
    assert isinstance(elevations, list)
    numeric = [float(value) for value in elevations if isinstance(value, (int, float))]
    assert numeric[1] - numeric[0] > 2000
    assert len(east.meshes) == 2


def test_profile_opening_and_polyline_wall_resolve(reference_model: JsonObject) -> None:
    north = _element(reference_model, "wall.north")
    north["path"] = {
        "kind": "polyline",
        "points": [
            {"anchor": "anchor.house.nw"},
            {"point": [5000, 8200]},
            {"anchor": "anchor.house.ne"},
        ],
    }
    opening = _element(reference_model, "opening.window.north")
    opening["geometry"] = {
        "kind": "profile",
        "profile": {"outer": [[0, 0], [1540, 0], [1400, 1240], [140, 1240]]},
        "depth": 300,
    }
    resolved = ModelResolver(reference_model).resolve()
    assert len(resolved.element("wall.north").meshes) == 2
    assert resolved.element("opening.window.north").data["width"] == pytest.approx(1540)


def test_derived_space_uses_declared_wall_boundaries(
    reference_model: JsonObject,
) -> None:
    space = _element(reference_model, "space.living")
    space["geometry"] = {"kind": "derived", "seedPoint": [5000, 4000]}
    resolved = ModelResolver(reference_model).resolve().element("space.living")
    assert resolved.data["area"] == pytest.approx(80_000_000)


def test_upward_slab_extrusion_changes_vertical_range(
    reference_model: JsonObject,
) -> None:
    slab = _element(reference_model, "slab.ground")
    slab["extrusionDirection"] = "up"
    resolved = ModelResolver(reference_model).resolve().element("slab.ground")
    assert resolved.data["bottomElevation"] == 0.0
    assert resolved.data["topElevation"] == 200.0


def _mesh_area_projection(mesh: MeshData) -> float:
    vertices = mesh.vertices
    faces = mesh.faces
    area = 0.0
    for face in faces:
        a, b, c = (vertices[index] for index in face[:3])
        cross = (
            (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
            (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
            (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]),
        )
        area += math.sqrt(sum(value * value for value in cross)) / 2
    return area


def _set_wall_heights(model: JsonObject) -> None:
    elements = model["elements"]
    assert isinstance(elements, dict)
    for element in elements.values():
        if isinstance(element, dict) and element.get("kind") == "wall":
            element["top"] = {"kind": "height", "height": 2700}


def _element(model: JsonObject, element_id: str) -> JsonObject:
    elements = model["elements"]
    assert isinstance(elements, dict)
    element = elements[element_id]
    assert isinstance(element, dict)
    return element
