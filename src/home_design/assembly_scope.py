"""Explicit assembly ownership and dependency scope for safe package duplication."""

from __future__ import annotations

from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject


class AssemblyScope:
    """Collect nested assembly parts, their owned cuts, and private supporting definitions."""

    def __init__(self, source: JsonObject) -> None:
        """Index the source's typed references and explicit grouping relationships."""
        self.index: ModelIndex = ModelIndex(source)

    def collect(
        self, instance: str, recorded: JsonObject | None = None
    ) -> dict[str, set[str]]:
        """Preserve shared definitions and external assemblies while collecting owned construction."""
        selected = {registry: set[str]() for registry in self.index.registries}
        root = self.index.registries["elements"].get(instance)
        if root is None or root.get("kind") != "assembly":
            raise HomeDesignError(
                "Select a canonical assembly to duplicate",
                code="assembly.unavailable",
                subject_id=instance,
            )
        excluded: set[str] = set()
        if recorded is not None:
            self._recorded(selected, recorded, excluded)
        selected["elements"].add(instance)
        previous: set[str] = set()
        while previous != selected["elements"]:
            previous = set(selected["elements"])
            self._parts(selected)
            for identity in sorted(selected["elements"]):
                record = self.index.registries["elements"][identity].get(
                    "recipeInstance"
                )
                if isinstance(record, dict):
                    self._recorded(selected, record, excluded)
        self._relationships(selected)
        self._private_definitions(selected, excluded)
        return selected

    def _recorded(
        self, selected: dict[str, set[str]], record: JsonObject, excluded: set[str]
    ) -> None:
        """Include otherwise unreferenced recipe-owned objects and preserve explicitly shared stock."""
        shared = {
            Authoring.text(value)
            for value in Authoring.object(record["sharedTypes"]).values()
        }
        excluded.update(shared)
        for registry, value in Authoring.object(record["objectIds"]).items():
            selected[registry].update(
                Authoring.text(identity)
                for identity in Authoring.object(value).values()
                if identity in self.index.registries[registry]
                and identity not in shared
            )

    def _parts(self, selected: dict[str, set[str]]) -> None:
        """Follow explicit nested membership and cuts/access spaces owned by included elements."""
        previous = -1
        while previous != len(selected["elements"]):
            previous = len(selected["elements"])
            for identity, relationship in self.index.registries[
                "relationships"
            ].items():
                if (
                    relationship.get("kind") == "aggregates"
                    and relationship.get("assembly") in selected["elements"]
                ):
                    selected["relationships"].add(identity)
                    selected["elements"].update(
                        Authoring.text(value)
                        for value in Authoring.array(relationship["parts"])
                    )
            for identity, element in self.index.registries["elements"].items():
                if (
                    element.get("kind") in {"penetration", "clearanceZone"}
                    and element.get("owner") in selected["elements"]
                ):
                    selected["elements"].add(identity)

    def _relationships(self, selected: dict[str, set[str]]) -> None:
        """Retain connection intent without copying an external parent assembly's membership."""
        for identity, relationship in self.index.registries["relationships"].items():
            references = self.index.outgoing.get(identity, [])
            if (
                relationship.get("kind") == "aggregates"
                and relationship.get("assembly") not in selected["elements"]
            ):
                continue
            if any(
                reference.target_id in selected["elements"] for reference in references
            ):
                selected["relationships"].add(identity)

    def _private_definitions(
        self, selected: dict[str, set[str]], excluded: set[str]
    ) -> None:
        """Copy private anchors and stock while retaining definitions used outside this package."""
        changed = True
        while changed:
            changed = False
            owned = {identity for values in selected.values() for identity in values}
            for reference in self.index.references:
                if (
                    reference.owner_id not in owned
                    or reference.registry not in {"anchors", "types", "materials"}
                    or reference.target_id in owned
                    or reference.target_id in excluded
                ):
                    continue
                users = self.index.incoming.get(reference.target_id, [])
                if users and all(user.owner_id in owned for user in users):
                    selected[reference.registry].add(reference.target_id)
                    changed = True
