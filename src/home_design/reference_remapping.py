"""Typed canonical reference remapping for reusable assembly operations."""

from __future__ import annotations

from copy import deepcopy

from home_design.construction import Authoring
from home_design.errors import ChangeConflictError
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonPointer


class ReferenceRemapping:
    """Rebind declared reference slots without rewriting labels or arbitrary metadata."""

    @staticmethod
    def records(objects: JsonObject, identities: dict[str, str]) -> None:
        """Rebind instance provenance, including nested recipes, without changing local names."""
        for value in Authoring.object(objects.get("elements", {})).values():
            record = Authoring.object(value).get("recipeInstance")
            if not isinstance(record, dict):
                continue
            mappings = [
                Authoring.object(record[field]) for field in ("bindings", "sharedTypes")
            ]
            mappings.extend(
                Authoring.object(value)
                for value in Authoring.object(record["objectIds"]).values()
            )
            for mapping in mappings:
                for name, target in mapping.items():
                    mapping[name] = identities.get(
                        Authoring.text(target), Authoring.text(target)
                    )
            for raw in Authoring.object(record.get("connectionPoints", {})).values():
                point = Authoring.object(raw)
                target = Authoring.text(point["element"])
                point["element"] = identities.get(target, target)

    @staticmethod
    def apply(
        source: JsonObject, identities: dict[str, str], owners: set[str] | None = None
    ) -> JsonObject:
        """Return a copy with reference values and reference dictionary keys rebound.

        :param source: Source registries; object IDs remain unchanged by this operation.
        :param identities: Existing target IDs mapped to their replacement IDs.
        :param owners: Optional set of objects whose references may change.
        :returns: A separate document with only declared reference slots updated.
        """
        result = deepcopy(source)
        references = [
            reference
            for reference in ModelIndex(source).references
            if reference.target_id in identities
            and (owners is None or reference.owner_id in owners)
        ]
        for reference in references:
            if reference.storage == "value":
                JsonPointer.set(result, reference.path, identities[reference.target_id])
        for reference in sorted(
            references, key=lambda item: len(item.path), reverse=True
        ):
            if reference.storage != "key":
                continue
            parent_path, _, _ = reference.path.rpartition("/")
            parent = Authoring.object(JsonPointer.get(result, parent_path))
            replacement = identities[reference.target_id]
            if replacement == reference.target_id:
                continue
            if replacement in parent:
                raise ChangeConflictError(
                    f"Reference key {replacement} already exists at {parent_path}",
                    code="change.reference-key-conflict",
                    path=reference.path,
                )
            parent[replacement] = parent.pop(reference.target_id)
            JsonPointer.set(result, parent_path, parent)
        return result
