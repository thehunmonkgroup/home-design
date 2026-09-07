"""Port-level service connectivity, coordinated placements and native IFC network exports."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest

from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class ServiceFixture:
    """Provide a source, a three-port junction and two terminals with separate branch circuits."""

    @staticmethod
    def port(
        position: list[JsonValue], direction: list[JsonValue], flow: str
    ) -> JsonObject:
        """Describe an illustrative electrical mating interface without product-design inference."""
        return {
            "position": position,
            "direction": direction,
            "flow": flow,
            "medium": "electrical",
            "connectionType": "illustrativeConnector",
            "section": {"kind": "circle", "diameter": 20},
        }

    @classmethod
    def configure(cls, model: JsonObject) -> None:
        """Use touching boxes and explicit local connection points in an isolated public model."""
        (
            model["elements"],
            model["relationships"],
            model["requirements"],
            model["solarStudies"],
        ) = ({}, {}, [], [])
        Authoring.object(model["anchors"])["anchor.services"] = {
            "kind": "point3",
            "name": "Service network origin",
            "position": [0, -4000, 0],
        }
        type_ports: dict[str, JsonObject] = {
            "source": {"out": cls.port([50, 0, 50], [1, 0, 0], "source")},
            "junction": {
                "in": cls.port([-50, 0, 50], [-1, 0, 0], "sink"),
                "branchA": cls.port([50, 0, 50], [1, 0, 0], "source"),
                "branchB": cls.port([0, 50, 50], [0, 1, 0], "source"),
            },
            "terminalA": {"in": cls.port([-50, 0, 50], [-1, 0, 0], "sink")},
            "terminalB": {"in": cls.port([0, -50, 50], [0, -1, 0], "sink")},
        }
        types = Authoring.object(model["types"])
        elements = Authoring.object(model["elements"])
        for key, ports in type_ports.items():
            types[f"type.{key}"] = {
                "kind": "serviceDeviceType",
                "name": f"Illustrative {key}",
                "role": (
                    "junction"
                    if key == "junction"
                    else "equipment" if key == "source" else "terminal"
                ),
                "material": "material.timber",
                "ports": ports,
                "solids": {
                    "body": {
                        "section": {"kind": "rectangle", "width": 100, "depth": 100},
                        "depth": 100,
                    }
                },
            }
            elements[f"device.{key}"] = {
                "kind": "serviceDevice",
                "name": key,
                "type": f"type.{key}",
                "storey": "level.ground",
            }
        Authoring.object(types["type.junction"])["portGroups"] = [
            ["in", "branchA", "branchB"]
        ]
        Authoring.object(elements["device.source"])["placement"] = {
            "origin": {"anchor": "anchor.services"}
        }
        placements: list[tuple[str, str, list[JsonValue]]] = [
            ("junction", "source", [100, 0, 0]),
            ("terminalA", "junction", [100, 0, 0]),
            ("terminalB", "junction", [0, 100, 0]),
        ]
        for key, host, offset in placements:
            placement: JsonObject = {
                "origin": {
                    "host": {
                        "kind": "component",
                        "element": f"device.{host}",
                        "offset": offset,
                    }
                }
            }
            Authoring.object(elements[f"device.{key}"])["placement"] = placement
        connections = Authoring.object(model["relationships"])
        for key, first, port, second in (
            ("supply", "source", "out", "junction"),
            ("branchA", "junction", "branchA", "terminalA"),
            ("branchB", "junction", "branchB", "terminalB"),
        ):
            connections[f"connection.{key}"] = {
                "kind": "connectsPorts",
                "a": {"element": f"device.{first}", "port": port},
                "b": {"element": f"device.{second}", "port": "in"},
            }
        elements["system.power"] = {
            "kind": "serviceSystem",
            "name": "Illustrative power network",
            "systemType": "electrical",
            "members": [
                {"element": f"device.{key}", "port": port}
                for key, ports in type_ports.items()
                for port in ports
            ],
        }
        for suffix in ("A", "B"):
            elements[f"circuit.branch{suffix}"] = {
                "kind": "serviceCircuit",
                "name": f"Branch {suffix}",
                "system": "system.power",
                "members": [
                    {"element": "device.junction", "port": f"branch{suffix}"},
                    {"element": f"device.terminal{suffix}", "port": "in"},
                ],
            }

    @staticmethod
    def port_definition(model: JsonObject, device: str, key: str) -> JsonObject:
        """Return one reusable local interface for targeted compatibility changes."""
        return Authoring.object(
            Authoring.object(
                Authoring.object(Authoring.object(model["types"])[f"type.{device}"])[
                    "ports"
                ]
            )[key]
        )


def test_component_names_do_not_turn_semantic_participants_into_placement_cycles() -> (
    None
):
    """Names beginning with host/port preserve semantic-only mutual connection intent."""
    model: JsonObject = {
        "elements": {
            "host.connector": {
                "kind": "hardware",
                "participants": [{"element": "port.connector"}],
            },
            "port.connector": {
                "kind": "hardware",
                "participants": [{"element": "host.connector"}],
            },
        }
    }
    assert ModelIndex(model).dependency_cycles() == []
    elements = Authoring.object(model["elements"])
    for first, second in (
        ("host.connector", "port.connector"),
        ("port.connector", "host.connector"),
    ):
        Authoring.object(elements[first])["placement"] = {
            "origin": {"host": {"kind": "component", "element": second}}
        }
    assert ModelIndex(model).dependency_cycles()


def test_service_branch_network_follows_transactional_anchor_edits(
    reference_model: JsonObject, validator: ModelValidator, loader: ModelLoader
) -> None:
    """Geometry dependencies propagate a move while circuit/connection identity remains stable."""
    ServiceFixture.configure(reference_model)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    before = ModelResolver(reference_model).resolve()
    assert before.element("system.power").data["portCount"] == 6
    assert before.element("system.power").data["status"] == "connected"
    assert before.element("circuit.branchA").data["connections"] == [
        "connection.branchA"
    ]
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.moveServices",
            "description": "Move the coordinated network",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "moveAnchor",
                    "anchorId": "anchor.services",
                    "position": [300, -3600, 500],
                }
            ],
        },
    )
    after = ModelResolver(changed).resolve()
    for key in ("source", "junction", "terminalA", "terminalB"):
        old_ports = Authoring.object(before.element(f"device.{key}").data["ports"])
        new_ports = Authoring.object(after.element(f"device.{key}").data["ports"])
        for port_key in old_ports:
            first = Authoring.array(
                Authoring.object(Authoring.object(old_ports[port_key])["frame"])[
                    "origin"
                ]
            )
            second = Authoring.object(Authoring.object(new_ports[port_key])["frame"])[
                "origin"
            ]
            assert second == pytest.approx(
                [
                    number(value, "port coordinate") + shift
                    for value, shift in zip(first, (300, 400, 500))
                ]
            )
    assert before.element("system.power").data == after.element("system.power").data


def test_rectangular_ports_match_physical_orientation_and_allow_rotated_dimension_pairs(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A rotated 40x20 interface mates a 20x40 face only when its actual corners align."""
    ServiceFixture.configure(reference_model)
    first = ServiceFixture.port_definition(reference_model, "source", "out")
    second = ServiceFixture.port_definition(reference_model, "junction", "in")
    first["section"] = {"kind": "rectangle", "width": 20, "height": 40}
    second["section"] = {"kind": "rectangle", "width": 40, "height": 20}
    second["up"] = [0, 1, 0]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    second["up"] = [0, 0, 1]
    assert any(
        "size or section orientation" in item.message
        for item in validator.validate(reference_model).errors
    )


