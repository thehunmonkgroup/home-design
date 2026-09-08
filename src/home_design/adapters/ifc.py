"""IFC4 adapter preserving stable identity and authoring relationships."""

from __future__ import annotations

import uuid
from dataclasses import replace
from collections.abc import Callable
from pathlib import Path
from itertools import combinations
from typing import ClassVar

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.material
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.type
from ifcopenshell.entity_instance import entity_instance

from home_design.constants import GUID_NAMESPACE, IFC_SCHEMA
from home_design.capabilities import ComponentRegistry
from home_design.errors import ExportError
from home_design.geometry import number, vector2, vector3
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedElement, ResolvedModel
from home_design.adapters.ifc_properties import IfcProperties
from home_design.adapters.ifc_electrical import IfcElectrical
from home_design.adapters.ifc_plumbing import IfcPlumbing
from home_design.adapters.ifc_mechanical import IfcMechanical
from home_design.adapters.ifc_hardware import IfcHardware
from home_design.adapters.ifc_reinforcement import IfcReinforcement
from home_design.adapters.ifc_mounted_parts import IfcMountedParts
from home_design.adapters.ifc_services import IfcServices
from home_design.adapters.ifc_units import IfcUnits
from home_design.adapters.ifc_structural import IfcStructural
from home_design.adapters.ifc_quantities import IfcQuantities
from home_design.mounted_parts import MountedParts
from home_design.member_assemblies import MemberAssemblies
from home_design.construction import Authoring
from home_design.layers import LayerAssembly
from home_design.solids import SolidOperations


