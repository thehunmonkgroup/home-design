"""Directional geometric fall checks shared by profile sweeps and service routes."""

from __future__ import annotations

import math
from collections.abc import Sequence

from home_design.errors import ResolutionError
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import Vec3


class DrainageFall:
    """Check each authored tangent direction without substituting an overall endpoint drop."""

    RATIO_TOLERANCE: float = 1e-9
    LEGACY_MINIMUM_RUN_MM: float = 0.001

    @classmethod
    def ratios(cls, points: Sequence[Vec3]) -> list[JsonValue]:
        """Retain the existing finite sweep-report convention for vertical segments."""
        return [
            (a[2] - b[2]) / max(math.dist(a[:2], b[:2]), cls.LEGACY_MINIMUM_RUN_MM)
            for a, b in zip(points, points[1:])
        ]

    @classmethod
    def check(cls, points: Sequence[Vec3], minimum: float) -> JsonObject:
        """Require directional fall on every span, including unconditionally descending vertical spans.

        Filleted paths use these authored span directions as their arc tangents.
        The downward minimum-grade cone is convex, so intermediate tangent
        directions on the minor circular bend satisfy the same lower bound.

        :raises ResolutionError: If a path rises or has insufficient fall.
        """
        segments: list[JsonValue] = []
        ratios: list[float] = []
        for index, (a, b) in enumerate(zip(points, points[1:])):
            horizontal = math.dist(a[:2], b[:2])
            drop = a[2] - b[2]
            if (horizontal == 0 and drop <= 0) or (
                horizontal > 0 and drop < (minimum - cls.RATIO_TOLERANCE) * horizontal
            ):
                raise ResolutionError(
                    f"Drainage path span {index} rises or falls less than its specified minimum"
                )
            ratio = drop / horizontal if horizontal else None
            if ratio is not None:
                ratios.append(ratio)
            segments.append(
                {
                    "index": index,
                    "horizontalRunMm": horizontal,
                    "dropMm": drop,
                    "fallRatio": ratio,
                    "vertical": horizontal == 0,
                }
            )
        return {
            "minimumFall": minimum,
            "minimumObservedFall": min(ratios) if ratios else None,
            "segments": segments,
            "status": "satisfied",
        }
