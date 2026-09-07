"""Planar boundary regularization preserves holes, thin stock and shared edge topology."""

from __future__ import annotations

import pytest
import trimesh

from home_design.construction import ConstructionGeometry
from home_design.solid_surfaces import SolidSurfaces
from home_design.solids import SolidOperations


@pytest.mark.parametrize("height,offset", [(100.0, 0.0), (0.025, 20000.0)])
def test_planar_regions_preserve_through_holes_and_thin_material(
    height: float, offset: float
) -> None:
    """Hole boundaries remain closed and millimetre-scale placement does not consume thin stock."""
    stock = ConstructionGeometry.member(
        (offset, offset, offset),
        (offset, offset, offset + height),
        {"kind": "rectangle", "width": 100, "depth": 100},
        "wood",
        "layer:0",
    )
    cutter = ConstructionGeometry.member(
        (offset, offset, offset - 1),
        (offset, offset, offset + height + 1),
        {"kind": "rectangle", "width": 20, "depth": 20},
        None,
        "void",
    )
    cut = SolidOperations.difference(stock, [cutter])
    assert cut is not None
    repaired = SolidSurfaces.regularize(cut)
    assert repaired.material_id == "wood" and repaired.role == "layer:0"
    assert SolidOperations.volume(repaired) == pytest.approx(
        (100**2 - 20**2) * height, rel=1e-9, abs=1e-6
    )
    surface = trimesh.Trimesh(
        vertices=repaired.vertices, faces=repaired.faces, process=False
    )
    assert surface.is_watertight and surface.is_winding_consistent
    assert surface.euler_number == 0
    assert repaired == SolidSurfaces.regularize(cut)
