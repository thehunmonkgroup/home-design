"""Reusable service-fitting solids with explicit interfaces and connected internal passages."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, cast

import manifold3d
import numpy as np
from shapely.geometry import Polygon

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import extrude_polygon, number, vector2, vector3
from home_design.json_types import JsonObject
from home_design.placement import LocalFrame, tuple3
from home_design.resolved import Face, MeshData, Vec2, Vec3
from home_design.service_routes import RouteGeometry
from home_design.solids import SolidOperations


@dataclass(frozen=True)
class FittingShape:
    """Type-local material, construction masks, generated port frames and inspection data."""

    volumes: dict[str, MeshData]
    ports: dict[str, tuple[LocalFrame, JsonObject]]
    data: JsonObject
    body: MeshData | None = None


class FittingGeometry:
    """Build elbows, branched passages, parallel-face transitions and physical end caps."""

    IDENTITY: LocalFrame = LocalFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    AREA_TOLERANCE_MM2: float = 1e-5

    def __init__(self, definition: JsonObject, clearance: float) -> None:
        """Retain reusable stock, approximation and instance clearance intent."""
        self.definition: JsonObject = definition
        self.geometry: JsonObject = Authoring.object(definition["geometry"])
        self.clearance: float = clearance
        self.thickness: float = number(
            definition.get("wallThickness", 0), "fitting wall thickness"
        )

    def section(
        self, section: JsonObject, path: JsonObject | None = None
    ) -> RouteGeometry:
        """Share the route section/tolerance contract across every fitting part."""
        return RouteGeometry(
            {**self.definition, "section": section},
            {
                **(path or {}),
                "chordTolerance": self.definition["chordTolerance"],
                "clearance": self.clearance,
            },
        )

    def path(self, value: JsonObject) -> FittingShape:
        """Resolve one type-local tangent path and its two outward port frames."""
        section = Authoring.object(value["section"])
        body, volumes, frames, data = self.section(section, value).resolve(
            [
                vector3(point, "fitting path")
                for point in Authoring.array(value["path"])
            ],
            Authoring.text(self.definition["material"]),
            vector3(value["up"], "fitting up") if "up" in value else None,
        )
        start = frames[0]
        outward = LocalFrame(
            start.origin,
            tuple3([-v for v in start.x]),
            start.y,
            tuple3([-v for v in start.z]),
        )
        return FittingShape(
            volumes,
            {"start": (outward, section), "end": (frames[-1], section)},
            data,
            body,
        )

    @staticmethod
    def cross_section(mesh: MeshData, frame: LocalFrame) -> manifold3d.CrossSection:
        """Slice a construction volume in an arbitrary interface's local XY plane."""
        transform = np.asarray(
            [
                [*axis, -sum(a * b for a, b in zip(axis, frame.origin))]
                for axis in (frame.x, frame.y, frame.z)
            ],
            dtype=np.double,
        )
        matrix = cast(
            np.ndarray[tuple[Literal[3], Literal[4]], np.dtype[np.double]], transform
        )
        return SolidOperations.solid(mesh).transform(matrix).slice(0)

    @staticmethod
    def contour(profile: Polygon) -> manifold3d.CrossSection:
        """Convert a convex service profile into the solid kernel's planar domain."""
        coordinates = cast(
            np.ndarray[tuple[int, Literal[2]], np.dtype[np.double]],
            np.asarray(list(profile.exterior.coords)[:-1], dtype=np.double),
        )
        return manifold3d.CrossSection([coordinates], manifold3d.FillRule.EvenOdd)

    def _branch_root(
        self, trunk: FittingShape, arm: FittingShape, value: JsonObject, key: str
    ) -> None:
        """Require the entire branch root section to open into the declared trunk."""
        frame, section = arm.ports["start"]
        geometry = self.section(section, value)
        for volume, offset in (("envelope", 0), ("bore", -self.thickness)):
            if volume not in trunk.volumes:
                continue
            root = self.contour(geometry.profile(offset))
            available = self.cross_section(trunk.volumes[volume], frame)
            if (root - available).area() > self.AREA_TOLERANCE_MM2:
                raise ResolutionError(
                    f"Fitting branch {key} root {volume} does not fit inside its trunk"
                )

    def _external_ports(self, parts: dict[str, FittingShape]) -> None:
        """Reject external mating faces buried in another arm or the trunk."""
        for key, part in parts.items():
            for port_key, (frame, section) in part.ports.items():
                if key != "trunk" and port_key == "start":
                    continue
                profile = self.contour(self.section(section).profile(0))
                for other_key, other in parts.items():
                    if key == other_key:
                        continue
                    if (
                        profile ^ self.cross_section(other.volumes["envelope"], frame)
                    ).area() > self.AREA_TOLERANCE_MM2:
                        raise ResolutionError(
                            f"Fitting port {key}/{port_key} is buried in {other_key}"
                        )

    def branch(self) -> FittingShape:
        """Union trunk/arm envelopes and passages before subtracting the shared bore once."""
        trunk = self.path(Authoring.object(self.geometry["trunk"]))
        parts = {"trunk": trunk}
        ports = dict(trunk.ports)
        for key, value in sorted(Authoring.object(self.geometry["branches"]).items()):
            if key in {"start", "end", "trunk"}:
                raise ResolutionError(f"Fitting branch name {key} is reserved")
            definition = Authoring.object(value)
            arm = self.path(definition)
            self._branch_root(trunk, arm, definition, key)
            parts[key] = arm
            ports[key] = arm.ports["end"]
        self._external_ports(parts)
        volumes: dict[str, MeshData] = {}
        for key in trunk.volumes:
            mesh = SolidOperations.union(
                [part.volumes[key] for part in parts.values()],
                None,
                f"construction:{key}",
            )
            if mesh is None:
                raise ResolutionError(
                    "Fitting branch union has no construction geometry"
                )
            volumes[key] = mesh
        stock: list[MeshData] = []
        for key, part in parts.items():
            if part.body is None:
                raise ResolutionError("Fitting arm has no physical stock")
            piece = SolidOperations.difference(
                part.body,
                [
                    other.volumes["bore"]
                    for other_key, other in parts.items()
                    if other_key != key and "bore" in other.volumes
                ],
            )
            if piece is not None:
                stock.append(piece)
        body = SolidOperations.union(
            stock, Authoring.text(self.definition["material"]), "body"
        )
        return FittingShape(
            volumes,
            ports,
            {"paths": {key: part.data for key, part in parts.items()}},
            body,
        )

    @staticmethod
    def _point(section: JsonObject, angle: float, offset: float) -> Vec2:
        """Intersect a polar ray with a circular or rectangular section boundary."""
        cosine, sine = math.cos(angle), math.sin(angle)
        if section["kind"] == "circle":
            distance = number(section["diameter"], "diameter") / 2 + offset
        else:
            width = number(section["width"], "width") / 2 + offset
            height = number(section["height"], "height") / 2 + offset
            distance = min(
                width / abs(cosine) if abs(cosine) > 1e-12 else math.inf,
                height / abs(sine) if abs(sine) > 1e-12 else math.inf,
            )
        return distance * cosine, distance * sine

    def _angles(self, sections: list[JsonObject]) -> list[float]:
        """Retain all rectangular corners and bound every circular endpoint chord."""
        quadrants = max(self.section(section).quadrants for section in sections)
        angles = {index * math.pi / (2 * quadrants) for index in range(4 * quadrants)}
        for section in sections:
            if section["kind"] != "rectangle":
                continue
            for offset in (0, -self.thickness, self.clearance):
                corner = math.atan2(
                    number(section["height"], "height") / 2 + offset,
                    number(section["width"], "width") / 2 + offset,
                )
                angles.update(
                    (corner, math.pi - corner, math.pi + corner, 2 * math.pi - corner)
                )
        result = sorted(angles)
        if len(result) > 10000:
            raise ResolutionError(
                "Transition requires more than 10000 section vertices"
            )
        return [
            angle
            for index, angle in enumerate(result)
            if not index or angle - result[index - 1] > 1e-10
        ]

    def _transition_volume(
        self,
        sections: list[JsonObject],
        angles: list[float],
        offset: float,
        end: Vec3,
        role: str,
    ) -> MeshData:
        """Loft corresponding convex boundaries with explicit triangular side faces."""
        loops = [
            [self._point(section, angle, offset) for angle in angles]
            for section in sections
        ]
        count = len(angles)
        vertices: list[Vec3] = (
            [(x, y, 0) for x, y in loops[0]]
            + [(x + end[0], y + end[1], end[2]) for x, y in loops[1]]
            + [(0, 0, 0), end]
        )
        faces: list[Face] = []
        for index in range(count):
            following = (index + 1) % count
            faces.extend(
                (
                    (2 * count, following, index),
                    (2 * count + 1, count + index, count + following),
                    (index, following, count + following),
                    (index, count + following, count + index),
                )
            )
        mesh = MeshData(tuple(vertices), tuple(faces), None, role)
        result = SolidOperations.mesh(SolidOperations.solid(mesh), None, role)
        if result is None:
            raise ResolutionError("Transition produced no positive construction volume")
        return result

    def transition(self) -> FittingShape:
        """Generate concentric or eccentric reducers and round/rectangular shape transitions."""
        sections = [
            Authoring.object(self.geometry[key])
            for key in ("startSection", "endSection")
        ]
        for section in sections:
            geometry = self.section(section)
            geometry.profile(-self.thickness)
        offset = vector2(self.geometry.get("offset", [0, 0]), "transition offset")
        end: Vec3 = (*offset, number(self.geometry["length"], "transition length"))
        angles = self._angles(sections)
        volumes = {
            key: self._transition_volume(
                sections, angles, distance, end, f"construction:{key}"
            )
            for key, distance in (("envelope", 0), ("clearance", self.clearance))
        }
        if self.thickness:
            volumes["bore"] = self._transition_volume(
                sections, angles, -self.thickness, end, "construction:bore"
            )
        return FittingShape(
            volumes,
            {
                "start": (
                    LocalFrame((0, 0, 0), (-1, 0, 0), (0, 1, 0), (0, 0, -1)),
                    sections[0],
                ),
                "end": (replace(self.IDENTITY, origin=end), sections[1]),
            },
            {
                "lengthMm": end[2],
                "pathControls": [[0, 0, 0], list(end)],
                "sectionUp": [0, 1, 0],
                "bendRadius": 0,
                "offset": list(offset),
                "sectionSides": len(angles),
                "maxDeviationMm": max(
                    self.section(section).section_error for section in sections
                ),
            },
        )

    def cap(self) -> FittingShape:
        """Leave an actual closed end thickness beyond one open mating passage."""
        section = Authoring.object(self.geometry["section"])
        geometry = self.section(section)
        depth = number(self.geometry["depth"], "cap depth")
        if depth <= self.thickness:
            raise ResolutionError("Cap depth must exceed its end-wall thickness")
        volumes = {
            key: extrude_polygon(
                geometry.profile(distance), 0, depth, None, f"construction:{key}"
            )
            for key, distance in (("envelope", 0), ("clearance", self.clearance))
        }
        if self.thickness:
            volumes["bore"] = extrude_polygon(
                geometry.profile(-self.thickness),
                0,
                depth - self.thickness,
                None,
                "construction:bore",
            )
        return FittingShape(
            volumes,
            {
                "start": (
                    LocalFrame((0, 0, 0), (-1, 0, 0), (0, 1, 0), (0, 0, -1)),
                    section,
                )
            },
            {
                "depthMm": depth,
                "maxDeviationMm": geometry.section_error,
                "pathControls": [[0, 0, 0], [0, 0, depth]],
                "sectionUp": [0, 1, 0],
                "bendRadius": 0,
            },
        )

    def resolve(self) -> FittingShape:
        """Dispatch a strict fitting recipe and validate its physical passage envelope."""
        role = Authoring.text(self.geometry["kind"])
        if role == "trap":
            if self.definition["family"] != "pipe" or self.definition["medium"] not in {
                "waste",
                "condensate",
            }:
                raise ResolutionError(
                    "A trap requires a waste or condensate pipe fitting"
                )
            shape = self.path(self.geometry)
        elif role == "elbow":
            shape = self.path(self.geometry)
            points = [
                vector3(value, "elbow point")
                for value in Authoring.array(self.geometry["path"])
            ]
            directions = [
                ConstructionGeometry.unit(tuple3([b[i] - a[i] for i in range(3)]))
                for a, b in zip(points, points[1:])
            ]
            if (
                sum(value**2 for value in ConstructionGeometry.cross(*directions))
                < 1e-16
            ):
                raise ResolutionError("An elbow requires a genuine tangent bend")
        else:
            shape = {
                "branch": self.branch,
                "transition": self.transition,
                "cap": self.cap,
            }[role]()
        bore = shape.volumes.get("bore")
        if (
            bore is not None
            and SolidOperations.difference(bore, [shape.volumes["envelope"]])
            is not None
        ):
            raise ResolutionError("Fitting bore escapes its physical envelope")
        return shape