def test_service_network_exports_native_ports_circuits_and_stable_connections(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """IFC preserves six distinct ports, internal bus intent and circuit membership."""
    ServiceFixture.configure(reference_model)
    source = tmp_path / "services.json"
    source.write_text(json.dumps(reference_model), encoding="utf-8")
    result = BuildService().build(source, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert len(ifc.by_type("IfcDistributionPort")) == 6
    assert len(ifc.by_type("IfcRelConnectsPorts")) == 3
    assert len(ifc.by_type("IfcDistributionCircuit")) == 2
    system = ifc.by_guid(IfcExporter.stable_guid("system.power"))
    assert system.PredefinedType == "ELECTRICAL"
    circuit = ifc.by_guid(IfcExporter.stable_guid("circuit.branchA"))
    port = ifc.by_guid(IfcExporter.stable_guid("device.junction/port/branchA"))
    assert port.FlowDirection == "SOURCE"
    assert port.PredefinedType == "CABLE"
    assert port.Nests[0].RelatingObject.Tag == "device.junction"
    assert port.ObjectPlacement.RelativePlacement.Location.Coordinates == pytest.approx(
        (150, -4000, 50)
    )
    assert [relation.RelatingGroup for relation in port.HasAssignments] == [circuit]
    assert circuit in system.IsGroupedBy[0].RelatedObjects
    connection = ifc.by_guid(IfcExporter.stable_guid("connection.branchA"))
    assert connection.RelatingPort == port
    assert connection.RelatedPort.FlowDirection == "SINK"
    first_guids = sorted(value.GlobalId for value in ifc.by_type("IfcRoot"))
    second = BuildService().build(source, tmp_path / "again")
    assert first_guids == sorted(
        value.GlobalId
        for value in ifcopenshell.open(second.ifc_model).by_type("IfcRoot")
    )
    assert result.glb_model.read_bytes() == second.glb_model.read_bytes()
    manifest = json.loads(result.render_manifest.read_text())
    assert (
        manifest["elements"]["device.junction"]["data"]["ports"]["branchA"]["circuitId"]
        == "circuit.branchA"
    )


def test_port_locators_follow_orientation_and_reject_placement_cycles(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A port-local access volume follows a rotated source while semantic mates stay separate."""
    ServiceFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    elements["zone.port"] = {
        "kind": "clearanceZone",
        "name": "Port approach",
        "owner": "device.source",
        "purpose": "installation",
        "placement": {"origin": {"port": {"element": "device.source", "port": "out"}}},
        "geometry": {
            "section": {"kind": "rectangle", "width": 10, "depth": 10},
            "depth": 50,
            "placement": {"origin": [0, 0, -50]},
        },
    }
    placement = Authoring.object(
        Authoring.object(elements["device.source"])["placement"]
    )
    placement["rotation"] = [0, 0, 90]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    zone = ModelResolver(reference_model).resolve().element("zone.port")
    assert Authoring.object(zone.data["placement"])["origin"] == pytest.approx(
        [0, -3950, 50]
    )
    assert Authoring.object(zone.data["placement"])["z"] == pytest.approx([0, 1, 0])
    assert zone.data["portPlacements"] == [{"element": "device.source", "port": "out"}]
    placement["origin"] = {"port": {"element": "device.terminalB", "port": "in"}}
    assert any(
        item.code == "dependency.cycle"
        for item in validator.validate(reference_model).errors
    )


def test_declared_open_and_capped_ports_are_intentional_network_boundaries(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Unconnected ends require explicit state and remain owned by a declared system."""
    ServiceFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    del Authoring.object(reference_model["relationships"])["connection.branchB"]
    del elements["circuit.branchB"]
    Authoring.object(elements["device.junction"])["portStates"] = {"branchB": "open"}
    Authoring.object(elements["device.terminalB"])["portStates"] = {"in": "capped"}
    system = Authoring.object(elements["system.power"])
    system["members"] = [
        value
        for value in Authoring.array(system["members"])
        if Authoring.object(value)["element"] != "device.terminalB"
    ]
    elements["system.capped"] = {
        "kind": "serviceSystem",
        "name": "Capped terminal",
        "systemType": "electrical",
        "members": [{"element": "device.terminalB", "port": "in"}],
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    assert resolved.element("system.capped").data["portCount"] == 1
    assert resolved.element("system.capped").data["connections"] == []


def test_cross_system_mates_are_rejected(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Individually connected groups cannot silently merge through an external mate."""
    ServiceFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    system = Authoring.object(elements["system.power"])
    system["members"] = [
        value
        for value in Authoring.array(system["members"])
        if Authoring.object(value)["element"] != "device.source"
    ]
    elements["system.source"] = {
        "kind": "serviceSystem",
        "name": "Separate source system",
        "systemType": "electrical",
        "members": [{"element": "device.source", "port": "out"}],
    }
    assert any(
        "joins different systems" in item.message
        for item in validator.validate(reference_model).errors
    )


def test_connected_service_loops_are_not_geometry_dependency_cycles(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Two independent mates and two declared internal buses form a valid undirected loop."""
    ServiceFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    source_type = Authoring.object(types["type.source"])
    junction_type = Authoring.object(types["type.junction"])
    source_type["ports"] = {
        "first": ServiceFixture.port([50, -25, 50], [1, 0, 0], "bidirectional"),
        "second": ServiceFixture.port([50, 25, 50], [1, 0, 0], "bidirectional"),
    }
    junction_type["ports"] = {
        "first": ServiceFixture.port([-50, -25, 50], [-1, 0, 0], "bidirectional"),
        "second": ServiceFixture.port([-50, 25, 50], [-1, 0, 0], "bidirectional"),
    }
    for definition in (source_type, junction_type):
        definition["portGroups"] = [["first", "second"]]
    elements = Authoring.object(reference_model["elements"])
    for key in (
        "device.terminalA",
        "device.terminalB",
        "circuit.branchA",
        "circuit.branchB",
    ):
        del elements[key]
    Authoring.object(elements["system.power"])["members"] = [
        {"element": f"device.{device}", "port": port}
        for device in ("source", "junction")
        for port in ("first", "second")
    ]
    reference_model["relationships"] = {
        f"connection.{key}": {
            "kind": "connectsPorts",
            "a": {"element": "device.source", "port": key},
            "b": {"element": "device.junction", "port": key},
        }
        for key in ("first", "second")
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()


@pytest.mark.parametrize(
    "failure, message",
    [
        ("medium", "incompatible medium"),
        ("technology", "incompatible connectionType"),
        ("flow", "flow directions"),
        ("position", "misaligned endpoints"),
        ("direction", "opposing port directions"),
        ("size", "incompatible size"),
        ("section", "transition between section shapes"),
        ("missing_port", "Unknown service port"),
        ("missing_element", "missing element"),
        ("duplicate", "multiple external connections"),
        ("disconnected", "disconnected"),
        ("internal_group", "Unknown service port"),
        ("missing_bus", "disconnected"),
        ("unassigned", "no system membership"),
        ("duplicate_system", "multiple systems"),
        ("wrong_system_medium", "incompatible medium"),
        ("wrong_circuit", "parent system"),
        ("duplicate_circuit", "multiple circuits"),
        ("open_connected", "declared open"),
        ("unknown_state", "Unknown service port state"),
    ],
)
def test_invalid_service_networks_report_actionable_diagnostics(
    reference_model: JsonObject, validator: ModelValidator, failure: str, message: str
) -> None:
    """Validate physical mates and membership without treating semantic connections as placement edges."""
    ServiceFixture.configure(reference_model)
    port = ServiceFixture.port_definition(reference_model, "source", "out")
    elements = Authoring.object(reference_model["elements"])
    types = Authoring.object(reference_model["types"])
    relationships = Authoring.object(reference_model["relationships"])
    source = Authoring.object(elements["device.source"])
    system = Authoring.object(elements["system.power"])
    mutations: dict[str, tuple[str, JsonValue]] = {
        "medium": ("medium", "water"),
        "technology": ("connectionType", "other"),
        "flow": ("flow", "sink"),
        "position": ("position", [51, 0, 50]),
        "direction": ("direction", [-1, 0, 0]),
        "size": ("section", {"kind": "circle", "diameter": 25}),
        "section": ("section", {"kind": "rectangle", "width": 20, "height": 20}),
    }
    if failure in mutations:
        key, value = mutations[failure]
        port[key] = value
    elif failure in {"missing_port", "missing_element"}:
        reference = Authoring.object(
            Authoring.object(relationships["connection.supply"])["a"]
        )
        reference["port" if failure == "missing_port" else "element"] = "missing"
    elif failure == "duplicate":
        relationships["connection.duplicate"] = deepcopy(
            relationships["connection.supply"]
        )
    elif failure == "disconnected":
        del relationships["connection.supply"]
    elif failure == "internal_group":
        Authoring.object(types["type.junction"])["portGroups"] = [["in", "absent"]]
    elif failure == "missing_bus":
        del Authoring.object(types["type.junction"])["portGroups"]
    elif failure == "unassigned":
        del elements["system.power"]
        del elements["circuit.branchA"]
        del elements["circuit.branchB"]
    elif failure == "duplicate_system":
        elements["system.duplicate"] = deepcopy(system)
    elif failure == "wrong_system_medium":
        system["systemType"] = "water"
    elif failure == "wrong_circuit":
        elements["device.spare"] = {
            "kind": "serviceDevice",
            "name": "Spare source",
            "type": "type.source",
            "placement": {"origin": {"point": [0, 0, 3000]}},
            "portStates": {"out": "open"},
        }
        elements["system.spare"] = {
            "kind": "serviceSystem",
            "name": "Separate system",
            "systemType": "electrical",
            "members": [{"element": "device.spare", "port": "out"}],
        }
        Authoring.object(elements["circuit.branchA"])["members"] = [
            {"element": "device.spare", "port": "out"}
        ]
    elif failure == "duplicate_circuit":
        elements["circuit.duplicate"] = deepcopy(elements["circuit.branchA"])
    elif failure == "open_connected":
        source["portStates"] = {"out": "open"}
    else:
        source["portStates"] = {"unknown": "open"}
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert any(message in item.message for item in report.errors), report.to_dict()
