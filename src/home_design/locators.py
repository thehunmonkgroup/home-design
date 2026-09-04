"""Resolution of shared anchors, paths, levels, and profiles."""

from __future__ import annotations

import math
from collections.abc import Sequence

from home_design.errors import ResolutionError
from home_design.geometry import number, vector2, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import Vec2, Vec3


class LocatorResolver:
    """Resolve canonical locators without producing component geometry."""

    def __init__(self, model: JsonObject) -> None:
        """Initialize from a schema-valid model.

        :param model: Canonical model object.
        """
        self.model: JsonObject = model
        self.levels: dict[str, JsonObject] = self._registry("levels")
        self.anchors: dict[str, JsonObject] = self._registry("anchors")
        self.elements: dict[str, JsonObject] = self._registry("elements")

    def level_elevation(self, level_id: str) -> float:
        """Resolve a level elevation.

        :param level_id: Stable level ID.
        :returns: Elevation in millimetres.
        :raises ResolutionError: If the level does not exist.
        """
        level = self.levels.get(level_id)
        if level is None:
            raise ResolutionError(f"Unknown level {level_id}")
        return number(level.get("elevation"), f"level {level_id} elevation")

    def level_constraint(self, constraint: JsonObject) -> float:
        """Resolve a level constraint to elevation.

        :param constraint: Level constraint object.
        :returns: Elevation including offset.
        :raises ResolutionError: If the constraint is malformed.
        """
        level_id = constraint.get("level")
        if not isinstance(level_id, str):
            raise ResolutionError("Level constraint requires a level ID")
        return self.level_elevation(level_id) + number(
            constraint.get("offset"), "level offset"
        )

    def point2(self, locator: JsonValue, active: tuple[str, ...] = ()) -> Vec2:
        """Resolve a two-dimensional point locator.

        :param locator: Point literal or anchor locator.
        :param active: Anchor recursion stack.
        :returns: Canonical X/Y point.
        :raises ResolutionError: If the locator or anchor is incompatible.
        """
        if not isinstance(locator, dict):
            raise ResolutionError("Point locator must be an object")
        if "point" in locator:
            return vector2(locator["point"], "point locator")
        anchor_id = locator.get("anchor")
        if not isinstance(anchor_id, str):
            raise ResolutionError("Point locator requires point or anchor")
        if anchor_id in active:
            raise ResolutionError(
                f"Anchor dependency cycle: {' -> '.join((*active, anchor_id))}"
            )
        anchor = self.anchors.get(anchor_id)
        if anchor is None:
            raise ResolutionError(f"Unknown anchor {anchor_id}")
        kind = anchor.get("kind")
        if kind == "point2":
            return vector2(anchor.get("position"), f"anchor {anchor_id} position")
        if kind == "point3":
            x, y, _ = vector3(anchor.get("position"), f"anchor {anchor_id} position")
            return x, y
        if kind == "elementStation":
            element_id = anchor.get("element")
            if not isinstance(element_id, str):
                raise ResolutionError(f"Anchor {anchor_id} requires an element")
            element = self.elements.get(element_id)
            if element is None or element.get("kind") != "wall":
                raise ResolutionError(f"Anchor {anchor_id} requires a wall element")
            points = self.path2(element.get("path"), (*active, anchor_id))
            station = number(anchor.get("station"), f"anchor {anchor_id} station")
            point, tangent = point_at_station(points, station)
            transverse = number(anchor.get("transverseOffset", 0), "transverse offset")
            normal = (-tangent[1], tangent[0])
            return point[0] + normal[0] * transverse, point[1] + normal[1] * transverse
        raise ResolutionError(
            f"Anchor {anchor_id} of kind {kind} is not a point locator"
        )

    def point3_anchor(self, anchor_id: str) -> Vec3:
        """Resolve a three-dimensional anchor.

        :param anchor_id: Stable anchor ID.
        :returns: Canonical X/Y/Z point.
        :raises ResolutionError: If the anchor cannot produce a 3D point.
        """
        anchor = self.anchors.get(anchor_id)
        if anchor is None:
            raise ResolutionError(f"Unknown anchor {anchor_id}")
        kind = anchor.get("kind")
        if kind == "point3":
            return vector3(anchor.get("position"), f"anchor {anchor_id} position")
        if kind == "point2":
            x, y = vector2(anchor.get("position"), f"anchor {anchor_id} position")
            level_id = anchor.get("level")
            if not isinstance(level_id, str):
                raise ResolutionError(f"Anchor {anchor_id} requires a level")
            return x, y, self.level_elevation(level_id)
        if kind == "elementStation":
            x, y = self.point2({"anchor": anchor_id})
            element_id = anchor.get("element")
            element = (
                self.elements.get(element_id) if isinstance(element_id, str) else None
            )
            if element is None:
                raise ResolutionError(f"Anchor {anchor_id} has no resolvable element")
            storey_id = element.get("storey")
            base = (
                self.level_elevation(storey_id) if isinstance(storey_id, str) else 0.0
            )
            return (
                x,
                y,
                base + number(anchor.get("verticalOffset", 0), "vertical offset"),
            )
        raise ResolutionError(
            f"Anchor {anchor_id} of kind {kind} is not a point anchor"
        )

    def path2(self, path: JsonValue, active: tuple[str, ...] = ()) -> tuple[Vec2, ...]:
        """Resolve a line, polyline, or axis anchor path.

        :param path: Canonical path object.
        :param active: Anchor recursion stack.
        :returns: Ordered plan points.
        :raises ResolutionError: If the path is malformed or degenerate.
        """
        if not isinstance(path, dict):
            raise ResolutionError("Path must be an object")
        kind = path.get("kind")
        if kind == "line":
            points = (
                self.point2(path.get("start"), active),
                self.point2(path.get("end"), active),
            )
        elif kind == "polyline":
            locators = path.get("points")
            if not isinstance(locators, list):
                raise ResolutionError("Polyline requires points")
            points = tuple(self.point2(locator, active) for locator in locators)
        elif kind == "axisAnchor":
            anchor_id = path.get("anchor")
            if not isinstance(anchor_id, str):
                raise ResolutionError("Axis path requires an anchor")
            if anchor_id in active:
                raise ResolutionError(
                    f"Anchor dependency cycle: {' -> '.join((*active, anchor_id))}"
                )
            anchor = self.anchors.get(anchor_id)
            if anchor is None or anchor.get("kind") != "axis2":
                raise ResolutionError(
                    f"Axis path anchor {anchor_id} must be an axis2 anchor"
                )
            points = (
                self.point2(anchor.get("start"), (*active, anchor_id)),
                self.point2(anchor.get("end"), (*active, anchor_id)),
            )
        else:
            raise ResolutionError(f"Unsupported path kind {kind}")
        if len(points) < 2 or any(
            math.dist(a, b) <= 0.01 for a, b in zip(points, points[1:])
        ):
            raise ResolutionError("Path contains a zero-length segment")
        return points

    def profile2(
        self, profile: JsonValue
    ) -> tuple[tuple[Vec2, ...], tuple[tuple[Vec2, ...], ...]]:
        """Resolve a plan profile containing point locators.

        :param profile: Canonical profile object.
        :returns: Outer loop and hole loops.
        :raises ResolutionError: If the profile is malformed.
        """
        if not isinstance(profile, dict):
            raise ResolutionError("Profile must be an object")
        outer_value = profile.get("outer")
        if not isinstance(outer_value, list):
            raise ResolutionError("Profile requires an outer loop")
        outer = tuple(self.point2(locator) for locator in outer_value)
        holes_value = profile.get("holes", [])
        if not isinstance(holes_value, list):
            raise ResolutionError("Profile holes must be an array")
        holes = tuple(
            tuple(self.point2(locator) for locator in loop)
            for loop in holes_value
            if isinstance(loop, list)
        )
        return outer, holes

    def _registry(self, name: str) -> dict[str, JsonObject]:
        value = self.model.get(name, {})
        if not isinstance(value, dict):
            return {}
        return {key: item for key, item in value.items() if isinstance(item, dict)}


