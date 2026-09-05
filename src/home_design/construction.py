"""Shared typed authoring access and oriented construction geometry."""

from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import Point, Polygon

from home_design.errors import ResolutionError
from home_design.geometry import extrude_polygon, number, polygon_from_loops, vector2
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import MeshData, Vec3


class Authoring:
    """Read schema-validated JSON while retaining runtime error context."""

    @staticmethod
    def object(value: JsonValue, label: str = "value") -> JsonObject:
        """Return an object or a contextual resolution error."""
        if not isinstance(value, dict):
            raise ResolutionError(f"{label} must be an object")
        return value

    @staticmethod
    def array(value: JsonValue, label: str = "value") -> list[JsonValue]:
        """Return an array or a contextual resolution error."""
        if not isinstance(value, list):
            raise ResolutionError(f"{label} must be an array")
        return value

    @staticmethod
    def text(value: JsonValue, label: str = "value") -> str:
        """Return a string or a contextual resolution error."""
        if not isinstance(value, str):
            raise ResolutionError(f"{label} must be a string")
        return value


class ConstructionGeometry:
    """Generate section-based members in arbitrary three-dimensional directions."""

    @staticmethod
    def section(value: JsonObject) -> Polygon:
        """Resolve a centered nominal section or an explicit local profile."""
        kind = value.get("kind")
        if kind == "rectangle":
            half_width = number(value.get("width"), "section width") / 2
            half_depth = number(value.get("depth"), "section depth") / 2
            return Polygon(
                [
                    (-half_width, -half_depth),
                    (half_width, -half_depth),
                    (half_width, half_depth),
                    (-half_width, half_depth),
                ]
            )
        if kind == "circle":
            return Point(0, 0).buffer(
                number(value.get("diameter"), "section diameter") / 2, quad_segs=16
            )
        profile = Authoring.object(value.get("profile"), "section profile")
        outer = [
            vector2(point, "section point")
            for point in Authoring.array(profile.get("outer"))
        ]
        holes = [
            [vector2(point, "section hole point") for point in Authoring.array(loop)]
            for loop in Authoring.array(profile.get("holes", []))
        ]
        return polygon_from_loops(outer, holes)

    @staticmethod
    def cross(a: Vec3, b: Vec3) -> Vec3:
        """Return the cross product of two vectors."""
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    @staticmethod
    def unit(value: Vec3) -> Vec3:
        """Normalize a nonzero vector."""
        magnitude = math.sqrt(sum(coordinate * coordinate for coordinate in value))
        if magnitude < 1e-9:
            raise ResolutionError("Construction path contains a zero-length segment")
        return (value[0] / magnitude, value[1] / magnitude, value[2] / magnitude)

    @classmethod
    def member(
        cls,
        start: Vec3,
        end: Vec3,
        section: JsonObject,
        material: str | None,
        role: str,
        roll: float = 0,
    ) -> MeshData:
        """Extrude a local section along an axis with optional axial rotation."""
        length = math.dist(start, end)
        direction = cls.unit((end[0] - start[0], end[1] - start[1], end[2] - start[2]))
        reference = (0.0, 1.0, 0.0) if abs(direction[2]) > 0.999 else (0.0, 0.0, 1.0)
        across = cls.unit(cls.cross(reference, direction))
        up = cls.cross(direction, across)
        angle = math.radians(roll)
        rotated = [
            across[i] * math.cos(angle) + up[i] * math.sin(angle) for i in range(3)
        ]
        x_axis: Vec3 = (rotated[0], rotated[1], rotated[2])
        y_axis = cls.cross(direction, x_axis)
        local = extrude_polygon(cls.section(section), 0, length, material, role)
        vertices: tuple[Vec3, ...] = tuple(
            (
                start[0] + x_axis[0] * x + y_axis[0] * y + direction[0] * z,
                start[1] + x_axis[1] * x + y_axis[1] * y + direction[1] * z,
                start[2] + x_axis[2] * x + y_axis[2] * y + direction[2] * z,
            )
            for x, y, z in local.vertices
        )
        return MeshData(vertices, local.faces, material, role)

    @staticmethod
    def translated(mesh: MeshData, offset: Vec3, role: str | None = None) -> MeshData:
        """Translate a mesh without altering its topology or source identity."""
        return MeshData(
            tuple(
                (x + offset[0], y + offset[1], z + offset[2])
                for x, y, z in mesh.vertices
            ),
            mesh.faces,
            mesh.material_id,
            role or mesh.role,
        )

    @classmethod
    def sweep(
        cls, points: Sequence[Vec3], section: JsonObject, material: str | None
    ) -> tuple[MeshData, ...]:
        """Sweep a transported profile through shared miter planes in three dimensions.

        Each segment remains a closed solid. Adjacent caps coincide, including
        profile holes. Reversals and miters longer than a segment are rejected.
        """
        directions = [
            cls.unit((b[0] - a[0], b[1] - a[1], b[2] - a[2]))
            for a, b in zip(points, points[1:])
        ]
        first = directions[0]
        reference = (0.0, 1.0, 0.0) if abs(first[2]) > 0.999 else (0.0, 0.0, 1.0)
        across = cls.unit(cls.cross(reference, first))
        frames: list[tuple[Vec3, Vec3, Vec3, Vec3]] = [
            (across, cls.cross(first, across), first, first)
        ]
        for incoming, outgoing in zip(directions, directions[1:]):
            cosine = sum(a * b for a, b in zip(incoming, outgoing))
            if cosine < -0.999999:
                raise ResolutionError("Sweep path reverses at a joint")
            normal = cls.unit(
                (
                    incoming[0] + outgoing[0],
                    incoming[1] + outgoing[1],
                    incoming[2] + outgoing[2],
                )
            )
            frames.append((across, cls.cross(incoming, across), incoming, normal))
            rotation = cls.cross(incoming, outgoing)
            cross_once = cls.cross(rotation, across)
            cross_twice = cls.cross(rotation, cross_once)
            transported = [
                across[i] + cross_once[i] + cross_twice[i] / (1 + cosine)
                for i in range(3)
            ]
            across = cls.unit((transported[0], transported[1], transported[2]))
        last = directions[-1]
        frames.append((across, cls.cross(last, across), last, last))
        local = extrude_polygon(cls.section(section), 0, 1, material, "sweep")

        def joint_vertex(index: int, x: float, y: float) -> Vec3:
            x_axis, y_axis, direction, normal = frames[index]
            offset = tuple(x_axis[i] * x + y_axis[i] * y for i in range(3))
            distance = -sum(a * b for a, b in zip(offset, normal)) / sum(
                a * b for a, b in zip(direction, normal)
            )
            vertex = [
                points[index][i] + offset[i] + direction[i] * distance for i in range(3)
            ]
            return (vertex[0], vertex[1], vertex[2])

        meshes: list[MeshData] = []
        for index, direction in enumerate(directions):
            for x, y, _ in local.vertices:
                a, b = joint_vertex(index, x, y), joint_vertex(index + 1, x, y)
                if sum((b[i] - a[i]) * direction[i] for i in range(3)) <= 1e-6:
                    raise ResolutionError(
                        "Sweep miter consumes a segment; lengthen the path or reduce the section"
                    )
            vertices = tuple(
                joint_vertex(index + int(z), x, y) for x, y, z in local.vertices
            )
            meshes.append(MeshData(vertices, local.faces, material, f"sweep:{index}"))
        return tuple(meshes)

    @staticmethod
    def interval_segments(
        length: float, openings: Sequence[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Return remaining path intervals after explicit non-overlapping access gaps."""
        segments: list[tuple[float, float]] = []
        position = 0.0
        for start, end in sorted(openings):
            if start < position or end <= start or end > length:
                raise ResolutionError(
                    "Access openings overlap, reverse, or extend beyond their path"
                )
            if start > position:
                segments.append((position, start))
            position = end
        if position < length:
            segments.append((position, length))
        return segments
