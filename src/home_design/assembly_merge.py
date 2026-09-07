"""Three-way recipe updates that retain authored occurrence edits and expose conflicts."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum

from home_design.errors import ChangeConflictError
from home_design.json_types import JsonObject, JsonValue


class MissingValue(Enum):
    """Distinguish an absent field from an explicitly authored JSON null."""

    MISSING = "missing"


class AssemblyMerge:
    """Merge newly rendered recipe fields with edits to its previous expanded instance."""

    def __init__(self) -> None:
        """Collect all conflicting field paths in one repairable report."""
        self.conflicts: list[JsonValue] = []

    def merge(
        self, baseline: JsonObject, current: JsonObject, proposed: JsonObject
    ) -> JsonObject:
        """Retain independent edits; reject overlapping changes and reordered arrays.

        :param baseline: Previous recipe output reconstructed from its recorded inputs.
        :param current: Current authored instance objects.
        :param proposed: Newly rendered recipe output.
        :returns: Merged objects, without modifying any input.
        """
        self.conflicts = []
        result = self._value(baseline, current, proposed, "")
        if self.conflicts:
            raise ChangeConflictError(
                "Recipe update overlaps local edits; inspect the conflicting fields and choose the intended values before retrying",
                code="recipe.update-conflict",
                details={"paths": self.conflicts},
            )
        if not isinstance(result, dict):
            raise ChangeConflictError(
                "Recipe update cannot replace its registry document",
                code="recipe.update-root",
            )
        return result

    def _value(
        self,
        baseline: JsonValue | MissingValue,
        current: JsonValue | MissingValue,
        proposed: JsonValue | MissingValue,
        path: str,
    ) -> JsonValue | MissingValue:
        """Recursively merge dictionary fields while treating ordered arrays as authored units."""
        if self.equal(current, baseline):
            return deepcopy(proposed)
        if self.equal(proposed, baseline) or self.equal(current, proposed):
            return deepcopy(current)
        if (
            isinstance(baseline, dict)
            and isinstance(current, dict)
            and isinstance(proposed, dict)
        ):
            result: JsonObject = {}
            for key in sorted(set(baseline) | set(current) | set(proposed)):
                escaped = key.replace("~", "~0").replace("/", "~1")
                value = self._value(
                    baseline.get(key, MissingValue.MISSING),
                    current.get(key, MissingValue.MISSING),
                    proposed.get(key, MissingValue.MISSING),
                    f"{path}/{escaped}",
                )
                if not isinstance(value, MissingValue):
                    result[key] = value
            return result
        self.conflicts.append(path)
        return deepcopy(current)

    @classmethod
    def equal(
        cls, first: JsonValue | MissingValue, second: JsonValue | MissingValue
    ) -> bool:
        """Compare JSON intent without treating boolean true as numeric one."""
        if isinstance(first, dict) and isinstance(second, dict):
            return first.keys() == second.keys() and all(
                cls.equal(value, second[key]) for key, value in first.items()
            )
        if isinstance(first, list) and isinstance(second, list):
            return len(first) == len(second) and all(
                cls.equal(a, b) for a, b in zip(first, second)
            )
        if isinstance(first, bool) != isinstance(second, bool):
            return False
        return first == second
