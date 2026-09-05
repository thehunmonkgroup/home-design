"""Framed screen elevation profiles with roof closures and hosted door cutouts."""

from __future__ import annotations

from dataclasses import replace

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.geometry import extrude_wall_profile, number
from home_design.json_types import JsonObject
from home_design.resolved import MeshData, Vec2


class ScreenGeometry:
    """Partition a planar screen into non-overlapping frame and mesh regions."""

    @classmethod
    def resolve(
        cls,
        profile: Polygon,
        cutouts: list[Polygon],
        origin: Vec2,
        tangent: Vec2,
        base: float,
        definition: JsonObject,
    ) -> tuple[MeshData, ...]:
        """Cut openings, frame their boundaries and extrude the remaining infill."""
        width = number(definition.get("frameWidth"), "screen frame width")
        depth = number(definition.get("frameDepth"), "screen frame depth")
        if not profile.is_valid or profile.area <= 0:
            raise ResolutionError("Screen profile must have positive area")
        for index, cutout in enumerate(cutouts):
            if not profile.buffer(0.01).covers(cutout):
                raise ResolutionError("Screen opening extends outside its host profile")
            if any(cutout.intersection(other).area > 0.01 for other in cutouts[:index]):
                raise ResolutionError("Screen openings overlap")
        openings = unary_union(cutouts)
        body = profile.difference(openings)
        infill = profile.buffer(-width, join_style="mitre").difference(
            openings.buffer(width, join_style="mitre")
        )
        if infill.is_empty:
            raise ResolutionError("Screen frame leaves no usable infill")
        meshes: list[MeshData] = []
        for region, thickness, material, role in (
            (
                body.difference(infill),
                depth,
                Authoring.text(definition["material"]),
                "screen-frame",
            ),
            (
                infill,
                1.0,
                Authoring.text(definition["infillMaterial"]),
                "screen-infill",
            ),
        ):
            for polygon in cls.strips(region):
                mesh = extrude_wall_profile(
                    polygon, origin, tangent, 0, thickness, base, material
                )
                meshes.append(replace(mesh, role=role))
        return tuple(meshes)

    @classmethod
    def strips(cls, region: BaseGeometry) -> list[Polygon]:
        """Partition frame rings at vertex stations into closed, hole-free prisms."""
        result: list[Polygon] = []
        for polygon in cls.polygons(region):
            stations = sorted(
                {
                    x
                    for ring in (polygon.exterior, *polygon.interiors)
                    for x, _ in ring.coords
                }
            )
            _, low, _, high = polygon.bounds
            for start, end in zip(stations, stations[1:]):
                if end - start <= 1e-8:
                    continue
                clipped = polygon.intersection(box(start, low, end, high))
                parts = (
                    list(clipped.geoms)
                    if isinstance(clipped, (GeometryCollection, MultiPolygon))
                    else [clipped]
                )
                result.extend(
                    part
                    for part in parts
                    if isinstance(part, Polygon) and part.area > 1e-8
                )
        return result

    @staticmethod
    def polygons(region: BaseGeometry) -> list[Polygon]:
        """Accept polygonal regions only, including disconnected screen bays."""
        if region.is_empty:
            return []
        if isinstance(region, Polygon):
            return [region]
        if isinstance(region, MultiPolygon):
            return list(region.geoms)
        raise ResolutionError("Screen subtraction produced non-polygonal geometry")
