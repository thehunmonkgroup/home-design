"""Mechanical equipment interfaces, separate heat-recovery passages and native IFC identities."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.construction import Authoring
from home_design.json_types import JsonObject, JsonValue
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class MechanicalFixture:
    """Author fabricated housings with physical passages and independent service groups."""

    @staticmethod
    def port(medium: str, x: float = 0, end: bool = False) -> JsonObject:
        """Describe an outward interface on one end of an illustrative passage."""
        return {
            "position": [x, 0, 100 if end else 0],
            "direction": [0, 0, 1 if end else -1],
            "section": {"kind": "rectangle", "width": 40, "height": 40},
            "medium": medium,
            "connectionType": "illustrativeFace",
            "flow": "bidirectional",
        }

    @staticmethod
    def networks(model: JsonObject, definition: JsonObject) -> None:
        """Assign separate connected systems to authored internal passages and singleton interfaces."""
        ports = Authoring.object(definition["ports"])
        groups = [
            Authoring.array(value)
            for value in Authoring.array(definition.get("portGroups", []))
        ]
        assigned = {Authoring.text(key) for group in groups for key in group}
        groups.extend([[key] for key in ports if key not in assigned])
        elements = Authoring.object(model["elements"])
        source = Authoring.object(elements["device.test"])
        source["portStates"] = {key: "open" for key in ports}
        for index, group in enumerate(groups):
            medium = Authoring.object(ports[Authoring.text(group[0])])["medium"]
            elements[f"system.{index}"] = {
                "kind": "serviceSystem",
                "name": f"Independent passage {index}",
                "systemType": "supplyAir" if medium == "air" else medium,
                "members": [{"element": "device.test", "port": key} for key in group],
            }

    @classmethod
    def configure(cls, model: JsonObject, role: str) -> JsonObject:
        """Use two disjoint air passages for heat recovery and one passage for other equipment."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        channels = 2 if role == "heatRecoveryVentilator" else 1
        medium = "refrigerant" if role == "refrigerantUnit" else "air"
        ports: JsonObject = {}
        cuts: JsonObject = {}
        groups: list[JsonValue] = []
        for channel in range(channels):
            x = -60 if channel == 0 else 60
            keys = [f"channel{channel}.start", f"channel{channel}.end"]
            if role == "airTerminal":
                keys = keys[:1]
            for index, key in enumerate(keys):
                ports[key] = cls.port(medium, x, index == 1)
            if len(keys) > 1:
                groups.append(list(keys))
            cuts[f"passage{channel}"] = {
                "section": {"kind": "rectangle", "width": 40, "depth": 40},
                "depth": 100,
                "placement": {"origin": [x, 0, 0]},
            }
        definition: JsonObject = {
            "kind": "serviceDeviceType",
            "name": "Illustrative mechanical housing",
            "role": role,
            "material": "material.timber",
            "solids": {
                "body": {
                    "section": {"kind": "rectangle", "width": 200, "depth": 100},
                    "depth": 100,
                }
            },
            "cuts": cuts,
            "ports": ports,
            "portGroups": groups,
            "mechanical": {
                "designation": "Illustrative equipment",
                "airflowRateM3s": 0.1,
            },
        }
        Authoring.object(model["types"])["type.mechanical"] = definition
        model["elements"] = {
            "device.test": {
                "kind": "serviceDevice",
                "name": "Mechanical equipment",
                "type": "type.mechanical",
                "placement": {
                    "origin": {"point": [300, 400, 500]},
                    "rotation": [0, 0, 90],
                },
            }
        }
        cls.networks(model, definition)
        return definition


