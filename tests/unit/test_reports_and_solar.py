"""Independent checks for solar orientation, material quantities and drawing cuts."""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from home_design.adapters.drawings import DrawingExporter
from home_design.construction import Authoring
from home_design.geometry import extrude_polygon
from home_design.json_types import JsonObject
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.resolved import MeshData
from home_design.solar import RayOccluder, SolarPosition
from home_design.validation import ModelValidator


@pytest.mark.parametrize(
    ("at", "expected"),
    [("2026-06-21T12:00:00Z", 73.45), ("2026-12-21T12:00:00Z", 26.55)],
)
def test_solar_noon_matches_solstice_geometry_and_timezone_equivalence(
    at: str, expected: float
) -> None:
    position = SolarPosition.calculate(at, 40, 0)
    assert position["altitudeDegrees"] == pytest.approx(expected, abs=0.5)
    equivalent = SolarPosition.calculate(
        at.replace("12:00:00Z", "07:00:00-05:00"), 40, 0
    )
    assert equivalent == position
    rotated = SolarPosition.calculate(at, 40, 0, 90)
    original = Authoring.array(position["sunDirection"])
    direction = Authoring.array(rotated["sunDirection"])
    assert direction[0] == pytest.approx(original[1])
    assert isinstance(original[0], (float, int))
    assert direction[1] == pytest.approx(-original[0])


def test_shadow_rays_distinguish_obstruction_sky_and_surfaces_behind_origin() -> None:
    occluder = RayOccluder(
        [((-1000.0, -1000.0, 2000.0), (1000.0, -1000.0, 2000.0), (0.0, 1000.0, 2000.0))]
    )
    assert occluder.blocked((0, 0, 0), (0, 0, 1))
    assert not occluder.blocked((2000, 0, 0), (0, 0, 1))
    assert not occluder.blocked((0, 0, 3000), (0, 0, 1))


def test_section_retains_openings_instead_of_filling_nested_cut_loops() -> None:
    polygon = Polygon(
        [(0, 0), (4000, 0), (4000, 3000), (0, 3000)],
        [[(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)]],
    )
    solid = extrude_polygon(polygon, 0, 200, None, "slab")
    sections = DrawingExporter.section_polygons(solid, 2, 100)
    assert sum(section.area for section in sections) == pytest.approx(11_000_000)
    assert sum(len(section.interiors) for section in sections) == 1


@pytest.mark.parametrize("offset", [0.0, 1000000.0])
def test_drawing_projection_unions_near_coincident_facets_without_losing_holes(
    offset: float,
) -> None:
    """Opposite shell facets tolerate rounding noise at small and survey-scale origins."""
    profile = Polygon(
        [(offset, 0), (offset + 100, 0), (offset + 100, 100), (offset, 100)],
        [[(offset + 20, 20), (offset + 80, 20), (offset + 80, 80), (offset + 20, 80)]],
    )
    solid = extrude_polygon(profile, 0, 200, None, "hollow-stock")
    noisy = MeshData(
        tuple((x + (1e-10 if z > 0 else 0), y, z) for x, y, z in solid.vertices),
        solid.faces,
        solid.material_id,
        solid.role,
    )
    projected = DrawingExporter.project_polygons(noisy, 2)
    assert len(projected) == 1
    assert projected[0].is_valid
    assert projected[0].area == pytest.approx(6400, abs=0.001)
    assert len(projected[0].interiors) == 1


def test_concurrent_cavity_materials_do_not_double_count_wall_thickness(
    construction_model: JsonObject, validator: ModelValidator
) -> None:
    types = Authoring.object(construction_model["types"])
    wall_type = Authoring.object(types["type.wall"])
    layers = Authoring.array(wall_type["layers"])
    cavity = Authoring.object(layers[1])
    cavity["components"] = [
        {"material": "mat.wood", "fraction": 0.2},
        {"material": "mat.white", "fraction": 0.8},
    ]
    assert validator.validate(construction_model).is_valid
    resolved = ModelResolver(construction_model).resolve()
    wall = resolved.element("wall.south")
    assert wall.data["thickness"] == 176
    assert {mesh.material_id for mesh in wall.meshes} >= {
        "mat.stucco",
        "mat.wood",
        "mat.white",
    }
    schedule = ModelReports(resolved).schedules()
    assert Authoring.array(schedule["materials"])
    cavity["components"] = [
        {"material": "mat.wood", "fraction": 0.2},
        {"material": "mat.white", "fraction": 0.7},
    ]
    assert not validator.validate(construction_model).is_valid


def test_performance_requirements_use_type_defaults_and_explicit_element_overrides(
    construction_model: JsonObject, validator: ModelValidator
) -> None:
    types = Authoring.object(construction_model["types"])
    Authoring.object(types["type.wall"])["performance"] = {"rValueM2KW": 4}
    construction_model["requirements"] = [
        {
            "id": "requirement.thermal",
            "statement": "Wall assembly R value",
            "severity": "error",
            "appliesTo": ["wall.south"],
            "check": {
                "property": "performance.rValueM2KW",
                "operator": "atLeast",
                "value": 3.7,
            },
        }
    ]
    assert validator.validate(construction_model).is_valid
    elements = Authoring.object(construction_model["elements"])
    Authoring.object(elements["wall.south"])["performance"] = {"rValueM2KW": 3}
    report = validator.validate(construction_model)
    assert "requirement.unsatisfied" in {
        diagnostic.code for diagnostic in report.errors
    }


def test_framing_quantities_use_omitted_member_indices_and_true_length(
    construction_model: JsonObject,
) -> None:
    elements = Authoring.object(construction_model["elements"])
    Authoring.object(elements["framing.porch"])["omit"] = [3, 7]
    resolved = ModelResolver(construction_model).resolve()
    framing = resolved.element("framing.porch")
    assert framing.data["memberCount"] == 13
    volume = sum(ModelReports.mesh_volume(mesh) for mesh in framing.meshes)
    assert math.isclose(volume, 13 * 140 * 240 * 2998, rel_tol=1e-9)
