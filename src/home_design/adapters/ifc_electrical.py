"""Concrete IFC4 electrical and communications devices with native rated measures."""

from __future__ import annotations

from collections.abc import Callable

import ifcopenshell
from ifcopenshell.entity_instance import entity_instance

from home_design.adapters.ifc_properties import IfcProperties
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedModel
from home_design.service_ports import ServicePorts


class IfcElectrical:
    """Map authored product intent without assigning an unspecified technology subtype."""

    DEVICES: dict[str, tuple[str, str]] = {
        "receptacle": ("IfcOutlet", "POWEROUTLET"),
        "switch": ("IfcSwitchingDevice", "USERDEFINED"),
        "deviceBox": ("IfcJunctionBox", "USERDEFINED"),
        "junctionBox": ("IfcJunctionBox", "USERDEFINED"),
        "distributionPanel": ("IfcElectricDistributionBoard", "DISTRIBUTIONBOARD"),
        "circuitBreaker": ("IfcProtectiveDevice", "CIRCUITBREAKER"),
        "fuse": ("IfcProtectiveDevice", "USERDEFINED"),
        "surgeProtector": ("IfcProtectiveDevice", "USERDEFINED"),
        "light": ("IfcLightFixture", "USERDEFINED"),
        "smokeDetector": ("IfcSensor", "SMOKESENSOR"),
        "heatDetector": ("IfcSensor", "HEATSENSOR"),
        "carbonMonoxideDetector": ("IfcSensor", "COSENSOR"),
        "communicationsOutlet": ("IfcOutlet", "COMMUNICATIONSOUTLET"),
        "communicationsPanel": ("IfcCommunicationsAppliance", "USERDEFINED"),
        "groundingBar": ("IfcCableFitting", "JUNCTION"),
        "groundingElectrode": ("IfcCableFitting", "EXIT"),
        "bondingClamp": ("IfcCableFitting", "EXIT"),
    }

    @classmethod
    def device_class(cls, data: JsonObject) -> str:
        """Return the physical device class, retaining the generic service-device fallback."""
        return cls.DEVICES.get(
            Authoring.text(data["role"]), ("IfcDistributionElement", "")
        )[0]

    @classmethod
    def predefined(cls, product: entity_instance, data: JsonObject) -> None:
        """Write native classification on reusable types or untyped occurrences."""
        role = Authoring.text(data["role"])
        if role not in cls.DEVICES:
            return
        predefined = cls.DEVICES[role][1]
        product.PredefinedType = predefined
        if predefined == "USERDEFINED":
            if product.is_a("IfcTypeProduct"):
                product.ElementType = role
            else:
                product.ObjectType = role

    @staticmethod
    def properties(
        ifc: ifcopenshell.file,
        product: entity_instance,
        identity: str,
        data: JsonObject,
        guid: Callable[[str], str],
    ) -> None:
        """Export supported standard measures and retain all unit-explicit authored ratings."""
        properties = IfcProperties(guid)
        for key, name in (
            ("cable", "Pset_HomeDesignCable"),
            ("conduit", "Pset_HomeDesignConduit"),
        ):
            if key in data:
                properties.pset(
                    ifc, product, identity, name, Authoring.object(data[key])
                )
        if "electrical" not in data:
            return
        ratings = Authoring.object(data["electrical"])
        properties.pset(ifc, product, identity, "Pset_HomeDesignElectrical", ratings)
        properties.pset(
            ifc,
            product,
            identity,
            "Pset_ElectricalDeviceCommon",
            {
                native: ratings[key]
                for key, native in (
                    ("ratedVoltageV", "RatedVoltage"),
                    ("ratedCurrentA", "RatedCurrent"),
                    ("poles", "NumberOfPoles"),
                )
                if key in ratings
            },
        )

    @staticmethod
    def circuits(
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        guid: Callable[[str], str],
    ) -> None:
        """Associate scheduled circuits with their actual source panels and retain their checked schedule."""
        for element in model.elements:
            if "circuitSchedule" not in element.data:
                continue
            schedule = Authoring.object(element.data["circuitSchedule"])
            IfcProperties(guid).pset(
                ifc,
                products[element.element_id],
                element.element_id,
                "Pset_HomeDesignCircuitSchedule",
                schedule,
            )
            panel_id, _ = ServicePorts.reference(schedule["panel"])
            ifc.create_entity(
                "IfcRelAssignsToProduct",
                GlobalId=guid(f"rel.circuitPanel.{element.element_id}"),
                Name="Circuit supply panel",
                RelatedObjects=[products[element.element_id]],
                RelatingProduct=products[panel_id],
            )
