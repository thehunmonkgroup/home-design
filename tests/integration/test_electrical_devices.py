"""Electrical product intent, rated measures, purpose-aware ports and concrete IFC4 exports."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class ElectricalFixture:
    """Use illustrative fabricated stock and authored ratings, independently of product sizing."""

    @staticmethod
    def configure(model: JsonObject, role: str) -> JsonObject:
        """Place one open-ended device with a matching service system."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        function = (
            "signal"
            if role.startswith("communications")
            else (
                "protectiveEarth"
                if role in {"groundingBar", "groundingElectrode", "bondingClamp"}
                else "containment" if role in {"deviceBox", "junctionBox"} else "power"
            )
        )
        medium = "communications" if function == "signal" else "electrical"
        definition: JsonObject = {
            "kind": "serviceDeviceType",
            "name": "Illustrative electrical part",
            "role": role,
            "material": "material.timber",
            "solids": {
                "body": {
                    "section": {"kind": "rectangle", "width": 60, "depth": 40},
                    "depth": 50,
                }
            },
            "electrical": {
                "ratedVoltageV": 120,
                "ratedCurrentA": 20,
                "supply": "AC",
                "frequencyHz": 60,
                "poles": 1,
            },
            "ports": {
                "interface": {
                    "position": [0, 0, 50],
                    "direction": [0, 0, 1],
                    "section": {"kind": "circle", "diameter": 10},
                    "medium": medium,
                    "function": function,
                    "flow": "bidirectional",
                    "connectionType": "illustrativeFace",
                }
            },
        }
        Authoring.object(model["types"])["type.electrical"] = definition
        model["elements"] = {
            "device.test": {
                "kind": "serviceDevice",
                "name": "Electrical part",
                "type": "type.electrical",
                "placement": {"origin": {"point": [0, 0, 0]}},
                "portStates": {"interface": "open"},
            },
            "system.test": {
                "kind": "serviceSystem",
                "name": "Electrical system",
                "systemType": medium,
                "members": [{"element": "device.test", "port": "interface"}],
            },
        }
        return definition


@pytest.mark.parametrize(
    "role,native,predefined",
    [
        ("receptacle", "IfcOutlet", "POWEROUTLET"),
        ("switch", "IfcSwitchingDevice", "switch"),
        ("deviceBox", "IfcJunctionBox", "deviceBox"),
        ("junctionBox", "IfcJunctionBox", "junctionBox"),
        ("distributionPanel", "IfcElectricDistributionBoard", "DISTRIBUTIONBOARD"),
        ("circuitBreaker", "IfcProtectiveDevice", "CIRCUITBREAKER"),
        ("fuse", "IfcProtectiveDevice", "fuse"),
        ("surgeProtector", "IfcProtectiveDevice", "surgeProtector"),
        ("light", "IfcLightFixture", "light"),
        ("smokeDetector", "IfcSensor", "SMOKESENSOR"),
        ("heatDetector", "IfcSensor", "HEATSENSOR"),
        ("carbonMonoxideDetector", "IfcSensor", "COSENSOR"),
        ("communicationsOutlet", "IfcOutlet", "COMMUNICATIONSOUTLET"),
        ("communicationsPanel", "IfcCommunicationsAppliance", "communicationsPanel"),
        ("groundingBar", "IfcCableFitting", "JUNCTION"),
        ("groundingElectrode", "IfcCableFitting", "EXIT"),
        ("bondingClamp", "IfcCableFitting", "EXIT"),
    ],
)
def test_electrical_roles_export_native_devices_ratings_and_selectable_geometry(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    role: str,
    native: str,
    predefined: str,
) -> None:
    """Each product retains rated measures, its physical material, nested ports and native type."""
    definition = ElectricalFixture.configure(reference_model, role)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    device = result.element("device.test")
    assert device.data["electrical"] == definition["electrical"]
    assert device.data["netVolumeMm3"] == pytest.approx(60 * 40 * 50)
    output = tmp_path / "electrical.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("device.test"))
    assert product.is_a(native)
    assert product.IsTypedBy[0].RelatingType.is_a(native + "Type")
    assert ifcopenshell.util.element.get_predefined_type(product) == predefined
    pset = ifcopenshell.util.element.get_pset(product, "Pset_ElectricalDeviceCommon")
    assert pset["RatedVoltage"] == 120 and pset["RatedCurrent"] == 20
    assert pset["NumberOfPoles"] == 1
    rated = ifc.by_id(pset["id"])
    assert rated is not None
    assert {p.Name: p.NominalValue.is_a() for p in rated.HasProperties} == {
        "RatedVoltage": "IfcElectricVoltageMeasure",
        "RatedCurrent": "IfcElectricCurrentMeasure",
        "NumberOfPoles": "IfcInteger",
    }
    units = {
        unit.UnitType: unit.Name
        for unit in ifc.by_type("IfcProject")[0].UnitsInContext.Units
        if unit.is_a("IfcSIUnit")
    }
    assert (
        units["ELECTRICCURRENTUNIT"] == "AMPERE"
        and units["ELECTRICVOLTAGEUNIT"] == "VOLT"
    )
    assert len(ifc.by_type("IfcDistributionPort")) == 1
    manifest = GltfExporter().export(
        result, tmp_path / "electrical.glb", tmp_path / "manifest.json"
    )
    entry = Authoring.object(Authoring.object(manifest["elements"])["device.test"])
    assert entry["nodes"] and Authoring.object(entry["data"])["role"] == role
    schedules = ModelReports(result).schedules()
    row = Authoring.object(Authoring.array(schedules["serviceDevices"])[0])
    assert (
        Authoring.object(row["dimensionsAndSpecifications"])["electrical"]
        == definition["electrical"]
    )


