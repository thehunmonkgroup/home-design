"""Behavioral acceptance tests for coordinated exterior construction systems."""

from __future__ import annotations

import math

import pytest
import trimesh
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import number, vector2
from home_design.json_types import JsonObject
from home_design.resolver import ModelResolver
from home_design.terrain import TerrainSurface
from home_design.validation import ModelValidator


def test_reference_shell_has_complete_storeys_floors_and_excavated_interior(
    construction_model: JsonObject,
) -> None:
    resolved = ModelResolver(construction_model).resolve()
    for storey in ("level.lower", "level.upper"):
        walls = [
            element
            for element in resolved.elements
            if element.kind == "wall" and element.storey_id == storey
        ]
        assert len(walls) == 4
        perimeter = [
            LineString(
                [
                    vector2(point, "wall axis")
                    for point in Authoring.array(wall.data["axis"])
                ]
            )
            for wall in walls
        ]
        enclosed = list(polygonize(unary_union(perimeter)))
        assert len(enclosed) == 1
        assert enclosed[0].area == pytest.approx(60_000_000)
    lower = resolved.element("slab.house.lower")
    upper = resolved.element("slab.house.upper")
    assert lower.data["topElevation"] == 0
    assert upper.data["topElevation"] == 3000
    assert upper.data["bottomElevation"] == 2700
    for floor in (lower, upper):
        footprint = Authoring.object(floor.data["footprint"])
        assert Polygon(
            [
                vector2(point, "floor boundary")
                for point in Authoring.array(footprint["outer"])
            ]
        ).area == pytest.approx(60_000_000)
    for wall in resolved.elements:
        if wall.kind != "wall":
            continue
        if wall.storey_id == "level.lower":
            assert wall.data["topElevationRange"] == [2700, 2700]
            assert number(wall.data["baseElevation"], "wall base") <= 0
        else:
            assert wall.data["baseElevation"] == 3000
    terrain = TerrainSurface.from_element(
        Authoring.object(
            Authoring.object(construction_model["elements"])["terrain.proposed"]
        )
    )
    interior = Polygon([(226, 226), (9774, 226), (9774, 5774), (226, 5774)])
    for face in terrain.faces:
        triangle = Polygon([terrain.vertices[index][:2] for index in face])
        assert triangle.intersection(interior).area == 0
    assert terrain.height((4500, -1500)) < 0


