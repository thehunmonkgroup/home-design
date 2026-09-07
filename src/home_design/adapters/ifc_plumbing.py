"""IFC property preservation for typed plumbing stock and authored operating checks."""

from __future__ import annotations

from collections.abc import Callable

import ifcopenshell
from ifcopenshell.entity_instance import entity_instance

from home_design.adapters.ifc_properties import IfcProperties
from home_design.adapters.ifc_standard_services import IfcStandardServices
from home_design.construction import Authoring
from home_design.json_types import JsonObject


class IfcPlumbing:
    """Retain unit-explicit pipe specifications and geometry-check results on native products."""

    DEVICES: dict[str, tuple[str, str]] = {
        "valve": ("IfcValve", "USERDEFINED"),
        "manifold": ("IfcPipeFitting", "JUNCTION"),
        "fixtureConnection": ("IfcPipeFitting", "CONNECTOR"),
        "cleanout": ("IfcPipeFitting", "USERDEFINED"),
        "waterHeater": ("IfcBoiler", "WATER"),
        "plumbingPump": ("IfcPump", "USERDEFINED"),
        "storageTank": ("IfcTank", "STORAGE"),
        "waterMeter": ("IfcFlowMeter", "WATERMETER"),
    }
    VALVES: dict[str, str] = {
        "isolating": "ISOLATING",
        "check": "CHECK",
        "mixing": "MIXING",
        "pressureReducing": "PRESSUREREDUCING",
        "pressureRelief": "PRESSURERELIEF",
        "regulating": "REGULATING",
        "gasCock": "GASCOCK",
        "faucet": "FAUCET",
    }

    @classmethod
    def predefined(cls, product: entity_instance, data: JsonObject) -> None:
        """Preserve explicit valve function and avoid inventing unspecified pump technology."""
        role = Authoring.text(data["role"])
        predefined = cls.DEVICES[role][1]
        specification = Authoring.object(data.get("plumbing", {}))
        if role == "valve" and "valveType" in specification:
            predefined = cls.VALVES[Authoring.text(specification["valveType"])]
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
        """Export authored stock and conditions independently from generated net material quantities."""
        if data.get("family") != "pipe" and "plumbing" not in data:
            return
        properties = IfcProperties(guid)
        IfcStandardServices.apply(
            ifc,
            product,
            identity,
            data,
            Authoring.object(data.get("plumbing", data.get("pipe", {}))),
            guid,
        )
        for key, name in (
            ("plumbing", "Pset_HomeDesignPlumbing"),
            ("pipe", "Pset_HomeDesignPipe"),
            ("conditions", "Pset_HomeDesignPipeConditions"),
            ("fallCheck", "Pset_HomeDesignFallCheck"),
        ):
            if key in data:
                properties.pset(
                    ifc, product, identity, name, Authoring.object(data[key])
                )
