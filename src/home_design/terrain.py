"""Survey triangulation and piecewise-planar grade evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import triangulate, unary_union

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.geometry import vector3
from home_design.json_types import JsonObject
from home_design.resolved import Face, MeshData, Vec2, Vec3


@dataclass(frozen=True)
class TerrainSurface:
    """A validated triangulated survey surface in canonical millimetres."""

    vertices: tuple[Vec3, ...]
    faces: tuple[Face, ...]

    @classmethod
    def from_element(cls, element: JsonObject) -> TerrainSurface:
        """Use supplied triangles or triangulate unique survey X/Y positions."""
        vertices = tuple(
            vector3(value, "survey point")
            for value in Authoring.array(element.get("points"))
        )
        lookup = {(point[0], point[1]): index for index, point in enumerate(vertices)}
        if len(lookup) != len(vertices):
            raise ResolutionError("Terrain points must have unique X/Y coordinates")
        triangles = element.get("triangles")
        if isinstance(triangles, list):
            faces = tuple(
                tuple(
                    int(index)
                    for index in Authoring.array(face)
                    if isinstance(index, int)
                )
                for face in triangles
            )
        else:
            polygons = triangulate(MultiPoint(list(lookup)))
            faces = tuple(
                tuple(
                    lookup[(float(x), float(y))]
                    for x, y in list(polygon.exterior.coords)[:-1]
                )
                for polygon in polygons
            )
        if not faces:
            raise ResolutionError(
                "Terrain requires at least three non-collinear points"
            )
        oriented: list[Face] = []
        polygons: list[Polygon] = []
        for face in faces:
            if len(face) != 3 or min(face) < 0 or max(face) >= len(vertices):
                raise ResolutionError(
                    "Terrain triangle index is outside its survey points"
                )
            polygon = Polygon(
                [(vertices[index][0], vertices[index][1]) for index in face]
            )
            if polygon.area < 0.01:
                raise ResolutionError("Terrain contains a degenerate triangle")
            oriented.append(face if polygon.exterior.is_ccw else tuple(reversed(face)))
            polygons.append(polygon)
        if (
            sum(polygon.area for polygon in polygons) - unary_union(polygons).area
            > 0.01
        ):
            raise ResolutionError("Terrain triangles overlap in plan")
        return cls(vertices, tuple(oriented))

    def height(self, point: Vec2) -> float:
        """Interpolate within a triangle; reject extrapolation beyond survey coverage."""
        for face in self.faces:
            a, b, c = (self.vertices[index] for index in face)
            polygon = Polygon([(a[0], a[1]), (b[0], b[1]), (c[0], c[1])])
            if not polygon.buffer(0.001).covers(Point(point)):
                continue
            determinant = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            first = (
                (b[1] - c[1]) * (point[0] - c[0]) + (c[0] - b[0]) * (point[1] - c[1])
            ) / determinant
            second = (
                (c[1] - a[1]) * (point[0] - c[0]) + (a[0] - c[0]) * (point[1] - c[1])
            ) / determinant
            return first * a[2] + second * b[2] + (1 - first - second) * c[2]
        raise ResolutionError(f"No surveyed terrain triangle covers {point}")

    def mesh(self, material: str | None) -> MeshData:
        """Return an intentionally open survey surface."""
        return MeshData(self.vertices, self.faces, material, "terrain-surface")
