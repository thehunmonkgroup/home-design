"""Explicit labels and source units for human-facing component measurements."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from home_design.json_types import JsonObject, JsonPointer, JsonValue


@dataclass(frozen=True)
class PropertyField:
    """One declared resolved field and its presentation meaning."""

    path: str
    label: str
    unit: str | None = None
    group: str = "Dimensions"

    def read(self, data: JsonObject) -> JsonObject | None:
        """Keep measurements dimensioned and omit unavailable or invalid values."""
        try:
            value = JsonPointer.get(data, self.path)
        except (KeyError, IndexError, TypeError, ValueError):
            return None
        if self.unit is not None:
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                return None
        elif not isinstance(value, str):
            return None
        return {
            "id": self.path,
            "label": self.label,
            "value": value,
            "unit": self.unit,
            "group": self.group,
        }


class ViewProperties:
    """Declare supported review measurements without guessing units from arbitrary metadata."""

    LENGTHS: dict[str, str] = {
        "length": "Length",
        "lengthMm": "Length",
        "memberLength": "Member length",
        "stockLengthMm": "Stock length",
        "centerlineLengthMm": "Route length",
        "width": "Width",
        "height": "Height",
        "depth": "Depth",
        "thickness": "Thickness",
        "nominalWidth": "Nominal width",
        "nominalHeight": "Nominal height",
        "clearOpeningWidth": "Clear opening width",
        "clearOpeningHeight": "Clear opening height",
        "clearWidth": "Clear width",
        "riserHeight": "Riser height",
        "treadDepth": "Tread depth",
        "totalRise": "Total rise",
        "totalRun": "Total run",
        "topElevation": "Top elevation",
        "bottomElevation": "Bottom elevation",
        "baseElevation": "Base elevation",
        "spacing": "Spacing",
        "projection": "Mounting offset",
        "wallThickness": "Wall thickness",
        "bendRadius": "Bend radius",
        "clearance": "Clearance",
        "run": "Run",
        "rise": "Rise",
        "section/width": "Stock width",
        "section/depth": "Stock depth",
        "section/diameter": "Stock diameter",
    }
    AREAS: dict[str, str] = {
        "area": "Area",
        "netArea": "Net area",
        "grossArea": "Gross area",
        "glazedArea": "Glazed area",
        "sectionAreaMm2": "Section area",
    }
    VOLUMES: dict[str, str] = {
        "volume": "Volume",
        "volumeMm3": "Volume",
        "netVolumeMm3": "Net material volume",
        "grossVolumeMm3": "Gross volume",
        "cutVolumeMm3": "Cut volume",
    }
    COUNTS: dict[str, str] = {
        "memberCount": "Members",
        "portCount": "Service ports",
        "count": "Quantity",
        "riserCount": "Risers",
        "treadCount": "Treads",
    }
    TEXT: dict[str, str] = {
        "constructionRole": "Member purpose",
        "role": "Purpose",
        "form": "Form",
        "operation": "Operation",
        "handing": "Hinge side",
        "swingDirection": "Swing direction",
        "purpose": "Purpose",
        "status": "Status",
        "systemType": "System",
        "family": "Service family",
    }

    @classmethod
    def fields(cls) -> tuple[PropertyField, ...]:
        """Return the declared contract shared by every component family."""
        fields: list[PropertyField] = []
        for unit, mapping in (
            ("mm", cls.LENGTHS),
            ("mm2", cls.AREAS),
            ("mm3", cls.VOLUMES),
            ("count", cls.COUNTS),
        ):
            fields.extend(
                PropertyField("/" + key, label, unit) for key, label in mapping.items()
            )
        fields.extend(
            PropertyField("/" + key, label, "deg")
            for key, label in {
                "pitch": "Roof pitch",
                "roll": "Member rotation",
                "swingAngle": "Door swing angle",
            }.items()
        )
        fields.extend(
            PropertyField("/" + key, label, "N", "Loads")
            for key, label in {
                "forceN": "Force",
                "capacityN": "Authored capacity",
            }.items()
        )
        fields.extend(
            PropertyField("/" + key, label, None, "Construction")
            for key, label in cls.TEXT.items()
        )
        return tuple(fields)

    @classmethod
    def describe(cls, data: JsonObject) -> list[JsonValue]:
        """Publish finite scalar measurements and selected plain-language construction properties."""
        result: list[JsonValue] = []
        for field in cls.fields():
            if field.path == "/role" and isinstance(data.get("constructionRole"), str):
                continue
            entry = field.read(data)
            if entry is not None:
                if field.unit is None:
                    entry["value"] = cls.label(str(entry["value"]))
                result.append(entry)
        return result

    @staticmethod
    def label(value: str) -> str:
        """Present controlled construction enums as readable phrases."""
        return re.sub(r"([a-z])([A-Z])", r"\1 \2", value).replace("_", " ").capitalize()
