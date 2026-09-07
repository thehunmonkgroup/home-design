"""Applicable IFC4 standard quantities derived from authored stock and resolved material."""

from __future__ import annotations

import math
from collections.abc import Callable

import ifcopenshell
import ifcopenshell.util.pset
from ifcopenshell.entity_instance import entity_instance

from home_design.adapters.ifc_units import IfcUnits
from home_design.construction import Authoring, ConstructionGeometry
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedElement
from home_design.solids import SolidOperations


class IfcQuantities:
    """Use standard template names only where their quantity meaning and available data agree."""

    EXCLUDED: frozenset[str] = frozenset(
        {
            "terrain",
            "space",
            "opening",
            "penetration",
            "clearanceZone",
            "barrierCheck",
            "load",
            "detail",
        }
    )

    @staticmethod
    def section_area(
        section: JsonObject, wall: float = 0, service: bool = False
    ) -> float:
        """Measure an authored section analytically, independently of mesh approximation tolerance."""
        if section["kind"] == "circle":
            return (
                math.pi
                * (number(section["diameter"], "section diameter") / 2 - wall) ** 2
            )
        if service:
            return (number(section["width"], "section width") - 2 * wall) * (
                number(section["height"], "section height") - 2 * wall
            )
        return ConstructionGeometry.section(section).area

    @classmethod
    def values(cls, element: ResolvedElement) -> dict[str, tuple[str, float]]:
        """Return available quantities with their IFC measure kinds and declared project-unit values."""
        data = element.data
        values: dict[str, tuple[str, float]] = {
            "NetVolume": (
                "VOLUME",
                IfcUnits.volume(
                    sum(SolidOperations.volume(mesh) for mesh in element.meshes)
                ),
            )
        }
        if element.kind in {"member", "curvedMember"}:
            length = data.get("stockLengthMm", data.get("memberLength"))
            if length is not None:
                values["Length"] = ("LENGTH", number(length, "nominal member length"))
            if "section" in data:
                values["CrossSectionArea"] = (
                    "AREA",
                    IfcUnits.area(cls.section_area(Authoring.object(data["section"]))),
                )
        if element.kind == "serviceRoute":
            values["Length"] = (
                "LENGTH",
                number(data["centerlineLengthMm"], "route length"),
            )
            section = Authoring.object(data["section"])
            gross = cls.section_area(section, service=True)
            wall = number(data.get("wallThickness", 0), "route wall thickness")
            net = gross - cls.section_area(section, wall, True) if wall else gross
            if data["family"] in {"pipe", "duct"}:
                values["GrossCrossSectionArea"] = ("AREA", IfcUnits.area(gross))
                values["NetCrossSectionArea"] = ("AREA", IfcUnits.area(net))
            else:
                values["CrossSectionArea"] = ("AREA", IfcUnits.area(net))
        if element.kind == "reinforcingBar":
            values["Count"] = ("COUNT", 1.0)
            values["Length"] = (
                "LENGTH",
                number(data["centerlineLengthMm"], "nominal bar length"),
            )
        return values

    @classmethod
    def apply(
        cls,
        ifc: ifcopenshell.file,
        elements: tuple[ResolvedElement, ...],
        products: dict[str, entity_instance],
        guid: Callable[[str], str],
    ) -> None:
        """Export only available measures explicitly defined by applicable IFC4 quantity templates."""
        templates = ifcopenshell.util.pset.get_template("IFC4")
        for element in elements:
            if element.kind in cls.EXCLUDED or not element.meshes:
                continue
            product = products[element.element_id]
            values = cls.values(element)
            for template in templates.get_applicable(product.is_a(), qto_only=True):
                if not template.Name.startswith("Qto_"):
                    continue
                quantities: list[entity_instance] = []
                for field in template.HasPropertyTemplates:
                    if field.Name not in values:
                        continue
                    kind, value = values[field.Name]
                    if field.TemplateType != f"Q_{kind}":
                        continue
                    quantities.append(
                        ifc.create_entity(
                            f"IfcQuantity{kind.title()}",
                            Name=field.Name,
                            **{f"{kind.title()}Value": value},
                        )
                    )
                if not quantities:
                    continue
                identity = f"qto.standard.{element.element_id}/{template.Name}"
                quantity_set = ifc.create_entity(
                    "IfcElementQuantity",
                    GlobalId=guid(identity),
                    Name=template.Name,
                    MethodOfMeasurement="Nominal stock lengths/sections; final resolved net material volume",
                    Quantities=quantities,
                )
                ifc.create_entity(
                    "IfcRelDefinesByProperties",
                    GlobalId=guid(f"rel.{identity}"),
                    RelatedObjects=[product],
                    RelatingPropertyDefinition=quantity_set,
                )
