"""Keep saved authoring documents complete while returning compact CLI receipts."""

from __future__ import annotations

import json
from pathlib import Path

from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader


class CommandOutput:
    """Separate machine-readable document output from saved-document summaries."""

    @staticmethod
    def change(change: JsonObject, destination: Path | None) -> None:
        """Print the changeset, or save it and print bounded preparation evidence."""
        result = change
        if destination is not None:
            ModelLoader.write(change, destination)
            result = {
                "change": str(destination),
                "id": change["id"],
                "baseRevision": change["baseRevision"],
                "operationCount": len(Authoring.array(change["operations"])),
                "preconditionCount": len(
                    Authoring.array(change.get("preconditions", []))
                ),
                "sourceWritten": False,
            }
        print(json.dumps(result, indent=2))

    @staticmethod
    def preview(report: JsonObject, destination: Path | None) -> None:
        """Retain complete saved pages and summarize their counts on stdout."""
        result = report
        if destination is not None:
            ModelLoader.write(report, destination)
            result = {
                key: (
                    {field: item for field, item in value.items() if field != "items"}
                    if isinstance(value, dict) and "items" in value
                    else value
                )
                for key, value in report.items()
            }
            result["report"] = str(destination)
            result["summary"] = True
        print(json.dumps(result, indent=2))
