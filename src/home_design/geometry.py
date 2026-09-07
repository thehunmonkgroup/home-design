"""Exact-enough deterministic geometry utilities for architectural components."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from shapely import BufferJoinStyle, constrained_delaunay_triangles
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import split

from home_design.constants import GEOMETRY_TOLERANCE_MM
from home_design.errors import ResolutionError
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import Face, MeshData, Vec2, Vec3
from home_design.roof_controls import RoofControls


def number(value: JsonValue, label: str) -> float:
    """Coerce a JSON number to float.

    :param value: Candidate numeric value.
    :param label: Human-readable field name for errors.
    :returns: Floating point number.
    :raises ResolutionError: If the value is not numeric.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResolutionError(f"{label} must be numeric")
    return float(value)


def vector2(value: JsonValue, label: str) -> Vec2:
    """Coerce a JSON array to a 2D vector.

    :param value: Candidate two-number array.
    :param label: Human-readable field name for errors.
    :returns: Two-dimensional vector.
    :raises ResolutionError: If the value is not a numeric pair.
    """
    if not isinstance(value, list) or len(value) != 2:
        raise ResolutionError(f"{label} must be a two-number array")
    return number(value[0], label), number(value[1], label)


def vector3(value: JsonValue, label: str) -> Vec3:
    """Coerce a JSON array to a 3D vector.

    :param value: Candidate three-number array.
    :param label: Human-readable field name for errors.
    :returns: Three-dimensional vector.
    :raises ResolutionError: If the value is not a numeric triple.
    """
    if not isinstance(value, list) or len(value) != 3:
        raise ResolutionError(f"{label} must be a three-number array")
    return number(value[0], label), number(value[1], label), number(value[2], label)


def normalize2(value: Vec2, label: str) -> Vec2:
    """Normalize a 2D direction.

    :param value: Direction vector.
    :param label: Human-readable value name.
    :returns: Unit vector.
    :raises ResolutionError: If the vector has zero length.
    """
    magnitude = math.hypot(*value)
    if magnitude <= GEOMETRY_TOLERANCE_MM:
        raise ResolutionError(f"{label} cannot be a zero vector")
    return value[0] / magnitude, value[1] / magnitude


def polygon_from_loops(
    outer: Sequence[Vec2], holes: Sequence[Sequence[Vec2]] = ()
) -> Polygon:
    """Construct and validate a Shapely polygon.

    :param outer: Exterior loop without a repeated closing point.
    :param holes: Optional interior loops.
    :returns: Valid positive-area polygon.
    :raises ResolutionError: If topology is invalid.
    """
    polygon = Polygon(outer, holes)
    if (
        polygon.is_empty
        or not polygon.is_valid
        or polygon.area <= GEOMETRY_TOLERANCE_MM
    ):
        raise ResolutionError("Profile must be a valid, non-self-intersecting polygon")
    return polygon


def layer_thickness(component_type: JsonObject) -> float:
    """Sum the declared layers of a component type.

    :param component_type: Layered component type.
    :returns: Total thickness in millimetres.
    :raises ResolutionError: If layers are malformed.
    """
    layers = component_type.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ResolutionError("Layered component type must contain layers")
    thickness = 0.0
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise ResolutionError(f"Layer {index} must be an object")
        thickness += number(layer.get("thickness"), f"layer {index} thickness")
    return thickness


def primary_material(component_type: JsonObject) -> str | None:
    """Choose a representative material for a resolved body.

    :param component_type: Component type definition.
    :returns: Structural material, first material, or ``None``.
    """
    material = component_type.get("material")
    if isinstance(material, str):
        return material
    layers = component_type.get("layers")
    if not isinstance(layers, list):
        return None
    candidates = [layer for layer in layers if isinstance(layer, dict)]
    structural = next(
        (layer for layer in candidates if layer.get("function") == "structure"), None
    )
    chosen = structural or (candidates[0] if candidates else None)
    selected = chosen.get("material") if chosen else None
    return selected if isinstance(selected, str) else None