def path_length(points: Sequence[Vec2]) -> float:
    """Return total polyline length.

    :param points: Ordered path points.
    :returns: Length in source coordinate units.
    """
    return sum(math.dist(start, end) for start, end in zip(points, points[1:]))


def point_at_station(points: Sequence[Vec2], station: float) -> tuple[Vec2, Vec2]:
    """Resolve a point and tangent along a polyline.

    :param points: Ordered path points.
    :param station: Distance from path start.
    :returns: Point and forward unit tangent.
    :raises ResolutionError: If station is outside the path.
    """
    total = path_length(points)
    if station < -0.01 or station > total + 0.01:
        raise ResolutionError(f"Station {station:g} is outside path length {total:g}")
    remaining = min(max(station, 0.0), total)
    for start, end in zip(points, points[1:]):
        segment_length = math.dist(start, end)
        if remaining <= segment_length + 0.01:
            ratio = min(remaining / segment_length, 1.0)
            tangent = (
                (end[0] - start[0]) / segment_length,
                (end[1] - start[1]) / segment_length,
            )
            return (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            ), tangent
        remaining -= segment_length
    start, end = points[-2], points[-1]
    segment_length = math.dist(start, end)
    return end, (
        (end[0] - start[0]) / segment_length,
        (end[1] - start[1]) / segment_length,
    )
