"""Bounded arc tessellation, analytic mounting and native structural export."""

from __future__ import annotations

import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class CurveFixture:
    """Provide a curved rectangular beam with independently known volume."""

    @staticmethod
    def configure(model: JsonObject) -> JsonObject:
        """Place a half-circle beam away from the reference building."""
        Authoring.object(model["types"])["type.curvedStock"] = {
            "kind": "memberType",
            "name": "Curved stock",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 80, "depth": 120},
        }
        source: JsonObject = {
            "kind": "curvedMember",
            "name": "Curved beam",
            "type": "type.curvedStock",
            "role": "beam",
            "placement": {"origin": {"point": [0, -5000, 3000]}},
            "radius": 2000,
            "sweepAngle": 180,
            "chordTolerance": 1,
        }
        Authoring.object(model["elements"])["member.curve"] = source
        return source


@pytest.mark.parametrize("sweep", [180, -180, 360, -360])
def test_arc_solid_has_bounded_error_and_expected_volume(
    reference_model: JsonObject, validator: ModelValidator, sweep: int
) -> None:
    """Signed arcs and complete rings retain closed geometry and analytic quantities."""
    source = CurveFixture.configure(reference_model)
    source["sweepAngle"] = sweep
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    member = resolved.element("member.curve")
    count = number(member.data["segmentCount"], "segments")
    angle = math.radians(abs(sweep))
    expected_volume = 2000 * 80 * 120 * count * math.sin(angle / count)
    assert SolidOperations.volume(member.meshes[0]) == pytest.approx(expected_volume)
    assert member.data["analyticVolumeMm3"] == pytest.approx(2000 * 80 * 120 * angle)
    assert member.data["memberLength"] == pytest.approx(2000 * angle)
    assert number(member.data["maxDeviationMm"], "error") <= 1
    mesh = member.meshes[0]
    edges = {
        tuple(sorted((face[i], face[(i + 1) % len(face)])))
        for face in mesh.faces
        for i in range(len(face))
    }
    assert len(mesh.vertices) - len(edges) + len(mesh.faces) == (
        0 if abs(sweep) == 360 else 2
    )
    assert resolved.to_dict() == ModelResolver(reference_model).resolve().to_dict()


def test_circular_profile_shares_the_curve_error_budget(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Section and path approximations together stay below the requested tolerance."""
    source = CurveFixture.configure(reference_model)
    source["roll"] = 37
    definition = Authoring.object(
        Authoring.object(reference_model["types"])["type.curvedStock"]
    )
    definition["section"] = {"kind": "circle", "diameter": 100}
    assert validator.validate(reference_model).is_valid
    member = ModelResolver(reference_model).resolve().element("member.curve")
    assert 0 < number(member.data["maxDeviationMm"], "error") <= 1
    analytic = math.pi * 50**2 * 2000 * math.pi
    assert member.data["analyticVolumeMm3"] == pytest.approx(analytic)
    assert SolidOperations.volume(member.meshes[0]) == pytest.approx(analytic, rel=0.02)


def test_combined_section_and_path_resolution_has_a_size_limit(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Individually acceptable subdivisions cannot multiply into an unbounded loft."""
    source = CurveFixture.configure(reference_model)
    source["chordTolerance"] = 0.001
    definition = Authoring.object(
        Authoring.object(reference_model["types"])["type.curvedStock"]
    )
    definition["section"] = {"kind": "circle", "diameter": 100}
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert "2000000 loft vertices" in str(report.to_dict())


def test_arc_axis_mount_follows_rotated_placement(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Analytic arc stations rotate with their host and reject unsupported skin mounts."""
    source = CurveFixture.configure(reference_model)
    placement = Authoring.object(source["placement"])
    placement["rotation"] = [90, 0, 0]
    host: JsonObject = {
        "kind": "member",
        "element": "member.curve",
        "station": math.pi * 1000,
    }
    Authoring.object(reference_model["elements"])["member.mounted"] = {
        "kind": "member",
        "name": "Curve-mounted member",
        "type": "type.curvedStock",
        "role": "other",
        "axis": [{"host": host}, {"host": {**host, "offset": [0, 100, 0]}}],
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    member = ModelResolver(reference_model).resolve().element("member.mounted")
    axis = Authoring.array(member.data["axis"])
    assert axis[0] == pytest.approx([0, -5000, 5000])
    assert axis[1] == pytest.approx([0, -5100, 5000])
    host["surface"] = "positiveX"
    assert not validator.validate(reference_model).is_valid


def test_curved_member_exports_native_ifc_with_curve_intent(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """Closed tessellated structural geometry remains typed and IFC4-valid."""
    CurveFixture.configure(reference_model)
    source = tmp_path / "curve.json"
    ModelLoader.write(reference_model, source)
    result = BuildService().build(source, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    member = next(
        value for value in ifc.by_type("IfcBeam") if value.Tag == "member.curve"
    )
    assert member.Representation is not None
    assert len(member.IsTypedBy) == 1
    assert member.IsTypedBy[0].RelatingType.is_a("IfcBeamType")
    assert member.IsTypedBy[0].RelatingType.PredefinedType == "BEAM"


@pytest.mark.parametrize(
    "field,value",
    [
        ("sweepAngle", 0),
        ("sweepAngle", 361),
        ("radius", 30),
        ("chordTolerance", 1e-10),
        ("type", "wallType.exterior.wood-185"),
    ],
)
def test_invalid_curve_is_rejected(
    reference_model: JsonObject,
    validator: ModelValidator,
    field: str,
    value: int | float | str,
) -> None:
    """Invalid intent, self-intersecting sections and excessive meshes fail validation."""
    source = CurveFixture.configure(reference_model)
    source[field] = value
    assert not validator.validate(reference_model).is_valid
