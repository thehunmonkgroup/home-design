"""Regularized planar boundaries for volume-checked serialization of Boolean solids."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from shapely import set_precision
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from home_design.geometry import triangulate_polygon
from home_design.resolved import Face, MeshData, Vec3


@dataclass
class SurfacePlane:
    """A shared plane with separately oriented material boundaries."""

    origin: NDArray[np.float64]
    normal: NDArray[np.float64]
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    positive: list[BaseGeometry] = field(default_factory=list)
    negative: list[BaseGeometry] = field(default_factory=list)

    def project(self, points: NDArray[np.float64]) -> NDArray[np.float64]:
        """Project nearby world points onto the shared planar coordinate system."""
        relative = points - self.origin
        return np.column_stack((relative @ self.x, relative @ self.y))

    def point(self, x: float, y: float) -> NDArray[np.float64]:
        """Return one world point on the plane."""
        return self.origin + x * self.x + y * self.y


class SurfaceVertices:
    """Share boundary points within one connected shell while retaining original coordinates."""

    def __init__(self, original: NDArray[np.float64], tolerance: float) -> None:
        """Use the original mesh as the preferred coordinate source for nearby vertices."""
        self.original: NDArray[np.float64] = original
        self.tolerance: float = tolerance
        self.vertices: list[Vec3] = []

    def register(self, point: NDArray[np.float64]) -> int:
        """Reuse an existing boundary point or retain a nearby original mesh coordinate."""
        if self.vertices:
            distances = np.linalg.norm(np.asarray(self.vertices) - point, axis=1)
            closest = int(np.argmin(distances))
            if distances[closest] < self.tolerance:
                return closest
        distances = np.linalg.norm(self.original - point, axis=1)
        closest = int(np.argmin(distances))
        if distances[closest] < self.tolerance:
            point = self.original[closest]
        self.vertices.append((float(point[0]), float(point[1]), float(point[2])))
        return len(self.vertices) - 1


class SolidSurfaces:
    """Cancel coincident opposite faces and triangulate conforming planar boundaries.

    This produces a candidate mesh only. The caller must verify its material
    volume against the original native result before accepting it. Connected
    shells are processed separately so contact does not weld unrelated topology.
    """

    PLANE_TOLERANCE_MM: float = 1e-6
    PLANAR_GRID_MM: float = 1e-7
    MINIMUM_DOUBLE_AREA_MM2: float = 1e-12

    @classmethod
    def planes(
        cls, points: NDArray[np.float64], faces: tuple[Face, ...]
    ) -> list[SurfacePlane]:
        """Group largest triangles first so small contact slivers do not determine a plane."""
        triangles = [points[list(face)] for face in faces]
        triangles.sort(
            key=lambda tri: -np.linalg.norm(np.cross(tri[1] - tri[0], tri[2] - tri[0]))
        )
        planes: list[SurfacePlane] = []
        for triangle in triangles:
            cross = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            magnitude = np.linalg.norm(cross)
            if magnitude < cls.MINIMUM_DOUBLE_AREA_MM2:
                continue
            normal = np.asarray(cross / magnitude, dtype=np.float64)
            plane = next(
                (
                    candidate
                    for candidate in planes
                    if np.max(np.abs((triangle - candidate.origin) @ candidate.normal))
                    < cls.PLANE_TOLERANCE_MM
                ),
                None,
            )
            if plane is None:
                x = triangle[1] - triangle[0]
                x /= np.linalg.norm(x)
                y = np.asarray(np.cross(normal, x), dtype=np.float64)
                plane = SurfacePlane(triangle[0], normal, x, y)
                planes.append(plane)
            polygon = set_precision(
                Polygon(plane.project(triangle)), cls.PLANAR_GRID_MM
            )
            group = plane.positive if normal @ plane.normal > 0 else plane.negative
            group.append(polygon)
        return planes

    @classmethod
    def polygons(cls, geometry: BaseGeometry) -> tuple[Polygon, ...]:
        """Keep only nonempty polygon regions after oriented boundary cancellation."""
        if isinstance(geometry, Polygon):
            return () if geometry.is_empty else (geometry,)
        if isinstance(geometry, (MultiPolygon, GeometryCollection)):
            return tuple(
                polygon
                for part in geometry.geoms
                if isinstance(part, BaseGeometry)
                for polygon in cls.polygons(part)
            )
        return ()

    @classmethod
    def regions(
        cls, planes: list[SurfacePlane], vertices: SurfaceVertices
    ) -> list[tuple[SurfacePlane, int, list[list[int]]]]:
        """Remove planar overlap with opposite orientation and register all shared boundaries."""
        regions: list[tuple[SurfacePlane, int, list[list[int]]]] = []
        for plane in planes:
            positive = unary_union(plane.positive)
            negative = unary_union(plane.negative)
            for geometry, sign in ((positive - negative, 1), (negative - positive, -1)):
                for polygon in cls.polygons(geometry):
                    rings = [
                        [
                            vertices.register(plane.point(float(p[0]), float(p[1])))
                            for p in list(ring.coords)[:-1]
                        ]
                        for ring in (polygon.exterior, *polygon.interiors)
                    ]
                    regions.append((plane, sign, rings))
        return regions

    @classmethod
    def boundary(cls, ring: list[int], world: NDArray[np.float64]) -> list[int]:
        """Split each edge at shared collinear points to avoid topological T-junctions."""
        refined: list[int] = []
        for index, first in enumerate(ring):
            second = ring[(index + 1) % len(ring)]
            direction = world[second] - world[first]
            length_squared = direction @ direction
            if length_squared < cls.PLANE_TOLERANCE_MM**2:
                continue
            parameters = (world - world[first]) @ direction / length_squared
            distances = np.linalg.norm(
                world - world[first] - np.outer(parameters, direction), axis=1
            )
            included = [
                i
                for i in range(len(world))
                if 0 <= parameters[i] < 1 - 1e-12
                and distances[i] < cls.PLANE_TOLERANCE_MM
            ]
            refined.extend(sorted(included, key=lambda i: parameters[i]))
        return refined

    @classmethod
    def regularize(cls, mesh: MeshData) -> MeshData:
        """Return an oriented triangle mesh with cancelled planar folds and conforming edges."""
        points = np.asarray(mesh.vertices, dtype=np.float64)
        vertices = SurfaceVertices(points, cls.PLANE_TOLERANCE_MM)
        regions = cls.regions(cls.planes(points, mesh.faces), vertices)
        world = np.asarray(vertices.vertices, dtype=np.float64)
        faces: list[Face] = []
        for plane, sign, rings in regions:
            refined = [cls.boundary(ring, world) for ring in rings]
            if len(set(refined[0])) < 3:
                continue
            boundaries = [plane.project(world[refined[0]]).tolist()]
            boundaries.extend(
                plane.project(world[ring]).tolist()
                for ring in refined[1:]
                if len(set(ring)) >= 3
            )
            polygon = Polygon(boundaries[0], boundaries[1:])
            for triangle in triangulate_polygon(polygon):
                indices = [
                    vertices.register(plane.point(float(x), float(y)))
                    for x, y in list(triangle.exterior.coords)[:-1]
                ]
                if len(set(indices)) < 3:
                    continue
                coordinates = np.asarray([vertices.vertices[i] for i in indices])
                cross = np.cross(
                    coordinates[1] - coordinates[0], coordinates[2] - coordinates[0]
                )
                if cross @ plane.normal * sign < 0:
                    indices.reverse()
                faces.append(tuple(indices))
        return MeshData(
            tuple(vertices.vertices), tuple(faces), mesh.material_id, mesh.role
        )
