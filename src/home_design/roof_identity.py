"""Named plane and edge provenance for generated parametric roof faces."""

from __future__ import annotations

import math

from shapely.geometry import LineString

from home_design.boundaries import BoundaryIdentity
from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.geometry import polygon_normal
from home_design.json_types import JsonObject
from home_design.resolved import Vec2, Vec3
from home_design.topology import NamedSpan, PartIdentity


class RoofIdentity:
    """Identify roof planes by their support boundary and shared edges by adjacent planes."""

    @staticmethod
    def _shared(first: LineString, second: LineString) -> bool:
        """Recognize coincident clipped edges within the engine's geometric tolerance."""
        a, b = first.coords
        c, d = second.coords
        cross = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
        return (
            abs(cross) <= 1e-6 * first.length * second.length
            and first.intersection(second.buffer(0.01, cap_style="flat")).length > 0.01
        )

    @staticmethod
    def describe(
        geometry: JsonObject,
        footprint: tuple[Vec2, ...],
        faces: list[tuple[Vec3, ...]],
    ) -> tuple[tuple[str, ...], tuple[JsonObject, ...]]:
        """Return topology keys independently of polygon ordering and dimensional edits."""
        names = BoundaryIdentity.profile(Authoring.object(geometry["footprint"]))[0]
        spans = tuple(
            NamedSpan(name, footprint[index], footprint[(index + 1) % len(footprint)])
            for index, name in enumerate(names)
        )
        edges = [
            tuple(
                LineString(((a[0], a[1]), (b[0], b[1])))
                for a, b in zip(face, (*face[1:], face[0]))
            )
            for face in faces
        ]
        neighbors: list[list[list[int]]] = []
        external: list[list[str | None]] = []
        keys: list[str] = []
        for index, face in enumerate(faces):
            adjacent = [
                [
                    other_index
                    for other_index, other in enumerate(edges)
                    if other_index != index
                    and any(
                        RoofIdentity._shared(edge, candidate) for candidate in other
                    )
                ]
                for edge in edges[index]
            ]
            neighbors.append(adjacent)
            identities = [
                (
                    None
                    if adjacent[position]
                    else PartIdentity.edge(
                        (face[position][0], face[position][1]),
                        (
                            face[(position + 1) % len(face)][0],
                            face[(position + 1) % len(face)][1],
                        ),
                        spans,
                    )
                )
                for position in range(len(face))
            ]
            external.append(identities)
            normal = polygon_normal(face)
            supports = [
                identity
                for position, identity in enumerate(identities)
                if identity is not None
                and abs(
                    (face[(position + 1) % len(face)][0] - face[position][0])
                    * normal[0]
                    + (face[(position + 1) % len(face)][1] - face[position][1])
                    * normal[1]
                )
                <= 1e-6 * math.dist(face[position], face[(position + 1) % len(face)])
            ]
            form = Authoring.text(geometry["form"])
            keys.append(
                f"face.{form}"
                if form in {"flat", "shed"}
                else f"face.{form}.{PartIdentity.token(supports)}"
            )
        if len(set(keys)) != len(keys):
            raise ResolutionError(
                "Roof faces have ambiguous supporting boundary identities",
                code="roof.ambiguous-face-identity",
            )
        metadata: tuple[JsonObject, ...] = tuple(
            {
                "outer": [
                    (
                        identity
                        if identity is not None
                        else "shared."
                        + PartIdentity.token(
                            [
                                keys[index],
                                *[keys[other] for other in neighbors[index][position]],
                            ]
                        )
                    )
                    for position, identity in enumerate(identities)
                ],
                "holes": [],
            }
            for index, identities in enumerate(external)
        )
        return tuple(keys), metadata
