"""Presentation disciplines for coordinated envelope, framing and services review."""

from __future__ import annotations

from home_design.json_types import JsonObject
from home_design.capabilities import ComponentRegistry


class ReviewDiscipline:
    """Supply stable default review groups while allowing explicit authoring intent."""

    @staticmethod
    def classify(source: JsonObject) -> str:
        """Return the authored discipline or a default appropriate to the component."""
        discipline = source.get("discipline")
        if isinstance(discipline, str):
            return discipline
        kind = source.get("kind")
        if kind == "envelopePart" and "interface" in source:
            return "services"
        if kind == "sweep" and source.get("role") in {
            "gutter",
            "downspout",
            "drain",
            "interceptor",
        }:
            return "services"
        return ComponentRegistry.get(str(kind)).discipline
