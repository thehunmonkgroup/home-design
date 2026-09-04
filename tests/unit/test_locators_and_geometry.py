"""Unit tests for anchor and primitive geometry resolution."""

from __future__ import annotations

import math

import trimesh
from shapely.geometry import Polygon

from home_design.geometry import (
    extrude_planar_face,
    extrude_polygon,
    extrude_wall_profile,
    normalize2,
)
from home_design.json_types import JsonObject
from home_design.locators import LocatorResolver, path_length, point_at_station
from home_design.resolved import MeshData


def assert_closed_outward_mesh(mesh_data: MeshData) -> trimesh.Trimesh:
    """Assert that generated mesh faces consistently enclose positive volume."""
    mesh = trimesh.Trimesh(
        vertices=mesh_data.vertices,
        faces=mesh_data.faces,
        process=False,
        validate=False,
    )
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0
    return mesh


def test_locator_resolves_axis_and_element_station_anchor(
    reference_model: JsonObject,
) -> None:
    anchors = reference_model["anchors"]
    assert isinstance(anchors, dict)
    anchors["anchor.north.mid"] = {
        "kind": "elementStation",
        "name": "North midpoint",
        "element": "wall.north",
        "station": 5000,
        "transverseOffset": 100,
        "verticalOffset": 250,
    }
    resolver = LocatorResolver(reference_model)
    assert resolver.path2(
        {"kind": "axisAnchor", "anchor": "anchor.wall.north-axis"}
    ) == (
        (0.0, 8000.0),
        (10000.0, 8000.0),
    )
    assert resolver.point2({"anchor": "anchor.north.mid"}) == (5000.0, 8100.0)
    assert resolver.point3_anchor("anchor.north.mid") == (5000.0, 8100.0, 250.0)


def test_polyline_stationing_crosses_segments() -> None:
    points = ((0.0, 0.0), (3000.0, 0.0), (3000.0, 4000.0))
    assert path_length(points) == 7000.0
    point, tangent = point_at_station(points, 5000.0)
    assert point == (3000.0, 2000.0)
    assert tangent == (0.0, 1.0)


def test_polygon_extrusion_with_hole_is_closed_and_outward() -> None:
    polygon = Polygon(
        [(0, 0), (4000, 0), (4000, 3000), (0, 3000)],
        [[(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)]],
    )
    mesh_data = extrude_polygon(polygon, 0, 200, None, "test")
    mesh = assert_closed_outward_mesh(mesh_data)
    assert math.isclose(mesh.volume, polygon.area * 200, rel_tol=1e-6)


def test_clockwise_polygon_extrusion_is_closed_and_outward() -> None:
    polygon = Polygon([(0, 0), (0, 3000), (4000, 3000), (4000, 0)])
    mesh = assert_closed_outward_mesh(extrude_polygon(polygon, 0, 200, None, "test"))
    assert math.isclose(mesh.volume, polygon.area * 200, rel_tol=1e-6)


def test_wall_profile_with_opening_is_closed_and_outward() -> None:
    profile = Polygon(
        [(0, 0), (4000, 0), (4000, 3000), (0, 3000)],
        [[(1000, 1000), (1000, 2000), (2000, 2000), (2000, 1000)]],
    )
    mesh = assert_closed_outward_mesh(
        extrude_wall_profile(profile, (0, 0), (1, 0), 0, 185, 0, None)
    )
    assert math.isclose(mesh.volume, profile.area * 185, rel_tol=1e-6)


def test_planar_face_extrusion_is_closed_and_outward() -> None:
    boundary = (
        (0.0, 0.0, 3000.0),
        (4000.0, 0.0, 4000.0),
        (4000.0, 3000.0, 4000.0),
        (0.0, 3000.0, 3000.0),
    )
    assert_closed_outward_mesh(extrude_planar_face(boundary, 250, None, "roof-face"))


def test_normalize_direction_preserves_orientation() -> None:
    assert normalize2((3.0, 4.0), "test") == (0.6, 0.8)
