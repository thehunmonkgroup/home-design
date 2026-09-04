"""Topology and geometric-fit checks for integrated home components."""

from __future__ import annotations

import math
from collections import defaultdict

from shapely.geometry import Polygon

from home_design.constants import GEOMETRY_TOLERANCE_MM
from home_design.diagnostics import Diagnostic
from home_design.geometry import number, polygon_from_loops, vector2, vector3
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject
from home_design.locators import LocatorResolver, path_length, point_at_station
from home_design.resolved import Vec3


class TopologyValidator:
    """Validate profiles, hosted openings, and declared physical joins."""

    def __init__(self, model: JsonObject, index: ModelIndex) -> None:
        """Initialize topology validation.

        :param model: Schema-valid canonical model.
        :param index: Reference index for the same model.
        """
        self.model: JsonObject = model
        self.index: ModelIndex = index
        self.locators: LocatorResolver = LocatorResolver(model)
        self.elements: dict[str, JsonObject] = index.registries["elements"]

    def diagnostics(self) -> list[Diagnostic]:
        """Return topology and fit diagnostics.

        :returns: Topology diagnostic list.
        """
        diagnostics: list[Diagnostic] = []
        diagnostics.extend(self._profile_rules())
        diagnostics.extend(self._opening_rules())
        diagnostics.extend(self._join_rules())
        return diagnostics

    def _profile_rules(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for element_id, element in self.elements.items():
            profiles = self._element_profiles(element)
            for label, profile in profiles:
                try:
                    outer, holes = self.locators.profile2(profile)
                    polygon_from_loops(outer, holes)
                except Exception as error:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "topology.invalid-profile",
                            f"{label} is invalid: {error}",
                            f"/elements/{element_id}",
                            element_id,
                        )
                    )
            if element.get("kind") == "roof":
                geometry = element.get("geometry")
                if isinstance(geometry, dict) and geometry.get("kind") == "faceSet":
                    diagnostics.extend(self._roof_face_rules(element_id, geometry))
        return diagnostics

    def _opening_rules(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        intervals_by_host: dict[str, list[tuple[float, float, float, float, str]]] = (
            defaultdict(list)
        )
        for opening_id, opening in self.elements.items():
            if opening.get("kind") != "opening":
                continue
            host_id = self.index.host_for_opening(opening_id)
            host = self.elements.get(host_id) if host_id is not None else None
            if host_id is None or host is None or host.get("kind") != "wall":
                continue
            path = self.locators.path2(host.get("path"))
            total_length = path_length(path)
            geometry = opening.get("geometry")
            placement = opening.get("placement")
            if not isinstance(geometry, dict) or not isinstance(placement, dict):
                continue
            width, height = self._opening_dimensions(geometry)
            station = number(placement.get("station"), "opening station")
            start = station - {"start": 0.0, "center": width / 2, "end": width}.get(
                str(placement.get("stationReference")), 0.0
            )
            bottom = number(placement.get("verticalOffset"), "opening vertical offset")
            bottom -= {"bottom": 0.0, "center": height / 2, "top": height}.get(
                str(placement.get("verticalReference")), 0.0
            )
            if (
                start < -GEOMETRY_TOLERANCE_MM
                or start + width > total_length + GEOMETRY_TOLERANCE_MM
            ):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "opening.outside-host-path",
                        f"Opening interval [{start:g}, {start + width:g}] is outside wall length {total_length:g}",
                        f"/elements/{opening_id}/placement/station",
                        opening_id,
                    )
                )
            if bottom < -GEOMETRY_TOLERANCE_MM:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "opening.below-host-base",
                        f"Opening bottom {bottom:g} is below its host base",
                        f"/elements/{opening_id}/placement/verticalOffset",
                        opening_id,
                    )
                )
            host_top = host.get("top")
            if isinstance(host_top, dict) and host_top.get("kind") == "height":
                host_height = number(host_top.get("height"), "wall height")
                if bottom + height > host_height + GEOMETRY_TOLERANCE_MM:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "opening.above-host-top",
                            f"Opening top {bottom + height:g} exceeds wall height {host_height:g}",
                            f"/elements/{opening_id}/placement/verticalOffset",
                            opening_id,
                        )
                    )
            intervals_by_host[host_id].append(
                (start, start + width, bottom, bottom + height, opening_id)
            )
        for host_id, intervals in intervals_by_host.items():
            for index, current in enumerate(intervals):
                for other in intervals[index + 1 :]:
                    horizontal_overlap = min(current[1], other[1]) - max(
                        current[0], other[0]
                    )
                    vertical_overlap = min(current[3], other[3]) - max(
                        current[2], other[2]
                    )
                    if (
                        horizontal_overlap > GEOMETRY_TOLERANCE_MM
                        and vertical_overlap > GEOMETRY_TOLERANCE_MM
                    ):
                        diagnostics.append(
                            Diagnostic(
                                "error",
                                "opening.overlap",
                                f"Openings {current[4]} and {other[4]} overlap on {host_id}",
                                subject_id=host_id,
                            )
                        )
        return diagnostics

    def _join_rules(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for relationship_id, relationship in self.index.relationships("joins"):
            endpoints: list[tuple[float, float]] = []
            for field in ("a", "b"):
                endpoint = relationship.get(field)
                if not isinstance(endpoint, dict):
                    continue
                element_id = endpoint.get("element")
                element = (
                    self.elements.get(element_id)
                    if isinstance(element_id, str)
                    else None
                )
                if element is None:
                    continue
                points = self.locators.path2(element.get("path"))
                at = endpoint.get("at")
                if at == "start":
                    endpoints.append(points[0])
                elif at == "end":
                    endpoints.append(points[-1])
                else:
                    station = number(endpoint.get("station"), "join station")
                    endpoints.append(point_at_station(points, station)[0])
            if len(endpoints) == 2 and math.dist(*endpoints) > GEOMETRY_TOLERANCE_MM:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "join.disconnected",
                        f"Declared join endpoints differ by {math.dist(*endpoints):g} mm",
                        f"/relationships/{relationship_id}",
                        relationship_id,
                    )
                )
        return diagnostics

    def _roof_face_rules(
        self, element_id: str, geometry: JsonObject
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        faces = geometry.get("faces", [])
        if not isinstance(faces, list):
            return diagnostics
        for index, face in enumerate(faces):
            if not isinstance(face, dict):
                continue
            boundary = face.get("boundary")
            outer = boundary.get("outer") if isinstance(boundary, dict) else None
            if not isinstance(outer, list):
                continue
            points: list[Vec3] = [
                vector3(point, "roof face point")
                for point in outer
                if isinstance(point, list)
            ]
            if len(points) < 3 or not self._coplanar(points):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "roof.non-planar-face",
                        "Explicit roof face boundary must be planar and non-degenerate",
                        f"/elements/{element_id}/geometry/faces/{index}/boundary",
                        element_id,
                    )
                )
        return diagnostics

    @staticmethod
    def _coplanar(points: list[Vec3]) -> bool:
        a, b, c = points[:3]
        normal = (
            (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
            (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
            (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]),
        )
        magnitude = math.sqrt(sum(value * value for value in normal))
        if magnitude <= GEOMETRY_TOLERANCE_MM:
            return False
        return all(
            abs(sum(normal[axis] * (point[axis] - a[axis]) for axis in range(3)))
            / magnitude
            <= GEOMETRY_TOLERANCE_MM
            for point in points[3:]
        )

    @staticmethod
    def _opening_dimensions(geometry: JsonObject) -> tuple[float, float]:
        if geometry.get("kind") == "rectangle":
            return number(geometry.get("width"), "opening width"), number(
                geometry.get("height"), "opening height"
            )
        profile = geometry.get("profile")
        outer = profile.get("outer") if isinstance(profile, dict) else None
        if not isinstance(outer, list):
            return 0.0, 0.0
        polygon = Polygon(
            [
                vector2(point, "opening profile point")
                for point in outer
                if isinstance(point, list)
            ]
        )
        min_x, min_y, max_x, max_y = polygon.bounds
        return max_x - min_x, max_y - min_y

    @staticmethod
    def _element_profiles(element: JsonObject) -> list[tuple[str, JsonObject]]:
        profiles: list[tuple[str, JsonObject]] = []
        kind = element.get("kind")
        footprint = element.get("footprint")
        if kind == "slab" and isinstance(footprint, dict):
            profiles.append(("slab footprint", footprint))
        if kind == "space":
            geometry = element.get("geometry")
            if isinstance(geometry, dict) and geometry.get("kind") == "explicit":
                footprint = geometry.get("footprint")
                if isinstance(footprint, dict):
                    profiles.append(("space footprint", footprint))
        if kind == "roof":
            geometry = element.get("geometry")
            if isinstance(geometry, dict) and geometry.get("kind") == "parametric":
                footprint = geometry.get("footprint")
                if isinstance(footprint, dict):
                    profiles.append(("roof footprint", footprint))
        return profiles
