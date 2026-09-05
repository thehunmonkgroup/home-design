"""Checks for support paths, drainage routes, explicit requirements and grade."""

from __future__ import annotations

import math
from collections import defaultdict

from shapely.geometry import LineString, MultiPoint, Point, Polygon

from home_design.construction import Authoring
from home_design.diagnostics import Diagnostic
from home_design.geometry import number, polygon_from_loops, vector2, vector3
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import ResolvedElement, ResolvedModel, Vec2
from home_design.terrain import TerrainSurface
from home_design.requirements import RequirementEvaluator


class GradeReport:
    """Measure wall exposure at all piecewise-planar terrain crossings."""

    @staticmethod
    def evaluate(element: ResolvedElement, terrain: JsonObject) -> JsonObject:
        """Sample grade at wall stations or foundation footprint vertices."""
        surface = TerrainSurface.from_element(terrain)
        wall_top = []
        if element.kind == "wall":
            wall_top = [
                vector3(point, "wall top")
                for point in Authoring.array(element.data.get("topProfile"))
            ]
            path = [(point[0], point[1]) for point in wall_top]
        else:
            footprint = Authoring.object(
                element.data.get("footprint"), "grade-related footprint"
            )
            path = [
                vector2(point, "foundation perimeter")
                for point in Authoring.array(footprint.get("outer"))
            ]
            path.append(path[0])
        samples: list[JsonValue] = []
        station = 0.0
        bottom = number(
            element.data.get("baseElevation", element.data.get("bottomElevation")),
            "base elevation",
        )
        top_range = element.data.get("topElevationRange")
        top = (
            min(number(value, "wall top") for value in top_range)
            if isinstance(top_range, list)
            else number(element.data.get("topElevation"), "top elevation")
        )
        retained: list[float] = []
        for index, (start, end) in enumerate(zip(path, path[1:])):
            segment = LineString((start, end))
            points: set[Vec2] = {start, end}
            for face in surface.faces:
                triangle = [surface.vertices[index] for index in face]
                for a, b in zip(triangle, (*triangle[1:], triangle[0])):
                    intersection = segment.intersection(LineString((a[:2], b[:2])))
                    candidates = (
                        list(intersection.geoms)
                        if isinstance(intersection, MultiPoint)
                        else [intersection]
                    )
                    for candidate in candidates:
                        if isinstance(candidate, Point):
                            points.add((float(candidate.x), float(candidate.y)))
            for point in sorted(points, key=lambda value: math.dist(start, value)):
                if wall_top:
                    fraction = math.dist(start, point) / math.dist(start, end)
                    top = (
                        wall_top[index][2]
                        + (wall_top[index + 1][2] - wall_top[index][2]) * fraction
                    )
                grade = surface.height(point)
                retained_height = max(0.0, min(top, grade) - bottom)
                retained.append(retained_height)
                samples.append(
                    {
                        "station": station + math.dist(start, point),
                        "point": list(point),
                        "gradeElevation": grade,
                        "retainedHeight": retained_height,
                        "exposedHeight": max(0.0, top - max(bottom, grade)),
                        "coverAboveTop": grade - top,
                    }
                )
            station += math.dist(start, end)
        return {
            "samples": samples,
            "maximumRetainedHeight": max(retained),
            "minimumRetainedHeight": min(retained),
        }


