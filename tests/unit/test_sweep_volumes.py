"""Drainage construction masks preserve hollow paths through shared miter joints."""

from __future__ import annotations

import pytest

from home_design.construction import ConstructionGeometry
from home_design.json_types import JsonObject
from home_design.resolved import Vec3
from home_design.solids import SolidOperations
from home_design.sweep_volumes import SweepVolumes


@pytest.mark.parametrize("points", [
    [(0, 0, 0), (0, 0, -1000)],
    [(0, 0, 0), (1000, 0, 0), (1000, 0, -1000)],
])
def test_hollow_sweep_masks_reconcile_stock_and_void(points: list[Vec3]) -> None:
    """A transported enclosed bore accounts for all nonmaterial inside the envelope."""
    section: JsonObject = {"kind": "profile", "profile": {
        "outer": [[-60, -60], [60, -60], [60, 60], [-60, 60]],
        "holes": [[[-50, -50], [-50, 50], [50, 50], [50, -50]]],
    }}
    masks = SweepVolumes.resolve(points, section)
    stock = ConstructionGeometry.sweep(points, section, "metal")
    assert set(masks) == {"envelope", "bore"}
    assert all(m.material_id is None for m in masks.values())
    assert SolidOperations.volume(masks["envelope"]) == pytest.approx(
        SolidOperations.volume(masks["bore"]) + sum(SolidOperations.volume(m) for m in stock)
    )


def test_open_channel_has_an_envelope_without_an_enclosed_bore() -> None:
    """An open gutter's conservative envelope spans its channel without inventing a closed bore."""
    section: JsonObject = {"kind": "profile", "profile": {"outer": [
        [-60, 40], [-60, -40], [60, -40], [60, 40],
        [57, 40], [57, -37], [-57, -37], [-57, 40],
    ]}}
    points: list[Vec3] = [(0, 0, 0), (4500, 0, -30)]
    masks = SweepVolumes.resolve(points, section)
    assert set(masks) == {"envelope"}
    assert SolidOperations.volume(masks["envelope"]) > sum(
        SolidOperations.volume(m) for m in ConstructionGeometry.sweep(points, section, "metal")
    )
