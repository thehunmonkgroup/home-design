"""Generated fitting interfaces, branched passages, physical caps and native IFC families."""

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

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.service_ports import ServicePorts
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class FittingFixture:
    """Use minimal physical fitting recipes with illustrative stock and dimensions."""

    @staticmethod
    def geometry(role: str) -> JsonObject:
        """Author a tangent elbow, tee, eccentric reducer or closed cap."""
        section: JsonObject = {"kind": "circle", "diameter": 40}
        recipes: dict[str, JsonObject] = {
            "elbow": {
                "kind": "elbow",
                "section": section,
                "path": [[0, 0, 0], [0, 0, 200], [200, 0, 200]],
                "bendRadius": 100,
            },
            "branch": {
                "kind": "branch",
                "trunk": {"section": section, "path": [[0, 0, 0], [0, 0, 400]]},
                "branches": {
                    "side": {"section": section, "path": [[0, 0, 200], [200, 0, 200]]}
                },
            },
            "transition": {
                "kind": "transition",
                "startSection": section,
                "endSection": {"kind": "circle", "diameter": 20},
                "length": 100,
                "offset": [20, 0],
            },
            "cap": {"kind": "cap", "section": section, "depth": 60},
        }
        return recipes[role]

    @classmethod
    def configure(
        cls, model: JsonObject, role: str, family: str = "pipe"
    ) -> JsonObject:
        """Register one physical fitting and explicit membership for every generated port."""
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
            "kind": "serviceFittingType",
            "name": f"Illustrative {role}",
            "family": family,
            "material": "material.timber",
            "medium": medium,
            "connectionType": "illustrativeFace",
            "geometry": cls.geometry(role),
            "chordTolerance": 0.1,
            "flow": "forward",
        }
        if family != "cable":
            definition["wallThickness"] = 2
        Authoring.object(model["types"])["type.fitting"] = definition
        keys = (
            ["start"]
            + ([] if role == "cap" else ["end"])
            + (["side"] if role == "branch" else [])
        )
        elements = Authoring.object(model["elements"])
        elements["fitting.test"] = {
            "kind": "serviceFitting",
            "name": "Illustrative fitting",
            "type": "type.fitting",
            "storey": "level.ground",
            "placement": {"origin": {"point": [0, 0, 0]}},
            "clearance": 3,
            "portStates": {key: "open" for key in keys},
        }
        elements["system.test"] = {
            "kind": "serviceSystem",
            "name": "Fitting network",
            "systemType": "supplyAir" if medium == "air" else medium,
            "members": [{"element": "fitting.test", "port": key} for key in keys],
        }
        return definition

    @classmethod
    def trap(cls, model: JsonObject, medium: str = "waste") -> JsonObject:
        """Author a three-bend hollow return with a horizontal outlet and typed stock."""
        definition = cls.configure(model, "elbow")
        definition["medium"] = medium
        definition["pipe"] = {
            "designation": "Illustrative trap",
            "pressureRatingPa": 100000,
        }
        definition["geometry"] = {
            "kind": "trap",
            "section": {"kind": "circle", "diameter": 40},
            "path": [[0, 0, 200], [0, 0, 0], [200, 0, 0], [200, 0, 150], [400, 0, 150]],
            "bendRadius": 60,
        }
        elements = Authoring.object(model["elements"])
        Authoring.object(elements["system.test"])["systemType"] = medium
        Authoring.object(elements["fitting.test"])["conditions"] = {"pressurePa": 50000}
        return definition


