"""Host-relative coordinate frames shared by construction and service components."""

from __future__ import annotations

import logging
import math
from typing import Protocol

from shapely.geometry import Point, Polygon

from home_design.constants import GEOMETRY_TOLERANCE_MM
from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.member_assemblies import MemberAssemblies
from home_design.geometry import number, vector2, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.locators import point_at_station
from home_design.resolved import ResolvedElement, Vec3
from home_design.frames import LocalFrame as LocalFrame, tuple3 as tuple3
from home_design.round_paths import RoundPath

LOGGER = logging.getLogger(__name__)


class PlacementContext(Protocol):
    """Dependency resolution available to host placements."""

    elements: dict[str, JsonObject]

    def resolve_component(self, element_id: str) -> ResolvedElement:
        """Return the resolved host or reject a dependency cycle."""
        ...


class HostPlacement:
    """Resolve explicit surface coordinates without inferring physical connections."""

    def __init__(self, context: PlacementContext) -> None:
        """Use the canonical resolver to retain host dependency ordering."""
        self.context: PlacementContext = context

    def resolve(self, placement: JsonObject) -> LocalFrame:
        """Resolve a host frame and apply local mounting offsets and orientation.

        :param placement: Schema-validated HostPlacement object.
        :returns: Orthonormal frame at the mounted location.
        :raises ResolutionError: For incompatible hosts or points outside a surface.
        """
        host_id = Authoring.text(placement.get("element"), "placement host")
        host = self.context.resolve_component(host_id)
        kind = placement.get("kind")
        if kind == "member" and host.kind in MemberAssemblies.KINDS:
            host = MemberAssemblies.member(
                host, Authoring.text(placement.get("part"), "assembly member key")
            )
        elif "part" in placement:
            raise ResolutionError(
                "A member part key requires a generated member assembly"
            )
        LOGGER.debug("Resolving %s placement on %s", kind, host_id)
        if kind == "wall" and host.kind == "wall":
            frame = self._wall(host, placement)
        elif kind == "surface" and host.kind in {"slab", "roof", "footing"}:
            frame = self._surface(host, placement)
        elif kind == "member" and host.kind == "member":
            frame = self._member(host, placement)
        elif kind == "member" and host.kind == "curvedMember":
            frame = self._curved(host, placement)
        elif kind == "route" and host.kind in {"serviceRoute", "serviceFitting"}:
            frame = self._route(host, placement)
        elif kind == "component":
            value = Authoring.object(
                host.data.get("placement"), "component placement frame"
            )
            frame = LocalFrame(
                *(vector3(value[key], key) for key in ("origin", "x", "y", "z"))
            )
        else:
            raise ResolutionError(f"Placement kind {kind} cannot host on {host.kind}")
        return frame.adjusted(
            vector3(placement.get("offset", [0, 0, 0]), "host offset"),
            vector3(placement.get("rotation", [0, 0, 0]), "host rotation"),
        )

    @staticmethod
    def _route(host: ResolvedElement, placement: JsonObject) -> LocalFrame:
        """Locate a route/fitting axis using its retained analytic control path and section roll."""
        data = host.data
        if "paths" in data:
            branches = Authoring.object(data["paths"])
            key = Authoring.text(placement.get("branch"), "fitting branch key")
            if key not in branches:
                raise ResolutionError(f"Unknown fitting branch {key}")
            data = Authoring.object(branches[key])
        elif "branch" in placement:
            raise ResolutionError("A branch station requires a branched fitting")
        points = [
            vector3(value, "route path control")
            for value in Authoring.array(data["pathControls"])
        ]
        frame = RoundPath(
            points, 0, number(data["bendRadius"], "route bend radius"), 1
        ).station_frame(
            number(placement["station"], "route station"),
            vector3(data["sectionUp"], "route section up"),
        )
        if host.kind == "serviceFitting":
            source = Authoring.object(host.data["placement"])
            world = LocalFrame(
                *(vector3(source[key], key) for key in ("origin", "x", "y", "z"))
            )
            frame = LocalFrame(
                world.point(frame.origin),
                *(world.vector(axis) for axis in (frame.x, frame.y, frame.z)),
            )
        return frame

    @staticmethod
    def _layer_depth(
        host: ResolvedElement, placement: JsonObject
    ) -> tuple[float, float]:
        """Return selected layer start/end depth from the exterior or top."""
        layers = Authoring.array(host.data.get("layers", []))
        index = placement.get("layer")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < len(layers)
        ):
            raise ResolutionError(f"Host {host.element_id} has no layer {index}")
        depths = [
            number(Authoring.object(layer).get("thickness"), "layer thickness")
            for layer in layers
        ]
        start = sum(depths[:index])
        return start, start + depths[index]

    def _depth(self, host: ResolvedElement, placement: JsonObject) -> float:
        """Resolve a surface's normal distance inward from the exterior/top."""
        surface = str(placement.get("surface"))
        if surface in {"exterior", "top"}:
            return 0.0
        if surface in {"interior", "bottom"}:
            return number(host.data.get("thickness"), "host thickness")
        start, end = self._layer_depth(host, placement)
        if surface in {"layerExterior", "layerTop"}:
            return start
        if surface in {"layerInterior", "layerBottom"}:
            return end
        return (start + end) / 2

    def _wall(self, host: ResolvedElement, placement: JsonObject) -> LocalFrame:
        """Place on a wall path station and height above its resolved base."""
        axis = [
            vector2(value, "wall axis")
            for value in Authoring.array(host.data.get("axis"))
        ]
        station = number(placement.get("station"), "host station")
        point, tangent = point_at_station(axis, station)
        height = number(placement.get("height"), "host height")
        thickness = number(host.data.get("thickness"), "wall thickness")
        center = {"exterior": -thickness / 2, "interior": thickness / 2}.get(
            str(host.data.get("locationLine")),
            0.0,
        )
        normal: Vec3 = (-tangent[1], tangent[0], 0.0)
        depth = self._depth(host, placement)
        origin: Vec3 = (
            point[0] + normal[0] * (center + thickness / 2 - depth),
            point[1] + normal[1] * (center + thickness / 2 - depth),
            number(host.data.get("baseElevation"), "wall base") + height,
        )
        check = origin
        if placement.get("surface") == "layerCenter":
            start, _ = self._layer_depth(host, placement)
            check = tuple3([origin[i] + normal[i] * (depth - start) for i in range(3)])
        self._require_surface(host, check, normal)
        if placement.get("surface") in {"interior", "layerInterior"}:
            normal = tuple3([-coordinate for coordinate in normal])
        up: Vec3 = (0.0, 0.0, 1.0)
        return LocalFrame(origin, ConstructionGeometry.cross(up, normal), up, normal)

    def _surface(self, host: ResolvedElement, placement: JsonObject) -> LocalFrame:
        """Sample a slab, footing or selected roof plane at a model X/Y point."""
        x, y = vector2(placement.get("point"), "host plan point")
        if host.kind == "roof":
            return self._roof(host, placement, x, y)
        if "face" in placement:
            raise ResolutionError("Only a roof surface placement accepts a face ID")
        if host.kind == "footing" and "layer" not in placement:
            elevation = number(
                host.data.get(
                    "bottomElevation"
                    if placement.get("surface") == "bottom"
                    else "topElevation"
                ),
                "footing surface",
            )
        else:
            elevation = number(host.data.get("topElevation"), "slab top") - self._depth(
                host, placement
            )
        origin: Vec3 = (x, y, elevation)
        check = origin
        if placement.get("surface") == "layerCenter":
            start, _ = self._layer_depth(host, placement)
            check = (x, y, number(host.data.get("topElevation"), "slab top") - start)
        normal: Vec3 = (0.0, 0.0, 1.0)
        self._require_surface(host, check, normal)
        if placement.get("surface") in {"bottom", "layerBottom"}:
            normal = (0.0, 0.0, -1.0)
        return self._plane_frame(origin, normal)

    def _roof(
        self, host: ResolvedElement, placement: JsonObject, x: float, y: float
    ) -> LocalFrame:
        """Resolve against retained roof planes, rejecting ambiguous crease locations."""
        depth = self._depth(host, placement)
        candidates: list[LocalFrame] = []
        for value in Authoring.array(host.data.get("planes")):
            plane = Authoring.object(value)
            if "face" in placement and placement["face"] != plane.get("id"):
                continue
            boundary = [
                vector3(point, "roof plane")
                for point in Authoring.array(plane.get("boundary"))
            ]
            a = boundary[0]
            normal = self._polygon_normal(boundary)
            if normal[2] < 0:
                normal = tuple3([-coordinate for coordinate in normal])
            if normal[2] < 1e-9:
                raise ResolutionError(
                    "Roof surface placement requires a nonvertical plane"
                )
            shifted = [
                tuple3([point[i] - normal[i] * depth for i in range(3)])
                for point in boundary
            ]
            if (
                not Polygon([(point[0], point[1]) for point in shifted])
                .buffer(GEOMETRY_TOLERANCE_MM)
                .covers(Point(x, y))
            ):
                continue
            z = (
                a[2]
                - (normal[0] * (x - a[0]) + normal[1] * (y - a[1]) + depth) / normal[2]
            )
            origin: Vec3 = (x, y, z)
            check = origin
            if placement.get("surface") == "layerCenter":
                start, _ = self._layer_depth(host, placement)
                check = tuple3(
                    [origin[i] + normal[i] * (depth - start) for i in range(3)]
                )
            if not self._on_surface(host, check, normal):
                continue
            if placement.get("surface") in {"bottom", "layerBottom"}:
                normal = tuple3([-coordinate for coordinate in normal])
            candidates.append(self._plane_frame(origin, normal))
        if len(candidates) != 1:
            raise ResolutionError(
                f"Roof host placement resolves to {len(candidates)} faces; select a face and a point on it"
            )
        return candidates[0]

    @staticmethod
    def _curved(host: ResolvedElement, placement: JsonObject) -> LocalFrame:
        """Mount on an analytic arc axis with its rolled radial section frame."""
        if placement.get("surface", "axis") != "axis":
            raise ResolutionError("Curved member hosts support the analytic axis only")
        station = number(placement.get("station"), "member station")
        if not 0 <= station <= number(host.data["memberLength"], "arc length"):
            raise ResolutionError("Host station is outside the curved member axis")
        data = Authoring.object(host.data["placement"])
        frame = LocalFrame(
            *(vector3(data[key], key) for key in ("origin", "x", "y", "z"))
        )
        radius = number(host.data["radius"], "arc radius")
        sign = 1 if number(host.data["sweepAngle"], "arc sweep") > 0 else -1
        theta = (
            math.radians(number(host.data["startAngle"], "arc start"))
            + sign * station / radius
        )
        cosine, sine = math.cos(theta), math.sin(theta)
        return LocalFrame(
            frame.point((radius * cosine, radius * sine, 0)),
            frame.vector((-sign * cosine, -sign * sine, 0)),
            frame.z,
            frame.vector((-sign * sine, sign * cosine, 0)),
        ).adjusted((0, 0, 0), (0, 0, number(host.data["roll"], "arc roll")))

    def _member(self, host: ResolvedElement, placement: JsonObject) -> LocalFrame:
        """Place in the rolled section frame of an individual straight member."""
        start, end = [
            vector3(point, "member endpoint")
            for point in Authoring.array(host.data.get("axis"))
        ]
        length = math.dist(start, end)
        station = number(placement.get("station"), "member station")
        if not 0 <= station <= length:
            raise ResolutionError("Host station is outside the member axis")
        direction = ConstructionGeometry.unit(
            tuple3([end[i] - start[i] for i in range(3)])
        )
        reference: Vec3 = (
            (0.0, 1.0, 0.0) if abs(direction[2]) > 0.999 else (0.0, 0.0, 1.0)
        )
        across = ConstructionGeometry.unit(
            ConstructionGeometry.cross(reference, direction)
        )
        up = ConstructionGeometry.cross(direction, across)
        if "sectionFrame" in host.data:
            section_frame = Authoring.object(host.data["sectionFrame"])
            across = vector3(section_frame["x"], "member section X")
            up = vector3(section_frame["y"], "member section Y")
        frame = LocalFrame(start, across, up, direction).adjusted(
            (0.0, 0.0, station),
            (
                0.0,
                0.0,
                number(
                    self.context.elements.get(host.element_id, {}).get("roll", 0),
                    "member roll",
                ),
            ),
        )
        surface = placement.get("surface", "axis")
        if surface == "axis":
            return frame
        if surface in {"start", "end"}:
            required_station = 0.0 if surface == "start" else length
            if abs(station - required_station) > GEOMETRY_TOLERANCE_MM:
                raise ResolutionError(
                    f"Member {surface} requires station {required_station:g}"
                )
            self._require_surface(host, frame.origin, direction)
            return (
                frame
                if surface == "end"
                else LocalFrame(
                    frame.origin,
                    frame.x,
                    tuple3([-v for v in frame.y]),
                    tuple3([-v for v in frame.z]),
                )
            )
        section = ConstructionGeometry.section(
            Authoring.object(host.data.get("section"))
        )
        min_x, min_y, max_x, max_y = section.bounds
        local: dict[str, Vec3] = {
            "positiveX": (max_x, 0.0, 0.0),
            "negativeX": (min_x, 0.0, 0.0),
            "positiveY": (0.0, max_y, 0.0),
            "negativeY": (0.0, min_y, 0.0),
        }
        point = frame.point(local[str(surface)])
        normal_local: Vec3 = {
            "positiveX": (1.0, 0.0, 0.0),
            "negativeX": (-1.0, 0.0, 0.0),
            "positiveY": (0.0, 1.0, 0.0),
            "negativeY": (0.0, -1.0, 0.0),
        }[str(surface)]
        normal = frame.vector(normal_local)
        self._require_surface(host, point, None)
        return LocalFrame(
            point, ConstructionGeometry.cross(direction, normal), direction, normal
        )

    @staticmethod
    def _plane_frame(origin: Vec3, normal: Vec3) -> LocalFrame:
        """Project model east into the surface to obtain a stable tangent frame."""
        reference: Vec3 = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.99 else (0.0, 1.0, 0.0)
        dot = sum(a * b for a, b in zip(reference, normal))
        x = ConstructionGeometry.unit(
            tuple3([reference[i] - normal[i] * dot for i in range(3)])
        )
        return LocalFrame(origin, x, ConstructionGeometry.cross(normal, x), normal)

    @staticmethod
    def _polygon_normal(points: list[Vec3]) -> Vec3:
        """Use Newell's method so leading collinear edges remain valid."""
        normal = [0.0, 0.0, 0.0]
        for a, b in zip(points, points[1:] + points[:1]):
            normal[0] += (a[1] - b[1]) * (a[2] + b[2])
            normal[1] += (a[2] - b[2]) * (a[0] + b[0])
            normal[2] += (a[0] - b[0]) * (a[1] + b[1])
        return ConstructionGeometry.unit(tuple3(normal))

    @classmethod
    def _on_surface(
        cls, host: ResolvedElement, point: Vec3, normal: Vec3 | None
    ) -> bool:
        """Test actual coplanar faces, retaining holes and profiled boundaries."""
        for mesh in host.meshes:
            for face in mesh.faces:
                vertices = [mesh.vertices[index] for index in face]
                face_normal = normal or cls._polygon_normal(vertices)
                frame = cls._plane_frame(point, face_normal)
                relative = [
                    tuple3([vertex[i] - point[i] for i in range(3)])
                    for vertex in vertices
                ]
                if any(
                    abs(sum(a * b for a, b in zip(vertex, face_normal)))
                    > GEOMETRY_TOLERANCE_MM
                    for vertex in relative
                ):
                    continue
                projected = Polygon(
                    [
                        (
                            sum(a * b for a, b in zip(vertex, frame.x)),
                            sum(a * b for a, b in zip(vertex, frame.y)),
                        )
                        for vertex in relative
                    ]
                )
                if projected.area > 1e-9 and projected.buffer(
                    GEOMETRY_TOLERANCE_MM
                ).covers(Point(0, 0)):
                    return True
        return False

    @classmethod
    def _require_surface(
        cls, host: ResolvedElement, point: Vec3, normal: Vec3 | None
    ) -> None:
        """Reject unsupported positions, including holes in a host's actual face."""
        if not cls._on_surface(host, point, normal):
            raise ResolutionError(
                f"Host placement point is outside a physical surface of {host.element_id}"
            )

    @classmethod
    def references(cls, value: JsonValue) -> list[JsonValue]:
        """Retain authored host coordinates in resolved inspection/export metadata."""
        if isinstance(value, list):
            return [reference for child in value for reference in cls.references(child)]
        if not isinstance(value, dict):
            return []
        if isinstance(value.get("host"), dict):
            return [value["host"]]
        return [
            reference for child in value.values() for reference in cls.references(child)
        ]
