"""Physical cut ownership, material quantities and IFC void interoperability."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest
import trimesh
from shapely.geometry import Polygon

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.geometry import number, polygon_normal, vector3
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class CutFixture:
    """Author generic hosted cuts against public reference components."""

    @staticmethod
    def cut(host: str, placement: JsonObject, depth: float) -> JsonObject:
        """Create a square cut extruded inward along the host normal."""
        return {
            "kind": "penetration",
            "name": "Service cut",
            "host": host,
            "purpose": "service",
            "placement": {"origin": {"host": placement}, "rotation": [180, 0, 0]},
            "section": {"kind": "rectangle", "width": 100, "depth": 100},
            "depth": depth,
        }

    @staticmethod
    def floor() -> JsonObject:
        """Cut through the complete floor thickness."""
        return CutFixture.cut(
            "slab.ground",
            {
                "kind": "surface",
                "element": "slab.ground",
                "surface": "top",
                "point": [500, 500],
            },
            200,
        )


@pytest.mark.parametrize(
    ("host", "placement", "depth"),
    [
        (
            "slab.ground",
            {
                "kind": "surface",
                "element": "slab.ground",
                "surface": "top",
                "point": [500, 500],
            },
            200,
        ),
        (
            "wall.south",
            {
                "kind": "wall",
                "element": "wall.south",
                "surface": "exterior",
                "station": 500,
                "height": 1000,
            },
            185,
        ),
        (
            "roof.main",
            {
                "kind": "surface",
                "element": "roof.main",
                "surface": "top",
                "point": [3000, 1000],
            },
            250,
        ),
    ],
)
def test_cuts_remove_real_volume_from_horizontal_vertical_and_sloped_hosts(
    reference_model: JsonObject,
    validator: ModelValidator,
    host: str,
    placement: JsonObject,
    depth: float,
) -> None:
    """Every affected layer remains closed and keeps its identity/material."""
    original_model = ModelResolver(reference_model).resolve()
    before = original_model.element(host)
    Authoring.object(reference_model["elements"])["cut.service"] = CutFixture.cut(
        host, placement, depth
    )
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    after = resolved.element(host)
    old_volume = sum(SolidOperations.volume(mesh) for mesh in before.meshes)
    new_volume = sum(SolidOperations.volume(mesh) for mesh in after.meshes)
    assert old_volume - new_volume == pytest.approx(10000 * depth, abs=0.01)
    assert resolved.element("cut.service").data["cutVolumeMm3"] == pytest.approx(
        10000 * depth, abs=0.01
    )
    assert [(mesh.role, mesh.material_id) for mesh in after.meshes] == [
        (mesh.role, mesh.material_id) for mesh in before.meshes
    ]
    for mesh in after.meshes:
        shape = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
        assert shape.is_watertight and shape.is_winding_consistent
    envelope = ModelReports(resolved).envelope()
    assert all(
        Authoring.object(item)["elementId"] != "cut.service"
        for item in Authoring.array(envelope["shadingGeometry"])
    )
    if host != "roof.main":
        original_surface = next(
            Authoring.object(item)
            for item in Authoring.array(
                ModelReports(original_model).envelope()["surfaces"]
            )
            if Authoring.object(item)["elementId"] == host
        )
        surface = next(
            Authoring.object(item)
            for item in Authoring.array(envelope["surfaces"])
            if Authoring.object(item)["elementId"] == host
        )
        assert surface["areaM2"] == pytest.approx(
            number(original_surface["areaM2"], "original area") - 0.01
        )
    else:
        gross_area = 0.0
        for value in Authoring.array(before.data["planes"]):
            boundary = [
                vector3(point, "roof vertex")
                for point in Authoring.array(Authoring.object(value)["boundary"])
            ]
            gross_area += Polygon(
                [(point[0], point[1]) for point in boundary]
            ).area / abs(polygon_normal(boundary)[2])
        assert after.data["netExteriorAreaMm2"] == pytest.approx(
            gross_area - 10000, abs=0.01
        )


@pytest.mark.parametrize("host_kind", ["member", "framing", "footing"])
def test_member_notches_and_foundation_penetrations(
    reference_model: JsonObject,
    validator: ModelValidator,
    host_kind: str,
) -> None:
    """Framing and footings use the same cuts without specialized visual stand-ins."""
    types = Authoring.object(reference_model["types"])
    elements = Authoring.object(reference_model["elements"])
    types["type.test.member"] = {
        "kind": "memberType",
        "name": "Timber",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 100, "depth": 200},
    }
    types["type.test.footing"] = {
        "kind": "footingType",
        "name": "Footing",
        "material": "material.concrete",
        "depth": 300,
    }
    cut: JsonObject
    if host_kind == "footing":
        elements["test.host"] = {
            "kind": "footing",
            "name": "Pier",
            "type": "type.test.footing",
            "shape": "pier",
            "center": [500, 500],
            "diameter": 500,
            "datum": {"kind": "level", "level": "level.ground", "offset": 0},
        }
        cut = CutFixture.cut(
            "test.host",
            {
                "kind": "surface",
                "element": "test.host",
                "surface": "top",
                "point": [500, 500],
            },
            300,
        )
        expected = 3000000
    else:
        member: JsonObject = {
            "kind": host_kind,
            "name": "Floor member",
            "type": "type.test.member",
            "role": "joist",
            "axis": [{"point": [0, 0, 0]}, {"point": [1000, 0, 0]}],
        }
        if host_kind == "framing":
            member.update({"count": 2, "spacing": 400, "distribution": [0, 1, 0]})
        elements["test.host"] = member
        cut = {
            "kind": "penetration",
            "name": "Bearing seat",
            "purpose": "bearingSeat",
            "host": "test.host",
            "placement": {"origin": {"point": [50, 0, -120]}},
            "section": {"kind": "rectangle", "width": 100, "depth": 120},
            "depth": 70,
        }
        expected = 500000
    before = ModelResolver(reference_model).resolve().element("test.host")
    elements["cut.test"] = cut
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    after = resolved.element("test.host")
    assert sum(SolidOperations.volume(mesh) for mesh in before.meshes) - sum(
        SolidOperations.volume(mesh) for mesh in after.meshes
    ) == pytest.approx(expected)
    assert resolved.element("cut.test").data["cutVolumeMm3"] == pytest.approx(expected)
    if host_kind == "framing":
        assert before.meshes[1] == after.meshes[1]


def test_layer_selective_cuts_do_not_cut_or_count_other_layers(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Two cuts can share a path when they own disjoint construction layers."""
    before = ModelResolver(reference_model).resolve().element("wall.south")
    placement: JsonObject = {
        "kind": "wall",
        "element": "wall.south",
        "surface": "exterior",
        "station": 500,
        "height": 1000,
    }
    first = CutFixture.cut("wall.south", placement, 185)
    first["layers"] = [0]
    second = deepcopy(first)
    second["layers"] = [3]
    elements = Authoring.object(reference_model["elements"])
    elements["cut.siding"] = first
    elements["cut.gypsum"] = second
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    after = resolved.element("wall.south")
    assert before.meshes[1:3] == after.meshes[1:3]
    assert resolved.element("cut.siding").data["cutVolumeMm3"] == pytest.approx(200000)
    assert resolved.element("cut.gypsum").data["cutVolumeMm3"] == pytest.approx(130000)
    schedules = ModelReports(resolved).schedules()
    rows = Authoring.array(schedules["penetrations"])
    assert len(rows) == 2
    assert all(Authoring.object(row)["volumeM3"] == 0 for row in rows)


