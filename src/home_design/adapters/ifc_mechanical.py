"""IFC preservation of authored mechanical stock and operating conditions."""

from __future__ import annotations

from collections.abc import Callable

import ifcopenshell
from ifcopenshell.entity_instance import entity_instance

from home_design.adapters.ifc_properties import IfcProperties
from home_design.adapters.ifc_standard_services import IfcStandardServices
from home_design.construction import Authoring
from home_design.json_types import JsonObject


class IfcMechanical:
    """Keep unit-explicit mechanical inputs distinct from physical material quantities."""

    DEVICES: dict[str, tuple[str, str]] = {
        "damper": ("IfcDamper", "USERDEFINED"),
        "airTerminal": ("IfcAirTerminal", "USERDEFINED"),
        "fan": ("IfcFan", "USERDEFINED"),
        "airHandler": ("IfcUnitaryEquipment", "AIRHANDLER"),
        "heatRecoveryVentilator": ("IfcAirToAirHeatRecovery", "USERDEFINED"),
        "airFilter": ("IfcFilter", "AIRPARTICLEFILTER"),
        "coil": ("IfcCoil", "USERDEFINED"),
        "airConditioner": ("IfcUnitaryEquipment", "AIRCONDITIONINGUNIT"),
        "dehumidifier": ("IfcUnitaryEquipment", "DEHUMIDIFIER"),
        "refrigerantUnit": ("IfcUnitaryEquipment", "SPLITSYSTEM"),
    }
    SUBTYPES: dict[str, dict[str, str]] = {
        "damperType": {
            "backdraft": "BACKDRAFTDAMPER",
            "balancing": "BALANCINGDAMPER",
            "control": "CONTROLDAMPER",
            "fire": "FIREDAMPER",
            "smoke": "SMOKEDAMPER",
            "fireSmoke": "FIRESMOKEDAMPER",
            "gravity": "GRAVITYDAMPER",
            "relief": "RELIEFDAMPER",
        },
        "terminalType": {
            "register": "REGISTER",
            "grille": "GRILLE",
            "diffuser": "DIFFUSER",
            "louvre": "LOUVRE",
        },
        "fanType": {
            "centrifugalForwardCurved": "CENTRIFUGALFORWARDCURVED",
            "centrifugalRadial": "CENTRIFUGALRADIAL",
            "centrifugalBackwardCurved": "CENTRIFUGALBACKWARDINCLINEDCURVED",
            "centrifugalAirfoil": "CENTRIFUGALAIRFOIL",
            "tubeAxial": "TUBEAXIAL",
            "vaneAxial": "VANEAXIAL",
            "propellerAxial": "PROPELLORAXIAL",
        },
        "coilType": {
            "dxCooling": "DXCOOLINGCOIL",
            "electricHeating": "ELECTRICHEATINGCOIL",
            "gasHeating": "GASHEATINGCOIL",
            "hydronic": "HYDRONICCOIL",
            "waterCooling": "WATERCOOLINGCOIL",
            "waterHeating": "WATERHEATINGCOIL",
        },
        "heatRecoveryType": {
            "counterflowPlate": "FIXEDPLATECOUNTERFLOWEXCHANGER",
            "crossflowPlate": "FIXEDPLATECROSSFLOWEXCHANGER",
            "parallelflowPlate": "FIXEDPLATEPARALLELFLOWEXCHANGER",
            "rotaryWheel": "ROTARYWHEEL",
            "runaroundCoil": "RUNAROUNDCOILLOOP",
            "heatPipe": "HEATPIPE",
        },
    }

    @classmethod
    def predefined(cls, product: entity_instance, data: JsonObject) -> None:
        """Use declared technology and retain a meaningful role when technology is unspecified."""
        role = Authoring.text(data["role"])
        predefined = cls.DEVICES[role][1]
        specification = Authoring.object(data["mechanical"])
        for field, choices in cls.SUBTYPES.items():
            if field in specification:
                predefined = choices[Authoring.text(specification[field])]
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
        """Retain duct stock and signed pressure/temperature inputs on native products."""
        if data.get("family") != "duct" and "mechanical" not in data:
            return
        properties = IfcProperties(guid)
        IfcStandardServices.apply(
            ifc,
            product,
            identity,
            data,
            Authoring.object(data.get("mechanical", data.get("duct", {}))),
            guid,
        )
        for key, name in (
            ("mechanical", "Pset_HomeDesignMechanical"),
            ("duct", "Pset_HomeDesignDuct"),
            ("ductConditions", "Pset_HomeDesignDuctConditions"),
        ):
            if key in data:
                properties.pset(
                    ifc, product, identity, name, Authoring.object(data[key])
                )