class CoordinationValidator:
    """Validate authored engineering intent without inferring structural capacity."""

    def __init__(self, model: JsonObject, resolved: ResolvedModel) -> None:
        """Index canonical relationships and resolved coordination geometry."""
        self.model: JsonObject = model
        self.resolved: ResolvedModel = resolved
        self.index: ModelIndex = ModelIndex(model)
        self.elements: dict[str, ResolvedElement] = {
            element.element_id: element for element in resolved.elements
        }

    def diagnostics(self) -> list[Diagnostic]:
        """Return explicit requirement and physical coordination failures."""
        return (
            self._supports() + self._loads() + self._drainage() + self._requirements()
        )

    def _supports(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for relationship_id, relationship in self.index.relationships("supports"):
            bearing = relationship.get("bearingPoint")
            if bearing is None:
                continue
            point = vector3(bearing, "bearing point")
            for participant in ("support", "supported"):
                element = self.elements[Authoring.text(relationship.get(participant))]
                vertices = [
                    vertex for mesh in element.meshes for vertex in mesh.vertices
                ]
                if not vertices or any(
                    point[axis] < min(vertex[axis] for vertex in vertices) - 0.01
                    or point[axis] > max(vertex[axis] for vertex in vertices) + 0.01
                    for axis in range(3)
                ):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "support.bearing-outside-element",
                            f"Bearing point is outside {element.element_id}",
                            subject_id=relationship_id,
                        )
                    )
        return diagnostics

    def _loads(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        supports: dict[str, list[str]] = defaultdict(list)
        for _, relationship in self.index.relationships("supports"):
            supports[Authoring.text(relationship.get("supported"))].append(
                Authoring.text(relationship.get("support"))
            )
        for element in self.resolved.elements:
            if element.kind != "load":
                continue
            target = self.elements[Authoring.text(element.data.get("target"))]
            footprint = target.data.get("footprint")
            if isinstance(footprint, dict):
                target_polygon = self._polygon(footprint)
                load_polygon = self._polygon(
                    Authoring.object(element.data.get("footprint"))
                )
                if not target_polygon.buffer(0.01).covers(load_polygon):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "load.outside-target",
                            "Load footprint extends beyond its supported surface",
                            subject_id=element.element_id,
                        )
                    )
            if element.data.get("foundationRequired", True):
                failures = self._unsupported_leaves(target.element_id, supports, ())
                if failures:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "load.incomplete-support-path",
                            f"Load path does not reach foundations through: {', '.join(sorted(failures))}",
                            subject_id=element.element_id,
                        )
                    )
        return diagnostics

    def _unsupported_leaves(
        self, element_id: str, supports: dict[str, list[str]], active: tuple[str, ...]
    ) -> set[str]:
        if element_id in active:
            return {f"cycle at {element_id}"}
        element = self.elements[element_id]
        if element.kind == "footing" or (
            element.kind == "slab" and element.data.get("role") == "foundation"
        ):
            return set()
        if not supports[element_id]:
            return {element_id}
        return set().union(
            *(
                self._unsupported_leaves(support, supports, (*active, element_id))
                for support in supports[element_id]
            )
        )

    def _drainage(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for relationship_id, relationship in self.index.relationships("drainsTo"):
            source = self.elements[Authoring.text(relationship.get("source"))]
            target = self.elements[Authoring.text(relationship.get("target"))]
            source_path = Authoring.array(source.data.get("path"))
            target_path = Authoring.array(target.data.get("path"))
            if (
                math.dist(
                    vector3(source_path[-1], "drain end"),
                    vector3(target_path[0], "drain start"),
                )
                > 0.01
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "drainage.disconnected",
                        "Drain outlet and receiving inlet do not meet",
                        subject_id=relationship_id,
                    )
                )
        for element in self.resolved.elements:
            outlet = element.data.get("outlet")
            if element.kind != "sweep" or not isinstance(outlet, dict):
                continue
            if not outlet.get("stable"):
                diagnostics.append(
                    Diagnostic(
                        "warning",
                        "drainage.unverified-outlet",
                        "Discharge location has not been confirmed stable",
                        subject_id=element.element_id,
                    )
                )
            radius = number(outlet.get("exclusionRadius", 0), "outlet exclusion radius")
            point = vector3(
                Authoring.array(element.data.get("path"))[-1], "outlet point"
            )
            for footing in self.resolved.elements:
                if footing.kind != "footing":
                    continue
                polygon = self._polygon(Authoring.object(footing.data.get("footprint")))
                if polygon.distance(Point(point[:2])) < radius:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "drainage.outlet-near-footing",
                            f"Outlet is within {radius:g} mm of {footing.element_id}",
                            subject_id=element.element_id,
                        )
                    )
        return diagnostics

    def _requirements(self) -> list[Diagnostic]:
        return RequirementEvaluator(self.resolved).diagnostics()

    @staticmethod
    def _polygon(footprint: JsonObject) -> Polygon:
        outer = [
            vector2(point, "footprint point")
            for point in Authoring.array(footprint.get("outer"))
        ]
        holes = [
            [vector2(point, "footprint hole point") for point in Authoring.array(loop)]
            for loop in Authoring.array(footprint.get("holes", []))
        ]
        return polygon_from_loops(outer, holes)
