"""Lossless canonical specifications and material assemblies in IFC4."""

from __future__ import annotations

import json
from collections.abc import Callable

import ifcopenshell
import ifcopenshell.api.material
import ifcopenshell.api.pset
from ifcopenshell.entity_instance import entity_instance

from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.layers import LayerAssembly


class IfcProperties:
    """Export reusable layers and unit-explicit specifications without data loss."""

    def __init__(self, guid: Callable[[str], str]) -> None:
        """Use the adapter's deterministic source identity namespace."""
        self.guid: Callable[[str], str] = guid

    def pset(
        self,
        ifc: ifcopenshell.file,
        product: entity_instance,
        canonical_id: str,
        name: str,
        values: JsonObject,
    ) -> None:
        """Preserve scalar values directly and structured values as JSON text."""
        if not values:
            return
        pset = ifcopenshell.api.pset.add_pset(ifc, product=product, name=name)
        pset.GlobalId = self.guid(f"pset.{name}.{canonical_id}")
        for relation in getattr(product, "IsDefinedBy", ()):
            if (
                relation.is_a("IfcRelDefinesByProperties")
                and relation.RelatingPropertyDefinition == pset
            ):
                relation.GlobalId = self.guid(f"rel.pset.{name}.{canonical_id}")
        properties = {
            key: (
                json.dumps(value, sort_keys=True, ensure_ascii=False)
                if isinstance(value, (dict, list)) or value is None
                else value
            )
            for key, value in values.items()
        }
        ifcopenshell.api.pset.edit_pset(ifc, pset=pset, properties=properties)

    def layers(
        self,
        ifc: ifcopenshell.file,
        product: entity_instance,
        type_id: str,
        definition: JsonObject,
        materials: dict[str, entity_instance],
    ) -> None:
        """Associate complete ordered material layers with a reusable IFC type."""
        layers: list[entity_instance] = []
        for layer in LayerAssembly.layers(definition):
            material = materials.get(layer.material or "")
            if layer.components:
                material = ifcopenshell.api.material.add_material(
                    ifc, name=str(layer.source.get("name")), category="Framed cavity"
                )
                property_value = ifc.create_entity(
                    "IfcPropertySingleValue",
                    Name="ConcurrentMaterials",
                    NominalValue=ifc.create_entity(
                        "IfcText",
                        json.dumps(
                            [component.source for component in layer.components],
                            sort_keys=True,
                        ),
                    ),
                )
                ifc.create_entity(
                    "IfcMaterialProperties",
                    Name="Pset_HomeDesignComposition",
                    Properties=[property_value],
                    Material=material,
                )
            layers.append(
                ifc.create_entity(
                    "IfcMaterialLayer",
                    Material=material,
                    LayerThickness=layer.thickness,
                    Description=layer.identity,
                    Name=str(layer.source.get("name")),
                    Category=str(layer.source.get("function")),
                )
            )
        layer_set = ifc.create_entity(
            "IfcMaterialLayerSet",
            MaterialLayers=layers,
            LayerSetName=str(definition.get("name")),
            Description=str(definition.get("layerOrder")),
        )
        relation = ifcopenshell.api.material.assign_material(
            ifc, products=[product], type="IfcMaterialLayerSet", material=layer_set
        )
        if isinstance(relation, entity_instance):
            relation.GlobalId = self.guid(f"rel.material.{type_id}")

    @staticmethod
    def material_data(
        ifc: ifcopenshell.file,
        material: entity_instance,
        material_id: str,
        definition: JsonObject,
    ) -> None:
        """Preserve canonical material identity, appearance and engineering properties."""
        ifc.create_entity(
            "IfcMaterialProperties",
            Name="Pset_HomeDesignMaterial",
            Material=material,
            Properties=[
                ifc.create_entity(
                    "IfcPropertySingleValue",
                    Name=name,
                    NominalValue=ifc.create_entity("IfcText", value),
                )
                for name, value in (
                    ("CanonicalId", material_id),
                    (
                        "Definition",
                        json.dumps(definition, sort_keys=True, ensure_ascii=False),
                    ),
                )
            ],
        )

    @staticmethod
    def style(
        ifc: ifcopenshell.file,
        item: entity_instance,
        material: JsonObject,
        glass: bool = False,
    ) -> None:
        """Style a body item using the same material appearance as the GLB."""
        appearance = Authoring.object(material.get("appearance", {}))
        color = str(appearance.get("color", "#87cde1" if glass else "#b8b4ac"))
        rgb = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        opacity = appearance.get("opacity", 0.35 if glass else 1.0)
        opacity = float(opacity) if isinstance(opacity, (int, float)) else 1.0
        shading = ifc.create_entity(
            "IfcSurfaceStyleRendering",
            SurfaceColour=ifc.create_entity(
                "IfcColourRgb", Red=rgb[0], Green=rgb[1], Blue=rgb[2]
            ),
            Transparency=1 - opacity,
            ReflectanceMethod="NOTDEFINED",
        )
        style = ifc.create_entity(
            "IfcSurfaceStyle",
            Name=str(material.get("name", "Glass" if glass else "Default")),
            Side="BOTH",
            Styles=[shading],
        )
        ifc.create_entity("IfcStyledItem", Item=item, Styles=[style])
