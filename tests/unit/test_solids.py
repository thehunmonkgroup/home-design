"""Volume, topology and precision contracts for solid Boolean operations."""

from __future__ import annotations

import pytest
import trimesh

from home_design.construction import ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.resolved import MeshData
from home_design.geometry import extrude_wall_profile
from shapely.geometry import Polygon
from home_design.solids import SolidOperations


class SolidFixture:
    """Produce closed boxes with known analytic volumes."""

    @staticmethod
    def box(start: float = 0, end: float = 100, width: float = 100) -> MeshData:
        """Create a Z-aligned box retaining material provenance."""
        return ConstructionGeometry.member(
            (0, 0, start),
            (0, 0, end),
            {"kind": "rectangle", "width": width, "depth": width},
            "wood",
            "layer:0",
        )


def test_boolean_cut_preserves_real_hole_volume_material_and_determinism() -> None:
    """A through-cut exports a closed positive solid with the analytic net volume."""
    source = SolidFixture.box()
    cutter = SolidFixture.box(-10, 110, 20)
    result = SolidOperations.difference(source, [cutter])
    assert result is not None
    assert SolidOperations.volume(result) == pytest.approx(100**3 - 20**2 * 100)
    mesh = trimesh.Trimesh(vertices=result.vertices, faces=result.faces, process=False)
    assert mesh.is_watertight and mesh.is_winding_consistent
    assert result.role == "layer:0" and result.material_id == "wood"
    assert result == SolidOperations.difference(source, [cutter])
    shared = SolidOperations.intersection(source, cutter)
    assert shared is not None
    assert SolidOperations.volume(shared) == pytest.approx(20**2 * 100)
    combined = SolidOperations.union([result, shared], "wood", "reconstructed")
    assert combined is not None
    assert SolidOperations.volume(combined) == pytest.approx(100**3)


def test_empty_and_disconnected_results_remain_explicit() -> None:
    """Empty intersections differ from invalid inputs; disconnected solids survive."""
    source = SolidFixture.box()
    remote = SolidFixture.box(200, 300)
    assert SolidOperations.intersection(source, remote) is None
    assert SolidOperations.difference(source, [source]) is None
    result = SolidOperations.difference(source, [SolidFixture.box(40, 60, 200)])
    assert result is not None
    mesh = trimesh.Trimesh(vertices=result.vertices, faces=result.faces, process=False)
    assert mesh.is_watertight and mesh.euler_number == 4
    assert all(
        max(result.vertices[index][2] for index in face) <= 40
        or min(result.vertices[index][2] for index in face) >= 60
        for face in result.faces
    )
    assert mesh.volume == pytest.approx(800000)


def test_solid_kernel_preserves_small_dimensions_at_building_coordinates() -> None:
    """Double precision avoids losing thin material at large local coordinates."""
    source = ConstructionGeometry.translated(
        SolidFixture.box(0, 0.025), (20000, 30000, 10000)
    )
    assert SolidOperations.volume(source) == pytest.approx(250, abs=1e-5)
    cut = ConstructionGeometry.translated(
        SolidFixture.box(-10, 10, 20), (20000, 30000, 10000)
    )
    result = SolidOperations.difference(source, [cut])
    assert result is not None
    assert SolidOperations.volume(result) == pytest.approx(240, abs=1e-5)


def test_open_inputs_are_rejected_instead_of_silently_repaired() -> None:
    """A missing face cannot become a fabricated solid during a cut."""
    source = SolidFixture.box()
    broken = MeshData(source.vertices, source.faces[1:])
    with pytest.raises(ResolutionError, match="closed positive volume"):
        SolidOperations.solid(broken)


def test_point_touching_solids_keep_distinct_topological_vertices() -> None:
    """Canonical output ordering does not weld independent shells at one point."""
    first = SolidFixture.box()
    second = ConstructionGeometry.translated(first, (100, 100, 100))
    combined = SolidOperations.union([first, second], "wood", "touching")
    assert combined is not None
    assert SolidOperations.volume(combined) == pytest.approx(2000000)
    assert trimesh.Trimesh(
        vertices=combined.vertices, faces=combined.faces, process=False
    ).is_watertight


def test_sloped_face_contact_does_not_create_a_residual_solid() -> None:
    """Coincident sloped board faces have zero shared material at building coordinates."""
    first = extrude_wall_profile(
        Polygon([(0, 0), (40, 0), (40, 3023.094010767585), (0, 3000)]),
        (1000, -3000),
        (0, 1),
        0,
        140,
        0,
        "wood",
    )
    second = extrude_wall_profile(
        Polygon(
            [(0, 3000), (40, 3023.094010767585), (40, 3063.094010767585), (0, 3040)]
        ),
        (1000, -3000),
        (0, 1),
        0,
        140,
        0,
        "wood",
    )
    assert SolidOperations.intersection(first, second) is None
