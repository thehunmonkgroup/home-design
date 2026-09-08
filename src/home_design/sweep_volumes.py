"""Nonmaterial construction masks for profiled drainage and trim sweeps."""

from __future__ import annotations

from collections.abc import Sequence

from shapely.geometry import Polygon

from home_design.construction import ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import MeshData, Vec3
from home_design.solids import SolidOperations


class SweepVolumes:
    """Retain a convex stock envelope and enclosed profile bores before host cuts."""

    @classmethod
    def resolve(cls, points: Sequence[Vec3], section: JsonObject) -> dict[str, MeshData]:
        """Sweep masks through the same transported joints as the physical stock."""
        profile = ConstructionGeometry.section(section)
        envelope = profile.convex_hull
        if not isinstance(envelope, Polygon):
            raise ResolutionError("Sweep envelope requires a positive-area profile")
        volumes = {"envelope": cls.sweep(points, [envelope], "envelope")}
        if profile.interiors:
            volumes["bore"] = cls.sweep(
                points, [Polygon(ring) for ring in profile.interiors], "bore"
            )
        return volumes

    @staticmethod
    def sweep(points: Sequence[Vec3], profiles: list[Polygon], name: str) -> MeshData:
        """Combine closed mask segments without assigning them physical material."""
        meshes: list[MeshData] = []
        for profile in profiles:
            outer: list[JsonValue] = [[x, y] for x, y in list(profile.exterior.coords)[:-1]]
            meshes.extend(ConstructionGeometry.sweep(
                points, {"kind": "profile", "profile": {"outer": outer}}, None
            ))
        mask = SolidOperations.union(meshes, None, f"construction:{name}")
        if mask is None:
            raise ResolutionError(f"Sweep {name} has no construction volume")
        return mask