class IfcExporter:
    """Export the resolved model to semantically structured IFC4."""

    _ENTITY_CLASSES: ClassVar[dict[str, str]] = {
        kind: item.ifc_class for kind, item in ComponentRegistry.components.items()
    }
    _TYPE_CLASSES: ClassVar[dict[str, str]] = ComponentRegistry.type_classes()

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
            types.update(self._create_member_types(ifc, model, materials))
            types.update(self._create_assembly_types(ifc, model))
            products = self._create_products(
                ifc, model, body_context, axis_context, types
            )
            storeys = state["storeys"]
            if not isinstance(storeys, dict):
                raise ExportError("IFC spatial structure did not produce storeys")
            self._contain_products(ifc, model, products, storeys)
            self._create_relationships(ifc, model.relationships, products)
            self._create_member_connections(ifc, model, products)
            IfcHardware.apply(ifc, model, products, self.stable_guid)
            IfcReinforcement.quantities(ifc, model, products, self.stable_guid)
            IfcMountedParts.apply(ifc, model, products, self.stable_guid)
            IfcServices.apply(ifc, model, products, self.stable_guid)
            IfcQuantities.apply(
                ifc, self._expanded_elements(model), products, self.stable_guid
            )
            for element in model.elements:
                if element.kind == "penetration":
                    self._voids(
                        ifc,
                        f"{element.element_id}/voids",
                        {
                            "host": element.data["host"],
                            "opening": element.element_id,
                        },
                        products,
                    )
                for value in Authoring.array(
                    element.data.get("cavityContributions", [])
                ):
                    contribution = Authoring.object(value)
                    host_id = Authoring.text(contribution.get("host"))
                    layer = contribution.get("layerId", contribution["layer"])
                    layer_key = LayerAssembly.export_key(layer)
                    self._connects(
                        ifc,
                        f"{element.element_id}/cavity/{host_id}/{layer_key}",
                        {
                            "kind": "attaches",
                            "primary": host_id,
                            "attached": element.element_id,
                            "name": f"Cavity layer {layer} ownership",
                        },
                        products,
                    )
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
        IfcProperties(self.stable_guid).pset(
            ifc,
            project,
            str(model.project.get("id")),
            "Pset_HomeDesignProject",
            {
                "requirements": list(model.requirements),
                "relationships": model.relationships,
                "coordinateSystem": model.coordinate_system,
            },
        )
        IfcUnits.assign(ifc)
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
            IfcProperties.material_data(ifc, material, material_id, value)
        return materials

    @classmethod
    def _native_class(cls, kind: str, data: JsonObject) -> str | None:
        """Choose the same native family for reusable types and their physical occurrences."""
        if kind in {"envelopePart", "envelopePartType"}:
            native = IfcMountedParts.envelope_class(data)
            return native + "Type" if kind.endswith("Type") else native
        if kind in {
            "serviceRoute",
            "serviceFitting",
            "serviceDevice",
            "serviceRouteType",
            "serviceFittingType",
            "serviceDeviceType",
        }:
            native = IfcServices.geometry_class(kind, data)
            return native + "Type" if kind.endswith("Type") else native
        if kind in {"member", "curvedMember"}:
            return IfcStructural.classification(data)[0]
        return cls._TYPE_CLASSES.get(kind) or cls._ENTITY_CLASSES.get(kind)

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
            ifc_class = self._native_class(str(value.get("kind")), value)
            if ifc_class is None:
                continue
            product = self._root(
                ifc, ifc_class, type_id, str(value.get("name", type_id))
            )
            if hasattr(product, "PredefinedType"):
                product.PredefinedType = "NOTDEFINED"
            if value.get("kind") in {
                "serviceRouteType",
                "serviceFittingType",
                "serviceDeviceType",
            }:
                IfcServices.geometry_predefined(str(value["kind"]), product, value)
            properties = IfcProperties(self.stable_guid)
            properties.pset(ifc, product, type_id, "Pset_HomeDesignType", value)
            IfcElectrical.properties(ifc, product, type_id, value, self.stable_guid)
            IfcPlumbing.properties(ifc, product, type_id, value, self.stable_guid)
            IfcMechanical.properties(ifc, product, type_id, value, self.stable_guid)
            material_id = value.get("material")
            if isinstance(value.get("layers"), list):
                properties.layers(ifc, product, type_id, value, materials)
            elif isinstance(material_id, str) and material_id in materials:
                relation = ifcopenshell.api.material.assign_material(
                    ifc,
                    products=[product],
                    type="IfcMaterial",
                    material=materials[material_id],
                )
                if isinstance(relation, entity_instance):
                    self._set_relation_guid(relation, f"rel.material.{type_id}")
            products[type_id] = product
            if value.get("kind") in {
                "accessoryType",
                "envelopePartType",
                "serviceInsulationType",
            }:
                IfcMountedParts.predefined(
                    product, {**value, "role": value.get("role", "insulation")}
                )
            if value.get("kind") in {"reinforcingBarType", "reinforcingMeshType"}:
                IfcReinforcement.attributes(product, value)
            if value.get("kind") == "masonryPartType":
                product.PredefinedType = "USERDEFINED"
                product.ElementType = str(value["role"])
            if value.get("kind") in {"hardwareType", "fastenerType"}:
                IfcHardware.predefined(product, value)
        return products

    def _create_member_types(
        self,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        materials: dict[str, entity_instance],
    ) -> dict[str, entity_instance]:
        """Create only used role variants, preserving stock identity and matching occurrence classes."""
        products: dict[str, entity_instance] = {}
        for element in self._expanded_elements(model):
            if element.kind not in {"member", "curvedMember"}:
                continue
            type_id = Authoring.text(element.data["typeId"])
            role = IfcStructural.role(element.data)
            key = f"{type_id}|{role}"
            if key in products:
                continue
            definition = Authoring.object(model.types[type_id])
            identity = f"{type_id}/ifc/{role}"
            product = self._root(
                ifc,
                IfcStructural.classification(element.data)[0] + "Type",
                identity,
                Authoring.text(definition["name"]),
            )
            IfcStructural.predefined(product, element.data)
            IfcProperties(self.stable_guid).pset(
                ifc,
                product,
                identity,
                "Pset_HomeDesignType",
                {**definition, "canonicalTypeId": type_id, "constructionRole": role},
            )
            material_id = Authoring.text(definition["material"])
            relation = ifcopenshell.api.material.assign_material(
                ifc,
                products=[product],
                type="IfcMaterial",
                material=materials[material_id],
            )
            if isinstance(relation, entity_instance):
                self._set_relation_guid(relation, f"rel.material.{identity}")
            products[key] = product
        return products

    def _create_assembly_types(
        self, ifc: ifcopenshell.file, model: ResolvedModel
    ) -> dict[str, entity_instance]:
        """Keep host-dependent wall/floor/roof assembly roles on matching reusable type variants."""
        products: dict[str, entity_instance] = {}
        for element in model.elements:
            if element.kind not in {"wallFraming", "planarFraming"}:
                continue
            type_id = Authoring.text(element.data["typeId"])
            role = Authoring.text(element.data["assemblyType"])
            key = f"{type_id}|{role}"
            if key in products:
                continue
            definition = Authoring.object(model.types[type_id])
            identity = f"{type_id}/ifc/{role}"
            product = self._root(
                ifc,
                "IfcElementAssemblyType",
                identity,
                Authoring.text(definition["name"]),
            )
            IfcStructural.assembly_predefined(product, element.data)
            IfcProperties(self.stable_guid).pset(
                ifc,
                product,
                identity,
                "Pset_HomeDesignType",
                {**definition, "canonicalTypeId": type_id, "assemblyType": role},
            )
            products[key] = product
        return products

    @staticmethod
    def _product_type_key(element: ResolvedElement) -> str | None:
        """Select an exact role variant where IFC type assignment carries the occurrence function."""
        identity = element.data.get("typeId")
        if not isinstance(identity, str) or element.kind == "framing":
            return None
        if element.kind in {"member", "curvedMember"}:
            return f"{identity}|{IfcStructural.role(element.data)}"
        if element.kind in {"wallFraming", "planarFraming"}:
            return f"{identity}|{element.data['assemblyType']}"
        return identity

    def _create_products(
        self,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        body_context: entity_instance,
        axis_context: entity_instance,
        types: dict[str, entity_instance],
    ) -> dict[str, entity_instance]:
        products: dict[str, entity_instance] = {}
        for element in self._expanded_elements(model):
            ifc_class = self._native_class(element.kind, element.data)
            if ifc_class is None:
                raise ExportError(f"No native IFC class for {element.kind}")
            product = self._root(ifc, ifc_class, element.element_id, element.name)
            self._set_predefined_type(product, element)
            if element.kind in {"member", "curvedMember"}:
                IfcStructural.predefined(product, element.data)
            IfcElectrical.properties(
                ifc, product, element.element_id, element.data, self.stable_guid
            )
            IfcPlumbing.properties(
                ifc, product, element.element_id, element.data, self.stable_guid
            )
            IfcMechanical.properties(
                ifc, product, element.element_id, element.data, self.stable_guid
            )
            if element.kind in {"serviceRoute", "serviceFitting", "serviceDevice"}:
                IfcServices.geometry_predefined(element.kind, product, element.data)
            if element.kind in MountedParts.KINDS:
                IfcMountedParts.predefined(product, element.data)
            if element.kind in {"reinforcingBar", "reinforcingMesh"}:
                IfcReinforcement.attributes(product, element.data)
            if element.kind == "masonryPart":
                product.PredefinedType = "USERDEFINED"
                product.ObjectType = str(element.data["role"])
            if element.kind in {"hardware", "fastenerGroup"}:
                IfcHardware.predefined(product, element.data)
            if element.kind in {"door", "window"}:
                opening = model.element(Authoring.text(element.data["openingId"]))
                product.OverallWidth = number(opening.data["width"], "opening width")
                product.OverallHeight = number(opening.data["height"], "opening height")
            body = self._body_representation(ifc, body_context, element)
            self._style_body(ifc, body, element, model.materials)
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
            type_id = self._product_type_key(element)
            IfcProperties(self.stable_guid).pset(
                ifc, product, element.element_id, "Pset_HomeDesignData", element.data
            )
            if isinstance(type_id, str) and type_id in types:
                relation = ifcopenshell.api.type.assign_type(
                    ifc,
                    related_objects=[product],
                    relating_type=types[type_id],
                    should_map_representations=False,
                )
                self._set_relation_guid(relation, f"rel.type.{element.element_id}")
            products[element.element_id] = product
        for element in model.elements:
            if element.kind == "framing" or element.kind in MemberAssemblies.KINDS:
                children = [
                    product
                    for key, product in products.items()
                    if key.startswith(f"{element.element_id}/member/")
                ]
                if children:
                    relation = ifcopenshell.api.aggregate.assign_object(
                        ifc,
                        products=children,
                        relating_object=products[element.element_id],
                    )
                    self._set_relation_guid(
                        relation, f"rel.framing.{element.element_id}"
                    )
        return products

    @staticmethod
    def _expanded_elements(model: ResolvedModel) -> tuple[ResolvedElement, ...]:
        """Export repeated members as typed children with stable source-derived IDs."""
        elements: list[ResolvedElement] = []
        for element in model.elements:
            if element.kind in MemberAssemblies.CHILD_KINDS:
                elements.append(replace(element, meshes=()))
                elements.extend(MemberAssemblies.children(element))
                continue
            elements.append(element)
        return tuple(elements)

    @staticmethod
    def _style_body(
        ifc: ifcopenshell.file,
        body: entity_instance | None,
        element: ResolvedElement,
        materials: JsonObject,
    ) -> None:
        """Apply physical material appearance or translucent nonmaterial coordination styling."""
        if body is None:
            return
        for item, mesh in zip(body.Items, element.meshes):
            material: JsonObject = Authoring.object(
                materials.get(mesh.material_id or "", {})
            )
            if mesh.role == "coordination":
                material = {
                    "name": "Coordination volume",
                    "appearance": {"color": "#9b5fe6", "opacity": 45 / 255},
                }
            IfcProperties.style(
                ifc, item, material, mesh.role in {"window-glass", "door-glass"}
            )

    @staticmethod
    def _body_representation(
        ifc: ifcopenshell.file,
        context: entity_instance,
        element: ResolvedElement,
    ) -> entity_instance | None:
        if not element.meshes:
            return None
        items = []
        for mesh in element.meshes:
            if (
                element.kind == "serviceRoute"
                and element.data.get("family") == "cable"
                and len(set(mesh.vertices)) < len(mesh.vertices)
            ):
                mesh = SolidOperations.regularize(mesh)
            coordinates = ifc.create_entity(
                "IfcCartesianPointList3D", CoordList=mesh.vertices
            )
            faces = [
                ifc.create_entity(
                    "IfcIndexedPolygonalFace",
                    CoordIndex=tuple(index + 1 for index in face),
                )
                for face in mesh.faces
            ]
            items.append(
                ifc.create_entity(
                    "IfcPolygonalFaceSet",
                    Coordinates=coordinates,
                    Closed=element.kind != "terrain",
                    Faces=faces,
                )
            )
        return ifc.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=context,
            RepresentationIdentifier="Body",
            RepresentationType="Tessellation",
            Items=items,
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
            if element.kind in {"opening", "penetration"} or element.storey_id is None:
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
            "drainsTo": self._connects,
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

    def _create_member_connections(
        self,
        ifc: ifcopenshell.file,
        model: ResolvedModel,
        products: dict[str, entity_instance],
    ) -> None:
        """Export authored member-node joints and declared trimming interfaces."""
        for element in model.elements:
            if element.kind != "memberAssembly":
                continue
            prefix = f"{element.element_id}/member/"
            for value in Authoring.array(element.data["joints"]):
                joint = Authoring.object(value)
                parts = [
                    Authoring.text(part)
                    for part in Authoring.array(joint["parts"])
                    if prefix + Authoring.text(part) in products
                ]
                for first, second in combinations(parts, 2):
                    self._connects(
                        ifc,
                        f"{element.element_id}/joint/{joint['key']}/{first}/{second}",
                        {
                            "primary": prefix + first,
                            "attached": prefix + second,
                            "name": f"Authored node {joint['key']}",
                            "point": joint["point"],
                        },
                        products,
                    )
            for value in Authoring.array(element.data["members"]):
                member = Authoring.object(value)
                for target in Authoring.array(member.get("trimAgainst", [])):
                    if prefix + str(target) not in products:
                        continue
                    self._connects(
                        ifc,
                        f"{element.element_id}/trim/{member['key']}/{target}",
                        {
                            "primary": prefix + str(target),
                            "attached": prefix + str(member["key"]),
                            "name": "Authored trimming interface",
                        },
                        products,
                    )

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
        elif value.get("kind") == "drainsTo":
            relating_id, related_id = str(value.get("source")), str(value.get("target"))
        else:
            relating_id, related_id = str(value.get("primary")), str(
                value.get("attached")
            )
        geometry = None
        if "point" in value:
            point = ifc.create_entity(
                "IfcCartesianPoint",
                Coordinates=vector3(value["point"], "connection point"),
            )
            geometry = ifc.create_entity(
                "IfcConnectionPointGeometry", PointOnRelatingElement=point
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
            ConnectionGeometry=geometry,
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
        if element.kind == "penetration":
            product.PredefinedType = (
                "RECESS"
                if element.data.get("purpose") in {"recess", "notch", "bearingSeat"}
                else "OPENING"
            )
        elif element.kind == "serviceInsulation":
            product.PredefinedType = "INSULATION"
        elif element.kind == "slab":
            product.PredefinedType = {
                "foundation": "BASESLAB",
                "roofSlab": "ROOF",
                "landing": "LANDING",
            }.get(str(element.data.get("role")), "FLOOR")
        elif (
            element.kind in {"assembly", "framing"}
            or element.kind in MemberAssemblies.KINDS
        ):
            product.AssemblyPlace = "SITE"
            IfcStructural.assembly_predefined(product, element.data)
        elif element.kind == "footing":
            product.PredefinedType = {
                "pad": "PAD_FOOTING",
                "strip": "STRIP_FOOTING",
                "pier": "USERDEFINED",
            }[str(element.data.get("shape"))]
            product.ObjectType = str(element.data.get("shape"))
        elif element.kind == "stair":
            product.PredefinedType = "STRAIGHT"
            product.NumberOfRisers = element.data.get("riserCount")
            product.NumberOfTreads = element.data.get("treadCount")
            product.RiserHeight = element.data.get("riserHeight")
            product.TreadLength = element.data.get("treadDepth")
        elif element.kind == "railing":
            product.PredefinedType = (
                "HANDRAIL" if element.data.get("role") == "handrail" else "GUARDRAIL"
            )
        elif element.kind == "terrain":
            product.PredefinedType = "TERRAIN"
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
