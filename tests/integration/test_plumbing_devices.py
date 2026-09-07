"""Plumbing equipment roles, explicit interfaces, specifications and native IFC exports."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.service_ports import ServicePorts
from home_design.validation import ModelValidator


class PlumbingFixture:
    """Author illustrative equipment stock independently of real product dimensions."""

    @staticmethod
    def configure(model: JsonObject, role: str, count: int = 2) -> JsonObject:
        """Place a device with an explicit internal water passage and open external ends."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        ports: JsonObject = {
            f"water{index}": {
                "position": [index * 20, 0, 50],
                "direction": [0, 0, 1],
                "section": {"kind": "circle", "diameter": 10},
                "medium": "water",
                "flow": "bidirectional",
                "connectionType": "illustrativeFace",
            }
            for index in range(count)
        }
        definition: JsonObject = {
            "kind": "serviceDeviceType",
            "name": "Illustrative plumbing part",
            "role": role,
            "material": "material.timber",
            "solids": {
                "body": {
                    "section": {"kind": "rectangle", "width": 100, "depth": 80},
                    "depth": 50,
                }
            },
            "plumbing": {
                "designation": "Illustrative equipment",
                "pressureRatingPa": 1000000,
                "minimumTemperatureC": 0,
                "maximumTemperatureC": 90,
                "potableWater": True,
            },
            "ports": ports,
            "portGroups": [list(ports)] if count > 1 else [],
        }
        Authoring.object(model["types"])["type.plumbing"] = definition
        model["elements"] = {
            "device.test": {
                "kind": "serviceDevice",
                "name": "Plumbing part",
                "type": "type.plumbing",
                "placement": {"origin": {"point": [0, 0, 0]}},
                "portStates": {key: "open" for key in ports},
            },
            "system.test": {
                "kind": "serviceSystem",
                "name": "Water system",
                "systemType": "water",
                "members": [{"element": "device.test", "port": key} for key in ports],
            },
        }
        return definition


@pytest.mark.parametrize(
    "role,count,native,predefined",
    [
        ("valve", 2, "IfcValve", "valve"),
        ("manifold", 3, "IfcPipeFitting", "JUNCTION"),
        ("fixtureConnection", 1, "IfcPipeFitting", "CONNECTOR"),
        ("cleanout", 1, "IfcPipeFitting", "cleanout"),
        ("waterHeater", 2, "IfcBoiler", "WATER"),
        ("plumbingPump", 2, "IfcPump", "plumbingPump"),
        ("storageTank", 1, "IfcTank", "STORAGE"),
        ("waterMeter", 2, "IfcFlowMeter", "WATERMETER"),
    ],
)
def test_plumbing_roles_preserve_native_types_ports_geometry_and_specifications(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    role: str,
    count: int,
    native: str,
    predefined: str,
) -> None:
    """Physical material, native identity and specifications survive both export adapters."""
    definition = PlumbingFixture.configure(reference_model, role, count)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    device = result.element("device.test")
    assert device.data["plumbing"] == definition["plumbing"]
    assert device.data["netVolumeMm3"] == pytest.approx(100 * 80 * 50)
    output = tmp_path / "plumbing.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("device.test"))
    assert product.is_a(native)
    assert product.IsTypedBy[0].RelatingType.is_a(native + "Type")
    assert ifcopenshell.util.element.get_predefined_type(product) == predefined
    for target in (product, product.IsTypedBy[0].RelatingType):
        pset = ifcopenshell.util.element.get_pset(target, "Pset_HomeDesignPlumbing")
        assert pset["pressureRatingPa"] == 1000000
        assert pset["designation"] == "Illustrative equipment"
    ports = ifc.by_type("IfcDistributionPort")
    assert len(ports) == count
    assert all(port.PredefinedType == "PIPE" for port in ports)
    manifest = GltfExporter().export(
        result, tmp_path / "plumbing.glb", tmp_path / "manifest.json"
    )
    entry = Authoring.object(Authoring.object(manifest["elements"])["device.test"])
    assert (
        entry["nodes"]
        and Authoring.object(entry["data"])["plumbing"] == definition["plumbing"]
    )
    schedules = ModelReports(result).schedules()
    row = Authoring.object(Authoring.array(schedules["serviceDevices"])[0])
    assert (
        Authoring.object(row["dimensionsAndSpecifications"])["plumbing"]
        == definition["plumbing"]
    )