def triangulate_polygon(polygon: Polygon) -> tuple[Polygon, ...]:
    """Triangulate inside polygon boundaries while preserving every boundary edge."""
    triangles = constrained_delaunay_triangles(polygon)
    return tuple(part for part in triangles.geoms if isinstance(part, Polygon))


def extrude_polygon(
    polygon: Polygon, bottom_z: float, top_z: float, material_id: str | None, role: str
) -> MeshData:
    """Create a closed triangulated vertical extrusion.

    :param polygon: Source 2D polygon, including optional holes.
    :param bottom_z: Bottom elevation.
    :param top_z: Top elevation.
    :param material_id: Canonical material ID.
    :param role: Mesh role for adapters.
    :returns: Closed mesh.
    :raises ResolutionError: If the extrusion height is zero.
    """
    if abs(top_z - bottom_z) <= GEOMETRY_TOLERANCE_MM:
        raise ResolutionError("Extrusion height must be non-zero")
    polygon = orient(polygon, sign=1.0)
    vertices: list[Vec3] = []
    faces: list[Face] = []
    index_by_vertex: dict[tuple[float, float, float], int] = {}

    def add_vertex(point: Vec3) -> int:
        key: Vec3 = (
            round(point[0], 9),
            round(point[1], 9),
            round(point[2], 9),
        )
        if key not in index_by_vertex:
            index_by_vertex[key] = len(vertices)
            vertices.append(point)
        return index_by_vertex[key]

    for triangle in triangulate_polygon(polygon):
        coordinates = _counterclockwise_exterior(triangle)
        bottom = tuple(add_vertex((x, y, bottom_z)) for x, y in coordinates)
        top = tuple(add_vertex((x, y, top_z)) for x, y in coordinates)
        faces.append(tuple(reversed(bottom)))
        faces.append(top)
    for ring in (polygon.exterior, *polygon.interiors):
        coordinates = list(ring.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            a = add_vertex((start[0], start[1], bottom_z))
            b = add_vertex((end[0], end[1], bottom_z))
            c = add_vertex((end[0], end[1], top_z))
            d = add_vertex((start[0], start[1], top_z))
            faces.extend(((a, b, c), (a, c, d)))
    return MeshData(tuple(vertices), tuple(faces), material_id, role)


def extrude_planar_face(
    boundary: Sequence[Vec3],
    thickness: float,
    material_id: str | None,
    role: str,
) -> MeshData:
    """Extrude a planar roof face opposite its upward normal.

    :param boundary: Coplanar outer boundary.
    :param thickness: Normal thickness.
    :param material_id: Canonical material ID.
    :param role: Mesh role for adapters.
    :returns: Closed roof-face prism.
    :raises ResolutionError: If the face is degenerate.
    """
    if len(boundary) < 3:
        raise ResolutionError("A planar face requires at least three vertices")
    normal = polygon_normal(boundary)
    if normal[2] < 0:
        boundary = tuple(reversed(boundary))
        normal = tuple(-coordinate for coordinate in normal)
    lower = tuple(
        (
            point[0] - normal[0] * thickness,
            point[1] - normal[1] * thickness,
            point[2] - normal[2] * thickness,
        )
        for point in boundary
    )
    vertices = tuple(boundary) + lower
    count = len(boundary)
    faces: list[Face] = []
    for triangle in triangulate_planar(boundary):
        faces.append(triangle)
        faces.append(tuple(reversed(tuple(index + count for index in triangle))))
    for index in range(count):
        next_index = (index + 1) % count
        faces.extend(
            (
                (index, next_index + count, next_index),
                (index, index + count, next_index + count),
            )
        )
    return MeshData(vertices, tuple(faces), material_id, role)


def oriented_box(
    origin: Vec3,
    tangent: Vec2,
    width: float,
    depth: float,
    height: float,
    material_id: str | None,
    role: str,
) -> MeshData:
    """Create a closed box aligned to a plan tangent.

    :param origin: Bottom center in canonical coordinates.
    :param tangent: Horizontal width direction.
    :param width: Width along tangent.
    :param depth: Depth perpendicular to tangent.
    :param height: Vertical height.
    :param material_id: Canonical material ID.
    :param role: Mesh role.
    :returns: Closed box mesh.
    """
    tx, ty = normalize2(tangent, "box tangent")
    nx, ny = -ty, tx
    corners: list[Vec3] = []
    for z_offset in (0.0, height):
        for along, across in (
            (-width / 2, -depth / 2),
            (width / 2, -depth / 2),
            (width / 2, depth / 2),
            (-width / 2, depth / 2),
        ):
            corners.append(
                (
                    origin[0] + tx * along + nx * across,
                    origin[1] + ty * along + ny * across,
                    origin[2] + z_offset,
                )
            )
    faces = (
        (0, 2, 1),
        (0, 3, 2),
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 0, 4),
        (3, 4, 7),
    )
    return MeshData(tuple(corners), faces, material_id, role)


