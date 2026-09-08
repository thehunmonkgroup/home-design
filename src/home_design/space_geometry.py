"""Wall-axis and full-thickness interior footprints for derived spaces."""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from home_design.errors import ResolutionError
from home_design.geometry import normalize2
from home_design.resolved import Vec2


@dataclass(frozen=True, slots=True)
class SpaceWallPlan:
    """Authoritative wall path and its signed gross plan extents."""

    path: tuple[Vec2, ...]
    thickness: float = 0.0
    center_offset: float = 0.0

    def footprints(self) -> list[Polygon]:
        """Return the uncut, square-ended plan of each physical wall segment."""
        result: list[Polygon] = []
        low = self.center_offset - self.thickness / 2
        high = self.center_offset + self.thickness / 2
        for start, end in zip(self.path, self.path[1:]):
            tx, ty = normalize2((end[0] - start[0], end[1] - start[1]), "wall tangent")
            result.append(
                Polygon(
                    [
                        (point[0] - ty * offset, point[1] + tx * offset)
                        for point, offset in (
                            (start, low),
                            (end, low),
                            (end, high),
                            (start, high),
                        )
                    ]
                )
            )
        return result


class SpaceGeometry:
    """Select a closed axis region and optionally remove gross bounding walls."""

    @staticmethod
    def derive(
        space_id: str,
        walls: list[SpaceWallPlan],
        seed: Vec2,
        boundary_mode: str,
    ) -> Polygon:
        """Resolve a unique space polygon, preserving its interior rings.

        :param space_id: Canonical space identity for diagnostics.
        :param walls: Declared bounding walls, before openings or other cuts.
        :param seed: Point selecting the room-facing region of the wall network.
        :param boundary_mode: Axis extent or full-thickness interior extent.
        :returns: One nonempty connected polygon.
        :raises ResolutionError: If the mode, seed or resulting region is invalid.
        """
        if boundary_mode not in {"axis", "interior"}:
            raise ResolutionError(
                f"Space {space_id} has unknown boundary mode {boundary_mode}"
            )
        seed_point = Point(seed)
        candidates = list(polygonize([LineString(wall.path) for wall in walls]))
        matches = [
            candidate for candidate in candidates if candidate.covers(seed_point)
        ]
        if len(matches) != 1:
            raise ResolutionError(
                f"Space {space_id} seed must resolve inside exactly one closed wall boundary"
            )
        axis = matches[0]
        if boundary_mode == "axis":
            return axis
        if not axis.contains(seed_point):
            raise ResolutionError(
                f"Space {space_id} interior seed must be strictly inside the wall-axis boundary"
            )
        wall_plan = unary_union(
            [polygon for wall in walls for polygon in wall.footprints()]
        )
        interior = axis.difference(wall_plan)
        if interior.is_empty:
            raise ResolutionError(
                f"Space {space_id} interior is empty after excluding full wall thickness"
            )
        if not isinstance(interior, Polygon):
            raise ResolutionError(
                f"Space {space_id} interior contains multiple disconnected regions"
            )
        if not interior.is_valid:
            raise ResolutionError(f"Space {space_id} interior footprint is invalid")
        if not interior.contains(seed_point):
            raise ResolutionError(
                f"Space {space_id} interior seed lies in or on the full wall thickness"
            )
        return interior