def test_construction_solids_are_closed_and_terrain_is_an_open_surface(
    construction_model: JsonObject, validator: ModelValidator
) -> None:
    report = validator.validate(construction_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(construction_model).resolve()
    for element in resolved.elements:
        for data in element.meshes:
            mesh = trimesh.Trimesh(
                vertices=data.vertices, faces=data.faces, process=False
            )
            if element.kind == "terrain":
                assert not mesh.is_watertight
                assert all(normal[2] > 0 for normal in mesh.face_normals)
            else:
                assert mesh.is_watertight, (element.element_id, data.role)
                assert mesh.is_winding_consistent, (element.element_id, data.role)
                assert mesh.volume > 0, (element.element_id, data.role)


def test_grade_changes_propagate_to_footings_posts_stairs_and_handrails(
    construction_model: JsonObject,
) -> None:
    first = ModelResolver(construction_model).resolve()
    elements = Authoring.object(construction_model["elements"])
    terrain = Authoring.object(elements["terrain.proposed"])
    terrain["points"] = [
        [point[0], point[1], point[2] + 400]
        for point in TerrainSurface.from_element(terrain).vertices
    ]
    second = ModelResolver(construction_model).resolve()
    before = first.element("footing.spa").data["topElevation"]
    after = second.element("footing.spa").data["topElevation"]
    assert isinstance(before, (int, float)) and isinstance(after, (int, float))
    assert after - before == pytest.approx(400)
    assert (
        first.element("post.spa").data["memberLength"]
        != second.element("post.spa").data["memberLength"]
    )
    assert (
        first.element("stair.entry").data["riserCount"]
        != second.element("stair.entry").data["riserCount"]
    )
    assert (
        first.element("handrail.entry").data["path"]
        != second.element("handrail.entry").data["path"]
    )
    assert (
        first.element("stair.entry").data["clearWidth"]
        == second.element("stair.entry").data["clearWidth"]
        == 1220
    )
    assert (
        first.element("stair.entry").data["topElevation"]
        == second.element("stair.entry").data["topElevation"]
        == 3000
    )


def test_oriented_member_volume_preserves_rolled_section_and_true_axis_length() -> None:
    start = (100.0, 200.0, 300.0)
    end = (3100.0, 4200.0, 12300.0)
    mesh = ConstructionGeometry.member(
        start,
        end,
        {"kind": "rectangle", "width": 140, "depth": 240},
        None,
        "beam",
        roll=37,
    )
    solid = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
    assert solid.volume == pytest.approx(140 * 240 * math.dist(start, end))


def test_swept_profiles_have_shared_miters_and_preserve_hollow_sections() -> None:
    section: JsonObject = {
        "kind": "profile",
        "profile": {
            "outer": [[-50, -50], [50, -50], [50, 50], [-50, 50]],
            "holes": [[[-40, -40], [-40, 40], [40, 40], [40, -40]]],
        },
    }
    meshes = ConstructionGeometry.sweep(
        [(0, 0, 0), (1000, 0, 0), (1000, 1000, 0), (1000, 1000, 1000)], section, None
    )
    solids = [
        trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
        for mesh in meshes
    ]
    assert all(solid.is_watertight and solid.is_winding_consistent for solid in solids)
    assert sum(solid.volume for solid in solids) == pytest.approx(
        3000 * (100**2 - 80**2)
    )
    for a, b in zip(meshes, meshes[1:]):
        assert len(set(a.vertices) & set(b.vertices)) == 8
    with pytest.raises(ResolutionError, match="miter consumes"):
        ConstructionGeometry.sweep(
            [(0, 0, 0), (10, 0, 0), (10, 1000, 0)], section, None
        )


@pytest.mark.parametrize(
    "failure",
    [
        "stair_risers",
        "terrain_coverage",
        "drain_fall",
        "guard_gap",
        "support_path",
        "load_footprint",
        "framing_index",
        "missing_type",
        "bearing_point",
        "drain_connection",
        "outlet_exclusion",
        "support_cycle",
    ],
)
def test_invalid_construction_intent_is_rejected_before_export(
    construction_model: JsonObject, validator: ModelValidator, failure: str
) -> None:
    elements = Authoring.object(construction_model["elements"])
    expected = "geometry.resolution-failed"
    if failure == "stair_risers":
        Authoring.object(elements["stair.entry"])["riserCount"] = 2
    elif failure == "terrain_coverage":
        bottom = Authoring.object(Authoring.object(elements["stair.entry"])["bottom"])
        bottom["point"] = [1000000, 1000000]
    elif failure == "drain_fall":
        drain = Authoring.object(elements["drain.foundation"])
        drain["path"] = list(reversed(Authoring.array(drain["path"])))
    elif failure == "guard_gap":
        Authoring.object(elements["guard.porch"])["openings"] = [
            {"start": 1000, "end": 3000},
            {"start": 2000, "end": 4000},
        ]
    elif failure == "support_path":
        del Authoring.object(construction_model["relationships"])["support.footing"]
        expected = "load.incomplete-support-path"
    elif failure == "load_footprint":
        Authoring.object(elements["load.spa"])["target"] = "slab.upper"
        expected = "load.outside-target"
    elif failure == "framing_index":
        Authoring.object(elements["framing.porch"])["omit"] = [1000]
    elif failure == "bearing_point":
        Authoring.object(
            Authoring.object(construction_model["relationships"])["support.footing"]
        )["bearingPoint"] = [100000, 100000, 100000]
        expected = "support.bearing-outside-element"
    elif failure == "drain_connection":
        Authoring.object(construction_model["relationships"])["drain.disconnected"] = {
            "kind": "drainsTo",
            "source": "drain.foundation",
            "target": "drain.foundation",
        }
        expected = "drainage.disconnected"
    elif failure == "outlet_exclusion":
        Authoring.object(Authoring.object(elements["drain.foundation"])["outlet"])[
            "exclusionRadius"
        ] = 100000
        expected = "drainage.outlet-near-footing"
    elif failure == "support_cycle":
        Authoring.object(construction_model["relationships"])["support.cycle"] = {
            "kind": "supports",
            "support": "slab.spa",
            "supported": "post.spa",
        }
        expected = "load.incomplete-support-path"
    else:
        Authoring.object(elements["post.spa"])["type"] = "type.missing"
        expected = "reference.missing"
    report = validator.validate(construction_model)
    assert not report.is_valid
    assert expected in {
        diagnostic.code for diagnostic in report.errors
    }, report.to_dict()


def test_screens_remain_distinct_from_structural_guards(
    construction_model: JsonObject,
) -> None:
    elements = Authoring.object(construction_model["elements"])
    Authoring.object(elements["screen.porch"])["openings"] = [
        {"start": 1390.4, "end": 2390.4}
    ]
    resolved = ModelResolver(construction_model).resolve()
    assert resolved.element("screen.porch").data["isStructuralGuard"] is False
    assert resolved.element("guard.porch").data["isStructuralGuard"] is True
    assert resolved.element("handrail.entry").data["isStructuralGuard"] is False
    screen = resolved.element("screen.porch")
    assert any(mesh.material_id == "mat.screen" for mesh in screen.meshes)
    assert all(
        not (
            min(vertex[0] for vertex in mesh.vertices)
            < 2500
            < max(vertex[0] for vertex in mesh.vertices)
        )
        for mesh in screen.meshes
    )


def test_grade_exposure_uses_sloping_wall_top_at_each_station(
    construction_model: JsonObject,
) -> None:
    elements = Authoring.object(construction_model["elements"])
    Authoring.object(elements["wall.east"])["grade"] = "terrain.proposed"
    wall = ModelResolver(construction_model).resolve().element("wall.east")
    samples = [
        Authoring.object(value)
        for value in Authoring.array(Authoring.object(wall.data["grade"])["samples"])
    ]
    heights = [sample["exposedHeight"] for sample in samples]
    assert all(isinstance(height, (int, float)) for height in heights)
    assert max(float(str(height)) for height in heights) - min(
        float(str(height)) for height in heights
    ) == pytest.approx(2000)
