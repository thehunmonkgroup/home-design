"""Resolution of canonical design intent into adapter-neutral geometry."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

from shapely.affinity import translate
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.ops import polygonize

from home_design.errors import ResolutionError
from home_design.capabilities import ComponentRegistry
from home_design.components import ConstructionResolver
from home_design.terrain import TerrainSurface
from home_design.layers import LayerAssembly
from home_design.boundaries import BoundaryIdentity
from home_design.construction import Authoring, ConstructionGeometry
from home_design.coordination import GradeReport
from home_design.doors import DoorGeometry
from home_design.solar import SolarAnalysis
from home_design.screens import ScreenGeometry
from home_design.geometry import (
    RoofSurface,
    extrude_polygon,
    layer_thickness,
    normalize2,
    number,
    offset_footprint,
    oriented_box,
    polygon_from_loops,
    primary_material,
    roof_face_boundaries,
    vector2,
    vector3,
    polygon_normal,
)
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonValue
from home_design.locators import LocatorResolver, point_at_station
from home_design.resolved import MeshData, ResolvedElement, ResolvedModel, Vec2, Vec3
from home_design.roof_controls import RoofControls
from home_design.roof_identity import RoofIdentity
from home_design.topology import PartIdentity
from home_design.requirements import RequirementEvaluator
from home_design.placement import HostPlacement
from home_design.penetrations import Penetrations
from home_design.review import ReviewDiscipline
from home_design.wall_framing import FramedOpening, WallFraming
from home_design.planar_framing import PlanarFraming
from home_design.assembly_geometry import AssemblyGeometry
from home_design.curved_members import CurvedMember
from home_design.hardware import HardwareComponents
from home_design.masonry import MasonryParts
from home_design.reinforcement import Reinforcement
from home_design.mounted_parts import MountedParts, CoordinationVolumes
from home_design.services import ServiceComponents
from home_design.processing import ConstructionPipeline
from home_design.service_routes import ServiceRoutes
from home_design.service_fittings import ServiceFittings
from home_design.service_insulation import ServiceInsulation
from home_design.service_ports import ServicePorts


@dataclass(frozen=True, slots=True)
class HostedOpening:
    """Resolved wall-relative opening placement."""

    opening_id: str
    host_id: str
    start_station: float
    width: float
    bottom: float
    height: float
    depth: float
    profile: Polygon


class ModelResolver:
    """Resolve a validated authoring model into deterministic shared geometry."""

    def __init__(self, model: JsonObject) -> None:
        """Initialize model resolution.

        :param model: Fully validated canonical model.
        """
        self.model: JsonObject = model
        self.index: ModelIndex = ModelIndex(model)
        self.locators: LocatorResolver = LocatorResolver(model)
        self.elements: dict[str, JsonObject] = self.index.registries["elements"]
        self.types: dict[str, JsonObject] = self.index.registries["types"]
        self.roof_surfaces: dict[str, RoofSurface] = {}
        self.openings: dict[str, HostedOpening] = {}
        self._active_roofs: set[str] = set()
        self._resolved: dict[str, ResolvedElement] = {}
        self._active_elements: set[str] = set()
        self.construction: ConstructionResolver = ConstructionResolver(self)
        self._handlers: dict[str, Callable[[str, JsonObject], ResolvedElement]] = {
            "service": lambda identity, value: ServiceComponents.resolve(
                self.construction, identity, value
            ),
            "route": lambda identity, value: ServiceRoutes.resolve(
                self.construction, identity, value
            ),
            "fitting": lambda identity, value: ServiceFittings.resolve(
                self.construction, identity, value
            ),
            "insulation": lambda identity, value: ServiceInsulation.resolve(
                self.construction, identity, value
            ),
            "mounted": lambda identity, value: MountedParts.resolve(
                self.construction, identity, value
            ),
            "coordination": lambda identity, value: CoordinationVolumes.resolve(
                self.construction, identity, value
            ),
            "reinforcement": lambda identity, value: Reinforcement.resolve(
                self.construction, identity, value
            ),
            "masonry": lambda identity, value: MasonryParts.resolve(
                self.construction, identity, value
            ),
            "hardware": lambda identity, value: HardwareComponents.resolve(
                self.construction, identity, value
            ),
            "curved": lambda identity, value: CurvedMember.resolve(
                self.construction, identity, value
            ),
            "member-assembly": lambda identity, value: AssemblyGeometry(
                self.construction, value
            ).resolve(identity),
            "planar-framing": lambda identity, value: PlanarFraming(
                value, self.resolve_component(Authoring.text(value["host"])), self.types
            ).resolve(identity),
            "wall-framing": self._resolve_wall_framing,
            "penetration": Penetrations(self.construction).resolve,
            "panel": self._resolve_panel,
            "construction": self.construction.resolve,
            "slab": self._resolve_slab,
            "roof": self._resolve_roof,
            "wall": self._resolve_wall,
            "opening": self._resolve_opening,
            "fill": self._resolve_fill,
            "space": self._resolve_space,
            "assembly": self._resolve_assembly,
        }
        missing = {
            item.resolver for item in ComponentRegistry.components.values()
        } - self._handlers.keys()
        if missing:
            raise ResolutionError(
                f"Component registry has unbound resolvers: {sorted(missing)}"
            )

    def resolve(self) -> ResolvedModel:
        """Resolve all architectural components and integrations.

        :returns: Adapter-neutral resolved model.
        :raises ResolutionError: If validated intent is not geometrically resolvable.
        """
        self._prepare_roofs()
        self._prepare_openings()
        for element_id in self.elements:
            self.resolve_component(element_id)
        processed = ConstructionPipeline.standard().run(
            self._resolved, self._object("relationships")
        )
        resolved_elements = processed.elements
        result = ResolvedModel(
            model_version=str(self.model.get("modelVersion")),
            source_revision=int(number(self.model.get("revision", 0), "revision")),
            project=self._object("project"),
            coordinate_system=self._object("coordinateSystem"),
            levels=self._object("levels"),
            materials=self._object("materials"),
            types=self._object("types"),
            elements=tuple(
                resolved_elements[element_id] for element_id in self.elements
            ),
            relationships=self._object("relationships"),
            requirements=tuple(Authoring.array(self.model.get("requirements", []))),
            solar_studies=tuple(Authoring.array(self.model.get("solarStudies", []))),
            drawings=tuple(Authoring.array(self.model.get("drawings", []))),
            component_references=tuple(
                reference.to_dict(self.model)
                for reference in self.index.references
                if reference.owner_registry == "elements"
                and reference.registry == "elements"
            ),
        )
        if result.solar_studies:
            solar = SolarAnalysis(result)
            result = replace(
                result,
                solar_studies=tuple(
                    solar.study(Authoring.object(study))
                    for study in result.solar_studies
                ),
            )
        return replace(
            result, requirement_results=RequirementEvaluator(result).evaluate()
        )

    def resolve_component(self, element_id: str) -> ResolvedElement:
        """Resolve dependencies once while preserving canonical element identity."""
        if element_id in self._resolved:
            return self._resolved[element_id]
        if element_id in self._active_elements:
            raise ResolutionError(f"Element placement dependency cycle at {element_id}")
        self._active_elements.add(element_id)
        try:
            result = self._resolve_element(element_id, self.elements[element_id])
            result = self._with_specifications(result, self.elements[element_id])
            self._resolved[element_id] = result
            return result
        except ResolutionError as error:
            if error.subject_id is not None:
                raise
            raise ResolutionError(
                str(error),
                code=(
                    error.code
                    if error.code != "workflow.failed"
                    else "geometry.resolution-failed"
                ),
                path=f"/elements/{element_id}",
                subject_id=element_id,
                details=error.details,
            ) from error
        finally:
            self._active_elements.remove(element_id)

    def _with_specifications(
        self, resolved: ResolvedElement, source: JsonObject
    ) -> ResolvedElement:
        data = dict(resolved.data)
        data["discipline"] = ReviewDiscipline.classify(source)
        if "occupies" in source:
            data["occupies"] = source["occupies"]
        if "coordinationChecks" in source:
            data["coordinationChecks"] = source["coordinationChecks"]
        host_placements = HostPlacement.references(source)
        if host_placements:
            data["hostPlacements"] = host_placements
        port_placements = ServicePorts.references(source)
        if port_placements:
            data["portPlacements"] = port_placements
        component_type = self.types.get(str(source.get("type")), {})
        for field in ("specifications", "performance", "properties"):
            inherited = component_type.get(field, {})
            authored = source.get(field, {})
            merged: JsonObject = {
                **(inherited if isinstance(inherited, dict) else {}),
                **(authored if isinstance(authored, dict) else {}),
            }
            if merged:
                data[field] = merged
        for field in ("description", "tags", "externalIds"):
            if field in source:
                data[field] = source[field]
        requirements = [
            requirement
            for requirement in Authoring.array(self.model.get("requirements", []))
            if isinstance(requirement, dict)
            and resolved.element_id in Authoring.array(requirement.get("appliesTo", []))
        ]
        if requirements:
            data["requirements"] = list(requirements)
        grade_id = source.get("grade")
        if isinstance(grade_id, str):
            data["grade"] = {
                "terrainId": grade_id,
                **GradeReport.evaluate(resolved, self.elements[grade_id]),
            }
        return replace(resolved, data=data)

    def _resolve_element(self, element_id: str, element: JsonObject) -> ResolvedElement:
        capability = ComponentRegistry.get(str(element.get("kind")))
        return self._handlers[capability.resolver](element_id, element)

    def _resolve_wall_framing(
        self, element_id: str, element: JsonObject
    ) -> ResolvedElement:
        """Integrate wall framing with its host and authoritative opening extents."""
        host_id = Authoring.text(element["host"])
        return WallFraming(
            element,
            self.resolve_component(host_id),
            self.types,
            [
                FramedOpening(
                    item.opening_id,
                    item.start_station,
                    item.start_station + item.width,
                    item.bottom,
                    item.bottom + item.height,
                )
                for item in self.openings.values()
                if item.host_id == host_id
            ],
        ).resolve(element_id)

    def _resolve_panel(self, element_id: str, element: JsonObject) -> ResolvedElement:
        """Select profiled screen geometry when openings or a connected top require it."""
        if "top" in element or any(
            opening.host_id == element_id for opening in self.openings.values()
        ):
            return self._resolve_screen(element_id, element)
        return self.construction.resolve(element_id, element)

    def _resolve_assembly(
        self, element_id: str, element: JsonObject
    ) -> ResolvedElement:
        """Resolve the explicitly nonphysical grouping family."""
        return ResolvedElement(
            element_id,
            "assembly",
            str(element.get("name")),
            self._string(element.get("storey")),
            data={
                "assemblyType": element.get("assemblyType"),
                **(
                    {"recipeInstance": element["recipeInstance"]}
                    if "recipeInstance" in element
                    else {}
                ),
            },
        )

    def _resolve_slab(self, element_id: str, element: JsonObject) -> ResolvedElement:
        component_type = self._type_for(element)
        thickness = layer_thickness(component_type)
        outer, holes = self.locators.profile2(element.get("footprint"))
        polygon = polygon_from_loops(outer, holes)
        datum = self._dict(element.get("datum"), "slab datum")
        datum_z = self.elevation(datum)
        direction = str(element.get("extrusionDirection"))
        bottom_z, top_z = (
            (datum_z - thickness, datum_z)
            if direction == "down"
            else (datum_z, datum_z + thickness)
        )
        meshes = LayerAssembly.slab(polygon, top_z, component_type)
        return ResolvedElement(
            element_id,
            "slab",
            str(element.get("name")),
            self._string(element.get("storey")),
            meshes,
            {
                "typeId": element.get("type"),
                "role": element.get("role"),
                "thickness": thickness,
                "layers": LayerAssembly.metadata(component_type),
                "topElevation": top_z,
                "bottomElevation": bottom_z,
                "footprint": {
                    "outer": [list(point) for point in outer],
                    "holes": [[list(point) for point in loop] for loop in holes],
                    "boundaryIds": BoundaryIdentity.metadata(
                        self._dict(element["footprint"], "footprint")
                    ),
                },
            },
        )

    def _resolve_roof(self, element_id: str, element: JsonObject) -> ResolvedElement:
        component_type = self._type_for(element)
        thickness = layer_thickness(component_type)
        geometry = self._dict(element.get("geometry"), "roof geometry")
        identities: list[str] = []
        boundary_ids: list[JsonObject] = []
        if geometry.get("kind") == "faceSet":
            faces_value = geometry.get("faces")
            if not isinstance(faces_value, list):
                raise ResolutionError(f"Roof {element_id} requires faces")
            boundaries: list[tuple[Vec3, ...]] = []
            face_ids: list[str] = []
            for face in faces_value:
                face_object = self._dict(face, "roof face")
                boundary = self._dict(face_object.get("boundary"), "roof boundary")
                boundary_ids.append(BoundaryIdentity.metadata(boundary))
                outer_value = boundary.get("outer")
                if not isinstance(outer_value, list):
                    raise ResolutionError(
                        f"Roof {element_id} face requires an outer boundary"
                    )
                boundaries.append(
                    tuple(vector3(point, "roof face point") for point in outer_value)
                )
                face_ids.append(str(face_object.get("id")))
        else:
            surface = self.roof_surfaces[element_id]
            boundaries = list(roof_face_boundaries(surface))
            footprint, _ = self.locators.profile2(geometry["footprint"])
            keys, metadata = RoofIdentity.describe(geometry, footprint, boundaries)
            identities = list(keys)
            boundary_ids = list(metadata)
            aliases = Authoring.object(geometry.get("faceIds", {}))
            face_ids = [
                (
                    Authoring.text(aliases.get(identity, f"{element_id}.{identity}"))
                    if self.model.get("modelVersion") == "0.2"
                    else f"{element_id}.face-{index + 1}"
                )
                for index, identity in enumerate(identities)
            ]
        if len(set(face_ids)) != len(face_ids):
            raise ResolutionError(
                "Roof face IDs must be unique", code="roof.duplicate-face-id"
            )
        meshes = tuple(
            mesh
            for index, (boundary, face_id) in enumerate(zip(boundaries, face_ids))
            for mesh in LayerAssembly.roof(
                boundary,
                component_type,
                face_id,
                tuple(other for position, other in enumerate(boundaries) if position != index),
            )
        )
        face_id_values: list[JsonValue] = []
        face_id_values.extend(face_ids)
        return ResolvedElement(
            element_id,
            "roof",
            str(element.get("name")),
            self._string(element.get("storey")),
            meshes,
            {
                "typeId": element.get("type"),
                "thickness": thickness,
                "faceIds": face_id_values,
                "faceIdentities": dict(zip(identities, face_ids)),
                "planes": [
                    {
                        "id": face_id,
                        "boundary": [list(point) for point in boundary],
                        "boundaryIds": names,
                    }
                    for face_id, boundary, names in zip(
                        face_ids, boundaries, boundary_ids
                    )
                ],
                "layers": LayerAssembly.metadata(component_type),
                "form": (
                    geometry.get("form")
                    if geometry.get("kind") == "parametric"
                    else "faceSet"
                ),
            },
        )

    def _resolve_wall(self, element_id: str, element: JsonObject) -> ResolvedElement:
        component_type = self._type_for(element)
        thickness = layer_thickness(component_type)
        axis_points = self.locators.path2(element.get("path"))
        points = self._wall_resolution_points(element, axis_points)
        base_z = self._constraint_height(
            self._dict(element.get("base"), "wall base"), axis_points[0], "top"
        )
        center_offset = self._wall_center_offset(
            str(element.get("locationLine")), thickness
        )
        hosted = [
            opening
            for opening in self.openings.values()
            if opening.host_id == element_id
        ]
        meshes: list[MeshData] = []
        cumulative = 0.0
        net_area = 0.0
        gross_area = 0.0
        top_elevations: list[float] = []
        for segment_index, (start, end) in enumerate(zip(points, points[1:])):
            segment_length = math.dist(start, end)
            tangent = normalize2((end[0] - start[0], end[1] - start[1]), "wall tangent")
            top_start = self._wall_top(element, start, base_z)
            top_end = self._wall_top(element, end, base_z)
            top_elevations.extend((top_start, top_end))
            gross_area += segment_length * ((top_start + top_end) / 2 - base_z)
            profile = Polygon(
                [
                    (0.0, 0.0),
                    (segment_length, 0.0),
                    (segment_length, top_end - base_z),
                    (0.0, top_start - base_z),
                ]
            )
            for opening in hosted:
                overlap_start = max(opening.start_station, cumulative)
                overlap_end = min(
                    opening.start_station + opening.width, cumulative + segment_length
                )
                if overlap_end - overlap_start <= 0.01:
                    continue
                local_start = overlap_start - cumulative
                local_end = overlap_end - cumulative
                clipped = translate(
                    opening.profile,
                    xoff=opening.start_station - cumulative,
                    yoff=opening.bottom,
                )
                clipped = clipped.intersection(
                    Polygon(
                        [
                            (local_start, opening.bottom),
                            (local_end, opening.bottom),
                            (local_end, opening.bottom + opening.height),
                            (local_start, opening.bottom + opening.height),
                        ]
                    )
                )
                if not profile.buffer(0.01).covers(clipped):
                    raise ResolutionError(
                        f"Opening {opening.opening_id} extends outside the actual wall profile"
                    )
                profile = profile.difference(clipped)
            if isinstance(profile, Polygon):
                polygons = [profile]
            elif isinstance(profile, MultiPolygon):
                polygons = list(profile.geoms)
            else:
                raise ResolutionError(
                    f"Wall {element_id} subtraction produced invalid geometry"
                )
            for part_index, polygon in enumerate(polygons):
                net_area += polygon.area
                role = f"body:{segment_index + 1}:{part_index + 1}"
                meshes.extend(
                    LayerAssembly.wall(
                        polygon,
                        start,
                        tangent,
                        center_offset + thickness / 2,
                        base_z,
                        component_type,
                        role,
                    )
                )
            cumulative += segment_length
        return ResolvedElement(
            element_id,
            "wall",
            str(element.get("name")),
            self._string(element.get("storey")),
            tuple(meshes),
            {
                "typeId": element.get("type"),
                "axis": [list(point) for point in axis_points],
                "length": cumulative,
                "segmentIds": list(
                    BoundaryIdentity.path(
                        self._dict(element["path"], "wall path"), len(axis_points) - 1
                    )
                ),
                "topProfile": [
                    [point[0], point[1], self._wall_top(element, point, base_z)]
                    for point in points
                ],
                "topProfileIds": [
                    self._wall_top_identity(
                        element, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    )
                    for a, b in zip(points, points[1:])
                ],
                "baseElevation": base_z,
                "topElevationRange": [min(top_elevations), max(top_elevations)],
                "thickness": thickness,
                "locationLine": element.get("locationLine"),
                "netArea": net_area,
                "grossArea": gross_area,
                "layers": LayerAssembly.metadata(component_type),
            },
        )

    def _screen_path(self, element: JsonObject) -> list[Vec3]:
        """Require a straight, horizontal baseline for profiled/host screen panels."""
        points = self.construction.path(element)
        if len(points) != 2 or abs(points[0][2] - points[1][2]) > 0.01:
            raise ResolutionError(
                "Roof-following and hosted screens require a two-point horizontal path"
            )
        if math.dist(points[0], points[1]) <= 0.01:
            raise ResolutionError("Screen path must have positive length")
        return points

    def _resolve_screen(self, element_id: str, element: JsonObject) -> ResolvedElement:
        """Resolve a framed roof-height screen and its real hosted opening cuts."""
        points = self._screen_path(element)
        start, end = points
        base = start[2]
        length = math.dist(start, end)
        tangent = normalize2((end[0] - start[0], end[1] - start[1]), "screen tangent")
        definition = self._type_for(element)
        control: JsonObject = {
            "top": element.get(
                "top", {"kind": "height", "height": definition["height"]}
            )
        }
        plan = self._wall_resolution_points(
            control, ((start[0], start[1]), (end[0], end[1]))
        )
        tops = [
            (math.dist(plan[0], point), self._wall_top(control, point, base) - base)
            for point in plan
        ]
        for index, (a, b) in enumerate(zip(plan, plan[1:])):
            for ratio in (0.25, 0.5, 0.75):
                sample = (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)
                expected = (
                    tops[index][1] + (tops[index + 1][1] - tops[index][1]) * ratio
                )
                if abs(self._wall_top(control, sample, base) - base - expected) > 0.01:
                    raise ResolutionError("Split the screen at roof face changes")
        if min(height for _, height in tops) <= 0:
            raise ResolutionError("Screen top must be above its base")
        profile = Polygon([(0, 0), (length, 0), *reversed(tops)])
        hosted = [
            opening
            for opening in self.openings.values()
            if opening.host_id == element_id
        ]
        cutouts = [
            translate(opening.profile, xoff=opening.start_station, yoff=opening.bottom)
            for opening in hosted
        ]
        gaps = [
            (
                number(Authoring.object(value)["start"], "gap start"),
                number(Authoring.object(value)["end"], "gap end"),
            )
            for value in Authoring.array(element.get("openings", []))
        ]
        ConstructionGeometry.interval_segments(length, gaps)
        for low, high in gaps:
            gap = profile.intersection(
                Polygon(
                    [
                        (low, 0),
                        (high, 0),
                        (high, profile.bounds[3]),
                        (low, profile.bounds[3]),
                    ]
                )
            )
            if not isinstance(gap, Polygon):
                raise ResolutionError(
                    "Screen access gap must cut one contiguous region"
                )
            cutouts.append(gap)
        meshes = ScreenGeometry.resolve(
            profile, cutouts, plan[0], tangent, base, definition
        )
        return ResolvedElement(
            element_id,
            "panel",
            str(element.get("name")),
            self._string(element.get("storey")),
            meshes,
            {
                "path": [list(point) for point in points],
                "height": max(height for _, height in tops),
                "topProfile": [
                    [point[0], point[1], base + top[1]]
                    for point, top in zip(plan, tops)
                ],
                "length": length,
                "openings": element.get("openings", []),
                "hostedOpeningIds": [opening.opening_id for opening in hosted],
                "isStructuralGuard": False,
                "typeId": element.get("type"),
                "role": None,
            },
        )

    def _resolve_opening(self, element_id: str, element: JsonObject) -> ResolvedElement:
        opening = self.openings[element_id]
        host = self.elements[opening.host_id]
        panel_points = self._screen_path(host) if host.get("kind") == "panel" else None
        host_path = (
            tuple((point[0], point[1]) for point in panel_points)
            if panel_points
            else self.locators.path2(host.get("path"))
        )
        center_station = opening.start_station + opening.width / 2
        point, tangent = point_at_station(host_path, center_station)
        host_type = self._type_for(host)
        host_depth = (
            number(host_type.get("frameDepth"), "screen depth")
            if panel_points
            else layer_thickness(host_type)
        )
        placement = self._dict(element.get("placement"), "opening placement")
        normal = (-tangent[1], tangent[0])
        depth_offset = number(placement.get("depthOffset"), "opening depth offset")
        base_z = (
            panel_points[0][2]
            if panel_points
            else self._constraint_height(
                self._dict(host.get("base"), "wall base"), point, "top"
            )
        )
        origin = (
            point[0] + normal[0] * depth_offset,
            point[1] + normal[1] * depth_offset,
            base_z + opening.bottom,
        )
        mesh = oriented_box(
            origin,
            tangent,
            opening.width,
            max(opening.depth, host_depth + 2),
            opening.height,
            None,
            "void",
        )
        return ResolvedElement(
            element_id,
            "opening",
            str(element.get("name")),
            self._string(host.get("storey")),
            (mesh,),
            {
                "hostId": opening.host_id,
                "origin": list(origin),
                "tangent": list(tangent),
                "width": opening.width,
                "height": opening.height,
                "depth": opening.depth,
            },
        )

    def _resolve_fill(self, element_id: str, element: JsonObject) -> ResolvedElement:
        opening_id = self.index.opening_for_fill(element_id)
        if opening_id is None:
            raise ResolutionError(f"Fill element {element_id} has no opening")
        opening_element = self._resolve_opening(opening_id, self.elements[opening_id])
        opening_data = opening_element.data
        origin = vector3(opening_data.get("origin"), "opening origin")
        tangent = vector2(opening_data.get("tangent"), "opening tangent")
        component_type = self._type_for(element)
        width = number(component_type.get("nominalWidth"), "nominal width")
        height = number(component_type.get("nominalHeight"), "nominal height")
        depth = number(
            component_type.get("frameDepth", opening_data.get("depth")), "frame depth"
        )
        material_id = primary_material(component_type)
        opening_width = number(opening_data.get("width"), "opening width")
        opening_height = number(opening_data.get("height"), "opening height")
        adjusted_origin = (
            origin[0],
            origin[1],
            origin[2] + max((opening_height - height) / 2, 0.0),
        )
        if element.get("kind") == "door":
            meshes, operation_data = DoorGeometry.resolve(
                component_type,
                element,
                adjusted_origin,
                tangent,
                width,
                height,
                depth,
                material_id,
            )
        else:
            meshes = self._window_meshes(
                adjusted_origin, tangent, width, height, depth, material_id
            )
            operation_data = {
                "operation": component_type.get("operation"),
                "nominalWidth": width,
                "nominalHeight": height,
            }
        return ResolvedElement(
            element_id,
            str(element.get("kind")),
            str(element.get("name")),
            opening_element.storey_id,
            meshes,
            {
                "typeId": element.get("type"),
                "openingId": opening_id,
                "roughOpeningClearance": [
                    opening_width - width,
                    opening_height - height,
                ],
                "origin": list(adjusted_origin),
                "tangent": list(tangent),
                **operation_data,
            },
        )

    def _resolve_space(self, element_id: str, element: JsonObject) -> ResolvedElement:
        geometry = self._dict(element.get("geometry"), "space geometry")
        if geometry.get("kind") == "explicit":
            outer, holes = self.locators.profile2(geometry.get("footprint"))
            polygon = polygon_from_loops(outer, holes)
        else:
            polygon = self._derive_space_polygon(element_id, geometry)
            outer = tuple(
                (float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]
            )
            holes = tuple(
                tuple((float(x), float(y)) for x, y in list(ring.coords)[:-1])
                for ring in polygon.interiors
            )
        storey_id = self._string(element.get("storey"))
        base_z = self.locators.level_elevation(storey_id) if storey_id else 0.0
        height = number(element.get("height"), "space height")
        mesh = extrude_polygon(polygon, base_z, base_z + height, None, "space")
        return ResolvedElement(
            element_id,
            "space",
            str(element.get("name")),
            storey_id,
            (mesh,),
            {
                "typeId": element.get("type"),
                "height": height,
                "area": polygon.area,
                "footprint": {
                    "outer": [list(point) for point in outer],
                    "holes": [[list(point) for point in loop] for loop in holes],
                },
            },
        )

    def _prepare_roofs(self) -> None:
        for element_id, element in self.elements.items():
            if element.get("kind") == "roof":
                self._prepare_roof(element_id)

    def _prepare_roof(self, element_id: str) -> None:
        if element_id in self.roof_surfaces:
            return
        if element_id in self._active_roofs:
            raise ResolutionError(f"Roof placement dependency cycle at {element_id}")
        element = self.elements[element_id]
        geometry = self._dict(element.get("geometry"), "roof geometry")
        if geometry.get("kind") != "parametric":
            return
        self._active_roofs.add(element_id)
        try:
            self.roof_surfaces[element_id] = self._parametric_roof_surface(
                element, geometry
            )
        finally:
            self._active_roofs.remove(element_id)

    def _parametric_roof_surface(
        self, element: JsonObject, geometry: JsonObject
    ) -> RoofSurface:
        outer, holes = self.locators.profile2(geometry.get("footprint"))
        bearing = polygon_from_loops(outer, holes)
        edge_offsets = geometry.get("edgeOverhangs")
        if isinstance(edge_offsets, dict):
            names = BoundaryIdentity.profile(Authoring.object(geometry["footprint"]))[0]
            if set(edge_offsets) != set(names):
                raise ResolutionError(
                    "Named edge overhangs must cover exactly the roof footprint edges",
                    code="roof.edge-overhang-identities",
                )
            edge_offsets = [edge_offsets[name] for name in names]
        polygon = (
            RoofControls.edge_footprint(
                bearing, [number(value, "edge overhang") for value in edge_offsets]
            )
            if isinstance(edge_offsets, list)
            else offset_footprint(
                bearing, number(geometry.get("overhang"), "roof overhang")
            )
        )
        datum = self._dict(geometry.get("eaveDatum"), "roof eave datum")
        eave_z = self.elevation(datum)
        form = str(geometry.get("form"))
        pitch = number(geometry.get("pitch", 0), "roof pitch")
        if form == "shed":
            direction = normalize2(
                vector2(geometry.get("slopeDirection"), "roof slope direction"),
                "roof slope direction",
            )
        elif form == "gable":
            ridge = normalize2(
                vector2(geometry.get("ridgeDirection"), "roof ridge direction"),
                "roof ridge direction",
            )
            direction = (-ridge[1], ridge[0])
        else:
            direction = (1.0, 0.0)
        thickness = layer_thickness(self._type_for(element))
        if geometry.get("datumSurface") == "underside":
            eave_z += thickness / math.cos(math.radians(pitch))
        surface = RoofSurface(
            form,
            polygon,
            eave_z,
            pitch,
            direction,
            thickness,
            bearing if geometry.get("datumReference") == "bearing" else None,
        )
        if "datumPoint" in geometry:
            point = vector2(geometry["datumPoint"], "roof datum point")
            surface = replace(
                surface, eave_z=surface.eave_z + eave_z - surface.top_height(*point)
            )
        return surface

    def elevation(self, datum: JsonObject) -> float:
        """Resolve a level or an explicitly sampled element surface datum."""
        if datum.get("kind") == "level":
            return self.locators.level_constraint(datum)
        point = self.locators.plan_point(datum.get("point"))
        return self._constraint_height(datum, point, "top")

    def _prepare_openings(self) -> None:
        for opening_id, element in self.elements.items():
            if element.get("kind") != "opening":
                continue
            host_id = self.index.host_for_opening(opening_id)
            if host_id is None:
                raise ResolutionError(f"Opening {opening_id} has no host")
            geometry = self._dict(element.get("geometry"), "opening geometry")
            placement = self._dict(element.get("placement"), "opening placement")
            if geometry.get("kind") == "rectangle":
                width = number(geometry.get("width"), "opening width")
                height = number(geometry.get("height"), "opening height")
                profile = Polygon([(0, 0), (width, 0), (width, height), (0, height)])
            else:
                profile_object = self._dict(geometry.get("profile"), "opening profile")
                outer_value = self._list(
                    profile_object.get("outer"), "opening outer profile"
                )
                outer = [
                    vector2(point, "opening profile point") for point in outer_value
                ]
                holes_value = profile_object.get("holes", [])
                holes = [
                    [
                        vector2(point, "opening profile point")
                        for point in self._list(loop, "opening profile hole")
                    ]
                    for loop in self._list(holes_value, "opening profile holes")
                ]
                profile = polygon_from_loops(outer, holes)
                min_x, min_y, max_x, max_y = profile.bounds
                width, height = max_x - min_x, max_y - min_y
                profile = translate(profile, xoff=-min_x, yoff=-min_y)
            station = number(placement.get("station"), "opening station")
            start_station = station - {
                "start": 0.0,
                "center": width / 2,
                "end": width,
            }.get(str(placement.get("stationReference")), 0.0)
            bottom = number(placement.get("verticalOffset"), "opening vertical offset")
            bottom -= {"bottom": 0.0, "center": height / 2, "top": height}.get(
                str(placement.get("verticalReference")), 0.0
            )
            self.openings[opening_id] = HostedOpening(
                opening_id,
                host_id,
                start_station,
                width,
                bottom,
                height,
                number(geometry.get("depth"), "opening depth"),
                profile,
            )

    def _constraint_height(
        self, constraint: JsonObject, point: Vec2, default_surface: str
    ) -> float:
        kind = constraint.get("kind")
        if kind == "level":
            return self.locators.level_constraint(constraint)
        element_id = constraint.get("element")
        if not isinstance(element_id, str):
            raise ResolutionError("Surface constraint requires an element")
        surface = str(constraint.get("surface", default_surface))
        offset = number(constraint.get("offset"), "surface offset")
        referenced = self.elements.get(element_id)
        if referenced is None:
            raise ResolutionError(f"Unknown constrained element {element_id}")
        if surface not in {"top", "bottom", "underside"}:
            raise ResolutionError(f"Unknown surface {surface} on {element_id}")
        if referenced.get("kind") == "terrain":
            if surface != "top":
                raise ResolutionError("Terrain exposes only its top survey surface")
            return TerrainSurface.from_element(referenced).height(point) + offset
        if referenced.get("kind") in {"footing", "stair"}:
            resolved = self.resolve_component(element_id)
            return (
                number(
                    resolved.data.get(
                        "topElevation" if surface == "top" else "bottomElevation"
                    ),
                    "component surface",
                )
                + offset
            )
        if referenced.get("kind") == "slab":
            slab_type = self._type_for(referenced)
            thickness = layer_thickness(slab_type)
            outer, holes = self.locators.profile2(referenced.get("footprint"))
            if "point" in constraint and not polygon_from_loops(outer, holes).buffer(
                0.01
            ).covers(Point(point)):
                raise ResolutionError(f"No slab surface on {element_id} covers {point}")
            datum_z = self.elevation(self._dict(referenced.get("datum"), "slab datum"))
            direction = referenced.get("extrusionDirection")
            top = datum_z if direction == "down" else datum_z + thickness
            bottom = datum_z - thickness if direction == "down" else datum_z
            return (top if surface == "top" else bottom) + offset
        if referenced.get("kind") == "roof":
            self._prepare_roof(element_id)
        roof = self.roof_surfaces.get(element_id)
        if roof is not None:
            if not roof.footprint.buffer(0.01).covers(Point(point)):
                raise ResolutionError(f"No roof surface on {element_id} covers {point}")
            height = (
                roof.underside_height(*point)
                if surface in {"underside", "bottom"}
                else roof.top_height(*point)
            )
            return height + offset
        if referenced.get("kind") == "roof":
            return (
                self._explicit_roof_height(
                    referenced,
                    point,
                    surface,
                    self._string(constraint.get("selector")),
                )
                + offset
            )
        raise ResolutionError(f"Element {element_id} does not expose surface {surface}")

    def _wall_top(self, wall: JsonObject, point: Vec2, base_z: float) -> float:
        constraint = self._dict(wall.get("top"), "wall top")
        if constraint.get("kind") == "height":
            return base_z + number(constraint.get("height"), "wall height")
        return self._constraint_height(constraint, point, "underside")

    def _wall_top_identity(self, wall: JsonObject, point: Vec2) -> str:
        """Name the controlling top surface independently of sampled profile-knot positions."""
        constraint = Authoring.object(wall["top"])
        kind = Authoring.text(constraint["kind"])
        if kind != "surface":
            return f"{kind}.{constraint.get('level', 'top')}"
        identity = Authoring.text(constraint["element"])
        if self.elements[identity].get("kind") != "roof":
            return f"surface.{identity}"
        roof = self.resolve_component(identity)
        candidates: list[tuple[str, float]] = []
        selector = (
            constraint.get("selector") if identity not in self.roof_surfaces else None
        )
        underside = constraint.get("surface", "underside") in {"underside", "bottom"}
        for value in Authoring.array(roof.data["planes"]):
            plane = Authoring.object(value)
            face = Authoring.text(plane["id"])
            if selector is not None and selector != face:
                continue
            boundary = [
                vector3(vertex, "roof plane vertex")
                for vertex in Authoring.array(plane["boundary"])
            ]
            if (
                not Polygon([(vertex[0], vertex[1]) for vertex in boundary])
                .buffer(0.01)
                .covers(Point(point))
            ):
                continue
            normal = polygon_normal(boundary)
            origin = boundary[0]
            elevation = (
                origin[2]
                - (
                    normal[0] * (point[0] - origin[0])
                    + normal[1] * (point[1] - origin[1])
                )
                / normal[2]
            )
            if underside:
                elevation -= number(roof.data["thickness"], "roof thickness") / abs(
                    normal[2]
                )
            candidates.append((face, elevation))
        if not candidates:
            raise ResolutionError(
                "Wall top has no controlling roof plane",
                code="wall.missing-top-identity",
            )
        selected = (min if underside else max)(height for _, height in candidates)
        return PartIdentity.token(
            [face for face, height in candidates if abs(height - selected) <= 0.01]
        )

    def _wall_resolution_points(
        self, wall: JsonObject, points: tuple[Vec2, ...]
    ) -> tuple[Vec2, ...]:
        constraint = self._dict(wall.get("top"), "wall top")
        roof_id = (
            constraint.get("element") if constraint.get("kind") == "surface" else None
        )
        roof = self.roof_surfaces.get(roof_id) if isinstance(roof_id, str) else None
        if roof is None:
            if isinstance(roof_id, str):
                referenced = self.elements.get(roof_id)
                if referenced is not None and referenced.get("kind") == "roof":
                    return self._split_at_explicit_roof_edges(referenced, points)
            return points
        if roof.form != "gable":
            return points
        dx, dy = roof.direction
        projections = [x * dx + y * dy for x, y in roof.outer_points()]
        ridge_projection = (min(projections) + max(projections)) / 2
        resolved: list[Vec2] = [points[0]]
        for start, end in zip(points, points[1:]):
            start_projection = start[0] * dx + start[1] * dy
            end_projection = end[0] * dx + end[1] * dy
            span = end_projection - start_projection
            if abs(span) > 0.01:
                ratio = (ridge_projection - start_projection) / span
                if 0.000001 < ratio < 0.999999:
                    resolved.append(
                        (
                            start[0] + (end[0] - start[0]) * ratio,
                            start[1] + (end[1] - start[1]) * ratio,
                        )
                    )
            resolved.append(end)
        return tuple(resolved)

    def _split_at_explicit_roof_edges(
        self,
        roof: JsonObject,
        points: tuple[Vec2, ...],
    ) -> tuple[Vec2, ...]:
        geometry = self._dict(roof.get("geometry"), "roof geometry")
        if geometry.get("kind") != "faceSet":
            return points
        edges: list[LineString] = []
        for boundary, _ in self._explicit_roof_faces(roof):
            plan = [(point[0], point[1]) for point in boundary]
            edges.extend(
                LineString((start, end))
                for start, end in zip(plan, (*plan[1:], plan[0]))
            )
        resolved: list[Vec2] = [points[0]]
        for start, end in zip(points, points[1:]):
            segment = LineString((start, end))
            intersections: list[Vec2] = []
            for edge in edges:
                intersection = segment.intersection(edge)
                candidates = (
                    list(intersection.geoms)
                    if isinstance(intersection, MultiPoint)
                    else [intersection]
                )
                for candidate in candidates:
                    if isinstance(candidate, Point):
                        coordinate = (float(candidate.x), float(candidate.y))
                        if (
                            math.dist(coordinate, start) > 0.01
                            and math.dist(coordinate, end) > 0.01
                        ):
                            intersections.append(coordinate)
            intersections.sort(key=lambda coordinate: math.dist(start, coordinate))
            for coordinate in intersections:
                if math.dist(resolved[-1], coordinate) > 0.01:
                    resolved.append(coordinate)
            resolved.append(end)
        return tuple(resolved)

    def _explicit_roof_height(
        self,
        roof: JsonObject,
        point: Vec2,
        surface: str,
        selector: str | None,
    ) -> float:
        thickness = layer_thickness(self._type_for(roof))
        heights: list[float] = []
        for boundary, face_id in self._explicit_roof_faces(roof):
            if selector is not None and selector != face_id:
                continue
            polygon = Polygon([(vertex[0], vertex[1]) for vertex in boundary])
            if not polygon.buffer(0.01).covers(Point(point)):
                continue
            a, b, c = boundary[:3]
            normal = (
                (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
                (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
                (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]),
            )
            magnitude = math.sqrt(sum(value * value for value in normal))
            if magnitude <= 0.01 or abs(normal[2]) <= 0.01:
                continue
            top = (
                a[2]
                - (normal[0] * (point[0] - a[0]) + normal[1] * (point[1] - a[1]))
                / normal[2]
            )
            heights.append(
                top - thickness * magnitude / abs(normal[2])
                if surface in {"underside", "bottom"}
                else top
            )
        if not heights:
            label = f" selected by {selector}" if selector else ""
            raise ResolutionError(f"No explicit roof face{label} covers point {point}")
        return min(heights) if surface in {"underside", "bottom"} else max(heights)

    def _explicit_roof_faces(
        self, roof: JsonObject
    ) -> list[tuple[tuple[Vec3, ...], str]]:
        geometry = self._dict(roof.get("geometry"), "roof geometry")
        faces_value = self._list(geometry.get("faces"), "roof faces")
        result: list[tuple[tuple[Vec3, ...], str]] = []
        for face in faces_value:
            face_object = self._dict(face, "roof face")
            boundary = self._dict(face_object.get("boundary"), "roof face boundary")
            outer = self._list(boundary.get("outer"), "roof face outer boundary")
            result.append(
                (
                    tuple(vector3(vertex, "roof face vertex") for vertex in outer),
                    str(face_object.get("id")),
                )
            )
        return result

    def _derive_space_polygon(self, space_id: str, geometry: JsonObject) -> Polygon:
        boundary_ids = [
            relationship.get("element")
            for _, relationship in self.index.relationships("bounds")
            if relationship.get("space") == space_id
        ]
        lines = []
        for element_id in boundary_ids:
            element = (
                self.elements.get(element_id) if isinstance(element_id, str) else None
            )
            if element is not None and element.get("kind") == "wall":
                lines.append(LineString(self.locators.path2(element.get("path"))))
        candidates = list(polygonize(lines))
        seed = vector2(geometry.get("seedPoint"), "space seed point")
        seed_point = Point(seed)
        matches = [
            candidate for candidate in candidates if candidate.covers(seed_point)
        ]
        if len(matches) != 1:
            raise ResolutionError(
                f"Space {space_id} seed must resolve inside exactly one closed wall boundary"
            )
        return matches[0]

    @staticmethod
    def _window_meshes(
        origin: Vec3,
        tangent: Vec2,
        width: float,
        height: float,
        depth: float,
        material_id: str | None,
    ) -> tuple[MeshData, ...]:
        frame = min(70.0, width / 4, height / 4)
        tx, ty = normalize2(tangent, "window tangent")
        horizontal_shift = (width - frame) / 2
        left_origin = (
            origin[0] - tx * horizontal_shift,
            origin[1] - ty * horizontal_shift,
            origin[2],
        )
        right_origin = (
            origin[0] + tx * horizontal_shift,
            origin[1] + ty * horizontal_shift,
            origin[2],
        )
        bottom_origin = (origin[0], origin[1], origin[2])
        top_origin = (origin[0], origin[1], origin[2] + height - frame)
        glass_origin = (origin[0], origin[1], origin[2] + frame)
        return (
            oriented_box(
                left_origin, tangent, frame, depth, height, material_id, "window-frame"
            ),
            oriented_box(
                right_origin, tangent, frame, depth, height, material_id, "window-frame"
            ),
            oriented_box(
                bottom_origin,
                tangent,
                width - 2 * frame,
                depth,
                frame,
                material_id,
                "window-frame",
            ),
            oriented_box(
                top_origin,
                tangent,
                width - 2 * frame,
                depth,
                frame,
                material_id,
                "window-frame",
            ),
            oriented_box(
                glass_origin,
                tangent,
                width - 2 * frame,
                8.0,
                height - 2 * frame,
                None,
                "window-glass",
            ),
        )

    @staticmethod
    def _wall_center_offset(location_line: str, thickness: float) -> float:
        if location_line == "exterior":
            return -thickness / 2
        if location_line == "interior":
            return thickness / 2
        return 0.0

    def _type_for(self, element: JsonObject) -> JsonObject:
        type_id = element.get("type")
        component_type = self.types.get(type_id) if isinstance(type_id, str) else None
        if component_type is None:
            raise ResolutionError(f"Element references unknown type {type_id}")
        return component_type

    def _object(self, field: str) -> JsonObject:
        return self._dict(self.model.get(field), field)

    @staticmethod
    def _dict(value: JsonValue, label: str) -> JsonObject:
        if not isinstance(value, dict):
            raise ResolutionError(f"{label} must be an object")
        return value

    @staticmethod
    def _list(value: JsonValue, label: str) -> list[JsonValue]:
        if not isinstance(value, list):
            raise ResolutionError(f"{label} must be an array")
        return value

    @staticmethod
    def _string(value: JsonValue) -> str | None:
        return value if isinstance(value, str) else None