@pytest.mark.parametrize(
    "valve_type,predefined",
    [
        ("isolating", "ISOLATING"),
        ("check", "CHECK"),
        ("mixing", "MIXING"),
        ("pressureReducing", "PRESSUREREDUCING"),
        ("pressureRelief", "PRESSURERELIEF"),
        ("regulating", "REGULATING"),
        ("gasCock", "GASCOCK"),
        ("faucet", "FAUCET"),
    ],
)
def test_authored_valve_function_selects_native_classification(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    valve_type: str,
    predefined: str,
) -> None:
    """Valve function is explicit and independent of its fabricated shape."""
    definition = PlumbingFixture.configure(
        reference_model, "valve", 3 if valve_type == "mixing" else 2
    )
    Authoring.object(definition["plumbing"])["valveType"] = valve_type
    assert validator.validate(reference_model).is_valid
    output = tmp_path / "valve.ifc"
    IfcExporter().export(ModelResolver(reference_model).resolve(), output)
    ifc = ifcopenshell.open(output)
    product = ifc.by_guid(IfcExporter.stable_guid("device.test"))
    assert ifcopenshell.util.element.get_predefined_type(product) == predefined


def test_water_heater_retains_separate_water_gas_and_power_interfaces(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
) -> None:
    """Equipment bridges system interfaces without directly connecting different media."""
    definition = PlumbingFixture.configure(reference_model, "waterHeater")
    definition["portGroups"] = []
    ports = Authoring.object(definition["ports"])
    ports["gas"] = {
        **Authoring.object(ports["water0"]),
        "medium": "gas",
        "position": [-20, 0, 50],
    }
    ports["power"] = {
        **Authoring.object(ports["water0"]),
        "medium": "electrical",
        "function": "power",
        "position": [-40, 0, 50],
    }
    definition["electrical"] = {"ratedVoltageV": 120, "supply": "AC", "frequencyHz": 60}
    elements = Authoring.object(reference_model["elements"])
    del elements["system.test"]
    Authoring.object(elements["device.test"])["portStates"] = {
        key: "open" for key in ports
    }
    systems = {
        "water0": "coldWater",
        "water1": "hotWater",
        "gas": "gas",
        "power": "electrical",
    }
    for port, system in systems.items():
        elements[f"system.{port}"] = {
            "kind": "serviceSystem",
            "name": system,
            "systemType": system,
            "members": [{"element": "device.test", "port": port}],
        }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    resolved_ports = Authoring.object(result.element("device.test").data["ports"])
    assert {
        key: Authoring.object(port)["systemId"] for key, port in resolved_ports.items()
    } == {key: f"system.{key}" for key in systems}
    output = tmp_path / "heater.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert {port.SystemType for port in ifc.by_type("IfcDistributionPort")} == {
        "DOMESTICCOLDWATER",
        "DOMESTICHOTWATER",
        "GAS",
        "ELECTRICAL",
    }
    definition["portGroups"] = [["gas", "water0"]]
    invalid = validator.validate(reference_model)
    assert not invalid.is_valid and "incompatible media" in str(invalid.to_dict())


@pytest.mark.parametrize(
    "invalid",
    [
        "missingSpecification",
        "unknownSpecification",
        "temperatureRange",
        "missingFluid",
        "manifoldPorts",
        "mixingPorts",
        "wrongValveRole",
        "wrongHeaterMedium",
        "airPort",
        "powerRatings",
        "powerFunction",
        "frequency",
    ],
)
def test_invalid_plumbing_specifications_and_interfaces_are_rejected(
    reference_model: JsonObject,
    validator: ModelValidator,
    invalid: str,
) -> None:
    """Invalid authoring fails before a plausible physical body can conceal bad interfaces."""
    definition = PlumbingFixture.configure(reference_model, "valve")
    specification = Authoring.object(definition["plumbing"])
    ports = Authoring.object(definition["ports"])
    if invalid == "missingSpecification":
        del definition["plumbing"]
    elif invalid == "unknownSpecification":
        specification["unknown"] = 10
    elif invalid == "temperatureRange":
        specification["minimumTemperatureC"] = 100
    elif invalid == "manifoldPorts":
        definition["role"] = "manifold"
    elif invalid == "mixingPorts":
        specification["valveType"] = "mixing"
    elif invalid == "wrongValveRole":
        definition["role"] = "waterMeter"
        specification["valveType"] = "check"
    elif invalid == "wrongHeaterMedium":
        definition["role"] = "waterHeater"
        for port in ports.values():
            Authoring.object(port)["medium"] = "gas"
    else:
        definition["role"] = "fixtureConnection"
        port = Authoring.object(ports["water0"])
        port["medium"] = "air" if invalid == "airPort" else "electrical"
        if invalid != "powerFunction":
            port["function"] = "power"
        if invalid != "powerRatings":
            definition["electrical"] = {
                "supply": "DC",
                "frequencyHz": 60 if invalid == "frequency" else 0,
            }
        if invalid == "missingFluid":
            Authoring.object(ports["water1"]).update(port)
    report = validator.validate(reference_model)
    assert not report.is_valid
    messages = {
        "temperatureRange": "minimum temperature exceeds",
        "missingFluid": "requires at least 1 fluid",
        "manifoldPorts": "requires at least 3 fluid",
        "mixingPorts": "mixing valve requires at least three",
        "wrongValveRole": "valveType requires the valve role",
        "wrongHeaterMedium": "requires two water interfaces",
        "airPort": "purposeful electrical/communications interfaces",
        "powerRatings": "requires electrical ratings",
        "powerFunction": "purposeful electrical/communications interfaces",
        "frequency": "frequency requires matching",
    }
    if invalid in messages:
        assert messages[invalid] in str(report.to_dict())


