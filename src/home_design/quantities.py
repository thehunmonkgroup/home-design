"""Dimensioned quantities at shared geometry, report and adapter boundaries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar, Literal

from home_design.errors import ResolutionError
from home_design.json_types import JsonObject

QuantityUnit = Literal["mm", "m", "mm2", "m2", "mm3", "m3", "count"]


@dataclass(frozen=True, slots=True)
class Quantity:
    """Pair a finite measurement with an explicit physical dimension and unit."""

    value: float
    unit: QuantityUnit

    _UNITS: ClassVar[dict[QuantityUnit, tuple[str, float]]] = {
        "mm": ("length", 1),
        "m": ("length", 1000),
        "mm2": ("area", 1),
        "m2": ("area", 1_000_000),
        "mm3": ("volume", 1),
        "m3": ("volume", 1_000_000_000),
        "count": ("count", 1),
    }

    def __post_init__(self) -> None:
        """Reject nonfinite evidence before it reaches a report or export."""
        if self.unit not in self._UNITS or not math.isfinite(self.value):
            raise ResolutionError(
                "Quantity requires a supported unit and finite value",
                code="contract.invalid-quantity",
            )

    def in_unit(self, unit: QuantityUnit) -> Quantity:
        """Convert compatible dimensions without silently mixing lengths, areas or volumes."""
        source_dimension, source_scale = self._UNITS[self.unit]
        target_dimension, target_scale = self._UNITS[unit]
        if source_dimension != target_dimension:
            raise ResolutionError(
                f"Cannot convert {self.unit} to {unit}",
                code="contract.quantity-dimension",
            )
        return Quantity(self.value * source_scale / target_scale, unit)

    def to_dict(self) -> JsonObject:
        """Serialize the value with its explicit display or exchange unit."""
        return {"value": self.value, "unit": self.unit}
