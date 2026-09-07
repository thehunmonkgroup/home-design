"""Native IFC construction accessories, fastener quantities and realizing connections."""

from __future__ import annotations

from collections.abc import Callable
from itertools import combinations

import ifcopenshell
from ifcopenshell.entity_instance import entity_instance

from home_design.construction import Authoring
from home_design.geometry import number
from home_design.hardware import HardwareComponents
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedModel
from home_design.solids import SolidOperations
from home_design.adapters.ifc_units import IfcUnits
from home_design.adapters.ifc_properties import IfcProperties


class IfcHardware:
    """Preserve hardware roles and schedules without inferring engineering connections."""

    @staticmethod
    def predefined(product: entity_instance, definition: JsonObject) -> None:
        """Map authored construction roles to IFC4 accessory or fastener predefined types."""
        role = Authoring.text(definition["role"])
        if product.is_a("IfcDiscreteAccessory") or product.is_a(
            "IfcDiscreteAccessoryType"
        ):
            predefined = {
                "anchorPlate": "ANCHORPLATE",
                "bracket": "BRACKET",
                "postBase": "SHOE",
                "postCap": "SHOE",
            }.get(role, "USERDEFINED")
        else:
            predefined = role.upper() if role != "other" else "USERDEFINED"
        product.PredefinedType = predefined
        if product.is_a("IfcElementType"):
            product.ElementType = role
        else:
            product.ObjectType = role
        if product.is_a("IfcMechanicalFastener"):
            product.NominalDiameter = float(
                number(definition["nominalDiameter"], "fastener diameter")
            )
            product.NominalLength = float(
                number(definition["nominalLength"], "fastener length")
            )

    @classmethod
    def apply(
        cls,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        guid: Callable[[str], str],
    ) -> None:
        """Attach native net/count quantities and construction participant relations."""
        for element in model.elements:
            if element.kind not in HardwareComponents.KINDS:
                continue
            product = products[element.element_id]
            if element.kind == "fastenerGroup":
                IfcProperties(guid).pset(
                    ifc,
                    product,
                    element.element_id,
                    "Pset_MechanicalFastenerCommon",
                    {
                        "NominalDiameter": element.data["nominalDiameter"],
                        "NominalLength": element.data["nominalLength"],
                    },
                )
            volume = sum(
                SolidOperations.volume(mesh) for mesh in element.meshes
            ) + number(element.data.get("scheduledVolumeMm3", 0), "scheduled volume")
            quantities = [
                ifc.create_entity(
                    "IfcQuantityVolume",
                    Name="NetVolume",
                    VolumeValue=IfcUnits.volume(volume),
                )
            ]
            if element.kind == "fastenerGroup":
                quantities.append(
                    ifc.create_entity(
                        "IfcQuantityCount",
                        Name="Count",
                        CountValue=float(
                            number(element.data["quantity"], "fastener quantity")
                        ),
                    )
                )
                quantities.append(
                    ifc.create_entity(
                        "IfcQuantityCount",
                        Name="ModeledCount",
                        CountValue=float(len(element.meshes)),
                    )
                )
            quantity_set = ifc.create_entity(
                "IfcElementQuantity",
                GlobalId=guid(f"qto.hardware.{element.element_id}"),
                Name=(
                    "Qto_HomeDesignFastener"
                    if element.kind == "fastenerGroup"
                    else "Qto_HomeDesignHardware"
                ),
                MethodOfMeasurement=(
                    "Authored count and net fabricated type volume"
                    if element.data.get("representation") == "scheduled"
                    else "Net modeled geometry"
                ),
                Quantities=quantities,
            )
            ifc.create_entity(
                "IfcRelDefinesByProperties",
                GlobalId=guid(f"rel.qto.hardware.{element.element_id}"),
                RelatedObjects=[product],
                RelatingPropertyDefinition=quantity_set,
            )
            participants = sorted(
                Authoring.text(value)
                for value in Authoring.array(element.data["participantIds"])
            )
            if len(participants) == 1:
                ifc.create_entity(
                    "IfcRelConnectsElements",
                    GlobalId=guid(
                        f"rel.hardware.{element.element_id}.{participants[0]}"
                    ),
                    Name="Hardware attachment",
                    RelatingElement=products[participants[0]],
                    RelatedElement=product,
                )
            for first, second in combinations(participants, 2):
                ifc.create_entity(
                    "IfcRelConnectsWithRealizingElements",
                    GlobalId=guid(
                        f"rel.hardware.{element.element_id}.{first}.{second}"
                    ),
                    Name="Authored hardware connection",
                    RelatingElement=products[first],
                    RelatedElement=products[second],
                    RealizingElements=[product],
                    ConnectionType=str(element.data["role"]),
                )
