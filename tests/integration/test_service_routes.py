"""Routed service geometry, empty passages, connected edits and native segment exports."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest
import trimesh

from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.service_ports import ServicePorts
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class RouteFixture:
    """Create a single rounded route with explicit open ends and a containing system."""

    @staticmethod
    def configure(
        model: JsonObject, family: str = "pipe", rectangular: bool = False
    ) -> JsonObject:
        """Isolate service geometry from the public reference envelope."""
        (
            model["elements"],
            model["relationships"],
            model["requirements"],
            model["solarStudies"],
        ) = ({}, {}, [], [])
        medium = {
            "pipe": "water",
            "duct": "air",
            "cable": "electrical",
            "conduit": "electrical",
        }[family]
        definition: JsonObject = {
            "kind": "serviceRouteType",
            "name": "Illustrative route stock",
            "family": family,
            "material": "material.timber",
            "medium": medium,
            "connectionType": "illustrativeMatingFace",
            "flow": "forward",
            "section": (
                {"kind": "rectangle", "width": 80, "height": 40}
                if rectangular
                else {"kind": "circle", "diameter": 40}
            ),
        }
        if family != "cable":
            definition["wallThickness"] = 2
        Authoring.object(model["types"])["type.route"] = definition
        route: JsonObject = {
            "kind": "serviceRoute",
            "name": "Illustrative rounded route",
            "type": "type.route",
            "storey": "level.ground",
            "path": [
                {"point": [0, 0, 0]},
                {"point": [1000, 0, 0]},
                {"point": [1000, 1000, 0]},
            ],
            "bendRadius": 150,
            "chordTolerance": 0.2,
            "clearance": 5,
            "portStates": {"start": "open", "end": "open"},
        }
        elements = Authoring.object(model["elements"])
        elements["route.run"] = route
        elements["system.run"] = {
            "kind": "serviceSystem",
            "name": "Illustrative system",
            "systemType": "supplyAir" if medium == "air" else medium,
            "members": [
                {"element": "route.run", "port": "start"},
                {"element": "route.run", "port": "end"},
            ],
        }
        return route

    @classmethod
    def cavity(cls, model: JsonObject, volume: str = "bore") -> None:
        """Place a bend inside one explicit wall layer and derive its owned passage cut."""
        original_wall = deepcopy(
            Authoring.object(Authoring.object(model["elements"])["wall.south"])
        )
        route = cls.configure(model)
        original_wall["base"] = {"kind": "level", "level": "level.ground", "offset": 0}
        original_wall["top"] = {"kind": "height", "height": 2400}
        elements = Authoring.object(model["elements"])
        elements["wall.south"] = original_wall
        route["path"] = [
            {"point": [8000, 9.5, 500]},
            {"point": [9000, 9.5, 500]},
            {"point": [9000, 9.5, 1500]},
        ]
        route["occupies"] = {"regions": [{"host": "wall.south", "layer": 2}]}
        Authoring.object(model["materials"])["material.infill"] = {
            "name": "Illustrative cavity insulation"
        }
        wall_type = Authoring.object(
            Authoring.object(model["types"])["wallType.exterior.wood-185"]
        )
        Authoring.object(Authoring.array(wall_type["layers"])[2]).update(
            {"representation": "explicit", "material": "material.infill"}
        )
        elements["cut.passage"] = {
            "kind": "penetration",
            "name": "Owned route passage",
            "host": "wall.south",
            "owner": "route.run",
            "purpose": "service",
            "layers": [2],
            "geometrySource": {"element": "route.run", "volume": volume},
        }


@pytest.mark.parametrize(
    "family,rectangular,native,predefined",
    [
        ("pipe", False, "IfcPipeSegment", "RIGIDSEGMENT"),
        ("duct", True, "IfcDuctSegment", "RIGIDSEGMENT"),
        ("cable", False, "IfcCableSegment", "CABLESEGMENT"),
        ("conduit", True, "IfcCableCarrierSegment", "CONDUITSEGMENT"),
    ],
)
def test_route_material_ports_quantities_and_native_ifc(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    family: str,
    rectangular: bool,
    native: str,
    predefined: str,
) -> None:
    """Native segment bodies contain only material while separate masks retain passage geometry."""
    RouteFixture.configure(reference_model, family, rectangular)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolver = ModelResolver(reference_model)
    resolved = resolver.resolve()
    assert resolved.to_dict() == resolver.resolve().to_dict()
    route = resolved.element("route.run")
    length = 1700 + 75 * math.pi
    assert route.data["centerlineLengthMm"] == pytest.approx(length)
    assert 0 < number(route.data["maxDeviationMm"], "deviation") <= 0.2
    nominal_area = (
        80 * 40 - 76 * 36
        if rectangular
        else math.pi * (400 - (324 if family != "cable" else 0))
    )
    volume = SolidOperations.volume(route.meshes[0])
    assert volume == pytest.approx(length * nominal_area, rel=0.01)
    solid = trimesh.Trimesh(
        vertices=route.meshes[0].vertices, faces=route.meshes[0].faces, process=False
    )
    assert solid.is_watertight and solid.is_winding_consistent
    assert solid.euler_number == (2 if family == "cable" else 0)
    masks = route.construction_volumes
    assert set(masks) == (
        {"envelope", "clearance"}
        if family == "cable"
        else {"envelope", "clearance", "bore"}
    )
    if "bore" in masks:
        assert SolidOperations.intersection(route.meshes[0], masks["bore"]) is None
        assert SolidOperations.volume(masks["envelope"]) == pytest.approx(
            volume + SolidOperations.volume(masks["bore"])
        )
    ports = Authoring.object(route.data["ports"])
    assert ServicePorts.frame(Authoring.object(ports["start"])).z == pytest.approx(
        (-1, 0, 0)
    )
    assert ServicePorts.frame(Authoring.object(ports["end"])).z == pytest.approx(
        (0, 1, 0)
    )
    schedules = ModelReports(resolved).schedules()
    assert len(Authoring.array(schedules["serviceRoutes"])) == 1
    materials = Authoring.array(schedules["materials"])
    assert sum(
        number(Authoring.object(row)["volumeM3"], "volume") for row in materials
    ) == pytest.approx(volume / 1e9)
    output = tmp_path / "route.ifc"
    IfcExporter().export(resolved, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("route.run"))
    assert product.is_a(native)
    assert ifcopenshell.util.element.get_predefined_type(product) == predefined
    assert product.IsTypedBy[0].RelatingType.is_a(native + "Type")
    quantities = ifcopenshell.util.element.get_psets(product, qtos_only=True)[
        f"Qto_{native.removeprefix('Ifc')}BaseQuantities"
    ]
    assert quantities["Length"] == pytest.approx(length)
    if family in {"pipe", "duct"}:
        assert quantities["GrossCrossSectionArea"] == pytest.approx(
            (80 * 40 if rectangular else math.pi * 20**2) / 1e6
        )
        assert quantities["NetCrossSectionArea"] == pytest.approx(nominal_area / 1e6)
    else:
        assert quantities["CrossSectionArea"] == pytest.approx(nominal_area / 1e6)
    assert "GrossWeight" not in quantities
    assert len(ifc.by_type("IfcDistributionPort")) == 2
    if family == "conduit":
        assert all(
            port.PredefinedType == "CABLECARRIER"
            for port in ifc.by_type("IfcDistributionPort")
        )
    bodies = [
        representation
        for representation in product.Representation.Representations
        if representation.RepresentationIdentifier == "Body"
    ]
    assert len(bodies) == 1 and len(bodies[0].Items) == 1
    assert ifc.by_type("IfcQuantityLength")[0].LengthValue == pytest.approx(length)
    assert ifc.by_type("IfcQuantityVolume")[0].VolumeValue == pytest.approx(
        volume / 1e9
    )


@pytest.mark.parametrize("volume", ["bore", "envelope", "clearance"])
def test_curved_cavity_passage_cuts_preserve_net_infill_balance(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    volume: str,
) -> None:
    """A bend inside insulation displaces both tube stock and its empty passage exactly once."""
    RouteFixture.cavity(reference_model, volume)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    route, host, cut = (
        resolved.element(identity)
        for identity in ("route.run", "wall.south", "cut.passage")
    )
    bore = route.construction_volumes["bore"]
    assert all(SolidOperations.intersection(mesh, bore) is None for mesh in host.meshes)
    cavity = Authoring.object(Authoring.array(host.data["cavities"])[0])
    expected_void = SolidOperations.volume(bore)
    if volume == "clearance":
        expected_void = SolidOperations.volume(
            route.construction_volumes["clearance"]
        ) - SolidOperations.volume(route.meshes[0])
    assert cut.data["cutVolumeMm3"] == pytest.approx(expected_void)
    exported_volume = trimesh.Trimesh(
        vertices=cut.meshes[0].vertices, faces=cut.meshes[0].faces, process=False
    ).volume
    assert exported_volume == pytest.approx(expected_void)
    assert cavity["voidVolumeMm3"] == pytest.approx(expected_void)
    assert number(cavity["grossVolumeMm3"], "gross") == pytest.approx(
        sum(
            number(cavity[key], key)
            for key in ("infillVolumeMm3", "occupiedVolumeMm3", "voidVolumeMm3")
        )
    )
    output = tmp_path / "cavity.ifc"
    IfcExporter().export(resolved, output)
    ifc = ifcopenshell.open(output)
    assert (
        ifc.by_type("IfcRelVoidsElement")[0].RelatingBuildingElement.Tag == "wall.south"
    )
    assert ifc.by_guid(IfcExporter.stable_guid("cut.passage")).is_a("IfcOpeningElement")


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("missingCut", "host material inside its bore"),
        ("wrongOwner", "name its geometry source as owner"),
        ("missingVolume", "unavailable construction volume"),
        ("missingSource", "missing element"),
        ("mixedGeometry", ""),
    ],
)
def test_sourced_cut_contract_rejects_incomplete_or_ambiguous_passages(
    reference_model: JsonObject,
    validator: ModelValidator,
    mutation: str,
    message: str,
) -> None:
    """Masks require real source geometry, matching ownership and one unambiguous cutter definition."""
    RouteFixture.cavity(reference_model)
    elements = Authoring.object(reference_model["elements"])
    cut = Authoring.object(elements["cut.passage"])
    if mutation == "missingCut":
        del elements["cut.passage"]
    elif mutation == "wrongOwner":
        cut["owner"] = "wall.south"
    elif mutation in {"missingVolume", "missingSource"}:
        cut["owner"] = "wall.south" if mutation == "missingVolume" else "route.absent"
        Authoring.object(cut["geometrySource"])["element"] = cut["owner"]
        if mutation == "missingVolume":
            cut["host"] = "route.run"
    else:
        cut["depth"] = 10
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert any(
        message.lower() in item.message.lower() for item in report.errors
    ), report.to_dict()


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("bendRadius", 0, "section radius"),
        ("bendRadius", 2000, "consume"),
        ("up", [1, 0, 0], "zero-length"),
        ("chordTolerance", 1e-18, "numeric resolution"),
        (
            "path",
            [
                {"point": [0, 0, 0]},
                {"point": [1000, 1000, 0]},
                {"point": [0, 1000, 0]},
                {"point": [1000, 0, 0]},
            ],
            "intersects itself",
        ),
        (
            "path",
            [{"point": [0, 0, 0]}, {"point": [1000, 0, 0]}, {"point": [0, 0, 0]}],
            "reverses",
        ),
    ],
)
def test_invalid_route_geometry_is_rejected(
    reference_model: JsonObject,
    validator: ModelValidator,
    field: str,
    value: JsonValue,
    message: str,
) -> None:
    """Invalid orientation, bends, approximation budgets and crossing routes fail before export."""
    route = RouteFixture.configure(reference_model)
    route[field] = value
    report = validator.validate(reference_model)
    assert any(message in item.message for item in report.errors), report.to_dict()


def test_route_ports_follow_anchor_edits_and_export_deterministically(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
) -> None:
    """A downstream rectangular route inherits the upstream endpoint frame through a 3D bend."""
    first = RouteFixture.configure(reference_model, "duct", True)
    anchors = Authoring.object(reference_model["anchors"])
    anchors["anchor.start"] = {
        "kind": "point3",
        "name": "Route start",
        "position": [0, 0, 0],
    }
    anchors["anchor.corner"] = {
        "kind": "point3",
        "name": "Route corner",
        "position": [1000, 0, 0],
    }
    anchors["anchor.end"] = {
        "kind": "point3",
        "name": "Shared route endpoint",
        "position": [1000, 1000, 0],
    }
    first["path"] = [
        {"anchor": "anchor.start"},
        {"anchor": "anchor.corner"},
        {"anchor": "anchor.end"},
    ]
    first["portStates"] = {"start": "open"}
    elements = Authoring.object(reference_model["elements"])
    second = deepcopy(first)
    second["path"] = [
        {"port": {"element": "route.run", "port": "end"}},
        {"point": [1000, 1500, 0]},
        {"point": [1000, 1500, 1000]},
    ]
    second["portStates"] = {"end": "open"}
    elements["route.continuation"] = second
    Authoring.array(Authoring.object(elements["system.run"])["members"]).extend(
        [
            {"element": "route.continuation", "port": "start"},
            {"element": "route.continuation", "port": "end"},
        ]
    )
    Authoring.object(reference_model["relationships"])["connection.routes"] = {
        "kind": "connectsPorts",
        "a": {"element": "route.run", "port": "end"},
        "b": {"element": "route.continuation", "port": "start"},
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.route",
            "description": "Lengthen the route",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "moveAnchor",
                    "anchorId": "anchor.start",
                    "position": [-200, 0, 0],
                },
                {
                    "op": "moveAnchor",
                    "anchorId": "anchor.end",
                    "position": [1000, 1100, 0],
                },
            ],
        },
    )
    before, after = (
        ModelResolver(reference_model).resolve(),
        ModelResolver(changed).resolve(),
    )
    assert number(
        after.element("route.run").data["centerlineLengthMm"], "new length"
    ) - number(
        before.element("route.run").data["centerlineLengthMm"], "old length"
    ) == pytest.approx(
        300
    )
    assert number(
        after.element("route.continuation").data["centerlineLengthMm"], "new length"
    ) - number(
        before.element("route.continuation").data["centerlineLengthMm"], "old length"
    ) == pytest.approx(
        -100
    )
    start = ServicePorts.frame(
        Authoring.object(
            Authoring.object(after.element("route.continuation").data["ports"])["start"]
        )
    )
    assert start.origin == pytest.approx((1000, 1100, 0))
    assert after.element("system.run").data["connections"] == ["connection.routes"]
    endpoint = ServicePorts.frame(
        Authoring.object(
            Authoring.object(after.element("route.continuation").data["ports"])["end"]
        )
    )
    assert endpoint.z == pytest.approx((0, 0, 1))
    assert endpoint.y == pytest.approx((0, -1, 0))
    source = tmp_path / "routes.json"
    source.write_text(json.dumps(changed), encoding="utf-8")
    a, b = BuildService().build(source, tmp_path / "first"), BuildService().build(
        source, tmp_path / "second"
    )
    assert a.glb_model.read_bytes() == b.glb_model.read_bytes()
    native = ifcopenshell.open(a.ifc_model)
    assert len(native.by_type("IfcRelConnectsPorts")) == 1


@pytest.mark.parametrize("rectangular", [False, True])
def test_straight_hollow_routes_have_exact_section_volumes_and_no_default_clearance(
    reference_model: JsonObject, validator: ModelValidator, rectangular: bool
) -> None:
    """Straight routes need no bend radius and retain exact polygonal section accounting."""
    route = RouteFixture.configure(
        reference_model, "duct" if rectangular else "pipe", rectangular
    )
    route["path"] = [{"point": [0, 0, 0]}, {"point": [0, 0, 1000]}]
    del route["bendRadius"]
    del route["clearance"]
    definition = Authoring.object(
        Authoring.object(reference_model["types"])["type.route"]
    )
    del definition["flow"]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve().element("route.run")
    assert result.data["netVolumeMm3"] == pytest.approx(
        1000 * number(result.data["sectionAreaMm2"], "section area")
    )
    assert result.data["sectionCount"] == 2
    assert (
        result.construction_volumes["clearance"].vertices
        == result.construction_volumes["envelope"].vertices
    )
    assert all(
        Authoring.object(port)["flow"] == "bidirectional"
        for port in Authoring.object(result.data["ports"]).values()
    )


@pytest.mark.parametrize(
    "rectangular,field,value,message",
    [
        (False, "wallThickness", 20, "leaves no bore"),
        (True, "wallThickness", 21, "leaves no bore"),
        (False, "medium", "electrical", "incompatible medium"),
    ],
)
def test_invalid_route_stock_is_rejected(
    reference_model: JsonObject,
    validator: ModelValidator,
    rectangular: bool,
    field: str,
    value: JsonValue,
    message: str,
) -> None:
    """Stock dimensions and service family impose real physical and semantic constraints."""
    RouteFixture.configure(reference_model, "pipe", rectangular)
    Authoring.object(Authoring.object(reference_model["types"])["type.route"])[
        field
    ] = value
    report = validator.validate(reference_model)
    assert any(message in item.message for item in report.errors), report.to_dict()


def test_route_mates_reject_twisted_rectangular_sections(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Coincident endpoints are insufficient when a rectangular route presents the wrong orientation."""
    first = RouteFixture.configure(reference_model, "duct", True)
    first["portStates"] = {"start": "open"}
    second = deepcopy(first)
    second["path"] = [
        {"port": {"element": "route.run", "port": "end"}},
        {"point": [1000, 1500, 0]},
    ]
    second["portStates"] = {"end": "open"}
    second["up"] = [1, 0, 0]
    elements = Authoring.object(reference_model["elements"])
    elements["route.twisted"] = second
    Authoring.array(Authoring.object(elements["system.run"])["members"]).extend(
        [
            {"element": "route.twisted", "port": "start"},
            {"element": "route.twisted", "port": "end"},
        ]
    )
    Authoring.object(reference_model["relationships"])["connection.twisted"] = {
        "kind": "connectsPorts",
        "a": {"element": "route.run", "port": "end"},
        "b": {"element": "route.twisted", "port": "start"},
    }
    report = validator.validate(reference_model)
    assert any(
        "section orientation" in item.message for item in report.errors
    ), report.to_dict()
