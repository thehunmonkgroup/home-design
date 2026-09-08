"""Roof layer joints share the framing bisector without altering legacy face stacks."""

from __future__ import annotations

import pytest

from home_design.json_types import JsonObject
from home_design.layers import LayerAssembly
from home_design.resolved import Vec3
from home_design.roof_joints import RoofJoints
from home_design.solids import SolidOperations

SOUTH: tuple[Vec3, ...] = ((0, -1000, 0), (1000, -1000, 0), (1000, 0, 1000), (0, 0, 1000))
NORTH: tuple[Vec3, ...] = ((0, 0, 1000), (1000, 0, 1000), (1000, 1000, 0), (0, 1000, 0))


@pytest.mark.parametrize("shift", [(0, 0, 0), (7350, -12775, 200)])
def test_roof_layers_meet_without_cross_face_overlap(shift: Vec3) -> None:
    """Both finishes and cavity layers stop at one ridge plane after translation."""
    south = tuple((p[0] + shift[0], p[1] + shift[1], p[2] + shift[2]) for p in SOUTH)
    north = tuple((p[0] + shift[0], p[1] + shift[1], p[2] + shift[2]) for p in NORTH)
    definition: JsonObject = {
        "layers": [
            {"id": "finish", "thickness": 20, "material": "finish"},
            {"id": "cavity", "thickness": 200, "representation": "explicit"},
            {"id": "ceiling", "thickness": 13, "material": "gypsum"},
        ]
    }
    independent = LayerAssembly.roof(south, definition, "south", (north,))
    definition["layerJoin"] = "miter"
    first = LayerAssembly.roof(south, definition, "south", (north,))
    second = LayerAssembly.roof(north, definition, "north", (south,))
    assert sum(SolidOperations.volume(m) for m in first) < sum(
        SolidOperations.volume(m) for m in independent
    )
    for a in first:
        assert max(p[1] for p in a.vertices) == pytest.approx(shift[1])
        for b in second:
            assert min(p[1] for p in b.vertices) == pytest.approx(shift[1])
            assert abs((SolidOperations.solid(a) ^ SolidOperations.solid(b)).volume()) < 1e-5
    assert [m.role for m in first] == [m.role for m in independent]
    assert [m.material_id for m in first] == [m.material_id for m in independent]


def test_projected_edge_at_another_elevation_is_not_a_roof_joint() -> None:
    """Separate roofs never trim each other merely because their plans touch."""
    raised = tuple((p[0], p[1], p[2] + 100) for p in NORTH)
    assert RoofJoints.planes(SOUTH, (raised,)) == ()
    assert len(RoofJoints.planes(SOUTH, (NORTH,))) == 1
