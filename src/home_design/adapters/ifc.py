"""IFC4 adapter preserving stable identity and authoring relationships."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.type
import ifcopenshell.api.unit
from ifcopenshell.entity_instance import entity_instance
from ifcopenshell.util.shape_builder import SequenceOfVectors

from home_design.constants import GUID_NAMESPACE, IFC_SCHEMA
from home_design.errors import ExportError
from home_design.geometry import vector2
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedElement, ResolvedModel


class IfcExporter:
    """Export the resolved model to semantically structured IFC4."""

    _ENTITY_CLASSES: ClassVar[dict[str, str]] = {
        "wall": "IfcWall",
        "slab": "IfcSlab",
        "roof": "IfcRoof",
        "opening": "IfcOpeningElement",
        "door": "IfcDoor",
        "window": "IfcWindow",
        "space": "IfcSpace",
        "assembly": "IfcElementAssembly",
    }
    _TYPE_CLASSES: ClassVar[dict[str, str]] = {
        "wallType": "IfcWallType",
        "slabType": "IfcSlabType",
        "roofType": "IfcRoofType",
        "doorType": "IfcDoorType",
        "windowType": "IfcWindowType",
        "spaceType": "IfcSpaceType",
    }

    def export(self, model: ResolvedModel, output_path: Path) -> None:
        """Write a deterministic IFC4 file.

        :param model: Adapter-neutral resolved model.
        :param output_path: Destination IFC path.
        :raises ExportError: If IFC creation fails.
        """
        try:
            ifc = ifcopenshell.api.project.create_file(version=IFC_SCHEMA)
            state = self._create_spatial_structure(ifc, model)
            body_context, axis_context = self._create_contexts(ifc)
            materials = self._create_materials(ifc, model.materials)
            types = self._create_types(ifc, model.types, materials)
            products = self._create_products(
                ifc, model, body_context, axis_context, types
            )
            storeys = state["storeys"]
            if not isinstance(storeys, dict):
                raise ExportError("IFC spatial structure did not produce storeys")
            self._contain_products(ifc, model, products, storeys)
            self._create_relationships(ifc, model.relationships, products)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            ifc.write(str(output_path))
        except Exception as error:
            raise ExportError(f"Cannot export IFC: {error}") from error

    def _create_spatial_structure(
        self,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
    ) -> dict[str, entity_instance | dict[str, entity_instance]]:
        project = self._root(
            ifc,
            "IfcProject",
            str(model.project.get("id")),
            str(model.project.get("name")),
        )
        ifcopenshell.api.unit.assign_unit(ifc)
        site_data = model.project.get("site")
        building_data = model.project.get("building")
        if not isinstance(site_data, dict) or not isinstance(building_data, dict):
            raise ExportError("Project site and building identities are required")
        site = self._root(
            ifc, "IfcSite", str(site_data.get("id")), str(site_data.get("name"))
        )
        building = self._root(
            ifc,
            "IfcBuilding",
            str(building_data.get("id")),
            str(building_data.get("name")),
        )
        project_relation = ifcopenshell.api.aggregate.assign_object(
            ifc, products=[site], relating_object=project
        )
        site_relation = ifcopenshell.api.aggregate.assign_object(
            ifc, products=[building], relating_object=site
        )
        self._set_relation_guid(project_relation, "rel.spatial.project-site")
        self._set_relation_guid(site_relation, "rel.spatial.site-building")
        storeys: dict[str, entity_instance] = {}
        for level_id, level_value in model.levels.items():
            if not isinstance(level_value, dict) or level_value.get("kind") != "storey":
                continue
            storey = self._root(
                ifc, "IfcBuildingStorey", level_id, str(level_value.get("name"))
            )
            elevation = level_value.get("elevation")
            storey.Elevation = (
                float(elevation) if isinstance(elevation, (int, float)) else 0.0
            )
            relation = ifcopenshell.api.aggregate.assign_object(
                ifc, products=[storey], relating_object=building
            )
            self._set_relation_guid(relation, f"rel.spatial.building-{level_id}")
            storeys[level_id] = storey
        return {
            "project": project,
            "site": site,
            "building": building,
            "storeys": storeys,
        }

    @staticmethod
    def _create_contexts(
        ifc: ifcopenshell.file,
    ) -> tuple[entity_instance, entity_instance]:
        model_context = ifcopenshell.api.context.add_context(ifc, context_type="Model")
        body_context = ifcopenshell.api.context.add_context(
            ifc,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=model_context,
        )
        plan_context = ifcopenshell.api.context.add_context(ifc, context_type="Plan")
        axis_context = ifcopenshell.api.context.add_context(
            ifc,
            context_type="Plan",
            context_identifier="Axis",
            target_view="GRAPH_VIEW",
            parent=plan_context,
        )
        return body_context, axis_context

    @staticmethod
    def _create_materials(
        ifc: ifcopenshell.file, definitions: JsonObject
    ) -> dict[str, entity_instance]:
        materials: dict[str, entity_instance] = {}
        for material_id, value in definitions.items():
            if not isinstance(value, dict):
                continue
            material = ifcopenshell.api.material.add_material(
                ifc,
                name=str(value.get("name", material_id)),
                category=(
                    str(value.get("category"))
                    if value.get("category") is not None
                    else None
                ),
                description=(
                    str(value.get("description"))
                    if value.get("description") is not None
                    else None
                ),
            )
            materials[material_id] = material
        return materials

    def _create_types(
        self,
        ifc: ifcopenshell.file,
        definitions: JsonObject,
        materials: dict[str, entity_instance],
    ) -> dict[str, entity_instance]:
        products: dict[str, entity_instance] = {}
        for type_id, value in definitions.items():
            if not isinstance(value, dict):
                continue
            ifc_class = self._TYPE_CLASSES.get(str(value.get("kind")))
            if ifc_class is None:
                continue
            product = self._root(
                ifc, ifc_class, type_id, str(value.get("name", type_id))
            )
            product.PredefinedType = "NOTDEFINED"
            material_id = value.get("material")
            if not isinstance(material_id, str):
                layers = value.get("layers")
                if isinstance(layers, list):
                    structural = next(
                        (
                            layer
                            for layer in layers
                            if isinstance(layer, dict)
                            and layer.get("function") == "structure"
                        ),
                        None,
                    )
                    if structural is not None and isinstance(
                        structural.get("material"), str
                    ):
                        material_id = structural["material"]
            if isinstance(material_id, str) and material_id in materials:
                relation = ifcopenshell.api.material.assign_material(
                    ifc,
                    products=[product],
                    type="IfcMaterial",
                    material=materials[material_id],
                )
                if isinstance(relation, entity_instance):
                    self._set_relation_guid(relation, f"rel.material.{type_id}")
            products[type_id] = product
        return products

    def _create_products(
        self,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        body_context: entity_instance,
        axis_context: entity_instance,
        types: dict[str, entity_instance],
    ) -> dict[str, entity_instance]:
        products: dict[str, entity_instance] = {}
        for element in model.elements:
            ifc_class = self._ENTITY_CLASSES[element.kind]
            product = self._root(ifc, ifc_class, element.element_id, element.name)
            self._set_predefined_type(product, element)
            body = self._body_representation(ifc, body_context, element)
            axis = self._axis_representation(ifc, axis_context, element)
            representations = [
                representation
                for representation in (axis, body)
                if representation is not None
            ]
            if representations:
                product.Representation = ifc.create_entity(
                    "IfcProductDefinitionShape",
                    Name=None,
                    Description=None,
                    Representations=representations,
                )
            pset = ifcopenshell.api.pset.add_pset(
                ifc, product=product, name="Pset_HomeDesignIdentity"
            )
            pset.GlobalId = self.stable_guid(f"pset.identity.{element.element_id}")
            for relation in product.IsDefinedBy:
                if (
                    relation.is_a("IfcRelDefinesByProperties")
                    and relation.RelatingPropertyDefinition == pset
                ):
                    self._set_relation_guid(
                        relation, f"rel.pset.identity.{element.element_id}"
                    )
            ifcopenshell.api.pset.edit_pset(
                ifc,
                pset=pset,
                properties={
                    "CanonicalId": element.element_id,
                    "ModelVersion": model.model_version,
                    "SourceRevision": model.source_revision,
                },
            )
            type_id = element.data.get("typeId")
            if isinstance(type_id, str) and type_id in types:
                relation = ifcopenshell.api.type.assign_type(
                    ifc,
                    related_objects=[product],
                    relating_type=types[type_id],
                    should_map_representations=False,
                )
                self._set_relation_guid(relation, f"rel.type.{element.element_id}")
            products[element.element_id] = product
        return products

    @staticmethod
    def _body_representation(
        ifc: ifcopenshell.file,
        context: entity_instance,
        element: ResolvedElement,
    ) -> entity_instance | None:
        if not element.meshes:
            return None
        vertices: list[SequenceOfVectors] = [
            [tuple(vertex) for vertex in mesh.vertices] for mesh in element.meshes
        ]
        faces = [[list(face) for face in mesh.faces] for mesh in element.meshes]
        return ifcopenshell.api.geometry.add_mesh_representation(
            ifc,
            context=context,
            vertices=vertices,
            faces=faces,
            unit_scale=1.0,
        )

    @staticmethod
    def _axis_representation(
        ifc: ifcopenshell.file,
        context: entity_instance,
        element: ResolvedElement,
    ) -> entity_instance | None:
        axis_value = element.data.get("axis")
        if element.kind != "wall" or not isinstance(axis_value, list):
            return None
        points = []
        for coordinate in axis_value:
            if isinstance(coordinate, list):
                point = vector2(coordinate, "wall axis coordinate")
                points.append(
                    ifc.create_entity(
                        "IfcCartesianPoint",
                        Coordinates=point,
                    )
                )
        if len(points) < 2:
            return None
        polyline = ifc.create_entity("IfcPolyline", Points=points)
        return ifc.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=context,
            RepresentationIdentifier="Axis",
            RepresentationType="Curve2D",
            Items=[polyline],
        )

    @staticmethod
    def _contain_products(
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
        storeys: dict[str, entity_instance],
    ) -> None:
        by_storey: dict[str, list[entity_instance]] = {}
        spaces_by_storey: dict[str, list[entity_instance]] = {}
        for element in model.elements:
            if element.kind == "opening" or element.storey_id is None:
                continue
            target = spaces_by_storey if element.kind == "space" else by_storey
            target.setdefault(element.storey_id, []).append(
                products[element.element_id]
            )
        for storey_id, items in by_storey.items():
            storey = storeys.get(storey_id)
            if storey is None:
                continue
            relation = ifcopenshell.api.spatial.assign_container(
                ifc,
                products=items,
                relating_structure=storey,
            )
            IfcExporter._set_relation_guid(relation, f"rel.containment.{storey_id}")
        for storey_id, spaces in spaces_by_storey.items():
            storey = storeys.get(storey_id)
            if storey is None:
                continue
            relation = ifcopenshell.api.aggregate.assign_object(
                ifc,
                products=spaces,
                relating_object=storey,
            )
            IfcExporter._set_relation_guid(relation, f"rel.spatial.{storey_id}-spaces")

    def _create_relationships(
        self,
        ifc: ifcopenshell.file,
        relationships: JsonObject,
        products: dict[str, entity_instance],
    ) -> None:
        handlers: dict[
            str,
            Callable[
                [ifcopenshell.file, str, JsonObject, dict[str, entity_instance]], None
            ],
        ] = {
            "voids": self._voids,
            "fills": self._fills,
            "joins": self._joins,
            "supports": self._connects,
            "attaches": self._connects,
            "bounds": self._bounds,
            "aggregates": self._aggregates,
        }
        for relationship_id, value in relationships.items():
            if not isinstance(value, dict):
                continue
            handler = handlers.get(str(value.get("kind")))
            if handler is not None:
                handler(ifc, relationship_id, value, products)

    def _voids(
        self,
        ifc: ifcopenshell.file,
        relationship_id: str,
        value: JsonObject,
        products: dict[str, entity_instance],
    ) -> None:
        relation = ifcopenshell.api.feature.add_feature(
            ifc,
            feature=products[str(value.get("opening"))],
            element=products[str(value.get("host"))],
        )
        self._name_relation(relation, relationship_id, value)

    def _fills(
        self,
        ifc: ifcopenshell.file,
        relationship_id: str,
        value: JsonObject,
        products: dict[str, entity_instance],
    ) -> None:
        relation = ifcopenshell.api.feature.add_filling(
            ifc,
            opening=products[str(value.get("opening"))],
            element=products[str(value.get("element"))],
        )
        self._name_relation(relation, relationship_id, value)

    def _joins(
        self,
        ifc: ifcopenshell.file,
        relationship_id: str,
        value: JsonObject,
        products: dict[str, entity_instance],
    ) -> None:
        a = value.get("a")
        b = value.get("b")
        if not isinstance(a, dict) or not isinstance(b, dict):
            return
        relation = ifc.create_entity(
            "IfcRelConnectsPathElements",
            GlobalId=self.stable_guid(relationship_id),
            Name=(
                str(value.get("name"))
                if value.get("name") is not None
                else relationship_id
            ),
            Description=(
                str(value.get("description"))
                if value.get("description") is not None
                else None
            ),
            ConnectionGeometry=None,
            RelatingElement=products[str(a.get("element"))],
            RelatedElement=products[str(b.get("element"))],
            RelatingPriorities=[],
            RelatedPriorities=[],
            RelatedConnectionType=self._connection_type(str(b.get("at"))),
            RelatingConnectionType=self._connection_type(str(a.get("at"))),
        )
        self._set_relation_guid(relation, relationship_id)

    def _connects(
        self,
        ifc: ifcopenshell.file,
        relationship_id: str,
        value: JsonObject,
        products: dict[str, entity_instance],
    ) -> None:
        if value.get("kind") == "supports":
            relating_id, related_id = str(value.get("support")), str(
                value.get("supported")
            )
        else:
            relating_id, related_id = str(value.get("primary")), str(
                value.get("attached")
            )
        ifc.create_entity(
            "IfcRelConnectsElements",
            GlobalId=self.stable_guid(relationship_id),
            Name=(
                str(value.get("name"))
                if value.get("name") is not None
                else relationship_id
            ),
            Description=(
                str(value.get("description"))
                if value.get("description") is not None
                else None
            ),
            ConnectionGeometry=None,
            RelatingElement=products[relating_id],
            RelatedElement=products[related_id],
        )

    def _bounds(
        self,
        ifc: ifcopenshell.file,
        relationship_id: str,
        value: JsonObject,
        products: dict[str, entity_instance],
    ) -> None:
        ifc.create_entity(
            "IfcRelSpaceBoundary",
            GlobalId=self.stable_guid(relationship_id),
            Name=(
                str(value.get("name"))
                if value.get("name") is not None
                else relationship_id
            ),
            Description=(
                str(value.get("description"))
                if value.get("description") is not None
                else None
            ),
            RelatingSpace=products[str(value.get("space"))],
            RelatedBuildingElement=products[str(value.get("element"))],
            ConnectionGeometry=None,
            PhysicalOrVirtualBoundary=(
                "PHYSICAL" if value.get("boundaryType") == "physical" else "VIRTUAL"
            ),
            InternalOrExternalBoundary="INTERNAL",
        )

    def _aggregates(
        self,
        ifc: ifcopenshell.file,
        relationship_id: str,
        value: JsonObject,
        products: dict[str, entity_instance],
    ) -> None:
        parts = value.get("parts")
        if not isinstance(parts, list):
            return
        relation = ifcopenshell.api.aggregate.assign_object(
            ifc,
            products=[products[str(part)] for part in parts],
            relating_object=products[str(value.get("assembly"))],
        )
        self._name_relation(relation, relationship_id, value)

    @staticmethod
    def _set_predefined_type(
        product: entity_instance, element: ResolvedElement
    ) -> None:
        if element.kind == "slab":
            product.PredefinedType = {
                "foundation": "BASESLAB",
                "roofSlab": "ROOF",
                "landing": "LANDING",
            }.get(str(element.data.get("role")), "FLOOR")
        elif element.kind == "assembly":
            product.AssemblyPlace = "SITE"
            product.PredefinedType = "USERDEFINED"
            product.ObjectType = str(element.data.get("assemblyType", "Assembly"))
        elif hasattr(product, "PredefinedType"):
            product.PredefinedType = "NOTDEFINED"

    @staticmethod
    def _connection_type(at: str) -> str:
        return {"start": "ATSTART", "end": "ATEND", "path": "ATPATH"}.get(
            at, "NOTDEFINED"
        )

    @staticmethod
    def _root(
        ifc: ifcopenshell.file, ifc_class: str, canonical_id: str, name: str
    ) -> entity_instance:
        entity = ifcopenshell.api.root.create_entity(
            ifc, ifc_class=ifc_class, name=name
        )
        entity.GlobalId = IfcExporter.stable_guid(canonical_id)
        if hasattr(entity, "Tag"):
            entity.Tag = canonical_id
        return entity

    @staticmethod
    def _name_relation(
        relation: entity_instance | None, canonical_id: str, value: JsonObject
    ) -> None:
        if relation is None:
            return
        IfcExporter._set_relation_guid(relation, canonical_id)
        relation.Name = (
            str(value.get("name")) if value.get("name") is not None else canonical_id
        )
        relation.Description = (
            str(value.get("description"))
            if value.get("description") is not None
            else None
        )

    @staticmethod
    def _set_relation_guid(relation: entity_instance | None, canonical_id: str) -> None:
        if relation is not None:
            relation.GlobalId = IfcExporter.stable_guid(canonical_id)

    @staticmethod
    def stable_guid(canonical_id: str) -> str:
        """Return a deterministic IFC-compressed GUID.

        :param canonical_id: Stable canonical object or relation ID.
        :returns: 22-character IFC GUID.
        """
        value = uuid.uuid5(uuid.NAMESPACE_URL, f"{GUID_NAMESPACE}:{canonical_id}")
        return ifcopenshell.guid.compress(value.hex)
