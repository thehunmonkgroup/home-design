"""Bearing and edge controls for parametric roof recipes."""

from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import Polygon

from home_design.errors import ResolutionError
from home_design.resolved import Vec2, Vec3


class RoofControls:
    """Construct independently offset convex roof boundaries."""

    @staticmethod
    def hip_planes(footprint: Polygon) -> tuple[Vec3, ...]:
        """Return signed inward-distance planes for a rectangular hip bearing line."""
        rectangle = footprint.minimum_rotated_rectangle
        if not isinstance(rectangle, Polygon) or abs(
            rectangle.area - footprint.area
        ) > max(1.0, footprint.area * 1e-6):
            raise ResolutionError("Hip roofs require a rectangular footprint")
        points = list(rectangle.exterior.coords)[:-1]
        sign = 1 if rectangle.exterior.is_ccw else -1
        planes: list[Vec3] = []
        for start, end in zip(points, (*points[1:], points[0])):
            length = math.dist(start, end)
            nx = -(end[1] - start[1]) / length * sign
            ny = (end[0] - start[0]) / length * sign
            planes.append((nx, ny, -nx * start[0] - ny * start[1]))
        return tuple(planes)

    @staticmethod
    def clip(points: list[Vec2], plane: Vec3) -> list[Vec2]:
        """Clip a convex polygon to a signed half-plane without introducing holes."""
        if not points:
            return []
        result: list[Vec2] = []
        for start, end in zip(points, (*points[1:], points[0])):
            first = plane[0] * start[0] + plane[1] * start[1] + plane[2]
            second = plane[0] * end[0] + plane[1] * end[1] + plane[2]
            if first <= 1e-7:
                result.append(start)
            if (first < -1e-7 and second > 1e-7) or (first > 1e-7 and second < -1e-7):
                ratio = first / (first - second)
                result.append(
                    (
                        start[0] + ratio * (end[0] - start[0]),
                        start[1] + ratio * (end[1] - start[1]),
                    )
                )
        return list(dict.fromkeys(result))

    @staticmethod
    def edge_footprint(polygon: Polygon, distances: Sequence[float]) -> Polygon:
        """Offset each authored edge without changing bearing geometry.

        :param polygon: Convex footprint with no holes.
        :param distances: Outward offsets in authored boundary order.
        :returns: Valid expanded polygon.
        """
        points: list[Vec2] = [
            (float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]
        ]
        if len(distances) != len(points):
            raise ResolutionError(
                "edgeOverhangs must have one distance per footprint edge"
            )
        if polygon.interiors or not polygon.equals(polygon.convex_hull):
            raise ResolutionError(
                "Independent roof edge overhangs require a convex footprint without holes"
            )
        sign = 1.0 if polygon.exterior.is_ccw else -1.0
        lines: list[tuple[Vec2, Vec2]] = []
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            length = math.dist(start, end)
            if length < 0.01:
                raise ResolutionError("Roof footprint has a zero-length edge")
            dx, dy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
            distance = distances[index]
            lines.append(
                (
                    (start[0] + sign * dy * distance, start[1] - sign * dx * distance),
                    (dx, dy),
                )
            )
        corners: list[Vec2] = []
        for index, (point, direction) in enumerate(lines):
            previous, previous_direction = lines[index - 1]
            cross = (
                previous_direction[0] * direction[1]
                - previous_direction[1] * direction[0]
            )
            if abs(cross) < 1e-9:
                raise ResolutionError(
                    "Independent roof overhangs require non-collinear adjacent edges"
                )
            delta = (point[0] - previous[0], point[1] - previous[1])
            station = (delta[0] * direction[1] - delta[1] * direction[0]) / cross
            corners.append(
                (
                    previous[0] + station * previous_direction[0],
                    previous[1] + station * previous_direction[1],
                )
            )
        result = Polygon(corners)
        if not result.is_valid or result.area <= 0:
            raise ResolutionError("Roof edge overhangs do not form a valid footprint")
        return result
