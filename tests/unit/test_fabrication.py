"""Bounded revolved fabrication geometry for tapered collars, boots and seals."""

from __future__ import annotations

import math

import pytest

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.fabrication import FabricationGeometry
from home_design.json_types import JsonObject
from home_design.solids import SolidOperations


class RevolutionFixture:
    """Provide a hollow conical collar with an independently calculable volume."""

    @staticmethod
    def collar() -> JsonObject:
        """Define outer radii 60/30 and inner radii 40/20 over 100 mm height."""
        return {
            "kind": "revolve",
            "profile": {"outer": [[40, 0], [60, 0], [30, 100], [20, 100]]},
            "chordTolerance": 0.05,
        }


def test_revolved_collar_preserves_taper_bore_and_approximation_bound() -> None:
    """Circular approximation stays inside the analytic annular frustum and retains its bore."""
    source = RevolutionFixture.collar()
    mesh = FabricationGeometry.revolution(source, "material.test", "body")
    solid = SolidOperations.solid(mesh)
    analytic_volume = (
        math.pi * 100 / 3 * (60**2 + 60 * 30 + 30**2 - 40**2 - 40 * 20 - 20**2)
    )
    assert solid.volume() == pytest.approx(analytic_volume, rel=0.003)
    assert solid.volume() < analytic_volume
    angles = sorted(
        {
            math.atan2(y, x) % (2 * math.pi)
            for x, y, z in mesh.vertices
            if abs(z) < 1e-6 and math.hypot(x, y) > 50
        }
    )
    gaps = [b - a for a, b in zip(angles, angles[1:] + [angles[0] + 2 * math.pi])]
    assert max(60 * (1 - math.cos(gap / 2)) for gap in gaps) <= 0.05 + 1e-8
    bore = FabricationGeometry.extrusion(
        {"section": {"kind": "circle", "diameter": 30}, "depth": 100}, None, "probe"
    )
    assert SolidOperations.intersection(mesh, bore) is None
    assert mesh.material_id == "material.test"


def test_revolved_profile_holes_and_local_pose_preserve_material() -> None:
    """An internal profile hole creates a ring cavity, independent of loop winding and pose."""
    profile: JsonObject = {
        "outer": [[20, 0], [60, 0], [60, 100], [20, 100]],
        "holes": [[[30, 20], [50, 20], [50, 80], [30, 80]]],
    }
    source: JsonObject = {"kind": "revolve", "profile": profile, "chordTolerance": 0.1}
    first = FabricationGeometry.revolution(source, None, "body")
    volume = math.pi * ((60**2 - 20**2) * 100 - (50**2 - 30**2) * 60)
    assert SolidOperations.volume(first) == pytest.approx(volume, rel=0.003)
    profile["outer"] = list(reversed(Authoring.array(profile["outer"])))
    source["placement"] = {"origin": [100, 200, 300], "rotation": [90, 0, 0]}
    moved = FabricationGeometry.revolution(source, None, "body")
    assert SolidOperations.volume(moved) == pytest.approx(SolidOperations.volume(first))
    assert min(y for _, y, _ in moved.vertices) == pytest.approx(100)
    assert max(y for _, y, _ in moved.vertices) == pytest.approx(200)


@pytest.mark.parametrize(
    "failure",
    [
        "negative_radius",
        "self_crossing",
        "numeric_tolerance",
        "segment_limit",
        "vertex_limit",
    ],
)
def test_invalid_revolution_is_rejected_before_expensive_geometry(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine rejects clipped radial intent, invalid profiles and unsafe allocation sizes."""
    source = RevolutionFixture.collar()
    if failure == "negative_radius":
        source["profile"] = {"outer": [[-10, 0], [60, 0], [30, 100], [20, 100]]}
    elif failure == "self_crossing":
        source["profile"] = {"outer": [[20, 0], [60, 100], [60, 0], [20, 100]]}
    elif failure == "numeric_tolerance":
        source["chordTolerance"] = 1e-20
    elif failure == "segment_limit":
        source["chordTolerance"] = 1e-6
    else:
        monkeypatch.setattr(FabricationGeometry, "MAX_REVOLUTION_VERTICES", 100)
    with pytest.raises(ResolutionError):
        FabricationGeometry.revolution(source, None, "body")
