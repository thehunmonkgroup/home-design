"""Survey ingestion producing reviewable canonical terrain transactions."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.terrain import TerrainSurface
from home_design.units import LengthConverter


class SurveyImporter:
    """Read x/y/z survey CSV files without modifying existing designs."""

    @staticmethod
    def change(
        model: JsonObject,
        source: Path,
        element_id: str,
        state: str,
        units: str,
        origin: tuple[float, float, float],
        name: str | None = None,
    ) -> JsonObject:
        """Convert source-unit coordinates to local millimetres and prepare a change."""
        scale = float(LengthConverter.parse_millimetres(f"1 {units}"))
        points: list[JsonValue] = []
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not {"x", "y", "z"}.issubset(
                reader.fieldnames
            ):
                raise HomeDesignError("Survey CSV requires x,y,z column headers")
            for line, row in enumerate(reader, start=2):
                try:
                    coordinates = [float(row[axis]) for axis in ("x", "y", "z")]
                except (TypeError, ValueError) as error:
                    raise HomeDesignError(
                        f"Invalid survey coordinate on row {line}"
                    ) from error
                if not all(math.isfinite(value) for value in coordinates):
                    raise HomeDesignError(f"Non-finite survey coordinate on row {line}")
                points.append(
                    [(coordinates[index] - origin[index]) * scale for index in range(3)]
                )
        terrain: JsonObject = {
            "kind": "terrain",
            "name": name or f"{state.title()} survey",
            "state": state,
            "points": points,
            "specifications": {
                "sourceFile": source.name,
                "sourceUnits": units,
                "sourceOrigin": ", ".join(str(value) for value in origin),
            },
        }
        surface = TerrainSurface.from_element(terrain)
        terrain["triangles"] = [list(face) for face in surface.faces]
        elements = Authoring.object(model.get("elements"))
        previous = elements.get(element_id)
        if isinstance(previous, dict) and previous.get("kind") != "terrain":
            raise HomeDesignError(
                f"Survey import would replace a non-terrain element: {element_id}"
            )
        preconditions: list[JsonValue] = []
        if previous is not None:
            preconditions.append(
                {"path": f"/elements/{element_id}", "equals": previous}
            )
        return {
            "changeVersion": "0.1",
            "id": f"change.import.{element_id}",
            "description": f"Import {state} survey from {source.name}",
            "baseRevision": int(number(model.get("revision"), "model revision")),
            "preconditions": preconditions,
            "operations": [
                {
                    "op": "putObject",
                    "registry": "elements",
                    "objectId": element_id,
                    "value": terrain,
                }
            ],
        }
