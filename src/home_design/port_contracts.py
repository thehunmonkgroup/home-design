"""Typed resolved service interfaces shared by network checks and IFC ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.frames import LocalFrame
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.quantities import Quantity


@dataclass(frozen=True, slots=True)
class PortSection:
    """An explicitly dimensioned circular or rectangular mating interface."""

    kind: Literal["circle", "rectangle"]
    width: Quantity
    height: Quantity

    @classmethod
    def from_dict(cls, value: JsonValue) -> PortSection:
        """Validate interface dimensions before comparing connected components."""
        source = Authoring.object(value, "port section")
        kind = Authoring.text(source["kind"], "port section kind")
        if kind == "circle":
            width = height = number(source["diameter"], "port diameter")
        elif kind == "rectangle":
            width = number(source["width"], "port width")
            height = number(source["height"], "port height")
        else:
            raise ResolutionError(
                "Unsupported port section", code="contract.invalid-port"
            )
        if width <= 0 or height <= 0:
            raise ResolutionError(
                "Port section dimensions must be positive", code="contract.invalid-port"
            )
        return cls(kind, Quantity(width, "mm"), Quantity(height, "mm"))


@dataclass(frozen=True, slots=True)
class ResolvedPort:
    """The oriented interface contract independent of device-specific properties."""

    frame: LocalFrame
    section: PortSection
    medium: str
    flow: Literal["source", "sink", "bidirectional"]
    connection_type: str
    function: str | None
    source: JsonObject

    @classmethod
    def from_dict(cls, value: JsonValue) -> ResolvedPort:
        """Read common resolved fields while retaining all supplementary device metadata."""
        source = Authoring.object(value, "resolved service port")
        flow = source["flow"]
        if flow not in ("source", "sink", "bidirectional"):
            raise ResolutionError(
                "Unsupported service port flow", code="contract.invalid-port"
            )
        function = source.get("function")
        return cls(
            LocalFrame.from_dict(source["frame"]),
            PortSection.from_dict(source["section"]),
            Authoring.text(source["medium"], "service medium"),
            flow,
            Authoring.text(source["connectionType"], "connection type"),
            Authoring.text(function, "port function") if function is not None else None,
            source,
        )
