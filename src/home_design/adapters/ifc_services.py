"""Native IFC distribution systems, circuits, nested ports and physical connections."""

from __future__ import annotations

from collections.abc import Callable
from math import dist

import ifcopenshell
from ifcopenshell.entity_instance import entity_instance

from home_design.adapters.ifc_properties import IfcProperties
from home_design.adapters.ifc_electrical import IfcElectrical
from home_design.adapters.ifc_plumbing import IfcPlumbing
from home_design.adapters.ifc_mechanical import IfcMechanical
from home_design.construction import Authoring
from home_design.constants import GEOMETRY_TOLERANCE_MM
from home_design.geometry import vector3
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedModel
from home_design.service_ports import ServicePorts
from home_design.solids import SolidOperations
from home_design.adapters.ifc_units import IfcUnits


class IfcServices:
    """Preserve port ownership, system boundaries and native one-to-one mating relationships."""

    SYSTEM_TYPES: dict[str, str] = {
        "electrical": "ELECTRICAL",
        "communications": "COMMUNICATION",
        "water": "WATERSUPPLY",
        "coldWater": "DOMESTICCOLDWATER",
        "hotWater": "DOMESTICHOTWATER",
        "waste": "WASTEWATER",
        "vent": "VENT",
        "gas": "GAS",
        "supplyAir": "VENTILATION",
        "exhaustAir": "EXHAUST",
        "refrigerant": "REFRIGERATION",
        "condensate": "DRAINAGE",
        "other": "USERDEFINED",
    }

    @classmethod
    def _ports(
        cls,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        guid: Callable[[str], str],
    ) -> dict[tuple[str, str], entity_instance]:
        """Nest ports in their actual device, with full oriented model-space placement."""
        ports: dict[tuple[str, str], entity_instance] = {}
        for element in model.elements:
            children: list[entity_instance] = []
            for key, value in Authoring.object(element.data.get("ports", {})).items():
                data = Authoring.object(value)
                identity = f"{element.element_id}/port/{key}"
                frame = ServicePorts.frame(data)
                system = model.element(Authoring.text(data["systemId"]))
                native_type = cls.SYSTEM_TYPES[
                    Authoring.text(system.data["systemType"])
                ]
                medium = Authoring.text(data["medium"])
                port = ifc.create_entity(
                    "IfcDistributionPort",
                    GlobalId=guid(identity),
                    Name=key,
                    ObjectType=medium,
                    FlowDirection={
                        "source": "SOURCE",
                        "sink": "SINK",
                        "bidirectional": "SOURCEANDSINK",
                    }[Authoring.text(data["flow"])],
                    PredefinedType=(
                        "CABLECARRIER"
                        if data.get("function") == "containment"
                        else (
                            {
                                "pipe": "PIPE",
                                "duct": "DUCT",
                                "cable": "CABLE",
                                "conduit": "CABLECARRIER",
                            }[Authoring.text(element.data["family"])]
                            if element.kind in {"serviceRoute", "serviceFitting"}
                            else (
                                "CABLE"
                                if medium in {"electrical", "communications"}
                                else (
                                    "DUCT"
                                    if medium == "air"
                                    else "USERDEFINED" if medium == "other" else "PIPE"
                                )
                            )
                        )
                    ),
                    SystemType=native_type,
                    ObjectPlacement=ifc.create_entity(
                        "IfcLocalPlacement",
                        RelativePlacement=ifc.create_entity(
                            "IfcAxis2Placement3D",
                            Location=ifc.create_entity(
                                "IfcCartesianPoint", Coordinates=frame.origin
                            ),
                            Axis=ifc.create_entity(
                                "IfcDirection", DirectionRatios=frame.z
                            ),
                            RefDirection=ifc.create_entity(
                                "IfcDirection", DirectionRatios=frame.x
                            ),
                        ),
                    ),
                )
                IfcProperties(guid).pset(
                    ifc,
                    port,
                    identity,
                    "Pset_HomeDesignPort",
                    {"CanonicalId": identity, **data},
                )
                ports[(element.element_id, key)] = port
                children.append(port)
            if children:
                ifc.create_entity(
                    "IfcRelNests",
                    GlobalId=guid(f"rel.ports.{element.element_id}"),
                    RelatingObject=products[element.element_id],
                    RelatedObjects=children,
                )
        return ports

    @classmethod
    def _groups(
        cls,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        ports: dict[tuple[str, str], entity_instance],
        guid: Callable[[str], str],
    ) -> None:
        """Assign components and their ports to native systems and nested circuit groups."""
        for element in model.elements:
            if element.kind not in {"serviceSystem", "serviceCircuit"}:
                continue
            group = products[element.element_id]
            group.PredefinedType = cls.SYSTEM_TYPES[
                Authoring.text(element.data["systemType"])
            ]
            group.ObjectType = element.data["systemType"]
            members = [
                products[Authoring.text(key)]
                for key in Authoring.array(element.data["componentIds"])
            ]
            for reference in Authoring.array(element.data["members"]):
                key = ServicePorts.reference(reference)
                port_data = Authoring.object(
                    Authoring.object(model.element(key[0]).data["ports"])[key[1]]
                )
                if (
                    port_data.get("circuitId", port_data["systemId"])
                    == element.element_id
                ):
                    members.append(ports[key])
            if element.kind == "serviceSystem":
                members.extend(
                    products[circuit.element_id]
                    for circuit in model.elements
                    if circuit.kind == "serviceCircuit"
                    and circuit.data["system"] == element.element_id
                )
            ifc.create_entity(
                "IfcRelAssignsToGroup",
                GlobalId=guid(f"rel.system.{element.element_id}"),
                RelatingGroup=group,
                RelatedObjects=members,
            )

    @staticmethod
    def _quantities(
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        guid: Callable[[str], str],
    ) -> None:
        """Add net quantities for freestanding devices; mounted quantities use the shared adapter."""
        for element in model.elements:
            if (
                element.kind not in {"serviceDevice", "serviceRoute", "serviceFitting"}
                or "mountHostId" in element.data
            ):
                continue
            quantities = [
                ifc.create_entity(
                    "IfcQuantityVolume",
                    Name="NetVolume",
                    VolumeValue=IfcUnits.volume(
                        sum(SolidOperations.volume(mesh) for mesh in element.meshes)
                    ),
                )
            ]
            if element.kind == "serviceRoute":
                quantities.append(
                    ifc.create_entity(
                        "IfcQuantityLength",
                        Name="Length",
                        LengthValue=element.data["centerlineLengthMm"],
                    )
                )
            quantity_set = ifc.create_entity(
                "IfcElementQuantity",
                GlobalId=guid(f"qto.services.{element.element_id}"),
                Name=(
                    "Qto_HomeDesignServiceRoute"
                    if element.kind == "serviceRoute"
                    else (
                        "Qto_HomeDesignServiceFitting"
                        if element.kind == "serviceFitting"
                        else "Qto_HomeDesignServiceDevice"
                    )
                ),
                Quantities=quantities,
            )
            ifc.create_entity(
                "IfcRelDefinesByProperties",
                GlobalId=guid(f"rel.qto.services.{element.element_id}"),
                RelatedObjects=[products[element.element_id]],
                RelatingPropertyDefinition=quantity_set,
            )

    @classmethod
    def apply(
        cls,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        guid: Callable[[str], str],
    ) -> None:
        """Export validated connectivity without turning internal device groups into extra external mates."""
        ports = cls._ports(ifc, model, products, guid)
        cls._groups(ifc, model, products, ports, guid)
        cls._quantities(ifc, model, products, guid)
        IfcElectrical.circuits(ifc, model, products, guid)
        for identity, value in model.relationships.items():
            relation = Authoring.object(value)
            if relation["kind"] != "connectsPorts":
                continue
            a, b = (
                ports[ServicePorts.reference(relation["a"])],
                ports[ServicePorts.reference(relation["b"])],
            )
            if a.FlowDirection == "SINK" or b.FlowDirection == "SOURCE":
                a, b = b, a
            ifc.create_entity(
                "IfcRelConnectsPorts",
                GlobalId=guid(identity),
                Name=relation.get("name", identity),
                RelatingPort=a,
                RelatedPort=b,
            )

    @staticmethod
    def route_class(data: JsonObject) -> str:
        """Select a concrete IFC4 product family with a matching concrete type."""
        return {
            "pipe": "IfcPipeSegment",
            "duct": "IfcDuctSegment",
            "cable": "IfcCableSegment",
            "conduit": "IfcCableCarrierSegment",
        }[Authoring.text(data["family"])]

    @staticmethod
    def route_predefined(product: entity_instance, data: JsonObject) -> None:
        """Retain route construction intent using native IFC4 predefined segment types."""
        product.PredefinedType = {
            "pipe": "RIGIDSEGMENT",
            "duct": "RIGIDSEGMENT",
            "cable": "CABLESEGMENT",
            "conduit": "CONDUITSEGMENT",
        }[Authoring.text(data["family"])]

        if (
            data["family"] in {"pipe", "duct"}
            and Authoring.object(data.get(Authoring.text(data["family"]), {})).get(
                "construction"
            )
            == "flexible"
        ):
            product.PredefinedType = "FLEXIBLESEGMENT"
        if data["family"] == "cable":
            construction = Authoring.object(data.get("cable", {})).get(
                "construction", "cable"
            )
            product.PredefinedType = {
                "cable": "CABLESEGMENT",
                "conductor": "CONDUCTORSEGMENT",
                "core": "CORESEGMENT",
                "opticalFiber": "USERDEFINED",
            }[Authoring.text(construction)]
            if construction == "opticalFiber":
                if product.is_a("IfcTypeProduct"):
                    product.ElementType = "opticalFiber"
                else:
                    product.ObjectType = "opticalFiber"

    @staticmethod
    def fitting_class(data: JsonObject) -> str:
        """Map the physical fitting family to a concrete native IFC4 class."""
        return {
            "pipe": "IfcPipeFitting",
            "duct": "IfcDuctFitting",
            "cable": "IfcCableFitting",
            "conduit": "IfcCableCarrierFitting",
        }[Authoring.text(data["family"])]

    @staticmethod
    def _carrier_junction(data: JsonObject) -> str:
        """Distinguish simultaneous cross takeoffs from separate branches along a trunk."""
        geometry = Authoring.object(data.get("geometry", {}))
        branches = Authoring.object(geometry.get("branches", {}))
        if "paths" in data:
            branches = {
                key: value
                for key, value in Authoring.object(data["paths"]).items()
                if key != "trunk"
            }
        roots = [
            vector3(Authoring.array(Authoring.object(value)["path"])[0], "branch root")
            for value in branches.values()
        ]
        if len(roots) == 1:
            return "TEE"
        if len(roots) == 2 and dist(*roots) <= GEOMETRY_TOLERANCE_MM:
            return "CROSS"
        return "USERDEFINED"

    @classmethod
    def fitting_predefined(cls, product: entity_instance, data: JsonObject) -> None:
        """Use each family's supported bend, junction, transition and closure classifications."""
        geometry = Authoring.object(data.get("geometry", {}))
        role = Authoring.text(data.get("role", geometry.get("kind")))
        family = Authoring.text(data["family"])
        predefined = {
            "elbow": "BEND",
            "branch": "JUNCTION",
            "transition": "TRANSITION",
            "cap": "USERDEFINED",
            "trap": "USERDEFINED",
        }[role]
        if family == "cable":
            predefined = {"elbow": "USERDEFINED"}.get(role, predefined)
        if family == "conduit":
            predefined = {
                "elbow": "BEND",
                "transition": "REDUCER",
                "cap": "USERDEFINED",
                "branch": cls._carrier_junction(data),
            }[role]
        product.PredefinedType = predefined
        if predefined == "USERDEFINED":
            if product.is_a("IfcTypeProduct"):
                product.ElementType = role
            else:
                product.ObjectType = role

    @classmethod
    def device_class(cls, data: JsonObject) -> str:
        """Dispatch discipline-specific equipment with a generic service-device fallback."""
        role = Authoring.text(data["role"])
        if role in IfcPlumbing.DEVICES:
            return IfcPlumbing.DEVICES[role][0]
        if role in IfcMechanical.DEVICES:
            return IfcMechanical.DEVICES[role][0]
        return IfcElectrical.device_class(data)

    @staticmethod
    def device_predefined(product: entity_instance, data: JsonObject) -> None:
        """Apply classification using the authored equipment discipline."""
        if Authoring.text(data["role"]) in IfcPlumbing.DEVICES:
            IfcPlumbing.predefined(product, data)
        elif Authoring.text(data["role"]) in IfcMechanical.DEVICES:
            IfcMechanical.predefined(product, data)
        else:
            IfcElectrical.predefined(product, data)

    @classmethod
    def geometry_class(cls, kind: str, data: JsonObject) -> str:
        """Select a physical service class for either its occurrence or reusable type."""
        return {
            "serviceRoute": cls.route_class,
            "serviceFitting": cls.fitting_class,
            "serviceDevice": cls.device_class,
        }[kind.removesuffix("Type")](data)

    @classmethod
    def geometry_predefined(
        cls, kind: str, product: entity_instance, data: JsonObject
    ) -> None:
        """Apply the physical family's native predefined-type contract."""
        {
            "serviceRoute": cls.route_predefined,
            "serviceFitting": cls.fitting_predefined,
            "serviceDevice": cls.device_predefined,
        }[kind.removesuffix("Type")](product, data)