@pytest.mark.parametrize(
    "failure", ["outside", "layer", "overlap", "missingHost", "entireHost"]
)
def test_invalid_cut_ownership_rejects_build_inputs(
    reference_model: JsonObject, validator: ModelValidator, failure: str
) -> None:
    """Cuts cannot silently miss a host, overlap ownership or select absent layers."""
    cut = CutFixture.floor()
    elements = Authoring.object(reference_model["elements"])
    elements["cut.first"] = cut
    if failure == "outside":
        cut["placement"] = {"origin": {"point": [50000, 50000, 0]}}
    elif failure == "layer":
        cut["layers"] = [99]
    elif failure == "overlap":
        elements["cut.second"] = deepcopy(cut)
    elif failure == "entireHost":
        cut["placement"] = {"origin": {"point": [6000, 4000, -1000]}}
        cut["section"] = {"kind": "rectangle", "width": 50000, "depth": 50000}
        cut["depth"] = 2000
    else:
        cut["host"] = "host.absent"
    report = validator.validate(reference_model)
    assert not report.is_valid


def test_ifc_void_body_matches_only_the_removed_volume_and_exports_deterministically(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """IFC and GLB share cut hosts; nonphysical cut volumes do not render as solids."""
    Authoring.object(reference_model["elements"])["cut.service"] = CutFixture.floor()
    resolver = ModelResolver(reference_model)
    assert resolver.resolve().to_dict() == resolver.resolve().to_dict()
    source = tmp_path / "penetration.json"
    ModelLoader.write(reference_model, source)
    first = BuildService().build(source, tmp_path / "first")
    second = BuildService().build(source, tmp_path / "second")
    assert first.glb_model.read_bytes() == second.glb_model.read_bytes()
    assert first.resolved_model.read_bytes() == second.resolved_model.read_bytes()
    manifest = json.loads(first.render_manifest.read_text())
    assert manifest["elements"]["cut.service"]["nodes"] == []
    assert manifest["elements"]["slab.ground"]["nodes"]
    ifc = ifcopenshell.open(first.ifc_model)
    cut = next(
        item for item in ifc.by_type("IfcOpeningElement") if item.Tag == "cut.service"
    )
    assert cut.VoidsElements[0].RelatingBuildingElement.Tag == "slab.ground"
    assert cut.PredefinedType == "OPENING"
    assert not cut.ContainedInStructure
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