@pytest.mark.parametrize(
    "invalid",
    [
        "missingFunction",
        "waterPort",
        "signalPower",
        "dcFrequency",
        "acZero",
        "untypedFrequency",
        "groundPower",
        "missingSignal",
        "negativeRating",
        "unrecognizedRating",
        "genericRatings",
    ],
)
def test_invalid_electrical_device_specs_fail_before_export(
    reference_model: JsonObject,
    validator: ModelValidator,
    invalid: str,
) -> None:
    """Physical connection size cannot disguise incompatible function or malformed rated data."""
    definition = ElectricalFixture.configure(reference_model, "receptacle")
    port = Authoring.object(Authoring.object(definition["ports"])["interface"])
    ratings = Authoring.object(definition["electrical"])
    if invalid == "missingFunction":
        del port["function"]
    elif invalid == "waterPort":
        port["medium"] = "water"
    elif invalid == "signalPower":
        port["function"] = "signal"
    elif invalid == "dcFrequency":
        ratings["supply"] = "DC"
    elif invalid == "acZero":
        ratings["frequencyHz"] = 0
    elif invalid == "untypedFrequency":
        del ratings["supply"]
    elif invalid == "groundPower":
        definition["role"] = "groundingBar"
    elif invalid == "missingSignal":
        definition["role"] = "communicationsOutlet"
    elif invalid == "negativeRating":
        ratings["ratedCurrentA"] = -1
    elif invalid == "unrecognizedRating":
        ratings["ratedCurrent"] = 20
    else:
        definition["role"] = "equipment"
    assert not validator.validate(reference_model).is_valid


@pytest.mark.parametrize(
    "family,function", [("cable", "power"), ("conduit", "containment")]
)
def test_port_functions_follow_device_route_and_fitting_connections(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    family: str,
    function: str,
) -> None:
    """A connected physical run carries its interface purpose through generated ports and native IFC."""
    ElectricalFixture.configure(
        reference_model, "receptacle" if family == "cable" else "deviceBox"
    )
    types, elements = Authoring.object(reference_model["types"]), Authoring.object(
        reference_model["elements"]
    )
    common: JsonObject = {
        "name": "Illustrative electrical stock",
        "family": family,
        "material": "material.timber",
        "medium": "electrical",
        "function": function,
        "connectionType": "illustrativeFace",
    }
    if family == "conduit":
        common["wallThickness"] = 1
    types["type.route"] = {
        **common,
        "kind": "serviceRouteType",
        "section": {"kind": "circle", "diameter": 10},
    }
    types["type.cap"] = {
        **common,
        "kind": "serviceFittingType",
        "chordTolerance": 0.1,
        "geometry": {
            "kind": "cap",
            "section": {"kind": "circle", "diameter": 10},
            "depth": 20,
        },
    }
    Authoring.object(elements["device.test"])["portStates"] = {}
    elements["route.test"] = {
        "kind": "serviceRoute",
        "name": "Electrical run",
        "type": "type.route",
        "chordTolerance": 0.1,
        "path": [
            {"port": {"element": "device.test", "port": "interface"}},
            {"point": [0, 0, 250]},
        ],
    }
    elements["cap.test"] = {
        "kind": "serviceFitting",
        "name": "Electrical end",
        "type": "type.cap",
        "placement": {"origin": {"port": {"element": "route.test", "port": "end"}}},
    }
    members = Authoring.array(Authoring.object(elements["system.test"])["members"])
    members.extend(
        [
            {"element": "route.test", "port": "start"},
            {"element": "route.test", "port": "end"},
            {"element": "cap.test", "port": "start"},
        ]
    )
    reference_model["relationships"] = {
        "connection.entry": {
            "kind": "connectsPorts",
            "a": {"element": "device.test", "port": "interface"},
            "b": {"element": "route.test", "port": "start"},
        },
        "connection.end": {
            "kind": "connectsPorts",
            "a": {"element": "route.test", "port": "end"},
            "b": {"element": "cap.test", "port": "start"},
        },
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    assert {
        Authoring.text(Authoring.object(port)["function"])
        for e in result.elements
        for port in Authoring.object(e.data.get("ports", {})).values()
    } == {function}
    IfcExporter().export(result, tmp_path / "run.ifc")
    ifc = ifcopenshell.open(tmp_path / "run.ifc")
    assert {port.PredefinedType for port in ifc.by_type("IfcDistributionPort")} == {
        "CABLE" if family == "cable" else "CABLECARRIER"
    }
    assert len(ifc.by_type("IfcRelConnectsPorts")) == 2
    del Authoring.object(types["type.cap"])["function"]
    report = validator.validate(reference_model)
    assert not report.is_valid and "incompatible port function" in str(report.to_dict())
    Authoring.object(types["type.cap"])["function"] = function
    Authoring.object(types["type.route"])["function"] = (
        "containment" if family == "cable" else "power"
    )
    report = validator.validate(reference_model)
    assert (
        not report.is_valid
        and "family" in str(report.to_dict())
        and "incompatible port function" in str(report.to_dict())
    )
