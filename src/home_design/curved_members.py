"""Circular-arc structural members with explicit geometric approximation bounds."""

from __future__ import annotations

import math

from shapely.geometry import Point, Polygon

from home_design.components import ConstructionResolver
from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import extrude_polygon, number
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import MeshData, ResolvedElement, Vec3
from home_design.solids import SolidOperations


class CurvedMember:
    """Loft true radial cross sections along a bounded circular arc."""

    MAX_SEGMENTS: int = 10000
    MAX_LOFT_VERTICES: int = 2000000

    @classmethod
    def resolve(
        cls, construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Resolve curve intent into a closed solid and report its actual error bound."""
        definition = construction.context.types[Authoring.text(source["type"])]
        section = Authoring.object(definition["section"])
        tolerance = number(source["chordTolerance"], "curve tolerance")
        profile, profile_error = cls._profile(section, tolerance)
        radius = number(source["radius"], "curve radius")
        angle = math.radians(number(source["sweepAngle"], "sweep angle"))
        start_angle = math.radians(number(source.get("startAngle", 0), "start angle"))
        roll = math.radians(number(source.get("roll", 0), "section roll"))
        sign = 1 if angle > 0 else -1
        radial = [
            sign * (x * math.cos(roll) - y * math.sin(roll))
            for ring in (profile.exterior, *profile.interiors)
            for x, y in ring.coords
        ]
        inner = radius - max(radial)
        outer = radius - min(radial)
        if section["kind"] == "circle":
            section_radius = number(section["diameter"], "section diameter") / 2
            inner, outer = radius - section_radius, radius + section_radius
        if inner <= 1e-6:
            raise ResolutionError(
                "Curved member section reaches or crosses its bend center"
            )
        max_step = min(
            math.pi / 2,
            2 * math.acos(max(-1.0, 1 - (tolerance - profile_error) / outer)),
        )
        if max_step <= 0:
            raise ResolutionError("Curve tolerance is below numeric resolution")
        count = max(1, math.ceil(abs(angle) / max_step))
        if count > cls.MAX_SEGMENTS:
            raise ResolutionError("Curve tolerance requires more than 10000 segments")
        frame = construction.placement(Authoring.object(source["placement"]))
        material = Authoring.text(definition["material"])
        template = extrude_polygon(profile, 0, 1, material, "body")
        if count * len(template.vertices) > cls.MAX_LOFT_VERTICES:
            raise ResolutionError(
                "Curve tolerance requires more than 2000000 loft vertices"
            )
        angles = [start_angle + angle * index / count for index in range(count + 1)]
        if math.isclose(abs(angle), 2 * math.pi, abs_tol=1e-12):
            angles[-1] = start_angle
        pieces: list[MeshData] = []
        for index in range(count):
            vertices = tuple(
                frame.point(
                    cls._vertex(radius, sign, roll, angles[index + int(z)], x, y)
                )
                for x, y, z in template.vertices
            )
            pieces.append(MeshData(vertices, template.faces, material, "body"))
        mesh = SolidOperations.union(pieces, material, "body")
        if mesh is None:
            raise ResolutionError("Curved member produced no solid")
        path: list[JsonValue] = [
            list(frame.point((radius * math.cos(theta), radius * math.sin(theta), 0)))
            for theta in angles
        ]
        centroid = profile.centroid
        centroid_radial = sign * (
            centroid.x * math.cos(roll) - centroid.y * math.sin(roll)
        )
        area = (
            math.pi * (number(section["diameter"], "section diameter") / 2) ** 2
            if section["kind"] == "circle"
            else profile.area
        )
        storey = source.get("storey")
        return ResolvedElement(
            element_id,
            "curvedMember",
            Authoring.text(source["name"]),
            storey if isinstance(storey, str) else None,
            (mesh,),
            {
                "typeId": source["type"],
                "role": source["role"],
                "section": section,
                "placement": frame.to_dict(),
                "radius": radius,
                "startAngle": source.get("startAngle", 0),
                "sweepAngle": source["sweepAngle"],
                "roll": source.get("roll", 0),
                "chordTolerance": tolerance,
                "maxDeviationMm": outer * (1 - math.cos(abs(angle) / count / 2))
                + profile_error,
                "segmentCount": count,
                "path": path,
                "memberLength": radius * abs(angle),
                "polylineLengthMm": count
                * 2
                * radius
                * math.sin(abs(angle) / count / 2),
                "analyticVolumeMm3": area * (radius - centroid_radial) * abs(angle),
                "netVolumeMm3": SolidOperations.volume(mesh),
            },
        )

    @staticmethod
    def _vertex(
        radius: float, sign: int, roll: float, theta: float, x: float, y: float
    ) -> Vec3:
        """Place a rolled profile point on a radial section with consistent winding."""
        distance = radius - sign * (x * math.cos(roll) - y * math.sin(roll))
        height = x * math.sin(roll) + y * math.cos(roll)
        return distance * math.cos(theta), distance * math.sin(theta), height

    @classmethod
    def _profile(cls, section: JsonObject, tolerance: float) -> tuple[Polygon, float]:
        """Allocate part of the error budget to circular section tessellation."""
        if section["kind"] != "circle":
            return ConstructionGeometry.section(section), 0.0
        radius = number(section["diameter"], "section diameter") / 2
        half_angle = math.acos(max(-1.0, 1 - tolerance / 2 / radius))
        if half_angle <= 0:
            raise ResolutionError("Section tolerance is below numeric resolution")
        quadrants = max(2, math.ceil(math.pi / 4 / half_angle))
        if quadrants * 4 > cls.MAX_SEGMENTS:
            raise ResolutionError("Section tolerance requires more than 10000 segments")
        return Point(0, 0).buffer(radius, quad_segs=quadrants), radius * (
            1 - math.cos(math.pi / (4 * quadrants))
        )