@pytest.mark.parametrize("role", ["elbow", "branch", "transition", "cap"])
@pytest.mark.parametrize(
    "family,native,port_type",
    [
        ("pipe", "IfcPipeFitting", "PIPE"),
        ("duct", "IfcDuctFitting", "DUCT"),
        ("cable", "IfcCableFitting", "CABLE"),
        ("conduit", "IfcCableCarrierFitting", "CABLECARRIER"),
    ],
)
def test_fitting_solids_ports_and_native_ifc_families(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    role: str,
    family: str,
    native: str,
    port_type: str,
) -> None:
    """Every fitting family has real material, generated interfaces and concrete native IFC types."""
    FittingFixture.configure(reference_model, role, family)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolver = ModelResolver(reference_model)
    resolved = resolver.resolve()
    assert resolved.to_dict() == resolver.resolve().to_dict()
    fitting = resolved.element("fitting.test")
    body = fitting.meshes[0]
    solid = trimesh.Trimesh(vertices=body.vertices, faces=body.faces, process=False)
    assert solid.is_watertight and solid.is_winding_consistent
    assert solid.volume == pytest.approx(
        number(fitting.data["netVolumeMm3"], "material volume")
    )
    volumes = fitting.construction_volumes
    bore_volume = SolidOperations.volume(volumes["bore"]) if "bore" in volumes else 0
    assert SolidOperations.volume(volumes["envelope"]) == pytest.approx(
        solid.volume + bore_volume
    )
    if "bore" in volumes:
        assert SolidOperations.intersection(body, volumes["bore"]) is None
    count = {"elbow": 2, "branch": 3, "transition": 2, "cap": 1}[role]
    assert len(Authoring.object(fitting.data["ports"])) == count
    output = tmp_path / "fitting.ifc"
    IfcExporter().export(resolved, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    units = {
        unit.UnitType: unit
        for unit in ifc.by_type("IfcProject")[0].UnitsInContext.Units
    }
    assert units["LENGTHUNIT"].Name == "METRE" and units["LENGTHUNIT"].Prefix == "MILLI"
    assert units["AREAUNIT"].Name == "SQUARE_METRE" and units["AREAUNIT"].Prefix is None
    assert (
        units["VOLUMEUNIT"].Name == "CUBIC_METRE" and units["VOLUMEUNIT"].Prefix is None
    )
    product = ifc.by_guid(IfcExporter.stable_guid("fitting.test"))
    assert product.is_a(native)
    assert product.IsTypedBy[0].RelatingType.is_a(native + "Type")
    assert len(ifc.by_type("IfcDistributionPort")) == count
    assert {port.PredefinedType for port in ifc.by_type("IfcDistributionPort")} == {
        port_type
    }
    assert ifcopenshell.util.element.get_predefined_type(product) not in (
        None,
        "NOTDEFINED",
    )
    if role == "cap":
        assert product.IsTypedBy[0].RelatingType.PredefinedType == "USERDEFINED"
        assert ifcopenshell.util.element.get_predefined_type(product) == "cap"
    quantities = ifc.by_type("IfcQuantityVolume")
    assert len(quantities) == 1 and quantities[0].VolumeValue == pytest.approx(
        solid.volume / 1e9
    )


@pytest.mark.parametrize(
    "start,end",
    [
        (
            {"kind": "circle", "diameter": 80},
            {"kind": "rectangle", "width": 100, "height": 40},
        ),
        (
            {"kind": "rectangle", "width": 100, "height": 40},
            {"kind": "circle", "diameter": 80},
        ),
        (
            {"kind": "rectangle", "width": 100, "height": 40},
            {"kind": "rectangle", "width": 60, "height": 90},
        ),
    ],
)
def test_transitions_preserve_different_interface_shapes_and_eccentric_offsets(
    reference_model: JsonObject,
    validator: ModelValidator,
    start: JsonObject,
    end: JsonObject,
) -> None:
    """Parallel transition faces retain actual section dimensions through an eccentric taper."""
    definition = FittingFixture.configure(reference_model, "transition", "duct")
    geometry = Authoring.object(definition["geometry"])
    geometry.update({"startSection": start, "endSection": end, "offset": [30, -20]})
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    fitting = ModelResolver(reference_model).resolve().element("fitting.test")
    ports = Authoring.object(fitting.data["ports"])
    assert Authoring.object(ports["start"])["section"] == start
    assert Authoring.object(ports["end"])["section"] == end
    assert ServicePorts.frame(Authoring.object(ports["end"])).origin == pytest.approx(
        (30, -20, 100)
    )
    assert number(fitting.data["maxDeviationMm"], "deviation") <= 0.1


def test_closed_cap_retains_end_wall_and_accurate_material_quantity(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A physical cap ends its bore before the outer end instead of merely labeling a port capped."""
    FittingFixture.configure(reference_model, "cap")
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    cap = ModelResolver(reference_model).resolve().element("fitting.test")
    assert max(
        p[2] for p in cap.construction_volumes["bore"].vertices
    ) == pytest.approx(58)
    assert max(p[2] for p in cap.meshes[0].vertices) == pytest.approx(60)
    assert cap.data["netVolumeMm3"] == pytest.approx(
        math.pi * (20**2 * 60 - 18**2 * 58), rel=0.01
    )


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("outsideRoot", "does not fit inside"),
        ("oversizeRoot", "does not fit inside"),
        ("buriedEnd", "buried"),
        ("reserved", "reserved"),
        ("thinCap", "depth must exceed"),
        ("straightElbow", "genuine tangent bend"),
    ],
)
def test_invalid_fittings_reject_unconnected_passages_and_unusable_interfaces(
    reference_model: JsonObject, validator: ModelValidator, mutation: str, message: str
) -> None:
    """A declared internal group cannot conceal malformed geometry or a buried mating face."""
    role = (
        "cap"
        if mutation == "thinCap"
        else "elbow" if mutation == "straightElbow" else "branch"
    )
    definition = FittingFixture.configure(reference_model, role)
    geometry = Authoring.object(definition["geometry"])
    if role == "cap":
        geometry["depth"] = 2
    elif role == "elbow":
        geometry["path"] = [[0, 0, 0], [0, 0, 200], [0, 0, 400]]
    else:
        branches = Authoring.object(geometry["branches"])
        branch = Authoring.object(branches["side"])
        if mutation == "outsideRoot":
            branch["path"] = [[100, 0, 200], [200, 0, 200]]
        elif mutation == "oversizeRoot":
            branch["section"] = {"kind": "circle", "diameter": 80}
        elif mutation == "buriedEnd":
            branch["path"] = [[0, 0, 200], [10, 0, 200]]
        else:
            branches["end"] = branches.pop("side")
    report = validator.validate(reference_model)
    assert any(message in item.message for item in report.errors), report.to_dict()


def test_branched_fitting_routes_transitions_and_caps_follow_one_rigid_host_edit(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
) -> None:
    """A complete branch network preserves mating frames and identity as its supporting frame moves."""
    FittingFixture.configure(reference_model, "branch")
    elements, types = Authoring.object(reference_model["elements"]), Authoring.object(
        reference_model["types"]
    )
    root = Authoring.object(elements["fitting.test"])
    root.pop("portStates")
    root["placement"] = {
        "origin": {"anchor": "anchor.fitting"},
        "rotation": [20, 0, 30],
    }
    Authoring.object(reference_model["anchors"])["anchor.fitting"] = {
        "kind": "point3",
        "name": "Fitting network support",
        "position": [500, -3000, 100],
    }
    types["type.route"] = {
        "kind": "serviceRouteType",
        "name": "Illustrative pipe",
        "family": "pipe",
        "section": {"kind": "circle", "diameter": 40},
        "wallThickness": 2,
        "material": "material.timber",
        "medium": "water",
        "connectionType": "illustrativeFace",
        "flow": "forward",
    }
    members = Authoring.array(Authoring.object(elements["system.test"])["members"])
    routes: list[tuple[str, str, list[JsonValue], bool]] = [
        ("input", "start", [0, 0, -500], True),
        ("main", "end", [0, 0, 900], False),
        ("side", "side", [700, 0, 200], False),
    ]
    for key, port, offset, incoming in routes:
        endpoint: JsonObject = {"port": {"element": "fitting.test", "port": port}}
        other: JsonObject = {
            "host": {"kind": "component", "element": "fitting.test", "offset": offset}
        }
        elements[f"route.{key}"] = {
            "kind": "serviceRoute",
            "name": key,
            "type": "type.route",
            "storey": "level.ground",
            "path": [other, endpoint] if incoming else [endpoint, other],
            "chordTolerance": 0.1,
            "portStates": {"start": "open"} if incoming else {},
        }
        members.extend(
            [
                {"element": f"route.{key}", "port": "start"},
                {"element": f"route.{key}", "port": "end"},
            ]
        )
    for key, role, parent, diameter in (
        ("mainCap", "cap", "route.main", 40),
        ("reducer", "transition", "route.side", 40),
        ("smallCap", "cap", "fitting.reducer", 20),
    ):
        definition = deepcopy(Authoring.object(types["type.fitting"]))
        geometry = FittingFixture.geometry(role)
        if role == "cap":
            geometry["section"] = {"kind": "circle", "diameter": diameter}
        definition["geometry"] = geometry
        types[f"type.{key}"] = definition
        elements[f"fitting.{key}"] = {
            "kind": "serviceFitting",
            "name": key,
            "type": f"type.{key}",
            "storey": "level.ground",
            "placement": {"origin": {"port": {"element": parent, "port": "end"}}},
        }
        members.append({"element": f"fitting.{key}", "port": "start"})
        if role == "transition":
            members.append({"element": f"fitting.{key}", "port": "end"})
    relationships = Authoring.object(reference_model["relationships"])
    Authoring.object(types["type.reducer"])["portOverrides"] = {
        "end": {"connectionType": "illustrativeReducedFace"}
    }
    Authoring.object(types["type.smallCap"])[
        "connectionType"
    ] = "illustrativeReducedFace"
    types["type.source"] = {
        "kind": "serviceDeviceType",
        "name": "Illustrative source",
        "role": "equipment",
        "material": "material.timber",
        "solids": {
            "body": {
                "section": {"kind": "rectangle", "width": 100, "depth": 100},
                "depth": 100,
                "placement": {"origin": [0, 0, -100]},
            }
        },
        "ports": {
            "out": {
                "position": [0, 0, 0],
                "direction": [0, 0, 1],
                "section": {"kind": "circle", "diameter": 40},
                "medium": "water",
                "connectionType": "illustrativeFace",
                "flow": "source",
            }
        },
    }
    elements["device.source"] = {
        "kind": "serviceDevice",
        "name": "Source equipment",
        "type": "type.source",
        "storey": "level.ground",
        "placement": {
            "origin": {"port": {"element": "route.input", "port": "start"}},
            "rotation": [180, 0, 0],
        },
    }
    Authoring.object(elements["route.input"])["portStates"] = {}
    members.append({"element": "device.source", "port": "out"})
    for key, first, port, second in (
        ("source", "device.source", "out", "route.input"),
        ("input", "route.input", "end", "fitting.test"),
        ("main", "fitting.test", "end", "route.main"),
        ("side", "fitting.test", "side", "route.side"),
        ("mainCap", "route.main", "end", "fitting.mainCap"),
        ("reducer", "route.side", "end", "fitting.reducer"),
        ("smallCap", "fitting.reducer", "end", "fitting.smallCap"),
    ):
        relationships[f"connection.{key}"] = {
            "kind": "connectsPorts",
            "a": {"element": first, "port": port},
            "b": {"element": second, "port": "start"},
        }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    before = ModelResolver(reference_model).resolve()
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.network",
            "description": "Move the branched network",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "moveAnchor",
                    "anchorId": "anchor.fitting",
                    "position": [800, -2600, 600],
                }
            ],
        },
    )
    after = ModelResolver(changed).resolve()
    for original in before.elements:
        updated = after.element(original.element_id)
        if original.meshes:
            assert updated.data["netVolumeMm3"] == pytest.approx(
                number(original.data["netVolumeMm3"], "original stock")
            )
        for key, value in Authoring.object(original.data.get("ports", {})).items():
            old = ServicePorts.frame(Authoring.object(value))
            new = ServicePorts.frame(
                Authoring.object(Authoring.object(updated.data["ports"])[key])
            )
            assert new.origin == pytest.approx(
                [p + d for p, d in zip(old.origin, (300, 400, 500))]
            )
            assert new.z == pytest.approx(old.z)
    assert after.element("system.test").data["portCount"] == 14
    source = tmp_path / "fittings.json"
    source.write_text(json.dumps(changed), encoding="utf-8")
    first, second = BuildService().build(
        source, tmp_path / "first"
    ), BuildService().build(source, tmp_path / "second")
    assert first.glb_model.read_bytes() == second.glb_model.read_bytes()
    ifc = ifcopenshell.open(first.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert len(ifc.by_type("IfcRelConnectsPorts")) == 7
    assert len(ifc.by_type("IfcDistributionPort")) == 14
    assert sorted(entity.GlobalId for entity in ifc.by_type("IfcRoot")) == sorted(
        entity.GlobalId
        for entity in ifcopenshell.open(second.ifc_model).by_type("IfcRoot")
    )
    del relationships["connection.side"]
    assert any(
        "disconnected" in item.message
        for item in validator.validate(reference_model).errors
    )


@pytest.mark.parametrize("volume", ["bore", "clearance"])
def test_branch_fitting_cavity_ownership_and_derived_passage_cuts(
    reference_model: JsonObject,
    validator: ModelValidator,
    volume: str,
) -> None:
    """Junction stock and shared passages displace insulation without duplicate volume."""
    wall = deepcopy(
        Authoring.object(Authoring.object(reference_model["elements"])["wall.south"])
    )
    FittingFixture.configure(reference_model, "branch")
    wall["base"] = {"kind": "level", "level": "level.ground", "offset": 0}
    wall["top"] = {"kind": "height", "height": 2400}
    elements = Authoring.object(reference_model["elements"])
    elements["wall.south"] = wall
    Authoring.object(reference_model["materials"])["material.infill"] = {
        "name": "Illustrative cavity insulation"
    }
    layers = Authoring.array(
        Authoring.object(
            Authoring.object(reference_model["types"])["wallType.exterior.wood-185"]
        )["layers"]
    )
    Authoring.object(layers[2]).update(
        {"representation": "explicit", "material": "material.infill"}
    )
    fitting = Authoring.object(elements["fitting.test"])
    fitting["placement"] = {"origin": {"point": [8000, 9.5, 500]}}
    fitting["occupies"] = {"regions": [{"host": "wall.south", "layer": 2}]}
    elements["cut.fitting"] = {
        "kind": "penetration",
        "name": "Junction passage",
        "host": "wall.south",
        "owner": "fitting.test",
        "purpose": "service",
        "layers": [2],
        "geometrySource": {"element": "fitting.test", "volume": volume},
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    physical = result.element("fitting.test")
    host = result.element("wall.south")
    assert all(
        SolidOperations.partition(mesh, physical.construction_volumes["bore"])[1]
        is None
        for mesh in host.meshes
    )
    cavity = Authoring.object(Authoring.array(host.data["cavities"])[0])
    material = number(physical.data["netVolumeMm3"], "material")
    expected_void = SolidOperations.volume(physical.construction_volumes[volume]) - (
        material if volume == "clearance" else 0
    )
    assert cavity["occupiedVolumeMm3"] == pytest.approx(material)
    assert cavity["voidVolumeMm3"] == pytest.approx(expected_void)
    assert result.element("cut.fitting").data["cutVolumeMm3"] == pytest.approx(
        expected_void
    )
    del elements["cut.fitting"]
    assert any(
        "host material inside its bore" in item.message
        for item in validator.validate(reference_model).errors
    )


@pytest.mark.parametrize("role", ["elbow", "branch", "cap"])
def test_rectangular_fittings_retain_oriented_hollow_sections(
    reference_model: JsonObject, validator: ModelValidator, role: str
) -> None:
    """Rectangular bends, junctions and closures share the same real passage contract as round stock."""
    definition = FittingFixture.configure(reference_model, role, "duct")
    geometry = Authoring.object(definition["geometry"])
    section: JsonObject = {"kind": "rectangle", "width": 60, "height": 40}
    if role == "branch":
        Authoring.object(geometry["trunk"])["section"] = section
        arm = Authoring.object(Authoring.object(geometry["branches"])["side"])
        arm.update({"section": section, "up": [0, 1, 0]})
    else:
        geometry["section"] = section
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    fitting = ModelResolver(reference_model).resolve().element("fitting.test")
    assert all(
        Authoring.object(port)["section"] == section
        for port in Authoring.object(fitting.data["ports"]).values()
    )
    assert SolidOperations.volume(
        fitting.construction_volumes["envelope"]
    ) == pytest.approx(
        number(fitting.data["netVolumeMm3"], "stock")
        + SolidOperations.volume(fitting.construction_volumes["bore"])
    )
    if role == "cap":
        assert fitting.data["netVolumeMm3"] == pytest.approx(
            60 * 40 * 60 - 56 * 36 * 58
        )


@pytest.mark.parametrize("variant", ["angled", "curved", "cross", "staggered"])
def test_angled_curved_and_cross_branches_have_distinct_external_ports(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path, variant: str
) -> None:
    """Branch generation supports nonorthogonal takeoffs, tangent turns and more than one arm."""
    definition = FittingFixture.configure(reference_model, "branch", "conduit")
    geometry = Authoring.object(definition["geometry"])
    branches = Authoring.object(geometry["branches"])
    arm = Authoring.object(branches["side"])
    if variant == "angled":
        arm["path"] = [[0, 0, 200], [200, 0, 400]]
    elif variant == "curved":
        arm.update(
            {"path": [[0, 0, 200], [150, 0, 200], [150, 0, 400]], "bendRadius": 50}
        )
    else:
        branch_station = 250 if variant == "staggered" else 200
        branches["back"] = {
            "section": {"kind": "circle", "diameter": 40},
            "path": [[0, 0, branch_station], [-200, 0, branch_station]],
        }
        elements = Authoring.object(reference_model["elements"])
        Authoring.object(Authoring.object(elements["fitting.test"])["portStates"])[
            "back"
        ] = "open"
        Authoring.array(Authoring.object(elements["system.test"])["members"]).append(
            {"element": "fitting.test", "port": "back"}
        )
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    fitting = result.element("fitting.test")
    expected_count = 4 if variant in {"cross", "staggered"} else 3
    assert len(Authoring.object(fitting.data["ports"])) == expected_count
    assert SolidOperations.volume(
        fitting.construction_volumes["envelope"]
    ) == pytest.approx(
        number(fitting.data["netVolumeMm3"], "stock")
        + SolidOperations.volume(fitting.construction_volumes["bore"])
    )
    output = tmp_path / "branches.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    product = ifc.by_guid(IfcExporter.stable_guid("fitting.test"))
    assert ifcopenshell.util.element.get_predefined_type(product) == (
        "CROSS" if variant == "cross" else "branch" if variant == "staggered" else "TEE"
    )
    if variant == "staggered":
        assert product.IsTypedBy[0].RelatingType.PredefinedType == "USERDEFINED"


def test_fitting_port_overrides_change_mating_intent_without_moving_interfaces(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Adapters and mixing branches can author port-specific technology and flow on generated faces."""
    definition = FittingFixture.configure(reference_model, "transition")
    definition["portOverrides"] = {
        "start": {"connectionType": "illustrativeThread", "flow": "bidirectional"},
        "end": {"connectionType": "illustrativeCompression"},
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    fitting = ModelResolver(reference_model).resolve().element("fitting.test")
    ports = Authoring.object(fitting.data["ports"])
    start, end = Authoring.object(ports["start"]), Authoring.object(ports["end"])
    assert (
        start["flow"] == "bidirectional"
        and start["connectionType"] == "illustrativeThread"
    )
    assert (
        end["flow"] == "source" and end["connectionType"] == "illustrativeCompression"
    )
    assert ServicePorts.frame(start).origin == pytest.approx((0, 0, 0))
    Authoring.object(definition["portOverrides"])["absent"] = {"flow": "sink"}
    assert any(
        "Unknown fitting port overrides" in item.message
        for item in validator.validate(reference_model).errors
    )


@pytest.mark.parametrize("medium", ["waste", "condensate"])
def test_trap_has_physical_return_passage_and_native_export(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    medium: str,
) -> None:
    """A rounded trap retains its hollow solid, generated mating faces and authored pipe ratings."""
    FittingFixture.trap(reference_model, medium)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    trap = result.element("fitting.test")
    length = 750 - 360 + 90 * math.pi
    assert trap.data["centerlineLengthMm"] == pytest.approx(length)
    assert trap.data["netVolumeMm3"] == pytest.approx(
        math.pi * (20**2 - 18**2) * length, rel=0.01
    )
    assert (
        SolidOperations.intersection(trap.meshes[0], trap.construction_volumes["bore"])
        is None
    )
    assert SolidOperations.volume(
        trap.construction_volumes["envelope"]
    ) == pytest.approx(
        number(trap.data["netVolumeMm3"], "stock")
        + SolidOperations.volume(trap.construction_volumes["bore"])
    )
    ports = Authoring.object(trap.data["ports"])
    assert ServicePorts.frame(Authoring.object(ports["start"])).origin == (0, 0, 200)
    assert ServicePorts.frame(Authoring.object(ports["start"])).z == (0, 0, 1)
    assert ServicePorts.frame(Authoring.object(ports["end"])).origin == (400, 0, 150)
    assert ServicePorts.frame(Authoring.object(ports["end"])).z == (1, 0, 0)
    assert (
        Authoring.object(Authoring.array(trap.data["pipeRatingChecks"])[0])["status"]
        == "satisfied"
    )
    output = tmp_path / "trap.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("fitting.test"))
    assert product.is_a("IfcPipeFitting")
    assert ifcopenshell.util.element.get_predefined_type(product) == "trap"
    assert (
        ifcopenshell.util.element.get_pset(product, "Pset_HomeDesignPipe")[
            "designation"
        ]
        == "Illustrative trap"
    )
    assert (
        ifcopenshell.util.element.get_pset(product, "Pset_HomeDesignPipeConditions")[
            "pressurePa"
        ]
        == 50000
    )
    manifest = GltfExporter().export(
        result, tmp_path / "trap.glb", tmp_path / "manifest.json"
    )
    entry = Authoring.object(Authoring.object(manifest["elements"])["fitting.test"])
    assert entry["nodes"] and Authoring.object(entry["data"])["role"] == "trap"


@pytest.mark.parametrize(
    "invalid,message",
    [
        ("upsideDown", "lowered return"),
        ("flat", "lowered return"),
        ("wrongMedium", "waste or condensate"),
        ("pressure", "conflicts with authored"),
        ("wrongFamily", "waste or condensate"),
    ],
)
def test_trap_rejects_invalid_placement_medium_and_stock_conditions(
    reference_model: JsonObject,
    validator: ModelValidator,
    invalid: str,
    message: str,
) -> None:
    """A trap label cannot substitute for a placed return or compatible plumbing stock."""
    definition = FittingFixture.trap(reference_model)
    elements = Authoring.object(reference_model["elements"])
    fitting = Authoring.object(elements["fitting.test"])
    if invalid == "upsideDown":
        Authoring.object(fitting["placement"])["rotation"] = [180, 0, 0]
    elif invalid == "flat":
        Authoring.object(definition["geometry"])["path"] = [
            [0, 0, 0],
            [0, 200, 0],
            [200, 200, 0],
            [200, 400, 0],
        ]
    elif invalid == "wrongMedium":
        definition["medium"] = "water"
        Authoring.object(elements["system.test"])["systemType"] = "water"
    elif invalid == "wrongFamily":
        definition["family"], definition["medium"] = "duct", "air"
        del definition["pipe"]
        del fitting["conditions"]
        Authoring.object(elements["system.test"])["systemType"] = "supplyAir"
    else:
        fitting["conditions"] = {"pressurePa": 200000}
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert message in str(report.to_dict())
