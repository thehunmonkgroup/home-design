"""Fabricated connection hardware, fastener schedules and native IFC connections."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class HardwareFixture:
    """Provide an illustrative fabricated shoe and an authored four-screw connection."""

    @staticmethod
    def configure(model: JsonObject) -> tuple[JsonObject, JsonObject]:
        """Author exact rectangular stock, a through-hole and a separate fastener type."""
        Authoring.object(model["materials"])["material.hardwareSteel"] = {
            "name": "Hardware steel",
            "category": "steel",
            "appearance": {"color": "#87959b"},
        }
        types = Authoring.object(model["types"])
        types["type.connectionStock"] = {
            "kind": "memberType",
            "name": "Connection stock",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 80, "depth": 80},
        }
        types["type.shoe"] = {
            "kind": "hardwareType",
            "name": "Illustrative fabricated shoe",
            "role": "postBase",
            "material": "material.hardwareSteel",
            "solids": {
                "base": {
                    "section": {"kind": "rectangle", "width": 100, "depth": 80},
                    "depth": 4,
                },
                "left": {
                    "section": {"kind": "rectangle", "width": 4, "depth": 80},
                    "depth": 100,
                    "placement": {"origin": [-48, 0, 4]},
                },
                "right": {
                    "section": {"kind": "rectangle", "width": 4, "depth": 80},
                    "depth": 100,
                    "placement": {"origin": [48, 0, 4]},
                },
            },
            "cuts": {
                "boltHole": {
                    "section": {"kind": "rectangle", "width": 10, "depth": 10},
                    "depth": 4,
                }
            },
        }
        types["type.screw"] = {
            "kind": "fastenerType",
            "name": "Illustrative screw",
            "role": "screw",
            "material": "material.hardwareSteel",
            "nominalDiameter": 6,
            "nominalLength": 60,
            "solids": {
                "shank": {"section": {"kind": "circle", "diameter": 6}, "depth": 60},
                "head": {
                    "section": {"kind": "circle", "diameter": 10},
                    "depth": 4,
                    "placement": {"origin": [0, 0, 60]},
                },
            },
        }
        elements = Authoring.object(model["elements"])
        elements["member.support"] = {
            "kind": "member",
            "name": "Support",
            "type": "type.connectionStock",
            "role": "column",
            "axis": [{"point": [0, -4000, 0]}, {"point": [0, -4000, 1000]}],
        }
        elements["member.beam"] = {
            "kind": "member",
            "name": "Beam",
            "type": "type.connectionStock",
            "role": "beam",
            "axis": [{"point": [0, -4000, 1100]}, {"point": [2000, -4000, 1100]}],
        }
        hardware: JsonObject = {
            "kind": "hardware",
            "name": "Post shoe",
            "type": "type.shoe",
            "storey": "level.ground",
            "placement": {
                "origin": {
                    "host": {
                        "kind": "member",
                        "element": "member.support",
                        "surface": "end",
                        "station": 1000,
                    }
                }
            },
            "participants": [{"element": "member.support"}, {"element": "member.beam"}],
        }
        fasteners: JsonObject = {
            "kind": "fastenerGroup",
            "name": "Connection screws",
            "type": "type.screw",
            "storey": "level.ground",
            "placement": hardware["placement"],
            "participants": [
                {"element": "hardware.shoe"},
                {"element": "member.support"},
            ],
            "quantity": 4,
            "representation": "scheduled",
        }
        elements["hardware.shoe"], elements["fasteners.shoe"] = hardware, fasteners
        return hardware, fasteners

    @staticmethod
    def detailed(source: JsonObject) -> None:
        """Position the same four authored fasteners without changing their schedule."""
        source["representation"] = "detailed"
        source["instances"] = {
            f"screw{index}": {"origin": [x, y, 0]}
            for index, (x, y) in enumerate(((-20, -20), (20, -20), (20, 20), (-20, 20)))
        }


def test_fabricated_stock_union_and_hole_have_exact_net_volume(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Connected plates become one nonduplicated solid with the authored bolt hole."""
    HardwareFixture.configure(reference_model)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    hardware = resolved.element("hardware.shoe")
    assert len(hardware.meshes) == 1
    assert SolidOperations.volume(hardware.meshes[0]) == pytest.approx(
        100 * 80 * 4 + 2 * 4 * 80 * 100 - 10 * 10 * 4
    )
    assert hardware.data["participantIds"] == ["member.support", "member.beam"]
    assert hardware.data["discipline"] == "framing"
    assert resolved.to_dict() == ModelResolver(reference_model).resolve().to_dict()
    support = Authoring.object(
        Authoring.object(reference_model["elements"])["member.support"]
    )
    support["axis"] = [{"point": [0, -4000, 200]}, {"point": [0, -4000, 1200]}]
    moved = ModelResolver(reference_model).resolve().element("hardware.shoe")
    assert min(point[2] for point in moved.meshes[0].vertices) - min(
        point[2] for point in hardware.meshes[0].vertices
    ) == pytest.approx(200)


