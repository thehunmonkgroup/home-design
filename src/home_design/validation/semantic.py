"""Semantic constraints spanning canonical model registries."""

from __future__ import annotations

import math
from collections import Counter

from home_design.diagnostics import Diagnostic
from home_design.geometry import number, vector2, vector3
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonValue


class SemanticValidator:
    """Validate cardinality and domain rules beyond JSON Schema."""

    def __init__(self, model: JsonObject, index: ModelIndex) -> None:
        """Initialize semantic validation.

        :param model: Schema-valid canonical model.
        :param index: Reference index for the same model.
        """
        self.model: JsonObject = model
        self.index: ModelIndex = index
        self.elements: dict[str, JsonObject] = index.registries["elements"]

    def diagnostics(self) -> list[Diagnostic]:
        """Return all semantic diagnostics.

        :returns: Semantic diagnostic list.
        """
        diagnostics: list[Diagnostic] = []
        diagnostics.extend(self._relationship_cardinality())
        diagnostics.extend(self._relationship_rules())
        diagnostics.extend(self._direction_rules())
        diagnostics.extend(self._opening_fill_rules())
        diagnostics.extend(self._aggregate_rules())
        return diagnostics

    def _relationship_cardinality(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        void_counts = Counter(
            relationship.get("opening")
            for _, relationship in self.index.relationships("voids")
            if isinstance(relationship.get("opening"), str)
        )
        fill_counts = Counter(
            relationship.get("opening")
            for _, relationship in self.index.relationships("fills")
            if isinstance(relationship.get("opening"), str)
        )
        filled_element_counts = Counter(
            relationship.get("element")
            for _, relationship in self.index.relationships("fills")
            if isinstance(relationship.get("element"), str)
        )
        for element_id, element in self.elements.items():
            kind = element.get("kind")
            if kind == "opening" and void_counts[element_id] != 1:
                diagnostics.append(
                    self._error(
                        "relationship.opening-host-cardinality",
                        f"Opening must have exactly one voids relationship, found {void_counts[element_id]}",
                        element_id,
                    )
                )
            if kind in {"door", "window"} and filled_element_counts[element_id] != 1:
                diagnostics.append(
                    self._error(
                        "relationship.fill-cardinality",
                        f"{kind.title()} must fill exactly one opening, found {filled_element_counts[element_id]}",
                        element_id,
                    )
                )
        for opening_id, count in fill_counts.items():
            if count > 1:
                diagnostics.append(
                    self._error(
                        "relationship.multiple-fills",
                        f"Opening is filled by {count} elements",
                        str(opening_id),
                    )
                )
        return diagnostics

    def _relationship_rules(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for relationship_id, relationship in self.index.relationships("voids"):
            host_id = relationship.get("host")
            host = self.elements.get(host_id) if isinstance(host_id, str) else None
            if host is not None and host.get("kind") != "wall":
                diagnostics.append(
                    self._error(
                        "relationship.unsupported-opening-host",
                        "Hosted station placement in model 0.1 is exportable only on walls",
                        relationship_id,
                    )
                )
        for relationship_id, relationship in self.index.relationships("joins"):
            a = relationship.get("a")
            b = relationship.get("b")
            if (
                isinstance(a, dict)
                and isinstance(b, dict)
                and a.get("element") == b.get("element")
            ):
                diagnostics.append(
                    self._error(
                        "relationship.self-join",
                        "A wall cannot join itself",
                        relationship_id,
                    )
                )
        for relationship_id, relationship in self.index.relationships("supports"):
            if relationship.get("support") == relationship.get("supported"):
                diagnostics.append(
                    self._error(
                        "relationship.self-support",
                        "An element cannot support itself",
                        relationship_id,
                    )
                )
        for relationship_id, relationship in self.index.relationships("attaches"):
            if relationship.get("primary") == relationship.get("attached"):
                diagnostics.append(
                    self._error(
                        "relationship.self-attach",
                        "An element cannot attach to itself",
                        relationship_id,
                    )
                )
        return diagnostics

    def _direction_rules(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        anchors = self.index.registries["anchors"]
        for anchor_id, anchor in anchors.items():
            if anchor.get("kind") == "plane":
                diagnostics.extend(
                    self._unit_vector(
                        anchor.get("normal"),
                        f"/anchors/{anchor_id}/normal",
                        anchor_id,
                        3,
                    )
                )
                if "xDirection" in anchor:
                    diagnostics.extend(
                        self._unit_vector(
                            anchor.get("xDirection"),
                            f"/anchors/{anchor_id}/xDirection",
                            anchor_id,
                            3,
                        )
                    )
        for element_id, element in self.elements.items():
            if element.get("kind") != "roof":
                continue
            geometry = element.get("geometry")
            if not isinstance(geometry, dict) or geometry.get("kind") != "parametric":
                continue
            for field in ("slopeDirection", "ridgeDirection"):
                if field in geometry:
                    diagnostics.extend(
                        self._unit_vector(
                            geometry.get(field),
                            f"/elements/{element_id}/geometry/{field}",
                            element_id,
                            2,
                        )
                    )
            pitch = geometry.get("pitch")
            if (
                isinstance(pitch, (int, float))
                and not isinstance(pitch, bool)
                and not 0 < float(pitch) < 89
            ):
                diagnostics.append(
                    self._error(
                        "roof.invalid-pitch",
                        "Pitched roof angle must be greater than 0 and less than 89 degrees",
                        element_id,
                        f"/elements/{element_id}/geometry/pitch",
                    )
                )
        return diagnostics

    def _opening_fill_rules(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for relationship_id, relationship in self.index.relationships("fills"):
            opening_id = relationship.get("opening")
            fill_id = relationship.get("element")
            opening = (
                self.elements.get(opening_id) if isinstance(opening_id, str) else None
            )
            fill = self.elements.get(fill_id) if isinstance(fill_id, str) else None
            if opening is None or fill is None:
                continue
            opening_geometry = opening.get("geometry")
            fill_type_id = fill.get("type")
            fill_type = (
                self.index.registries["types"].get(fill_type_id)
                if isinstance(fill_type_id, str)
                else None
            )
            if not isinstance(opening_geometry, dict) or not isinstance(
                fill_type, dict
            ):
                continue
            if opening_geometry.get("kind") == "rectangle":
                opening_width = number(opening_geometry.get("width"), "opening width")
                opening_height = number(
                    opening_geometry.get("height"), "opening height"
                )
                nominal_width = number(fill_type.get("nominalWidth"), "nominal width")
                nominal_height = number(
                    fill_type.get("nominalHeight"), "nominal height"
                )
                if nominal_width > opening_width or nominal_height > opening_height:
                    diagnostics.append(
                        self._error(
                            "fill.exceeds-opening",
                            "Door or window nominal size exceeds its rough opening",
                            relationship_id,
                        )
                    )
        return diagnostics

    def _aggregate_rules(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        part_owners: dict[str, str] = {}
        for relationship_id, relationship in self.index.relationships("aggregates"):
            assembly_id = relationship.get("assembly")
            parts = relationship.get("parts", [])
            if not isinstance(parts, list):
                continue
            for part in parts:
                if part == assembly_id:
                    diagnostics.append(
                        self._error(
                            "aggregate.self",
                            "An assembly cannot aggregate itself",
                            relationship_id,
                        )
                    )
                if isinstance(part, str) and part in part_owners:
                    diagnostics.append(
                        self._error(
                            "aggregate.multiple-parents",
                            f"Part {part} is already aggregated by {part_owners[part]}",
                            relationship_id,
                        )
                    )
                elif isinstance(part, str):
                    part_owners[part] = str(assembly_id)
        return diagnostics

    def _unit_vector(
        self,
        value: JsonValue,
        path: str,
        subject_id: str,
        dimensions: int,
    ) -> list[Diagnostic]:
        coordinates = vector2(value, path) if dimensions == 2 else vector3(value, path)
        magnitude = math.sqrt(
            sum(coordinate * coordinate for coordinate in coordinates)
        )
        if not math.isclose(magnitude, 1.0, abs_tol=1e-6):
            return [
                self._error(
                    "geometry.non-unit-vector",
                    f"Direction vector must have unit length; found {magnitude:g}",
                    subject_id,
                    path,
                )
            ]
        return []

    @staticmethod
    def _error(code: str, message: str, subject_id: str, path: str = "") -> Diagnostic:
        return Diagnostic("error", code, message, path, subject_id)
