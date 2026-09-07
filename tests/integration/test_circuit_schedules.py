"""Typed route stock, panel schedules, declared ratings and physical protection-path validation."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.json_types import JsonObject, JsonValue
from home_design.geometry import number
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.service_ports import ServicePorts
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class CircuitFixture:
    """Provide a panel, series breaker, scheduled cable and load with complete physical interfaces."""

    @staticmethod
    def port(height: int, direction: int) -> JsonObject:
        """Describe a local bundled power interface; individual conductors remain stock specifications."""
        return {
            "position": [0, 0, height],
            "direction": [0, 0, direction],
            "section": {"kind": "circle", "diameter": 10},
            "medium": "electrical",
            "function": "power",
            "flow": "source" if direction > 0 else "sink",
            "connectionType": "illustrativeFace",
        }

    @classmethod
    def configure(cls, model: JsonObject, signal: bool = False) -> JsonObject:
        """Build an isolated connected circuit with explicitly authored load and rating values."""
        (
            model["elements"],
            model["relationships"],
            model["requirements"],
            model["solarStudies"],
        ) = ({}, {}, [], [])
        types, elements = Authoring.object(model["types"]), Authoring.object(
            model["elements"]
        )
        for key, role, depth, origin, ports in (
            ("panel", "distributionPanel", 50, 0, {"out": cls.port(50, 1)}),
            (
                "breaker",
                "circuitBreaker",
                30,
                50,
                {"in": cls.port(0, -1), "out": cls.port(30, 1)},
            ),
            ("load", "light", 20, 580, {"in": cls.port(0, -1)}),
        ):
            if signal:
                role = {
                    "panel": "communicationsPanel",
                    "breaker": "junctionBox",
                    "load": "communicationsOutlet",
                }[key]
                for port in ports.values():
                    port["medium"], port["function"] = "communications", "signal"
            types[f"type.{key}"] = {
                "kind": "serviceDeviceType",
                "name": f"Illustrative {key}",
                "role": role,
                "material": "material.timber",
                "solids": {
                    "body": {
                        "section": {"kind": "rectangle", "width": 60, "depth": 40},
                        "depth": depth,
                    }
                },
                "electrical": (
                    {"signalCategory": "illustrativeData", "dataRateMbps": 1000}
                    if signal
                    else {
                        "ratedVoltageV": 120,
                        "ratedCurrentA": 20,
                        "poles": 1,
                        "supply": "AC",
                        "frequencyHz": 60,
                    }
                ),
                "ports": {name: value for name, value in ports.items()},
            }
            if len(ports) > 1:
                Authoring.object(types[f"type.{key}"])["portGroups"] = [list(ports)]
            elements[f"device.{key}"] = {
                "kind": "serviceDevice",
                "name": key,
                "type": f"type.{key}",
                "placement": {"origin": {"point": [0, 0, origin]}},
            }
        types["type.cable"] = {
            "kind": "serviceRouteType",
            "name": "Illustrative cable",
            "family": "cable",
            "material": "material.timber",
            "medium": "communications" if signal else "electrical",
            "function": "signal" if signal else "power",
            "connectionType": "illustrativeFace",
            "section": {"kind": "circle", "diameter": 10},
            "flow": "forward",
            "cable": (
                {
                    "designation": "Illustrative data cable",
                    "signalCategory": "illustrativeData",
                    "dataRateMbps": 1000,
                    "shielded": True,
                }
                if signal
                else {
                    "designation": "Illustrative three-conductor stock",
                    "ratedVoltageV": 600,
                    "allowableCurrentA": 20,
                    "maximumProtectionA": 20,
                    "conductors": [
                        {
                            "function": function,
                            "count": 1,
                            "areaMm2": 2.5,
                            "materialSpec": "Illustrative copper",
                            "insulationSpec": "Illustrative insulation",
                        }
                        for function in ("power", "neutral", "protectiveEarth")
                    ],
                }
            ),
        }
        elements["route.cable"] = {
            "kind": "serviceRoute",
            "name": "Cable",
            "type": "type.cable",
            "chordTolerance": 0.1,
            "path": [
                {"port": {"element": "device.breaker", "port": "out"}},
                {"port": {"element": "device.load", "port": "in"}},
            ],
        }
        relationships = Authoring.object(model["relationships"])
        for name, first, a, second, b in (
            ("supply", "device.panel", "out", "device.breaker", "in"),
            ("protected", "device.breaker", "out", "route.cable", "start"),
            ("load", "route.cable", "end", "device.load", "in"),
        ):
            relationships[f"connection.{name}"] = {
                "kind": "connectsPorts",
                "a": {"element": first, "port": a},
                "b": {"element": second, "port": b},
            }
        members: list[JsonValue] = [
            {"element": f"device.{key}", "port": port}
            for key, ports in (
                ("panel", ("out",)),
                ("breaker", ("in", "out")),
                ("load", ("in",)),
            )
            for port in ports
        ]
        members.extend(
            [
                {"element": "route.cable", "port": "start"},
                {"element": "route.cable", "port": "end"},
            ]
        )
        elements["system.test"] = {
            "kind": "serviceSystem",
            "name": "Circuit system",
            "systemType": "communications" if signal else "electrical",
            "members": members,
        }
        schedule: JsonObject = {
            "panel": {"element": "device.panel", "port": "out"},
            "number": "1",
        }
        if signal:
            schedule["communications"] = {
                "signalCategory": "illustrativeData",
                "dataRateMbps": 1000,
            }
        else:
            schedule["electrical"] = {
                "nominalVoltageV": 120,
                "supply": "AC",
                "poles": 1,
                "frequencyHz": 60,
                "designCurrentA": 10,
                "overcurrentProtection": {"element": "device.breaker", "port": "out"},
                "loads": [
                    {
                        "terminal": {"element": "device.load", "port": "in"},
                        "apparentPowerVA": 900,
                    }
                ],
            }
        elements["circuit.test"] = {
            "kind": "serviceCircuit",
            "name": "Circuit 1",
            "system": "system.test",
            "members": deepcopy(members),
            "schedule": schedule,
        }
        return schedule


class MountedCircuitFixture:
    """Coordinate two panel circuits and independently connected earthing parts on one editable wall."""

    @staticmethod
    def mount(station: int, height: int) -> JsonObject:
        """Orient the local route axis down the wall while keeping fabricated stock outside its face."""
        return {
            "origin": {
                "host": {
                    "kind": "wall",
                    "element": "wall.host",
                    "surface": "interior",
                    "station": station,
                    "height": height,
                }
            },
            "rotation": [90, 0, 0],
        }

    @classmethod
    def rename(cls, value: JsonValue, mapping: dict[str, str]) -> JsonValue:
        """Clone scoped references for an independent branch while preserving shared stock types."""
        if isinstance(value, dict):
            return {key: cls.rename(child, mapping) for key, child in value.items()}
        if isinstance(value, list):
            return [cls.rename(child, mapping) for child in value]
        return mapping.get(value, value) if isinstance(value, str) else value

    @classmethod
    def configure(cls, model: JsonObject, signal: bool) -> None:
        """Place genuine branches with distinct mates, actual wall mounts and a shared panel bus."""
        CircuitFixture.configure(model, signal)
        elements, types, anchors = (
            Authoring.object(model["elements"]),
            Authoring.object(model["types"]),
            Authoring.object(model["anchors"]),
        )
        for key, point in (("start", [0, 0]), ("end", [4000, 0])):
            anchors[f"anchor.wall.{key}"] = {
                "kind": "point2",
                "name": f"Wall {key}",
                "position": [point[0], point[1]],
                "level": "level.ground",
            }
        elements["wall.host"] = {
            "kind": "wall",
            "name": "Electrical mounting wall",
            "storey": "level.ground",
            "type": "wallType.exterior.wood-185",
            "locationLine": "center",
            "path": {
                "kind": "line",
                "start": {"anchor": "anchor.wall.start"},
                "end": {"anchor": "anchor.wall.end"},
            },
            "base": {"kind": "level", "level": "level.ground", "offset": 0},
            "top": {"kind": "height", "height": 2700},
        }
        panel = Authoring.object(types["type.panel"])
        Authoring.object(
            Authoring.object(Authoring.object(panel["solids"])["body"])["section"]
        )["width"] = 240
        panel_ports = Authoring.object(panel["ports"])
        Authoring.object(panel_ports["out"])["position"] = [-70, 0, 50]
        panel_ports["branch2"] = {
            **Authoring.object(panel_ports["out"]),
            "position": [70, 0, 50],
        }
        panel["portGroups"] = [["out", "branch2"]]
        Authoring.object(elements["device.panel"]).update(
            {"placement": cls.mount(600, 1800), "projection": 20}
        )
        Authoring.object(elements["device.breaker"])["placement"] = {
            "origin": {
                "host": {
                    "kind": "component",
                    "element": "device.panel",
                    "offset": [-70, 0, 50],
                }
            }
        }
        Authoring.object(elements["device.load"]).update(
            {"placement": cls.mount(530, 1220), "projection": 20}
        )
        mapping = {
            "device.breaker": "device.breaker2",
            "device.load": "device.load2",
            "route.cable": "route.cable2",
        }
        for original, renamed in mapping.items():
            elements[renamed] = cls.rename(elements[original], mapping)
        Authoring.object(elements["device.breaker2"])["placement"] = {
            "origin": {
                "host": {
                    "kind": "component",
                    "element": "device.panel",
                    "offset": [70, 0, 50],
                }
            }
        }
        Authoring.object(elements["device.load2"])["placement"] = cls.mount(670, 920)
        if not signal:
            types["type.receptacle"] = {
                **Authoring.object(types["type.load"]),
                "role": "receptacle",
                "name": "Illustrative receptacle",
            }
            Authoring.object(elements["device.load2"])["type"] = "type.receptacle"
        relations = Authoring.object(model["relationships"])
        for key in ("supply", "protected", "load"):
            relations[f"connection.branch2.{key}"] = cls.rename(
                relations[f"connection.{key}"], mapping
            )
        Authoring.object(Authoring.object(relations["connection.branch2.supply"])["a"])[
            "port"
        ] = "branch2"
        second = Authoring.object(cls.rename(elements["circuit.test"], mapping))
        second["name"] = "Circuit 2"
        second_schedule = Authoring.object(second["schedule"])
        second_schedule["number"] = "2"
        Authoring.object(second_schedule["panel"])["port"] = "branch2"
        for value in Authoring.array(second["members"]):
            member = Authoring.object(value)
            if member["element"] == "device.panel":
                member["port"] = "branch2"
        elements["circuit.second"] = second
        Authoring.array(Authoring.object(elements["system.test"])["members"]).extend(
            deepcopy(Authoring.array(second["members"]))
        )
        if not signal:
            cls.earthing(model)
            cls.recessed_box(model)

    @classmethod
    def earthing(cls, model: JsonObject) -> None:
        """Declare a grounding bar with distinct protective-earth and bonding branches."""
        elements, types = Authoring.object(model["elements"]), Authoring.object(
            model["types"]
        )
        ports: JsonObject = {}
        members: list[JsonValue] = []
        for key, function, role, station, height, offset in (
            ("earth", "protectiveEarth", "groundingElectrode", 2430, 1100, -70),
            ("bond", "bonding", "bondingClamp", 2570, 1000, 70),
        ):
            ports[key] = {
                **CircuitFixture.port(50, 1),
                "position": [offset, 0, 50],
                "function": function,
                "flow": "bidirectional",
            }
            types[f"type.{key}"] = {
                **Authoring.object(types["type.load"]),
                "role": role,
                "electrical": {"enclosureRating": "Illustrative specification"},
                "ports": {
                    "in": {
                        **CircuitFixture.port(0, -1),
                        "function": function,
                        "flow": "bidirectional",
                    }
                },
            }
            elements[f"device.{key}"] = {
                "kind": "serviceDevice",
                "name": role,
                "type": f"type.{key}",
                "placement": cls.mount(station, height),
                "projection": 20,
            }
            types[f"type.wire.{key}"] = {
                **Authoring.object(types["type.cable"]),
                "function": function,
                "flow": "bidirectional",
                "cable": {
                    "designation": f"Illustrative {function} conductor",
                    "construction": "conductor",
                    "conductors": [
                        {
                            "function": function,
                            "count": 1,
                            "areaMm2": 2.5,
                            "materialSpec": "Illustrative copper",
                        }
                    ],
                },
            }
            elements[f"route.{key}"] = {
                "kind": "serviceRoute",
                "name": f"{function} wire",
                "type": f"type.wire.{key}",
                "chordTolerance": 0.1,
                "path": [
                    {"port": {"element": "device.groundBar", "port": key}},
                    {"port": {"element": f"device.{key}", "port": "in"}},
                ],
            }
            for first, a, second, b in (
                ("device.groundBar", key, f"route.{key}", "start"),
                (f"route.{key}", "end", f"device.{key}", "in"),
            ):
                Authoring.object(model["relationships"])[f"connection.{key}.{a}"] = {
                    "kind": "connectsPorts",
                    "a": {"element": first, "port": a},
                    "b": {"element": second, "port": b},
                }
                members.extend(
                    [{"element": first, "port": a}, {"element": second, "port": b}]
                )
        types["type.groundBar"] = {
            **Authoring.object(types["type.panel"]),
            "role": "groundingBar",
            "electrical": {"enclosureRating": "Illustrative specification"},
            "ports": ports,
            "portGroups": [["earth", "bond"]],
        }
        elements["device.groundBar"] = {
            "kind": "serviceDevice",
            "name": "Grounding bar",
            "type": "type.groundBar",
            "placement": cls.mount(2500, 1800),
            "projection": 20,
        }
        elements["system.earthing"] = {
            "kind": "serviceSystem",
            "name": "Explicit earthing and bonding",
            "systemType": "electrical",
            "members": members,
        }

    @staticmethod
    def recessed_box(model: JsonObject) -> None:
        """Cut a real flush box recess while retaining its hollow stock and explicit open entry."""
        mount: JsonObject = {
            "kind": "wall",
            "element": "wall.host",
            "surface": "interior",
            "station": 3500,
            "height": 1200,
        }
        types, elements = Authoring.object(model["types"]), Authoring.object(
            model["elements"]
        )
        types["type.flushBox"] = {
            "kind": "serviceDeviceType",
            "name": "Illustrative flush box",
            "role": "deviceBox",
            "material": "material.timber",
            "electrical": {"enclosureRating": "Illustrative specification"},
            "solids": {
                "body": {
                    "section": {"kind": "rectangle", "width": 50, "depth": 50},
                    "depth": 40,
                }
            },
            "cuts": {
                "interior": {
                    "section": {"kind": "rectangle", "width": 44, "depth": 44},
                    "depth": 37,
                    "placement": {"origin": [0, 0, 3]},
                }
            },
            "ports": {
                "entry": {
                    **CircuitFixture.port(3, -1),
                    "function": "containment",
                    "flow": "bidirectional",
                }
            },
        }
        elements["device.flushBox"] = {
            "kind": "serviceDevice",
            "name": "Flush box",
            "type": "type.flushBox",
            "placement": {"origin": {"host": mount}},
            "projection": -40,
            "portStates": {"entry": "open"},
        }
        elements["cut.flushBox"] = {
            "kind": "penetration",
            "name": "Owned box recess",
            "host": "wall.host",
            "owner": "device.flushBox",
            "purpose": "recess",
            "placement": {"origin": {"host": mount}, "rotation": [180, 0, 0]},
            "section": {"kind": "rectangle", "width": 50, "depth": 50},
            "depth": 40,
        }
        elements["system.boxEntry"] = {
            "kind": "serviceSystem",
            "name": "Open rough-in entry",
            "systemType": "electrical",
            "members": [{"element": "device.flushBox", "port": "entry"}],
        }


@pytest.mark.parametrize("signal", [False, True])
def test_mounted_branches_and_construction_parts_follow_a_rotated_wall_transaction(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
    signal: bool,
) -> None:
    """Moving the host coordinates physical mounts, branch circuits, earthing, recess cuts and exports."""
    MountedCircuitFixture.configure(reference_model, signal)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    before = ModelResolver(reference_model).resolve()
    original_rows = ModelReports(before).schedules()["circuitSchedules"]
    assert [
        Authoring.object(row)["routeLengthMm"] for row in Authoring.array(original_rows)
    ] == pytest.approx([500, 800])
    if not signal:
        assert before.element("system.earthing").data["portCount"] == 8
        assert before.element("device.flushBox").data["netVolumeMm3"] == pytest.approx(
            50 * 50 * 40 - 44 * 44 * 37
        )
        assert before.element("device.flushBox").data[
            "mountingRangeMm"
        ] == pytest.approx([-40, 0])
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": "change.rotateElectricalWall",
        "description": "Rotate and translate the coordinated mounting wall",
        "baseRevision": reference_model["revision"],
        "operations": [
            {
                "op": "moveAnchor",
                "anchorId": "anchor.wall.start",
                "position": [300, 400],
            },
            {
                "op": "moveAnchor",
                "anchorId": "anchor.wall.end",
                "position": [300, 4400],
            },
        ],
    }
    changed = ChangeEngine(loader, validator).apply(reference_model, change)
    after = ModelResolver(changed).resolve()
    for element in before.elements:
        moved = after.element(element.element_id)
        if element.kind == "serviceDevice":
            assert moved.data["mountHostId"] == element.data["mountHostId"]
        if element.kind in {"serviceDevice", "serviceRoute", "wall"}:
            assert sum(
                SolidOperations.volume(mesh) for mesh in moved.meshes
            ) == pytest.approx(
                sum(SolidOperations.volume(mesh) for mesh in element.meshes)
            )
        for key, value in Authoring.object(element.data.get("ports", {})).items():
            old_frame = ServicePorts.frame(Authoring.object(value))
            new_frame = ServicePorts.frame(
                Authoring.object(Authoring.object(moved.data["ports"])[key])
            )
            x, y, z = old_frame.origin
            assert new_frame.origin == pytest.approx([-y + 300, x + 400, z])
            nx, ny, nz = old_frame.z
            assert new_frame.z == pytest.approx([-ny, nx, nz])
    assert ModelReports(after).schedules()["circuitSchedules"] == original_rows
    for previous, current in zip(
        Authoring.array(ModelReports(before).schedules()["materials"]),
        Authoring.array(ModelReports(after).schedules()["materials"]),
        strict=True,
    ):
        previous_row, current_row = Authoring.object(previous), Authoring.object(
            current
        )
        assert current_row["materialId"] == previous_row["materialId"]
        assert number(current_row["volumeM3"], "material volume") == pytest.approx(
            number(previous_row["volumeM3"], "material volume")
        )
    source = tmp_path / "mounted-circuits.json"
    source.write_text(json.dumps(changed), encoding="utf-8")
    built = BuildService(loader, validator).build(source, tmp_path / "mounted-build")
    ifc = ifcopenshell.open(built.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    manifest = Authoring.object(
        json.loads(built.render_manifest.read_text(encoding="utf-8"))
    )
    for element in after.elements:
        if element.kind not in {"serviceDevice", "serviceRoute"}:
            continue
        assert Authoring.object(
            Authoring.object(manifest["elements"])[element.element_id]
        )["nodes"]
        native = ifc.by_guid(IfcExporter.stable_guid(element.element_id))
        assert native.IsTypedBy
        assert len(native.IsNestedBy[0].RelatedObjects) == len(
            Authoring.object(element.data["ports"])
        )
    if not signal:
        assert len(ifc.by_type("IfcRelVoidsElement")) == 1
        without_cut = deepcopy(changed)
        del Authoring.object(without_cut["elements"])["cut.flushBox"]
        invalid = validator.validate(without_cut)
        assert not invalid.is_valid and "overlaps host" in str(invalid.to_dict())


@pytest.mark.parametrize("signal", [False, True])
def test_circuit_schedules_export_checked_supply_stock_and_native_assignments(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
    signal: bool,
) -> None:
    """A complete build retains circuit rows, native relationships and nominal conductor stock once."""
    schedule = CircuitFixture.configure(reference_model, signal)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    row = Authoring.object(
        Authoring.array(ModelReports(result).schedules()["circuitSchedules"])[0]
    )
    assert row["panel"] == schedule["panel"] and row["number"] == "1"
    assert row["routeLengthMm"] == pytest.approx(500)
    assert row["ratingStatus"] == "checked"
    cable = result.element("route.cable")
    if not signal:
        assert row["connectedLoadVA"] == 900
        assert [
            Authoring.object(c)["stockLengthMm"]
            for c in Authoring.array(cable.data["conductorSchedule"])
        ] == [500, 500, 500]
    source = tmp_path / "circuit.json"
    source.write_text(json.dumps(reference_model), encoding="utf-8")
    build = BuildService(loader, validator)
    first, second = build.build(source, tmp_path / "first"), build.build(
        source, tmp_path / "second"
    )
    assert (first.output_directory / "model.glb").read_bytes() == (
        second.output_directory / "model.glb"
    ).read_bytes()
    assert (first.output_directory / "schedules.json").read_bytes() == (
        second.output_directory / "schedules.json"
    ).read_bytes()
    ifc = ifcopenshell.open(first.output_directory / "model.ifc")
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    circuit = ifc.by_guid(IfcExporter.stable_guid("circuit.test"))
    assert circuit.is_a("IfcDistributionCircuit")
    pset = ifcopenshell.util.element.get_pset(circuit, "Pset_HomeDesignCircuitSchedule")
    assert (
        json.loads(pset["panel"]) == schedule["panel"]
        and pset["ratingStatus"] == "checked"
    )
    assignment = ifc.by_guid(IfcExporter.stable_guid("rel.circuitPanel.circuit.test"))
    assert assignment.RelatingProduct.GlobalId == IfcExporter.stable_guid(
        "device.panel"
    )
    assert assignment.RelatedObjects == (circuit,)
    native_cable = ifc.by_guid(IfcExporter.stable_guid("route.cable"))
    assert (
        ifcopenshell.util.element.get_pset(native_cable, "Pset_HomeDesignCable")[
            "designation"
        ]
        == Authoring.object(cable.data["cable"])["designation"]
    )
    assert {r.GlobalId for r in ifc.by_type("IfcRoot")} == {
        r.GlobalId
        for r in ifcopenshell.open(second.output_directory / "model.ifc").by_type(
            "IfcRoot"
        )
    }


@pytest.mark.parametrize(
    "invalid",
    [
        "voltage",
        "supply",
        "frequency",
        "current",
        "poles",
        "protectionLimit",
        "loadReference",
        "duplicateLoad",
        "panelReference",
        "panelKind",
        "protectionKind",
        "protectionInput",
        "wrongSystem",
        "splitRoute",
        "negativeLoad",
        "unknownField",
        "oversizeConductors",
    ],
)
def test_invalid_circuit_specifications_and_stock_fail_validation(
    reference_model: JsonObject, validator: ModelValidator, invalid: str
) -> None:
    """Contradictory ratings and out-of-scope references cannot enter an exported schedule."""
    schedule = CircuitFixture.configure(reference_model)
    electrical = Authoring.object(schedule["electrical"])
    elements, types = Authoring.object(reference_model["elements"]), Authoring.object(
        reference_model["types"]
    )
    if invalid == "voltage":
        electrical["nominalVoltageV"] = 240
    elif invalid == "supply":
        electrical["supply"], electrical["frequencyHz"] = "DC", 0
    elif invalid == "frequency":
        electrical["frequencyHz"] = 50
    elif invalid == "current":
        Authoring.object(Authoring.object(types["type.cable"])["cable"])[
            "allowableCurrentA"
        ] = 5
    elif invalid == "poles":
        electrical["poles"] = 2
    elif invalid == "protectionLimit":
        Authoring.object(Authoring.object(types["type.cable"])["cable"])[
            "maximumProtectionA"
        ] = 15
    elif invalid == "loadReference":
        Authoring.object(Authoring.array(electrical["loads"])[0])["terminal"] = {
            "element": "device.load",
            "port": "missing",
        }
    elif invalid == "duplicateLoad":
        Authoring.array(electrical["loads"]).append(
            deepcopy(Authoring.array(electrical["loads"])[0])
        )
    elif invalid == "panelReference":
        schedule["panel"] = {"element": "missing.panel", "port": "out"}
    elif invalid == "panelKind":
        schedule["panel"] = {"element": "device.breaker", "port": "out"}
    elif invalid == "protectionKind":
        electrical["overcurrentProtection"] = {"element": "device.panel", "port": "out"}
    elif invalid == "protectionInput":
        electrical["overcurrentProtection"] = {
            "element": "device.breaker",
            "port": "in",
        }
    elif invalid == "wrongSystem":
        del schedule["electrical"]
        schedule["communications"] = {"signalCategory": "illustrative"}
    elif invalid == "splitRoute":
        Authoring.object(elements["circuit.test"])["members"] = [
            v
            for v in Authoring.array(
                Authoring.object(elements["circuit.test"])["members"]
            )
            if Authoring.object(v)["element"] != "device.load"
            and v != {"element": "route.cable", "port": "end"}
        ]
    elif invalid == "negativeLoad":
        Authoring.object(Authoring.array(electrical["loads"])[0])[
            "apparentPowerVA"
        ] = -1
    elif invalid == "unknownField":
        electrical["automaticSizing"] = True
    else:
        cable = Authoring.object(Authoring.object(types["type.cable"])["cable"])
        Authoring.object(Authoring.array(cable["conductors"])[0])["areaMm2"] = 100
    assert not validator.validate(reference_model).is_valid


def test_unknown_ratings_remain_unchecked_and_missing_loads_are_not_zero(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A partial specification remains useful without being reported as complete verification."""
    schedule = CircuitFixture.configure(reference_model)
    electrical = Authoring.object(schedule["electrical"])
    del electrical["loads"]
    del electrical["designCurrentA"]
    cable = Authoring.object(
        Authoring.object(Authoring.object(reference_model["types"])["type.cable"])[
            "cable"
        ]
    )
    del cable["ratedVoltageV"]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    row = Authoring.object(
        ModelResolver(reference_model)
        .resolve()
        .element("circuit.test")
        .data["circuitSchedule"]
    )
    assert row["ratingStatus"] == "partiallyChecked" and row["connectedLoadVA"] is None
    assert any(
        Authoring.object(check)["status"] == "notChecked"
        for check in Authoring.array(row["ratingChecks"])
    )


