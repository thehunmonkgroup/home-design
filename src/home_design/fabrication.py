"""Reusable fabricated solids assembled from local extrusions, revolutions and type cuts."""

from __future__ import annotations

import math
from typing import Literal, cast

import manifold3d
import numpy as np

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import extrude_polygon, number, vector3
from home_design.json_types import JsonObject
from home_design.placement import LocalFrame
from home_design.resolved import MeshData
from home_design.solids import SolidOperations


class FabricationGeometry:
    """Build one material volume from an explicit local fabrication recipe."""

    MAX_REVOLUTION_SEGMENTS: int = 10000
    MAX_REVOLUTION_VERTICES: int = 2000000

    @staticmethod
    def placement(value: JsonObject) -> LocalFrame:
        """Resolve a type-local rigid pose without model references."""
        return LocalFrame(
            vector3(value.get("origin", [0, 0, 0]), "local origin"),
            (1, 0, 0),
            (0, 1, 0),
            (0, 0, 1),
        ).adjusted(
            (0, 0, 0), vector3(value.get("rotation", [0, 0, 0]), "local rotation")
        )

    @classmethod
    def extrusion(cls, value: JsonObject, material: str | None, role: str) -> MeshData:
        """Extrude a section along local positive Z then apply its local placement."""
        section = ConstructionGeometry.section(Authoring.object(value["section"]))
        mesh = extrude_polygon(
            section, 0, number(value["depth"], "extrusion depth"), material, role
        )
        return cls.placement(Authoring.object(value.get("placement", {}))).mesh(mesh)

    @classmethod
    def revolution(cls, value: JsonObject, material: str | None, role: str) -> MeshData:
        """Revolve a radius/height profile about local Z with bounded circular approximation.

        :param value: A nonnegative radial profile, chord tolerance and optional local pose.
        :returns: Closed solid preserving holes and tapered radial walls.
        :raises ResolutionError: For an invalid radial profile or excessive tessellation.
        """
        profile = ConstructionGeometry.section(
            {"kind": "profile", "profile": value["profile"]}
        )
        radius = profile.bounds[2]
        if profile.bounds[0] < 0 or radius <= 0:
            raise ResolutionError(
                "A revolved profile requires nonnegative radii and positive radial extent"
            )
        tolerance = number(value["chordTolerance"], "revolution chord tolerance")
        step = min(math.pi / 2, 2 * math.acos(max(-1.0, 1 - tolerance / radius)))
        if step <= 0:
            raise ResolutionError("Revolution tolerance is below numeric resolution")
        segments = max(4, math.ceil(2 * math.pi / step))
        if segments > cls.MAX_REVOLUTION_SEGMENTS:
            raise ResolutionError(
                "Revolution tolerance requires more than 10000 segments"
            )
        contours = [
            cast(
                np.ndarray[tuple[int, Literal[2]], np.dtype[np.double]],
                np.asarray(list(ring.coords)[:-1], dtype=np.double),
            )
            for ring in (profile.exterior, *profile.interiors)
        ]
        if segments * sum(len(ring) for ring in contours) > cls.MAX_REVOLUTION_VERTICES:
            raise ResolutionError(
                "Revolution tolerance requires more than 2000000 vertices"
            )
        solid = manifold3d.CrossSection(contours, manifold3d.FillRule.EvenOdd).revolve(
            circular_segments=segments
        )
        mesh = SolidOperations.mesh(solid, material, role)
        if mesh is None:
            raise ResolutionError("Revolved profile produced no physical material")
        return cls.placement(Authoring.object(value.get("placement", {}))).mesh(mesh)

    @classmethod
    def local_solid(
        cls, value: JsonObject, material: str | None, role: str
    ) -> MeshData:
        """Resolve one explicitly shaped local stock or cutter."""
        if value.get("kind") == "revolve":
            return cls.revolution(value, material, role)
        return cls.extrusion(value, material, role)

    @classmethod
    def resolve(cls, definition: JsonObject) -> MeshData:
        """Union stock volumes before subtracting each named intersecting type cut."""
        material = Authoring.text(definition["material"])
        stock = [
            cls.local_solid(Authoring.object(value), material, "body")
            for _, value in sorted(Authoring.object(definition["solids"]).items())
        ]
        mesh = SolidOperations.union(stock, material, "body")
        if mesh is None:
            raise ResolutionError("Fabricated type has no physical stock")
        for key, value in sorted(Authoring.object(definition.get("cuts", {})).items()):
            cutter = cls.local_solid(Authoring.object(value), None, "void")
            if SolidOperations.intersection(mesh, cutter) is None:
                raise ResolutionError(
                    f"Fabricated type cut {key} does not intersect remaining stock"
                )
            result = SolidOperations.difference(mesh, [cutter])
            if result is None:
                raise ResolutionError(f"Fabricated type cut {key} removes all stock")
            mesh = result
        return mesh
