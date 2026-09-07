"""Native reinforcement dimensions and net construction-part quantities in IFC4."""

from __future__ import annotations

import math
from collections.abc import Callable

import ifcopenshell
from ifcopenshell.entity_instance import entity_instance

from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedModel
from home_design.solids import SolidOperations
from home_design.adapters.ifc_units import IfcUnits


class IfcReinforcement:
    """Preserve authored steel specifications independently of tessellated net geometry."""

    @staticmethod
    def attributes(product: entity_instance, data: JsonObject) -> None:
        """Assign native bar/mesh dimensions to an occurrence or reusable type."""
        bar = product.is_a("IfcReinforcingBar") or product.is_a("IfcReinforcingBarType")
        if bar:
            role = str(data["role"])
            product.PredefinedType = {"tie": "LIGATURE", "other": "USERDEFINED"}.get(
                role, role.upper()
            )
            diameter = number(data["nominalDiameter"], "bar diameter")
            product.NominalDiameter = diameter
            product.CrossSectionArea = IfcUnits.area(math.pi * diameter**2 / 4)
            product.BarSurface = (
                "TEXTURED"
                if data.get("barSurface", data.get("surface")) == "ribbed"
                else "PLAIN"
            )
            if "centerlineLengthMm" in data:
                product.BarLength = number(data["centerlineLengthMm"], "bar length")
        else:
            role = "mesh"
            product.PredefinedType = "USERDEFINED"
            for prefix in ("longitudinal", "transverse"):
                diameter = number(data[f"{prefix}Diameter"], "wire diameter")
                setattr(product, f"{prefix.title()}BarNominalDiameter", diameter)
                setattr(
                    product,
                    f"{prefix.title()}BarCrossSectionArea",
                    IfcUnits.area(math.pi * diameter**2 / 4),
                )
                setattr(
                    product,
                    f"{prefix.title()}BarSpacing",
                    number(data[f"{prefix}Spacing"], "wire spacing"),
                )
            if "length" in data:
                product.MeshLength = number(data["length"], "mesh length")
                product.MeshWidth = number(data["width"], "mesh width")
        if product.is_a("IfcElementType"):
            product.ElementType = role
        else:
            product.ObjectType = role
            product.SteelGrade = data.get("steelGrade")

    @staticmethod
    def quantities(
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        guid: Callable[[str], str],
    ) -> None:
        """Publish final material volumes with nominal uncut bar lengths and wire counts."""
        for element in model.elements:
            if element.kind not in {"reinforcingBar", "reinforcingMesh", "masonryPart"}:
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
            if element.kind == "reinforcingBar":
                quantities.append(
                    ifc.create_entity(
                        "IfcQuantityLength",
                        Name="NominalLength",
                        LengthValue=number(
                            element.data["centerlineLengthMm"], "bar length"
                        ),
                    )
                )
            if element.kind == "reinforcingMesh":
                quantities.append(
                    ifc.create_entity(
                        "IfcQuantityCount",
                        Name="WireCount",
                        CountValue=number(
                            element.data["longitudinalCount"], "longitudinal count"
                        )
                        + number(element.data["transverseCount"], "transverse count"),
                    )
                )
            quantity_set = ifc.create_entity(
                "IfcElementQuantity",
                GlobalId=guid(f"qto.parts.{element.element_id}"),
                Name="Qto_HomeDesignConstructionPart",
                MethodOfMeasurement="Net modeled geometry; nominal lengths/counts retain authored uncut intent",
                Quantities=quantities,
            )
            ifc.create_entity(
                "IfcRelDefinesByProperties",
                GlobalId=guid(f"rel.qto.parts.{element.element_id}"),
                RelatedObjects=[products[element.element_id]],
                RelatingPropertyDefinition=quantity_set,
            )