@pytest.mark.parametrize(
    "role,native,predefined",
    [
        ("damper", "IfcDamper", "damper"),
        ("airTerminal", "IfcAirTerminal", "airTerminal"),
        ("fan", "IfcFan", "fan"),
        ("airHandler", "IfcUnitaryEquipment", "AIRHANDLER"),
        ("heatRecoveryVentilator", "IfcAirToAirHeatRecovery", "heatRecoveryVentilator"),
        ("airFilter", "IfcFilter", "AIRPARTICLEFILTER"),
        ("coil", "IfcCoil", "coil"),
        ("airConditioner", "IfcUnitaryEquipment", "AIRCONDITIONINGUNIT"),
        ("dehumidifier", "IfcUnitaryEquipment", "DEHUMIDIFIER"),
        ("refrigerantUnit", "IfcUnitaryEquipment", "SPLITSYSTEM"),
    ],
)
def test_mechanical_roles_preserve_geometry_interfaces_and_native_types(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    role: str,
    native: str,
    predefined: str,
) -> None:
    """Typed products retain fabricated passages, actual stock volume and separate service systems."""
    definition = MechanicalFixture.configure(reference_model, role)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    device = result.element("device.test")
    channels = 2 if role == "heatRecoveryVentilator" else 1
    assert SolidOperations.volume(device.meshes[0]) == pytest.approx(
        (200 * 100 - channels * 40 * 40) * 100
    )
    assert device.data["mechanical"] == definition["mechanical"]
    output = tmp_path / "equipment.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("device.test"))
    assert product.is_a(native) and product.IsTypedBy[0].RelatingType.is_a(
        native + "Type"
    )
    assert ifcopenshell.util.element.get_predefined_type(product) == predefined
    assert len(ifc.by_type("IfcDistributionPort")) == len(
        Authoring.object(definition["ports"])
    )
    assert (
        ifcopenshell.util.element.get_pset(product, "Pset_HomeDesignMechanical")[
            "airflowRateM3s"
        ]
        == 0.1
    )
    if role in {"fan", "damper"}:
        for stock in (product, product.IsTypedBy[0].RelatingType):
            assert (
                ifcopenshell.util.element.get_pset(
                    stock,
                    f"Pset_{native[3:]}TypeCommon",
                    "NominalAirFlowRate",
                    should_inherit=False,
                )
                == 0.1
            )
    manifest = GltfExporter().export(
        result, tmp_path / "equipment.glb", tmp_path / "manifest.json"
    )
    assert Authoring.object(Authoring.object(manifest["elements"])["device.test"])[
        "nodes"
    ]


@pytest.mark.parametrize(
    "role,field,value,native",
    [
        ("damper", "damperType", "fireSmoke", "FIRESMOKEDAMPER"),
        ("airTerminal", "terminalType", "register", "REGISTER"),
        ("airTerminal", "terminalType", "grille", "GRILLE"),
        ("airTerminal", "terminalType", "diffuser", "DIFFUSER"),
        ("fan", "fanType", "propellerAxial", "PROPELLORAXIAL"),
        (
            "heatRecoveryVentilator",
            "heatRecoveryType",
            "counterflowPlate",
            "FIXEDPLATECOUNTERFLOWEXCHANGER",
        ),
    ],
)
def test_authored_mechanical_technology_selects_native_classification(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    role: str,
    field: str,
    value: str,
    native: str,
) -> None:
    """Declared equipment technology survives type assignment without a generic fallback."""
    definition = MechanicalFixture.configure(reference_model, role)
    Authoring.object(definition["mechanical"])[field] = value
    assert validator.validate(reference_model).is_valid
    output = tmp_path / "subtype.ifc"
    IfcExporter().export(ModelResolver(reference_model).resolve(), output)
    product = ifcopenshell.open(output).by_guid(IfcExporter.stable_guid("device.test"))
    assert ifcopenshell.util.element.get_predefined_type(product) == native


def test_powered_air_handler_preserves_independent_refrigerant_drain_and_control_interfaces(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
) -> None:
    """One equipment body belongs to independent air, refrigerant, condensate, power and signal systems."""
    definition = MechanicalFixture.configure(reference_model, "airHandler")
    ports = Authoring.object(definition["ports"])
    for key, medium in (
        ("refrigerant.in", "refrigerant"),
        ("refrigerant.out", "refrigerant"),
        ("drain", "condensate"),
        ("power", "electrical"),
        ("signal", "communications"),
    ):
        ports[key] = MechanicalFixture.port(medium)
    Authoring.object(ports["power"])["function"] = "power"
    Authoring.object(ports["signal"])["function"] = "signal"
    definition["electrical"] = {"ratedVoltageV": 230, "supply": "AC", "frequencyHz": 60}
    Authoring.array(definition["portGroups"]).append(
        ["refrigerant.in", "refrigerant.out"]
    )
    MechanicalFixture.networks(reference_model, definition)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    resolved_ports = Authoring.object(result.element("device.test").data["ports"])
    assert (
        len(
            {
                Authoring.text(Authoring.object(port)["systemId"])
                for port in resolved_ports.values()
            }
        )
        == 5
    )
    output = tmp_path / "multi-interface.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert len(ifc.by_type("IfcDistributionSystem")) == 5
    assert {port.PredefinedType for port in ifc.by_type("IfcDistributionPort")} == {
        "DUCT",
        "PIPE",
        "CABLE",
    }