def test_panel_circuit_numbers_are_unique_across_distinct_output_ports(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A second valid panel outlet cannot silently reuse an existing circuit designation."""
    CircuitFixture.configure(reference_model)
    elements, types = Authoring.object(reference_model["elements"]), Authoring.object(
        reference_model["types"]
    )
    panel_type = Authoring.object(types["type.panel"])
    Authoring.object(panel_type["ports"])["other"] = {
        **CircuitFixture.port(50, 1),
        "position": [20, 0, 50],
    }
    panel_type["portGroups"] = [["out", "other"]]
    Authoring.object(elements["device.panel"])["portStates"] = {"other": "open"}
    member: JsonObject = {"element": "device.panel", "port": "other"}
    Authoring.array(Authoring.object(elements["system.test"])["members"]).append(member)
    other_schedule: JsonObject = {
        "panel": member,
        "number": "1",
        "electrical": {"nominalVoltageV": 120, "supply": "AC", "poles": 1},
    }
    elements["circuit.other"] = {
        "kind": "serviceCircuit",
        "name": "Second circuit",
        "system": "system.test",
        "members": [member],
        "schedule": other_schedule,
    }
    report = validator.validate(reference_model)
    assert not report.is_valid and "Duplicate circuit number" in str(report.to_dict())
    other_schedule["number"] = "2"
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    rows = Authoring.array(
        ModelReports(ModelResolver(reference_model).resolve()).schedules()[
            "circuitSchedules"
        ]
    )
    assert [Authoring.object(row)["number"] for row in rows] == ["1", "2"]


def test_conduit_specifications_preserve_native_stock_without_material_double_count(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Conduit trade data describes the existing hollow solid and does not create extra material."""
    CircuitFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    types["type.conduit"] = {
        "kind": "serviceRouteType",
        "name": "Illustrative conduit",
        "family": "conduit",
        "material": "material.timber",
        "section": {"kind": "circle", "diameter": 30},
        "wallThickness": 2,
        "medium": "electrical",
        "function": "containment",
        "connectionType": "illustrativeCarrier",
        "conduit": {
            "designation": "Illustrative raceway",
            "nominalSize": "Authored trade designation",
            "flexible": True,
            "maximumFillFraction": 0.4,
        },
    }
    reference_model["elements"] = {
        "route.conduit": {
            "kind": "serviceRoute",
            "name": "Conduit",
            "type": "type.conduit",
            "path": [{"point": [0, 0, 0]}, {"point": [0, 0, 500]}],
            "chordTolerance": 0.1,
            "portStates": {"start": "open", "end": "open"},
        },
        "system.conduit": {
            "kind": "serviceSystem",
            "name": "Carrier network",
            "systemType": "electrical",
            "members": [
                {"element": "route.conduit", "port": "start"},
                {"element": "route.conduit", "port": "end"},
            ],
        },
    }
    reference_model["relationships"] = {}
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    stock = Authoring.object(types["type.conduit"])
    assert result.element("route.conduit").data["conduit"] == stock["conduit"]
    IfcExporter().export(result, tmp_path / "carrier.ifc")
    native = ifcopenshell.open(tmp_path / "carrier.ifc").by_guid(
        IfcExporter.stable_guid("route.conduit")
    )
    assert (
        ifcopenshell.util.element.get_pset(native, "Pset_HomeDesignConduit")[
            "maximumFillFraction"
        ]
        == 0.4
    )
    before = ModelReports(result).schedules()["materials"]
    del stock["conduit"]
    assert (
        ModelReports(ModelResolver(reference_model).resolve()).schedules()["materials"]
        == before
    )
    stock["conduit"] = {"designation": "Invalid fill limit", "maximumFillFraction": 1.1}
    assert not validator.validate(reference_model).is_valid


@pytest.mark.parametrize(
    "invalid",
    [
        "conduitOnCable",
        "cableOnConduit",
        "opticalPower",
        "multipleCore",
        "zeroConductorCount",
    ],
)
def test_route_stock_specifications_respect_their_physical_family(
    reference_model: JsonObject, validator: ModelValidator, invalid: str
) -> None:
    """Typed stock cannot contradict the segment family or single-core construction it classifies."""
    CircuitFixture.configure(reference_model)
    definition = Authoring.object(
        Authoring.object(reference_model["types"])["type.cable"]
    )
    cable = Authoring.object(definition["cable"])
    if invalid == "conduitOnCable":
        definition["conduit"] = {"designation": "Wrong family"}
    elif invalid == "cableOnConduit":
        definition["family"], definition["wallThickness"] = "conduit", 1
    elif invalid == "opticalPower":
        cable["construction"] = "opticalFiber"
    elif invalid == "multipleCore":
        cable["construction"] = "core"
    else:
        Authoring.object(Authoring.array(cable["conductors"])[0])["count"] = 0
    assert not validator.validate(reference_model).is_valid


def test_communications_schedule_rejects_insufficient_authored_data_rate(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Communications capacity comparisons use declared limits without guessing category compatibility."""
    schedule = CircuitFixture.configure(reference_model, True)
    Authoring.object(schedule["communications"])["dataRateMbps"] = 2000
    report = validator.validate(reference_model)
    assert not report.is_valid and "dataRateMbps" in str(report.to_dict())


def test_scheduled_cable_fitting_retains_and_checks_its_authored_voltage_rating(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Cable fittings can supply known limits instead of remaining permanently unrated in circuit rows."""
    schedule = CircuitFixture.configure(reference_model)
    del Authoring.object(schedule["electrical"])["overcurrentProtection"]
    elements, types = Authoring.object(reference_model["elements"]), Authoring.object(
        reference_model["types"]
    )
    del Authoring.object(Authoring.object(types["type.cable"])["cable"])[
        "maximumProtectionA"
    ]
    fitting: JsonObject = {
        "kind": "serviceFittingType",
        "name": "Rated cable adapter",
        "family": "cable",
        "medium": "electrical",
        "function": "power",
        "material": "material.timber",
        "connectionType": "illustrativeFace",
        "flow": "forward",
        "chordTolerance": 0.1,
        "geometry": {
            "kind": "transition",
            "startSection": {"kind": "circle", "diameter": 10},
            "endSection": {"kind": "circle", "diameter": 10},
            "length": 30,
        },
        "electrical": {"ratedVoltageV": 120, "supply": "AC", "frequencyHz": 60},
    }
    types["type.adapter"] = fitting
    elements["device.breaker"] = {
        "kind": "serviceFitting",
        "name": "Adapter",
        "type": "type.adapter",
        "placement": {"origin": {"point": [0, 0, 50]}},
    }
    for group in ("system.test", "circuit.test"):
        for value in Authoring.array(Authoring.object(elements[group])["members"]):
            member = Authoring.object(value)
            if member["element"] == "device.breaker":
                member["port"] = "start" if member["port"] == "in" else "end"
    for value in Authoring.object(reference_model["relationships"]).values():
        for field in ("a", "b"):
            member = Authoring.object(Authoring.object(value)[field])
            if member["element"] == "device.breaker":
                member["port"] = "start" if member["port"] == "in" else "end"
    Authoring.object(
        Authoring.object(
            Authoring.array(Authoring.object(elements["route.cable"])["path"])[0]
        )["port"]
    )["port"] = "end"
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    assert (
        Authoring.object(result.element("circuit.test").data["circuitSchedule"])[
            "ratingStatus"
        ]
        == "checked"
    )
    IfcExporter().export(result, tmp_path / "rated-fitting.ifc")
    native = ifcopenshell.open(tmp_path / "rated-fitting.ifc").by_guid(
        IfcExporter.stable_guid("device.breaker")
    )
    assert (
        ifcopenshell.util.element.get_pset(native, "Pset_ElectricalDeviceCommon")[
            "RatedVoltage"
        ]
        == 120
    )
    Authoring.object(fitting["electrical"])["ratedVoltageV"] = 60
    report = validator.validate(reference_model)
    assert not report.is_valid and "voltageV" in str(report.to_dict())


@pytest.mark.parametrize(
    "construction,predefined",
    [
        ("cable", "CABLESEGMENT"),
        ("conductor", "CONDUCTORSEGMENT"),
        ("core", "CORESEGMENT"),
        ("opticalFiber", "opticalFiber"),
    ],
)
def test_cable_construction_survives_native_ifc_classification(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    construction: str,
    predefined: str,
) -> None:
    """Native cable subtypes distinguish an individual conductor/core and an authored optical-fiber product."""
    CircuitFixture.configure(reference_model, construction == "opticalFiber")
    cable = Authoring.object(
        Authoring.object(Authoring.object(reference_model["types"])["type.cable"])[
            "cable"
        ]
    )
    if construction in {"conductor", "core"}:
        cable["conductors"] = [Authoring.array(cable["conductors"])[0]]
    Authoring.object(
        Authoring.object(Authoring.object(reference_model["types"])["type.cable"])[
            "cable"
        ]
    )["construction"] = construction
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    IfcExporter().export(
        ModelResolver(reference_model).resolve(), tmp_path / "stock.ifc"
    )
    product = ifcopenshell.open(tmp_path / "stock.ifc").by_guid(
        IfcExporter.stable_guid("route.cable")
    )
    assert ifcopenshell.util.element.get_predefined_type(product) == predefined


def test_declared_load_cannot_bypass_its_protective_device(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """An extra physical cable around a series breaker invalidates the declared protection path."""
    CircuitFixture.configure(reference_model)
    types, elements = Authoring.object(reference_model["types"]), Authoring.object(
        reference_model["elements"]
    )
    for owner, height in (("panel", 25), ("load", 10)):
        definition = Authoring.object(types[f"type.{owner}"])
        ports = Authoring.object(definition["ports"])
        ports["bypass"] = {
            **CircuitFixture.port(height, 1),
            "position": [30, 0, height],
            "direction": [1, 0, 0],
            "flow": "bidirectional",
        }
        definition["portGroups"] = [list(ports)]
    elements["route.bypass"] = {
        "kind": "serviceRoute",
        "name": "Unprotected bypass",
        "type": "type.cable",
        "chordTolerance": 0.1,
        "bendRadius": 30,
        "path": [
            {"port": {"element": "device.panel", "port": "bypass"}},
            {"point": [200, 0, 25]},
            {"point": [200, 0, 590]},
            {"port": {"element": "device.load", "port": "bypass"}},
        ],
    }
    for group in ("system.test", "circuit.test"):
        Authoring.array(Authoring.object(elements[group])["members"]).extend(
            [
                {"element": "device.panel", "port": "bypass"},
                {"element": "device.load", "port": "bypass"},
                {"element": "route.bypass", "port": "start"},
                {"element": "route.bypass", "port": "end"},
            ]
        )
    relations = Authoring.object(reference_model["relationships"])
    for owner, endpoint in (("panel", "start"), ("load", "end")):
        relations[f"connection.bypass.{owner}"] = {
            "kind": "connectsPorts",
            "a": {"element": f"device.{owner}", "port": "bypass"},
            "b": {"element": "route.bypass", "port": endpoint},
        }
    report = validator.validate(reference_model)
    assert not report.is_valid and "bypasses its overcurrent protection" in str(
        report.to_dict()
    )
