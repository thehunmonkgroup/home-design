"""Deterministic model input expansion and batch validation."""

from __future__ import annotations

import glob
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.validation import ModelValidator

LOGGER = logging.getLogger(__name__)


class ModelBatch:
    """Expand CLI inputs and report every model's validation outcome."""

    @staticmethod
    def expand(inputs: Sequence[str]) -> list[Path]:
        """Expand patterns in argument order, sorting each pattern's matches.

        :param inputs: Literal paths or glob patterns, including recursive ``**``.
        :returns: Paths deduplicated by resolved location.
        :raises ValueError: If an input has no file matches.
        """
        paths: dict[Path, Path] = {}
        for value in inputs:
            literal = Path(value).expanduser()
            matches = (
                [str(literal)]
                if literal.is_file()
                else sorted(glob.glob(str(literal), recursive=True))
            )
            if not matches:
                raise ValueError(f"No model files match: {value}")
            for match in matches:
                path = Path(match)
                if not path.is_file():
                    raise ValueError(f"Model input is not a file: {path}")
                paths.setdefault(path.resolve(), path)
        if not paths:
            raise ValueError("At least one model file is required")
        return list(paths.values())

    @staticmethod
    def validate(
        paths: Sequence[Path], loader: ModelLoader, validator: ModelValidator
    ) -> JsonObject:
        """Collect diagnostics, including load failures, without stopping early."""
        results: list[JsonValue] = []
        valid = True
        for path in paths:
            LOGGER.debug("Validating %s", path)
            report: JsonObject
            try:
                report = cast(
                    JsonObject, validator.validate(loader.load(path)).to_dict()
                )
            except (HomeDesignError, OSError, ValueError, KeyError) as error:
                report = {
                    "valid": False,
                    "counts": {"error": 1, "warning": 0, "info": 0},
                    "diagnostics": [
                        {
                            "severity": "error",
                            "code": "model.load",
                            "message": str(error),
                        }
                    ],
                }
            valid = valid and report["valid"] is True
            results.append({"source": str(path), **report})
        return {"valid": valid, "models": results}

    @staticmethod
    def format_text(report: JsonObject) -> str:
        """Render batch diagnostics with a source heading for each model."""
        lines: list[str] = []
        models = report["models"]
        if not isinstance(models, list):
            raise ValueError("Expected model validation results")
        for model in models:
            if not isinstance(model, dict):
                raise ValueError("Expected a model validation result")
            status = "Valid" if model["valid"] else "Invalid"
            lines.append(f"{model['source']}: {status}")
            diagnostics = model["diagnostics"]
            if isinstance(diagnostics, list):
                for item in diagnostics:
                    if isinstance(item, dict):
                        lines.append(
                            f"  {str(item['severity']).upper()} {item['code']} "
                            + f"{item.get('path', '')}: {item['message']}"
                        )
        return "\n".join(lines)