def test_mixing_valve_routes_follow_equipment_edits_and_keep_system_boundaries(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
) -> None:
    """Three physical connected branches follow one equipment move without merging their systems."""
    definition = PlumbingFixture.configure(reference_model, "valve", 3)
    Authoring.object(definition["plumbing"])["valveType"] = "mixing"
    elements = Authoring.object(reference_model["elements"])
    del elements["system.test"]
    device = Authoring.object(elements["device.test"])
    device["portStates"] = {}
    device["placement"] = {"origin": {"anchor": "anchor.valve"}}
    Authoring.object(reference_model["anchors"])["anchor.valve"] = {
        "kind": "point3",
        "name": "Valve mounting origin",
        "position": [0, 0, 0],
    }
    Authoring.object(reference_model["types"])["type.pipe"] = {
        "kind": "serviceRouteType",
        "name": "Illustrative branch pipe",
        "family": "pipe",
        "material": "material.timber",
        "section": {"kind": "circle", "diameter": 10},
        "wallThickness": 1,
        "medium": "water",
        "connectionType": "illustrativeFace",
        "flow": "bidirectional",
        "pipe": {"designation": "Branch stock"},
    }
    for index, system in enumerate(("coldWater", "hotWater", "water")):
        port, route = f"water{index}", f"route.{index}"
        elements[route] = {
            "kind": "serviceRoute",
            "name": f"Branch {index}",
            "type": "type.pipe",
            "path": [
                {"port": {"element": "device.test", "port": port}},
                {
                    "host": {
                        "kind": "component",
                        "element": "device.test",
                        "offset": [index * 20, 0, 250],
                    }
                },
            ],
            "chordTolerance": 0.1,
            "portStates": {"end": "open"},
        }
        elements[f"system.{index}"] = {
            "kind": "serviceSystem",
            "name": system,
            "systemType": system,
            "members": [
                {"element": "device.test", "port": port},
                {"element": route, "port": "start"},
                {"element": route, "port": "end"},
            ],
        }
        Authoring.object(reference_model["relationships"])[f"connection.{index}"] = {
            "kind": "connectsPorts",
            "a": {"element": "device.test", "port": port},
            "b": {"element": route, "port": "start"},
        }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.valve",
            "description": "Move connected equipment",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "moveAnchor",
                    "anchorId": "anchor.valve",
                    "position": [300, 400, 500],
                }
            ],
        },
    )
    before, after = (
        ModelResolver(reference_model).resolve(),
        ModelResolver(changed).resolve(),
    )
    for index in range(3):
        first, second = before.element(f"route.{index}"), after.element(
            f"route.{index}"
        )
        assert (
            first.data["centerlineLengthMm"] == second.data["centerlineLengthMm"] == 200
        )
        assert first.data["netVolumeMm3"] == pytest.approx(second.data["netVolumeMm3"])
        for key in ("start", "end"):
            old = Authoring.object(Authoring.object(first.data["ports"])[key])
            new = Authoring.object(Authoring.object(second.data["ports"])[key])
            assert old["systemId"] == new["systemId"] == f"system.{index}"
            assert ServicePorts.frame(new).origin == pytest.approx(
                tuple(
                    value + delta
                    for value, delta in zip(
                        ServicePorts.frame(old).origin, (300, 400, 500)
                    )
                )
            )
    output = tmp_path / "mixing.ifc"
    IfcExporter().export(after, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert len(ifc.by_type("IfcRelConnectsPorts")) == 3
    assert len(ifc.by_type("IfcPipeSegment")) == 3
    assert len(ifc.by_type("IfcDistributionSystem")) == 3
    assert (
        ifcopenshell.util.element.get_predefined_type(ifc.by_type("IfcValve")[0])
        == "MIXING"
    )