def test_custom_hardware_roles_keep_valid_ifc_type_classifications(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """Anchors and embeds retain their authored meaning without being mislabeled as plates."""
    HardwareFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    roles = {
        "hanger": "USERDEFINED",
        "strap": "USERDEFINED",
        "holdDown": "USERDEFINED",
        "postBase": "SHOE",
        "postCap": "SHOE",
        "bracket": "BRACKET",
        "anchor": "USERDEFINED",
        "anchorPlate": "ANCHORPLATE",
        "embed": "USERDEFINED",
    }
    for role in roles:
        definition = deepcopy(Authoring.object(types["type.shoe"]))
        definition["role"] = role
        types[f"type.hardware.{role}"] = definition
    source = tmp_path / "hardware-types.json"
    ModelLoader.write(reference_model, source)
    ifc = ifcopenshell.open(BuildService().build(source, tmp_path / "build").ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    definitions = {
        value.Tag: value for value in ifc.by_type("IfcDiscreteAccessoryType")
    }
    for role, expected in roles.items():
        assert definitions[f"type.hardware.{role}"].PredefinedType == expected
        assert definitions[f"type.hardware.{role}"].ElementType == role


def test_scheduled_and_detailed_fasteners_have_equal_material_quantities(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Rendering individual instances neither adds nor loses the authored fastener volume."""
    _, fasteners = HardwareFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve()
    scheduled = before.element("fasteners.shoe")
    assert not scheduled.meshes
    assert scheduled.data["scheduledVolumeMm3"] == pytest.approx(
        4 * number(scheduled.data["unitVolumeMm3"], "unit volume")
    )
    HardwareFixture.detailed(fasteners)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve()
    detailed = after.element("fasteners.shoe")
    assert len(detailed.meshes) == 4
    assert detailed.data["netVolumeMm3"] == pytest.approx(
        scheduled.data["netVolumeMm3"]
    )
    assert detailed.data["scheduledVolumeMm3"] == 0
    first = Authoring.array(ModelReports(before).schedules()["materials"])
    second = Authoring.array(ModelReports(after).schedules()["materials"])
    for rows in (first, second):
        steel = next(
            Authoring.object(value)
            for value in rows
            if Authoring.object(value)["materialId"] == "material.hardwareSteel"
        )
        assert steel["volumeM3"] == pytest.approx(
            (95600 + number(scheduled.data["netVolumeMm3"], "fastener volume")) / 1e9
        )


def test_hardware_cavity_and_owned_cut_reconcile_material_and_void_volume(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Embedded hardware replaces infill and a later metal cut becomes an owned cavity void."""
    hardware, _ = HardwareFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    layers = Authoring.array(
        Authoring.object(types["wallType.exterior.wood-185"])["layers"]
    )
    Authoring.object(layers[2])["representation"] = "explicit"
    hardware["placement"] = {"origin": {"point": [9500, 9.5, 1000]}}
    hardware["participants"] = [{"element": "wall.south"}]
    hardware["occupies"] = {"regions": [{"host": "wall.south", "layer": 2}]}
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    before = ModelResolver(reference_model).resolve()
    Authoring.object(reference_model["elements"])["cut.hardware"] = {
        "kind": "penetration",
        "name": "Hardware slot",
        "host": "hardware.shoe",
        "purpose": "notch",
        "placement": {"origin": {"point": [9548, 9.5, 1050]}},
        "section": {"kind": "rectangle", "width": 10, "depth": 10},
        "depth": 2,
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve()
    assert after.element("hardware.shoe").data["netVolumeMm3"] == pytest.approx(
        95600 - 80
    )
    first = Authoring.object(
        Authoring.array(before.element("wall.south").data["cavities"])[0]
    )
    second = Authoring.object(
        Authoring.array(after.element("wall.south").data["cavities"])[0]
    )
    assert first["occupiedVolumeMm3"] == pytest.approx(95600)
    assert second["occupiedVolumeMm3"] == pytest.approx(95600 - 80)
    assert number(second["voidVolumeMm3"], "new void") - number(
        first["voidVolumeMm3"], "old void"
    ) == pytest.approx(80)
    assert second["infillVolumeMm3"] == pytest.approx(first["infillVolumeMm3"])
    source = tmp_path / "embedded-hardware.json"
    ModelLoader.write(reference_model, source)
    ifc = ifcopenshell.open(BuildService().build(source, tmp_path / "build").ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    attachment = next(
        value
        for value in ifc.by_type("IfcRelConnectsElements")
        if value.Name == "Hardware attachment"
    )
    assert attachment.RelatingElement.Tag == "wall.south"
    assert attachment.RelatedElement.Tag == "hardware.shoe"
    quantities = [
        quantity
        for relation in attachment.RelatedElement.IsDefinedBy
        if relation.RelatingPropertyDefinition.is_a("IfcElementQuantity")
        for quantity in relation.RelatingPropertyDefinition.Quantities
    ]
    assert next(
        quantity for quantity in quantities if quantity.Name == "NetVolume"
    ).VolumeValue == pytest.approx((95600 - 80) / 1e9)


def test_scoped_hardware_participants_connect_native_assembly_members(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """A connection to a generated board resolves and exports using that board's own identity."""
    hardware, _ = HardwareFixture.configure(reference_model)
    Authoring.object(reference_model["elements"])["member.support"] = {
        "kind": "memberAssembly",
        "name": "Support assembly",
        "assemblyType": "other",
        "placement": {"origin": {"point": [0, -4000, 0]}},
        "nodes": {"base": {"local": [0, 0, 0]}, "top": {"local": [0, 0, 1000]}},
        "members": {
            "leg": {
                "start": "base",
                "end": "top",
                "memberType": "type.connectionStock",
                "role": "column",
            }
        },
    }
    host = Authoring.object(
        Authoring.object(Authoring.object(hardware["placement"])["origin"])["host"]
    )
    host["part"] = "leg"
    Authoring.object(Authoring.array(hardware["participants"])[0])["part"] = "leg"
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    assert "member.support/member/leg" in Authoring.array(
        resolved.element("hardware.shoe").data["participantIds"]
    )
    source = tmp_path / "scoped-hardware.json"
    ModelLoader.write(reference_model, source)
    ifc = ifcopenshell.open(BuildService().build(source, tmp_path / "build").ifc_model)
    relation = next(
        value
        for value in ifc.by_type("IfcRelConnectsWithRealizingElements")
        if value.RealizingElements[0].Tag == "hardware.shoe"
    )
    assert "member.support/member/leg" in {
        relation.RelatingElement.Tag,
        relation.RelatedElement.Tag,
    }
    Authoring.object(Authoring.array(hardware["participants"])[0])["part"] = "missing"
    assert not validator.validate(reference_model).is_valid


@pytest.mark.parametrize("detailed", [False, True])
def test_hardware_exports_native_types_quantities_and_realizing_connections(
    reference_model: JsonObject, tmp_path: Path, detailed: bool
) -> None:
    """IFC and browser preserve count-only groups and physical accessories consistently."""
    _, fasteners = HardwareFixture.configure(reference_model)
    if detailed:
        HardwareFixture.detailed(fasteners)
    source = tmp_path / "hardware.json"
    ModelLoader.write(reference_model, source)
    result = BuildService().build(source, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    hardware = next(
        product
        for product in ifc.by_type("IfcDiscreteAccessory")
        if product.Tag == "hardware.shoe"
    )
    assert hardware.IsTypedBy[0].RelatingType.PredefinedType == "SHOE"
    assert hardware.IsTypedBy[0].RelatingType.is_a("IfcDiscreteAccessoryType")
    fastener = next(
        product
        for product in ifc.by_type("IfcMechanicalFastener")
        if product.Tag == "fasteners.shoe"
    )
    assert fastener.IsTypedBy[0].RelatingType.PredefinedType == "SCREW"
    assert fastener.NominalDiameter == 6 and fastener.NominalLength == 60
    common = ifcopenshell.util.element.get_psets(fastener)[
        "Pset_MechanicalFastenerCommon"
    ]
    assert common["NominalDiameter"] == 6 and common["NominalLength"] == 60
    assert "Qto_HomeDesignFastener" in ifcopenshell.util.element.get_psets(
        fastener, qtos_only=True
    )
    assert (fastener.Representation is not None) == detailed
    quantities = {
        quantity.Name: quantity
        for relation in fastener.IsDefinedBy
        if relation.RelatingPropertyDefinition.is_a("IfcElementQuantity")
        for quantity in relation.RelatingPropertyDefinition.Quantities
    }
    assert quantities["Count"].CountValue == 4
    assert quantities["ModeledCount"].CountValue == (4 if detailed else 0)
    assert quantities["NetVolume"].VolumeValue > 0
    connections = ifc.by_type("IfcRelConnectsWithRealizingElements")
    assert {value.RealizingElements[0].Tag for value in connections} == {
        "hardware.shoe",
        "fasteners.shoe",
    }
    manifest = json.loads(result.render_manifest.read_text())
    assert len(manifest["elements"]["fasteners.shoe"]["nodes"]) == (
        4 if detailed else 0
    )


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "type",
        "self",
        "duplicate",
        "nonphysical",
        "part",
        "cutMiss",
        "cutAll",
        "quantity",
        "overlap",
        "scheduledPositions",
        "scheduledCavity",
    ],
)
def test_invalid_hardware_and_fastener_intent_is_rejected(
    reference_model: JsonObject, validator: ModelValidator, case: str
) -> None:
    """Reject invalid participants, incompatible types, destructive recipes and inconsistent counts."""
    hardware, fasteners = HardwareFixture.configure(reference_model)
    if case in {"missing", "self", "nonphysical", "part"}:
        reference: JsonObject = {
            "element": {
                "missing": "missing.target",
                "self": "hardware.shoe",
                "nonphysical": "opening.door.south",
                "part": "member.support",
            }[case]
        }
        if case == "part":
            reference["part"] = "unknown"
        hardware["participants"] = [reference]
    elif case == "duplicate":
        hardware["participants"] = [
            {"element": "member.support"},
            {"element": "member.support"},
        ]
    elif case == "type":
        hardware["type"] = "type.screw"
    elif case in {"cutMiss", "cutAll"}:
        definition = Authoring.object(
            Authoring.object(reference_model["types"])["type.shoe"]
        )
        definition["cuts"] = {
            "bad": {
                "section": {"kind": "rectangle", "width": 1000, "depth": 1000},
                "depth": 1000,
                "placement": {"origin": [5000 if case == "cutMiss" else 0, 0, 0]},
            }
        }
    elif case in {"quantity", "overlap", "scheduledPositions"}:
        HardwareFixture.detailed(fasteners)
        if case == "quantity":
            fasteners["quantity"] = 5
        elif case == "overlap":
            Authoring.object(fasteners["instances"])["screw1"] = {
                "origin": [-20, -20, 0]
            }
        else:
            fasteners["representation"] = "scheduled"
    else:
        fasteners["occupies"] = {"regions": [{"host": "wall.south", "layer": 0}]}
    report = validator.validate(reference_model)
    assert not report.is_valid
    if case == "nonphysical":
        assert "has no physical construction geometry" in str(report.to_dict())
