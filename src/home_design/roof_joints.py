"""Shared spatial bisectors for adjoining roof layers and framing domains."""

from __future__ import annotations

import math
from collections.abc import Sequence

from shapely import get_coordinates
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from home_design.geometry import polygon_normal
from home_design.resolved import Vec3


class RoofJoints:
    """Find clipping planes only where roof faces share an actual spatial edge."""

    @staticmethod
    def normal(boundary: Sequence[Vec3]) -> Vec3:
        """Orient a face normal upwards independently of polygon winding."""
        normal = polygon_normal(boundary)
        return normal if normal[2] >= 0 else (-normal[0], -normal[1], -normal[2])

    @classmethod
    def planes(
        cls,
        boundary: Sequence[Vec3],
        neighbors: Sequence[Sequence[Vec3]],
        inside: Vec3 | None = None,
    ) -> tuple[tuple[Vec3, Vec3], ...]:
        """Return bisector origins and normals directed into the selected face."""
        profile = Polygon([(point[0], point[1]) for point in boundary])
        normal = cls.normal(boundary)
        if inside is None:
            point = profile.representative_point()
            inside = (point.x, point.y, cls.elevation(boundary[0], normal, point.x, point.y))
        planes: list[tuple[Vec3, Vec3]] = []
        for other in neighbors:
            shared = profile.boundary.intersection(
                Polygon([(point[0], point[1]) for point in other]).boundary
            )
            other_normal = cls.normal(other)
            if shared.length <= 0.01 or not cls.same_edge(
                shared, boundary[0], normal, other[0], other_normal
            ):
                continue
            difference: Vec3 = (
                normal[0] - other_normal[0],
                normal[1] - other_normal[1],
                normal[2] - other_normal[2],
            )
            if math.sqrt(sum(value * value for value in difference)) <= 1e-8:
                continue
            midpoint = shared.representative_point()
            origin = (
                midpoint.x,
                midpoint.y,
                cls.elevation(boundary[0], normal, midpoint.x, midpoint.y),
            )
            if sum(difference[i] * (inside[i] - origin[i]) for i in range(3)) < 0:
                difference = (-difference[0], -difference[1], -difference[2])
            planes.append((origin, difference))
        return tuple(planes)

    @staticmethod
    def elevation(origin: Vec3, normal: Vec3, x: float, y: float) -> float:
        """Sample the unshifted roof plane at a plan position."""
        return origin[2] - (
            normal[0] * (x - origin[0]) + normal[1] * (y - origin[1])
        ) / normal[2]

    @classmethod
    def same_edge(
        cls,
        shared: BaseGeometry,
        first: Vec3,
        first_normal: Vec3,
        second: Vec3,
        second_normal: Vec3,
    ) -> bool:
        """Reject coincident plan edges whose spatial elevations differ."""
        if first_normal[2] <= 1e-9 or second_normal[2] <= 1e-9:
            return False
        return all(
            abs(cls.elevation(first, first_normal, x, y)
                - cls.elevation(second, second_normal, x, y)) <= 0.01
            for x, y in get_coordinates(shared)
        )
