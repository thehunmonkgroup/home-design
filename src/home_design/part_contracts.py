"""Typed generated-member records shared by fabrication, hosting and export."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.frames import LocalFrame
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.quantities import Quantity
from home_design.resolved import Vec3


@dataclass(frozen=True, slots=True)
class GeneratedMember:
    """A durable part key, stock geometry and final quantity with lossless domain metadata."""

    key: str
    type_id: str
    role: str
    axis: tuple[Vec3, Vec3]
    frame: LocalFrame
    section: JsonObject
    length: Quantity
    stock_length: Quantity
    net_volume: Quantity
    supplementary: JsonObject

    @classmethod
    def from_dict(cls, value: JsonValue) -> GeneratedMember:
        """Validate the generated-part interface once instead of repeating dictionary assumptions."""
        source = Authoring.object(value, "generated member")
        points = Authoring.array(source["axis"], "generated member axis")
        if len(points) != 2:
            raise ResolutionError(
                "Generated member axis requires two endpoints",
                code="contract.invalid-member",
            )
        axis = (vector3(points[0], "member start"), vector3(points[1], "member end"))
        frame = LocalFrame.from_dict(
            {
                **Authoring.object(source["sectionFrame"], "member section frame"),
                "origin": list(axis[0]),
            }
        )
        length = Quantity(number(source["lengthMm"], "member length"), "mm")
        stock = Quantity(number(source["stockLengthMm"], "stock length"), "mm")
        volume = Quantity(number(source["netVolumeMm3"], "member net volume"), "mm3")
        if length.value <= 0 or stock.value <= 0 or volume.value < 0:
            raise ResolutionError(
                "Generated member lengths must be positive and net volume nonnegative",
                code="contract.invalid-member",
            )
        return cls(
            Authoring.text(source["key"], "member key"),
            Authoring.text(source["typeId"], "member type"),
            Authoring.text(source["role"], "member role"),
            axis,
            frame,
            deepcopy(Authoring.object(source["section"], "member section")),
            length,
            stock,
            volume,
            deepcopy(source),
        )

    def with_volume(self, volume_mm3: float) -> GeneratedMember:
        """Retain identity, nominal stock and domain metadata after a physical cut."""
        if volume_mm3 < 0:
            raise ResolutionError("Generated member net volume cannot be negative")
        return replace(self, net_volume=Quantity(volume_mm3, "mm3"))

    def to_dict(self) -> JsonObject:
        """Preserve supplementary details while publishing the authoritative typed fields."""
        return {
            **deepcopy(self.supplementary),
            "key": self.key,
            "typeId": self.type_id,
            "role": self.role,
            "axis": [list(point) for point in self.axis],
            "section": deepcopy(self.section),
            "sectionFrame": {
                "x": list(self.frame.x),
                "y": list(self.frame.y),
                "z": list(self.frame.z),
            },
            "lengthMm": self.length.value,
            "stockLengthMm": self.stock_length.value,
            "netVolumeMm3": self.net_volume.value,
        }
