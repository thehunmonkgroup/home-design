"""Resolution of canonical design intent into adapter-neutral geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.affinity import translate
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.ops import polygonize

from home_design.errors import ResolutionError
from home_design.geometry import (
    RoofSurface,
    extrude_planar_face,
    extrude_polygon,
    extrude_wall_profile,
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
)
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonValue
from home_design.locators import LocatorResolver, point_at_station
from home_design.resolved import MeshData, ResolvedElement, ResolvedModel, Vec2, Vec3


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

    def resolve(self) -> ResolvedModel:
        """Resolve all architectural components and integrations.

        :returns: Adapter-neutral resolved model.
        :raises ResolutionError: If validated intent is not geometrically resolvable.
        """
        self._prepare_roofs()
        self._prepare_openings()
        resolved: dict[str, ResolvedElement] = {}
        for kind in (
            "slab",
            "roof",
            "wall",
            "opening",
            "door",
            "window",
            "space",
            "assembly",
        ):
            for element_id, element in self.elements.items():
                if element.get("kind") == kind:
                    resolved[element_id] = self._resolve_element(element_id, element)
        return ResolvedModel(
            model_version=str(self.model.get("modelVersion")),
            source_revision=int(number(self.model.get("revision", 0), "revision")),
            project=self._object("project"),
            coordinate_system=self._object("coordinateSystem"),
            levels=self._object("levels"),
            materials=self._object("materials"),
            types=self._object("types"),
            elements=tuple(resolved[element_id] for element_id in self.elements),
            relationships=self._object("relationships"),
        )

    def _resolve_element(self, element_id: str, element: JsonObject) -> ResolvedElement:
        kind = str(element.get("kind"))
        if kind == "slab":
            return self._resolve_slab(element_id, element)
        if kind == "roof":
            return self._resolve_roof(element_id, element)
        if kind == "wall":
            return self._resolve_wall(element_id, element)
        if kind == "opening":
            return self._resolve_opening(element_id, element)
        if kind in {"door", "window"}:
            return self._resolve_fill(element_id, element)
        if kind == "space":
            return self._resolve_space(element_id, element)
        return ResolvedElement(
            element_id,
            kind,
            str(element.get("name")),
            self._string(element.get("storey")),
            data={"assemblyType": element.get("assemblyType")},
        )

    def _resolve_slab(self, element_id: str, element: JsonObject) -> ResolvedElement:
        component_type = self._type_for(element)
        thickness = layer_thickness(component_type)
        outer, holes = self.locators.profile2(element.get("footprint"))
        polygon = polygon_from_loops(outer, holes)
        datum = self._dict(element.get("datum"), "slab datum")
        datum_z = self.locators.level_constraint(datum)
        direction = str(element.get("extrusionDirection"))
        bottom_z, top_z = (
            (datum_z - thickness, datum_z)
            if direction == "down"
            else (datum_z, datum_z + thickness)
        )
        mesh = extrude_polygon(
            polygon, bottom_z, top_z, primary_material(component_type), "body"
        )
        return ResolvedElement(
            element_id,
            "slab",
            str(element.get("name")),
            self._string(element.get("storey")),
            (mesh,),
            {
                "typeId": element.get("type"),
                "role": element.get("role"),
                "thickness": thickness,
                "topElevation": top_z,
                "bottomElevation": bottom_z,
                "footprint": {
                    "outer": [list(point) for point in outer],
                    "holes": [[list(point) for point in loop] for loop in holes],
                },
            },
        )

    def _resolve_roof(self, element_id: str, element: JsonObject) -> ResolvedElement:
        component_type = self._type_for(element)
        thickness = layer_thickness(component_type)
        geometry = self._dict(element.get("geometry"), "roof geometry")
        material_id = primary_material(component_type)
        if geometry.get("kind") == "faceSet":
            faces_value = geometry.get("faces")
            if not isinstance(faces_value, list):
                raise ResolutionError(f"Roof {element_id} requires faces")
            boundaries: list[tuple[Vec3, ...]] = []
            face_ids: list[str] = []
            for face in faces_value:
                face_object = self._dict(face, "roof face")
                boundary = self._dict(face_object.get("boundary"), "roof boundary")
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
            face_ids = [
                f"{element_id}.face-{index + 1}" for index in range(len(boundaries))
            ]
        meshes = tuple(
            extrude_planar_face(
                boundary, thickness, material_id, f"roof-face:{face_id}"
            )
            for boundary, face_id in zip(boundaries, face_ids)
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
        material_id = primary_material(component_type)
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
        top_elevations: list[float] = []
        for segment_index, (start, end) in enumerate(zip(points, points[1:])):
            segment_length = math.dist(start, end)
            tangent = normalize2((end[0] - start[0], end[1] - start[1]), "wall tangent")
            top_start = self._wall_top(element, start, base_z)
            top_end = self._wall_top(element, end, base_z)
            top_elevations.extend((top_start, top_end))
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
                mesh = extrude_wall_profile(
                    polygon,
                    start,
                    tangent,
                    center_offset,
                    thickness,
                    base_z,
                    material_id,
                )
                role = f"body:{segment_index + 1}:{part_index + 1}"
                meshes.append(
                    MeshData(mesh.vertices, mesh.faces, mesh.material_id, role)
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
                "baseElevation": base_z,
                "topElevationRange": [min(top_elevations), max(top_elevations)],
                "thickness": thickness,
                "locationLine": element.get("locationLine"),
            },
        )

    def _resolve_opening(self, element_id: str, element: JsonObject) -> ResolvedElement:
        opening = self.openings[element_id]
        host = self.elements[opening.host_id]
        host_path = self.locators.path2(host.get("path"))
        center_station = opening.start_station + opening.width / 2
        point, tangent = point_at_station(host_path, center_station)
        host_type = self._type_for(host)
        host_depth = layer_thickness(host_type)
        placement = self._dict(element.get("placement"), "opening placement")
        normal = (-tangent[1], tangent[0])
        depth_offset = number(placement.get("depthOffset"), "opening depth offset")
        base_z = self._constraint_height(
            self._dict(host.get("base"), "wall base"), point, "top"
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
            meshes = (
                oriented_box(
                    adjusted_origin,
                    tangent,
                    width,
                    min(depth, 60.0),
                    height,
                    material_id,
                    "door-panel",
                ),
            )
        else:
            meshes = self._window_meshes(
                adjusted_origin, tangent, width, height, depth, material_id
            )
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
            if element.get("kind") != "roof":
                continue
            geometry = self._dict(element.get("geometry"), "roof geometry")
            if geometry.get("kind") != "parametric":
                continue
            outer, holes = self.locators.profile2(geometry.get("footprint"))
            polygon = polygon_from_loops(outer, holes)
            polygon = offset_footprint(
                polygon, number(geometry.get("overhang"), "roof overhang")
            )
            eave_z = self.locators.level_constraint(
                self._dict(geometry.get("eaveDatum"), "roof eave datum")
            )
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
            self.roof_surfaces[element_id] = RoofSurface(
                form,
                polygon,
                eave_z,
                pitch,
                direction,
                layer_thickness(self._type_for(element)),
            )

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
        if referenced.get("kind") == "slab":
            slab_type = self._type_for(referenced)
            thickness = layer_thickness(slab_type)
            datum_z = self.locators.level_constraint(
                self._dict(referenced.get("datum"), "slab datum")
            )
            direction = referenced.get("extrusionDirection")
            top = datum_z if direction == "down" else datum_z + thickness
            bottom = datum_z - thickness if direction == "down" else datum_z
            return (top if surface == "top" else bottom) + offset
        roof = self.roof_surfaces.get(element_id)
        if roof is not None:
            height = (
                roof.underside_height(*point)
                if surface == "underside"
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
        projections = [
            x * dx + y * dy for x, y in list(roof.footprint.exterior.coords)[:-1]
        ]
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
                top - thickness * abs(normal[2]) / magnitude
                if surface == "underside"
                else top
            )
        if not heights:
            label = f" selected by {selector}" if selector else ""
            raise ResolutionError(f"No explicit roof face{label} covers point {point}")
        return min(heights) if surface == "underside" else max(heights)

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
