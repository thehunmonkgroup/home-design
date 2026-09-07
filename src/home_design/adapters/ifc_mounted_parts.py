"""Native mounted parts, nonphysical coordination volumes and their IFC associations."""

from __future__ import annotations

from collections.abc import Callable

import ifcopenshell
from ifcopenshell.entity_instance import entity_instance

from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.mounted_parts import MountedParts
from home_design.resolved import ResolvedModel
from home_design.solids import SolidOperations
from home_design.adapters.ifc_units import IfcUnits


class IfcMountedParts:
    """Keep physical mounting connections separate from access/barrier assignments."""

    @staticmethod
    def envelope_class(data: JsonObject) -> str:
        """Classify protective plates separately from coverings and penetration seals."""
        return "IfcPlate" if data["role"] == "protectivePlate" else "IfcCovering"

    @staticmethod
    def predefined(product: entity_instance, data: JsonObject) -> None:
        """Use the native membrane classification and retain other authored roles."""
        role = Authoring.text(data["role"])
        covering = product.is_a("IfcCovering") or product.is_a("IfcCoveringType")
        product.PredefinedType = (
            {
                "membrane": "MEMBRANE",
                "insulation": "INSULATION",
                "sleeve": "SLEEVING",
            }.get(role, "USERDEFINED")
            if covering
            else "USERDEFINED"
        )
        if product.is_a("IfcElementType"):
            product.ElementType = role
        else:
            product.ObjectType = role

    @staticmethod
    def apply(
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        guid: Callable[[str], str],
    ) -> None:
        """Export mounting identity, final material volumes and nonmaterial ownership."""
        for element in model.elements:
            if "interfaceHostId" in element.data:
                for service_id in Authoring.array(element.data["interfaceServiceIds"]):
                    ifc.create_entity(
                        "IfcRelConnectsWithRealizingElements",
                        GlobalId=guid(
                            f"rel.serviceInterface.{element.element_id}/{service_id}"
                        ),
                        Name="Authored service interface",
                        RelatingElement=products[
                            Authoring.text(element.data["interfaceHostId"])
                        ],
                        RelatedElement=products[Authoring.text(service_id)],
                        RealizingElements=[products[element.element_id]],
                        ConnectionType=Authoring.text(element.data["role"]),
                    )
            if element.kind in MountedParts.KINDS or "mountHostId" in element.data:
                host_id = Authoring.text(element.data["mountHostId"])
                ifc.create_entity(
                    "IfcRelConnectsElements",
                    GlobalId=guid(f"rel.mount.{element.element_id}"),
                    Name="Hosted mounting",
                    RelatingElement=products[host_id],
                    RelatedElement=products[element.element_id],
                )
                quantity_set = ifc.create_entity(
                    "IfcElementQuantity",
                    GlobalId=guid(f"qto.mounted.{element.element_id}"),
                    Name="Qto_HomeDesignMountedPart",
                    MethodOfMeasurement="Final modeled material after cavity composition and cuts",
                    Quantities=[
                        ifc.create_entity(
                            "IfcQuantityVolume",
                            Name="NetVolume",
                            VolumeValue=IfcUnits.volume(
                                sum(
                                    SolidOperations.volume(mesh)
                                    for mesh in element.meshes
                                )
                            ),
                        )
                    ],
                )
                ifc.create_entity(
                    "IfcRelDefinesByProperties",
                    GlobalId=guid(f"rel.qto.mounted.{element.element_id}"),
                    RelatedObjects=[products[element.element_id]],
                    RelatingPropertyDefinition=quantity_set,
                )
                continue
            if element.kind == "clearanceZone":
                participants = {Authoring.text(element.data["owner"])}
            elif element.kind == "barrierCheck":
                participants = {
                    Authoring.text(Authoring.object(value)["element"])
                    for value in Authoring.array(element.data["participants"])
                }
            else:
                continue
            for participant in sorted(participants):
                ifc.create_entity(
                    "IfcRelAssignsToProduct",
                    GlobalId=guid(
                        f"rel.coordination.{element.element_id}/{participant}"
                    ),
                    Name=Authoring.text(element.data["purpose"]),
                    RelatedObjects=[products[element.element_id]],
                    RelatingProduct=products[participant],
                )
