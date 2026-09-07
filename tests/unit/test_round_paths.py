"""True-radius path bends, closed ties, geometry limits and independent length checks."""

from __future__ import annotations

import math

import pytest
import trimesh

from home_design.errors import ResolutionError
from home_design.geometry import number
from home_design.resolved import Vec3
from home_design.round_paths import RoundPath
from home_design.solids import SolidOperations


@pytest.mark.parametrize("tolerance", [0.01, 1, 10])
def test_analytic_station_frames_are_independent_of_mesh_tolerance(
    tolerance: float,
) -> None:
    """A midpoint on a circular bend has its exact radius, tangent and transported section axes."""
    path = RoundPath([(0, 0, 0), (1000, 0, 0), (1000, 1000, 0)], 20, 100, tolerance)
    frame = path.station_frame(900 + 25 * math.pi)
    diagonal = math.sqrt(0.5)
    assert frame.origin == pytest.approx(
        (900 + 100 * diagonal, 100 - 100 * diagonal, 0)
    )
    assert frame.z == pytest.approx((diagonal, diagonal, 0))
    assert frame.x == pytest.approx((-diagonal, diagonal, 0))
    assert frame.y == pytest.approx((0, 0, 1))
    assert path.station_frame(0).origin == (0, 0, 0)
    assert path.station_frame(path.length).origin == pytest.approx((1000, 1000, 0))


def test_station_transport_continues_through_perpendicular_bend_planes() -> None:
    """The second bend preserves accumulated roll instead of resetting its frame to world up."""
    path = RoundPath(
        [(0, 0, 0), (1000, 0, 0), (1000, 1000, 0), (1000, 1000, 1000)], 20, 100, 0.1
    )
    frame = path.station_frame(900 + 50 * math.pi + 800 + 25 * math.pi)
    diagonal = math.sqrt(0.5)
    assert frame.origin == pytest.approx(
        (1000, 900 + 100 * diagonal, 100 - 100 * diagonal)
    )
    assert frame.x == pytest.approx((-1, 0, 0))
    assert frame.y == pytest.approx((0, -diagonal, diagonal))
    assert frame.z == pytest.approx((0, diagonal, diagonal))


@pytest.mark.parametrize("station", [-1, 1001, math.inf, math.nan])
def test_station_outside_analytic_path_is_rejected(station: float) -> None:
    """Invalid stations cannot silently clamp to a plausible support location."""
    with pytest.raises(ResolutionError, match="outside its analytic centerline length"):
        RoundPath([(0, 0, 0), (1000, 0, 0)], 20, 0, 0.1).station_frame(station)


def test_station_frame_rejects_closed_path_and_preserves_authored_up() -> None:
    """Open route stationing preserves section roll and does not imply wrapping closed paths."""
    path = RoundPath([(0, 0, 0), (0, 0, 1000)], 20, 0, 0.1)
    frame = path.station_frame(300, (1, 0, 0))
    assert frame.origin == (0, 0, 300)
    assert frame.x == (0, -1, 0) and frame.y == (1, 0, 0)
    with pytest.raises(ResolutionError, match="open rounded path"):
        RoundPath(
            [(0, 0, 0), (1000, 0, 0), (1000, 1000, 0)], 20, 100, 0.1, True
        ).station_frame(0)


@pytest.mark.parametrize("closed", [False, True])
def test_bend_length_and_closed_topology(closed: bool) -> None:
    """Rounded corners replace known tangent lengths and produce watertight bar geometry."""
    points: list[Vec3] = [(0, 0, 0), (1000, 0, 0), (1000, 1000, 0)]
    if closed:
        points.append((0, 1000, 0))
    path = RoundPath(points, 20, 100, 0.1, closed)
    mesh, data = path.resolve("steel")
    expected = 4000 - 800 + 200 * math.pi if closed else 2000 - 200 + 50 * math.pi
    assert data["centerlineLengthMm"] == pytest.approx(expected)
    assert 0 < number(data["maxDeviationMm"], "deviation") <= 0.1
    solid = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
    assert solid.is_watertight and solid.is_winding_consistent
    assert solid.euler_number == (0 if closed else 2)
    assert SolidOperations.volume(mesh) == pytest.approx(
        expected * math.pi * 100, rel=0.02
    )
    assert path.resolve("steel") == (mesh, data)


@pytest.mark.parametrize(
    "tolerance,radius,span,message",
    [
        (1e-18, 100, 1000, "numeric resolution"),
        (1e-7, 100, 1000, "10000 sides"),
        (0.00005, 100, 1000, "2000000 loft vertices"),
        (0.001, 1000000, 10000000, "10000 sections"),
    ],
)
def test_path_resolution_limits_fail_before_allocating_excessive_solids(
    tolerance: float, radius: float, span: float, message: str
) -> None:
    """Section, path and combined size limits independently bound the generated loft."""
    with pytest.raises(ResolutionError, match=message):
        RoundPath(
            [(0, 0, 0), (span, 0, 0), (span, span, 0)], 20, radius, tolerance
        ).resolve("steel")


def test_three_dimensional_open_bends_share_cap_frames() -> None:
    """Two perpendicular bend planes remain joined without duplicate material at their caps."""
    path = RoundPath(
        [(0, 0, 0), (1000, 0, 0), (1000, 1000, 0), (1000, 1000, 1000)], 20, 100, 0.1
    )
    mesh, data = path.resolve("steel")
    assert data["centerlineLengthMm"] == pytest.approx(3000 - 400 + 100 * math.pi)
    assert SolidOperations.volume(mesh) > 0


@pytest.mark.parametrize(
    "points,radius,closed,message",
    [
        ([(0, 0, 0), (0, 0, 0)], 100, False, "zero-length"),
        ([(0, 0, 0), (1000, 0, 0), (0, 0, 0)], 100, False, "reverses"),
        ([(0, 0, 0), (1000, 0, 0), (1000, 1000, 0)], 5, False, "section radius"),
        ([(0, 0, 0), (100, 0, 0), (100, 100, 0)], 200, False, "consume"),
        (
            [(0, 0, 0), (1000, 0, 0), (1000, 1000, 0), (0, 1000, 100)],
            100,
            True,
            "planar",
        ),
        (
            [(0, 0, 0), (1000, 1000, 0), (0, 1000, 0), (1000, 0, 0)],
            100,
            False,
            "intersects itself",
        ),
    ],
)
def test_invalid_rounded_paths_fail_before_export(
    points: list[Vec3], radius: float, closed: bool, message: str
) -> None:
    """Invalid paths do not become plausible-looking intersecting or collapsed bars."""
    with pytest.raises(ResolutionError, match=message):
        RoundPath(points, 20, radius, 0.1, closed).resolve("steel")
