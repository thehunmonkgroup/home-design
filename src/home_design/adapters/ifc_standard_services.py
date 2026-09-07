"""Standard IFC4 service specifications with explicit physical measures and bounded values."""

from __future__ import annotations

from collections.abc import Callable

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.pset
from ifcopenshell.entity_instance import entity_instance

from home_design.adapters.ifc_properties import IfcProperties
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject


class IfcStandardServices:
    """Map equivalent authored meanings, retaining unmatched specifications in custom sets."""

    @staticmethod
    def scalars(native: str, data: JsonObject, specification: JsonObject) -> JsonObject:
        """Use actual circular pipe dimensions and explicitly specified capacity or nominal flow."""
        values: JsonObject = {}
        if native == "IfcPipeSegment":
            section = Authoring.object(data.get("section", {}))
            if section.get("kind") == "circle":
                diameter = number(section["diameter"], "outer diameter")
                values["OuterDiameter"] = diameter
                wall = number(data.get("wallThickness", 0), "wall thickness")
                if wall > 0 and diameter > 2 * wall:
                    values["InnerDiameter"] = diameter - 2 * wall
        capacity = {"IfcBoiler": "WaterStorageCapacity", "IfcTank": "NominalCapacity"}
        if native in capacity and "capacityL" in specification:
            values[capacity[native]] = (
                number(specification["capacityL"], "capacity") / 1000
            )
        if native in {"IfcFan", "IfcDamper"} and "airflowRateM3s" in specification:
            values["NominalAirFlowRate"] = specification["airflowRateM3s"]
        return values

    @staticmethod
    def bounds(
        native: str, specification: JsonObject
    ) -> dict[str, tuple[str, float | None, float | None]]:
        """Convert Celsius to kelvin and suction magnitudes to signed gauge pressure bounds."""
        values: dict[str, tuple[str, float | None, float | None]] = {}
        temperatures = [
            (number(specification[key], key) + 273.15 if key in specification else None)
            for key in ("minimumTemperatureC", "maximumTemperatureC")
        ]
        if any(value is not None for value in temperatures):
            values["TemperatureRange"] = (
                "IfcThermodynamicTemperatureMeasure",
                temperatures[0],
                temperatures[1],
            )
        if (
            native in {"IfcPipeSegment", "IfcPipeFitting"}
            and "pressureRatingPa" in specification
        ):
            values["PressureRange"] = (
                "IfcPressureMeasure",
                None,
                number(specification["pressureRatingPa"], "pressure rating"),
            )
        if native in {"IfcDuctSegment", "IfcDuctFitting"}:
            lower = specification.get("negativePressureRatingPa")
            upper = specification.get("positivePressureRatingPa")
            if lower is not None or upper is not None:
                values["PressureRange"] = (
                    "IfcPressureMeasure",
                    (
                        -number(lower, "negative pressure rating")
                        if lower is not None
                        else None
                    ),
                    (
                        number(upper, "positive pressure rating")
                        if upper is not None
                        else None
                    ),
                )
        return values

    @classmethod
    def apply(
        cls,
        ifc: ifcopenshell.file,
        product: entity_instance,
        identity: str,
        data: JsonObject,
        specification: JsonObject,
        guid: Callable[[str], str],
    ) -> None:
        """Apply only fields whose standard template supports the corresponding native measure."""
        native = product.is_a().removesuffix("Type")
        name = f"Pset_{native.removeprefix('Ifc')}TypeCommon"
        template = ifcopenshell.util.pset.get_template("IFC4").get_by_name(name)
        if template is None:
            return
        fields = {item.Name: item for item in template.HasPropertyTemplates}
        scalars = cls.scalars(native, data, specification)
        if "Reference" in fields:
            scalars["Reference"] = data.get("typeId", identity)
        scalars = {
            key: value
            for key, value in scalars.items()
            if key in fields and fields[key].TemplateType == "P_SINGLEVALUE"
        }
        bounded = {
            key: value
            for key, value in cls.bounds(native, specification).items()
            if key in fields
            and fields[key].TemplateType == "P_BOUNDEDVALUE"
            and fields[key].PrimaryMeasureType == value[0]
        }
        if not scalars and not bounded:
            return
        # Every supported common set has Reference, so creation also uses the
        # shared deterministic identity and type/occurrence relationship handling.
        IfcProperties(guid).pset(ifc, product, identity, name, scalars)
        exported = ifcopenshell.util.element.get_pset(
            product, name, should_inherit=False
        )
        assert isinstance(exported, dict)
        pset = ifc.by_id(exported["id"])
        properties = list(pset.HasProperties)
        for key, (measure, lower, upper) in bounded.items():
            properties.append(
                ifc.create_entity(
                    "IfcPropertyBoundedValue",
                    Name=key,
                    LowerBoundValue=(
                        ifc.create_entity(measure, lower) if lower is not None else None
                    ),
                    UpperBoundValue=(
                        ifc.create_entity(measure, upper) if upper is not None else None
                    ),
                )
            )
        pset.HasProperties = properties
