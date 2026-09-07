"""Constrained triangulation preserves concave boundaries and holes in physical solids."""

from __future__ import annotations

import pytest
import trimesh
from shapely.geometry import Polygon

from home_design.geometry import (
    extrude_polygon,
    extrude_wall_profile,
    triangulate_polygon,
)
from home_design.solids import SolidOperations


@pytest.mark.parametrize(
    "profile",
    [
        Polygon([(0, 0), (100, 0), (100, 100), (90, 10), (10, 10), (0, 100)]),
        Polygon(
            [(0, 0), (100, 0), (100, 100), (60, 40), (0, 100)],
            [[(10, 10), (20, 10), (20, 20), (10, 20)]],
        ),
    ],
)
def test_concave_extrusions_preserve_closed_boundary_and_volume(
    profile: Polygon,
) -> None:
    """Triangle interiors stay inside every boundary and side/top edges remain paired."""
    triangles = triangulate_polygon(profile)
    assert all(profile.covers(triangle) for triangle in triangles)
    assert sum(triangle.area for triangle in triangles) == pytest.approx(profile.area)
    for mesh in (
        extrude_polygon(profile, 0, 40, "wood", "test"),
        extrude_wall_profile(profile, (1000, -3000), (0.6, 0.8), 0, 40, 1000, "wood"),
    ):
        topology = trimesh.Trimesh(
            vertices=mesh.vertices, faces=mesh.faces, process=False
        )
        assert topology.is_watertight and topology.is_winding_consistent
        assert SolidOperations.volume(mesh) == pytest.approx(profile.area * 40)
