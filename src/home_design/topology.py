"""Geometric provenance for stable identities of fitted construction parts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, Polygon

from home_design.errors import ResolutionError
from home_design.resolved import Vec2


@dataclass(frozen=True)
class NamedSpan:
    """One named geometric edge in the working construction plane."""

    identity: str
    start: Vec2
    end: Vec2

    @property
    def line(self) -> LineString:
        """Return the finite edge used to match construction interfaces."""
        return LineString((self.start, self.end))


class PartIdentity:
    """Derive keys from named bounding geometry, never disconnected-fragment ordinals."""

    TOLERANCE: float = 0.01

    @staticmethod
    def token(names: list[str]) -> str:
        """Keep simple provenance readable and encode compound identities unambiguously."""
        unique = sorted(set(names))
        if len(unique) == 1:
            return unique[0]
        return "join." + hashlib.sha256(json.dumps(unique).encode()).hexdigest()[:20]

    @classmethod
    def nearest(cls, point: Vec2, spans: tuple[NamedSpan, ...]) -> str:
        """Identify all equally near interfaces instead of choosing an arbitrary array entry."""
        if not spans:
            raise ResolutionError(
                "A generated part has no named boundary provenance",
                code="member.missing-provenance",
            )
        distances = [
            (span.identity, span.line.distance(Point(point))) for span in spans
        ]
        minimum = min(distance for _, distance in distances)
        return cls.token(
            [
                name
                for name, distance in distances
                if distance <= minimum + cls.TOLERANCE
            ]
        )

    @classmethod
    def edge(cls, start: Vec2, end: Vec2, spans: tuple[NamedSpan, ...]) -> str:
        """Match a fitted edge to parallel authored spans, retaining tied provenance."""
        length = math.dist(start, end)
        direction = ((end[0] - start[0]) / length, (end[1] - start[1]) / length)
        parallel = tuple(
            span
            for span in spans
            if abs(
                direction[0] * (span.end[1] - span.start[1])
                - direction[1] * (span.end[0] - span.start[0])
            )
            <= 1e-6 * math.dist(span.start, span.end)
        )
        if not parallel:
            raise ResolutionError(
                "A fitted boundary has no parallel authored edge",
                code="boundary.unmatched-edge",
            )
        return cls.nearest(((start[0] + end[0]) / 2, (start[1] + end[1]) / 2), parallel)

    @classmethod
    def fragment(
        cls, profile: Polygon, direction: Vec2, spans: tuple[NamedSpan, ...]
    ) -> str:
        """Name a board by its two bounding interfaces in its longitudinal frame."""
        u, v = direction
        low, left, high, right = affine_transform(profile, [u, v, -v, u, 0, 0]).bounds
        center = (left + right) / 2
        start = (u * low - v * center, v * low + u * center)
        end = (u * high - v * center, v * high + u * center)
        return cls.token(
            ["start:" + cls.nearest(start, spans), "end:" + cls.nearest(end, spans)]
        )