def extrude_wall_profile(
    profile: Polygon,
    path_start: Vec2,
    tangent: Vec2,
    center_offset: float,
    thickness: float,
    base_z: float,
    material_id: str | None,
) -> MeshData:
    """Extrude a wall elevation profile through its plan thickness.

    :param profile: Wall elevation polygon in station/height coordinates.
    :param path_start: Segment start in plan.
    :param tangent: Segment forward unit vector.
    :param center_offset: Signed body-center offset from the location line.
    :param thickness: Wall body thickness.
    :param base_z: Segment base elevation.
    :param material_id: Canonical material ID.
    :returns: Closed wall mesh containing any profile holes.
    """
    tx, ty = normalize2(tangent, "wall tangent")
    nx, ny = -ty, tx
    profile = orient(profile, sign=1.0)
    vertices: list[Vec3] = []
    faces: list[Face] = []
    index_by_vertex: dict[tuple[float, float, float], int] = {}

    def world_vertex(station_height: tuple[float, float], side: float) -> Vec3:
        station, height = station_height
        across = center_offset + side * thickness / 2
        return (
            path_start[0] + tx * station + nx * across,
            path_start[1] + ty * station + ny * across,
            base_z + height,
        )

    def add_vertex(point: Vec3) -> int:
        key: Vec3 = (
            round(point[0], 9),
            round(point[1], 9),
            round(point[2], 9),
        )
        if key not in index_by_vertex:
            index_by_vertex[key] = len(vertices)
            vertices.append(point)
        return index_by_vertex[key]

    for triangle in triangulate_polygon(profile):
        if not profile.covers(triangle.representative_point()):
            continue
        coordinates = _counterclockwise_exterior(triangle)
        left = tuple(
            add_vertex(world_vertex((point[0], point[1]), 1.0)) for point in coordinates
        )
        right = tuple(
            add_vertex(world_vertex((point[0], point[1]), -1.0))
            for point in coordinates
        )
        faces.append(tuple(reversed(left)))
        faces.append(right)
    for ring in (profile.exterior, *profile.interiors):
        coordinates = list(ring.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            start_point = (start[0], start[1])
            end_point = (end[0], end[1])
            a = add_vertex(world_vertex(start_point, -1.0))
            b = add_vertex(world_vertex(end_point, -1.0))
            c = add_vertex(world_vertex(end_point, 1.0))
            d = add_vertex(world_vertex(start_point, 1.0))
            faces.extend(((a, c, b), (a, d, c)))
    return MeshData(tuple(vertices), tuple(faces), material_id, "body")


@dataclass(frozen=True, slots=True)
class RoofSurface:
    """A roof surface recipe able to answer vertical constraints."""

    form: str
    footprint: Polygon
    eave_z: float
    pitch_degrees: float
    direction: Vec2
    thickness: float
    bearing_footprint: Polygon | None = None

    def top_height(self, x: float, y: float) -> float:
        """Return roof top elevation at a plan point.

        :param x: Canonical X coordinate.
        :param y: Canonical Y coordinate.
        :returns: Roof top elevation in millimetres.
        """
        pitch = math.tan(math.radians(self.pitch_degrees))
        dx, dy = self.direction
        projections = [point[0] * dx + point[1] * dy for point in self.outer_points()]
        projection = x * dx + y * dy
        if self.form == "flat":
            return self.eave_z
        if self.form == "shed":
            return self.eave_z + (projection - min(projections)) * pitch
        if self.form == "gable":
            center = (min(projections) + max(projections)) / 2
            return (
                self.eave_z
                + (max(projections) - min(projections)) / 2 * pitch
                - abs(projection - center) * pitch
            )
        reference = (
            self.bearing_footprint
            if self.bearing_footprint is not None
            else self.footprint
        )
        boundary_distance = min(
            nx * x + ny * y + offset
            for nx, ny, offset in RoofControls.hip_planes(reference)
        )
        return self.eave_z + boundary_distance * pitch

    def underside_height(self, x: float, y: float) -> float:
        """Return roof underside elevation at a plan point.

        :param x: Canonical X coordinate.
        :param y: Canonical Y coordinate.
        :returns: Underside plane elevation at the same X/Y in millimetres.
        """
        cosine = (
            math.cos(math.radians(self.pitch_degrees)) if self.form != "flat" else 1.0
        )
        return self.top_height(x, y) - self.thickness / cosine

    def outer_points(self) -> list[Vec2]:
        reference = (
            self.bearing_footprint
            if self.bearing_footprint is not None
            else self.footprint
        )
        return [(float(x), float(y)) for x, y in list(reference.exterior.coords)[:-1]]


def roof_face_boundaries(surface: RoofSurface) -> tuple[tuple[Vec3, ...], ...]:
    """Generate planar face boundaries for a supported roof recipe.

    :param surface: Resolved parametric roof surface.
    :returns: One boundary per roof plane.
    :raises ResolutionError: If a hip roof footprint is not rectangular.
    """
    if surface.form in {"flat", "shed"}:
        points = list(surface.footprint.exterior.coords)[:-1]
        return (tuple((x, y, surface.top_height(x, y)) for x, y in points),)
    if surface.form == "gable":
        return _gable_boundaries(surface)
    return _hip_boundaries(surface)


def offset_footprint(polygon: Polygon, overhang: float) -> Polygon:
    """Offset a footprint for roof overhang.

    :param polygon: Base footprint.
    :param overhang: Signed overhang distance.
    :returns: Offset polygon.
    :raises ResolutionError: If offsetting empties or splits the polygon.
    """
    result = polygon.buffer(overhang, join_style=BufferJoinStyle.mitre)
    if result.is_empty:
        raise ResolutionError("Roof overhang must resolve to one non-empty polygon")
    return result


def _gable_boundaries(surface: RoofSurface) -> tuple[tuple[Vec3, ...], ...]:
    dx, dy = surface.direction
    points = surface.outer_points()
    projections = [x * dx + y * dy for x, y in points]
    center = (min(projections) + max(projections)) / 2
    cx, cy = surface.footprint.centroid.coords[0]
    span = (
        max(
            surface.footprint.bounds[2] - surface.footprint.bounds[0],
            surface.footprint.bounds[3] - surface.footprint.bounds[1],
        )
        * 4
    )
    ridge_point = (
        cx + dx * (center - (cx * dx + cy * dy)),
        cy + dy * (center - (cx * dx + cy * dy)),
    )
    ridge_direction = (-dy, dx)
    cutter = LineString(
        [
            (
                ridge_point[0] - ridge_direction[0] * span,
                ridge_point[1] - ridge_direction[1] * span,
            ),
            (
                ridge_point[0] + ridge_direction[0] * span,
                ridge_point[1] + ridge_direction[1] * span,
            ),
        ]
    )
    pieces = split(surface.footprint, cutter)
    polygons = [geometry for geometry in pieces.geoms if isinstance(geometry, Polygon)]
    if len(polygons) != 2:
        raise ResolutionError("Gable roof footprint must split cleanly at its ridge")
    return tuple(
        tuple(
            (x, y, surface.top_height(x, y))
            for x, y in list(polygon.exterior.coords)[:-1]
        )
        for polygon in polygons
    )


def _hip_boundaries(surface: RoofSurface) -> tuple[tuple[Vec3, ...], ...]:
    reference = (
        surface.bearing_footprint
        if surface.bearing_footprint is not None
        else surface.footprint
    )
    planes = RoofControls.hip_planes(reference)
    boundaries: list[tuple[Vec3, ...]] = []
    for plane in planes:
        points = [
            (float(x), float(y))
            for x, y in list(surface.footprint.exterior.coords)[:-1]
        ]
        for other in planes:
            difference = (plane[0] - other[0], plane[1] - other[1], plane[2] - other[2])
            points = RoofControls.clip(points, difference)
        if len(points) >= 3 and Polygon(points).area > 0.01:
            boundaries.append(
                tuple((x, y, surface.top_height(x, y)) for x, y in points)
            )
    return tuple(boundaries)


def polygon_normal(boundary: Sequence[Vec3]) -> Vec3:
    """Return the unit Newell normal of a planar polygon boundary."""
    nx = ny = nz = 0.0
    for current, following in zip(boundary, (*boundary[1:], boundary[0])):
        nx += (current[1] - following[1]) * (current[2] + following[2])
        ny += (current[2] - following[2]) * (current[0] + following[0])
        nz += (current[0] - following[0]) * (current[1] + following[1])
    magnitude = math.sqrt(nx * nx + ny * ny + nz * nz)
    if magnitude <= GEOMETRY_TOLERANCE_MM:
        raise ResolutionError("Planar face has no stable normal")
    return nx / magnitude, ny / magnitude, nz / magnitude


def triangulate_planar(boundary: Sequence[Vec3]) -> tuple[Face, ...]:
    """Triangulate a planar boundary while preserving its outward winding."""
    normal = polygon_normal(boundary)
    omitted_axis = max(range(3), key=lambda axis: abs(normal[axis]))
    retained_axes = [axis for axis in range(3) if axis != omitted_axis]
    projected: list[Vec2] = [
        (point[retained_axes[0]], point[retained_axes[1]]) for point in boundary
    ]
    polygon = polygon_from_loops(projected)
    faces: list[Face] = []
    for triangle in triangulate_polygon(polygon):
        if not polygon.covers(triangle.representative_point()):
            continue
        face: list[int] = []
        for coordinate in list(triangle.exterior.coords)[:-1]:
            matches = [
                index
                for index, point in enumerate(projected)
                if math.dist(point, coordinate) <= GEOMETRY_TOLERANCE_MM
            ]
            if not matches:
                raise ResolutionError(
                    "Roof face triangulation introduced an unsupported vertex"
                )
            face.append(matches[0])
        oriented_face = tuple(face)
        if _face_normal_alignment(boundary, oriented_face, normal) < 0:
            oriented_face = tuple(reversed(oriented_face))
        faces.append(oriented_face)
    return tuple(faces)


def _counterclockwise_exterior(polygon: Polygon) -> tuple[Vec2, ...]:
    """Return a polygon exterior in counterclockwise order.

    :param polygon: Polygon supplying the exterior coordinates.
    :returns: Exterior coordinates without the repeated closing point.
    """
    coordinates = tuple(
        (float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]
    )
    signed_area = sum(
        current[0] * following[1] - following[0] * current[1]
        for current, following in zip(coordinates, (*coordinates[1:], coordinates[0]))
    )
    return coordinates if signed_area > 0 else tuple(reversed(coordinates))


def _face_normal_alignment(
    vertices: Sequence[Vec3], face: Face, expected_normal: Vec3
) -> float:
    """Measure a triangular face's alignment with an expected normal.

    :param vertices: Vertex coordinates containing the face.
    :param face: Triangle vertex indices.
    :param expected_normal: Desired outward normal.
    :returns: Positive value for aligned winding and negative for reversed winding.
    """
    first, second, third = (vertices[index] for index in face)
    edge_a = tuple(second[axis] - first[axis] for axis in range(3))
    edge_b = tuple(third[axis] - first[axis] for axis in range(3))
    cross = (
        edge_a[1] * edge_b[2] - edge_a[2] * edge_b[1],
        edge_a[2] * edge_b[0] - edge_a[0] * edge_b[2],
        edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0],
    )
    return sum(cross[axis] * expected_normal[axis] for axis in range(3))