@pytest.mark.parametrize(
    "technology,medium,count,native",
    [
        ("dxCooling", "refrigerant", 2, "DXCOOLINGCOIL"),
        ("hydronic", "water", 2, "HYDRONICCOIL"),
        ("waterCooling", "water", 2, "WATERCOOLINGCOIL"),
        ("waterHeating", "water", 2, "WATERHEATINGCOIL"),
        ("gasHeating", "gas", 1, "GASHEATINGCOIL"),
        ("electricHeating", "electrical", 1, "ELECTRICHEATINGCOIL"),
    ],
)
def test_coil_technology_requires_matching_external_interfaces(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    technology: str,
    medium: str,
    count: int,
    native: str,
) -> None:
    """Each authored coil technology retains its separate air and energy interfaces in IFC."""
    definition = MechanicalFixture.configure(reference_model, "coil")
    Authoring.object(definition["mechanical"])["coilType"] = technology
    ports = Authoring.object(definition["ports"])
    keys = [f"energy{index}" for index in range(count)]
    for index, key in enumerate(keys):
        ports[key] = MechanicalFixture.port(medium, 60, index == 1)
    if count > 1:
        Authoring.array(definition["portGroups"]).append(list(keys))
    if medium == "electrical":
        Authoring.object(ports[keys[0]])["function"] = "power"
        definition["electrical"] = {"ratedVoltageV": 230}
    MechanicalFixture.networks(reference_model, definition)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    output = tmp_path / "coil.ifc"
    IfcExporter().export(ModelResolver(reference_model).resolve(), output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_type("IfcCoil")[0]
    assert ifcopenshell.util.element.get_predefined_type(product) == native
    assert len(ifc.by_type("IfcDistributionSystem")) == 2


@pytest.mark.parametrize(
    "invalid",
    [
        "missingSpecification",
        "airPorts",
        "wrongMedium",
        "powerRating",
        "powerFunction",
        "frequency",
        "wrongSubtype",
        "efficiency",
        "coilFluid",
        "refrigerantPorts",
        "hrvMissing",
        "hrvMerged",
        "hrvOverlap",
    ],
)
def test_invalid_mechanical_roles_and_passages_are_rejected(
    reference_model: JsonObject,
    validator: ModelValidator,
    invalid: str,
) -> None:
    """Invalid role metadata and mixed or incomplete heat-recovery streams cannot resolve."""
    role = (
        "heatRecoveryVentilator"
        if invalid.startswith("hrv")
        else (
            "coil"
            if invalid == "coilFluid"
            else "refrigerantUnit" if invalid == "refrigerantPorts" else "fan"
        )
    )
    definition = MechanicalFixture.configure(reference_model, role)
    ports = Authoring.object(definition["ports"])
    specification = Authoring.object(definition["mechanical"])
    if invalid == "missingSpecification":
        del definition["mechanical"]
    elif invalid in {"airPorts", "refrigerantPorts"}:
        del ports["channel0.end"]
    elif invalid == "wrongMedium":
        Authoring.object(ports["channel0.start"])["medium"] = "waste"
    elif invalid in {"powerRating", "powerFunction", "frequency"}:
        ports["power"] = MechanicalFixture.port("electrical")
        if invalid != "powerFunction":
            Authoring.object(ports["power"])["function"] = "power"
        if invalid != "powerRating":
            definition["electrical"] = {
                "ratedVoltageV": 230,
                "supply": "DC",
                "frequencyHz": 60 if invalid == "frequency" else 0,
            }
    elif invalid == "wrongSubtype":
        specification["terminalType"] = "grille"
    elif invalid == "efficiency":
        specification["heatRecoveryEfficiency"] = 1.1
    elif invalid == "coilFluid":
        specification["coilType"] = "hydronic"
    elif invalid == "hrvMissing":
        definition["portGroups"] = []
    elif invalid == "hrvMerged":
        definition["portGroups"] = [list(ports)]
    else:
        Authoring.array(Authoring.array(definition["portGroups"])[1]).append(
            "channel0.start"
        )
    report = validator.validate(reference_model)
    assert not report.is_valid
