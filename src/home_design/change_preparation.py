"""Prepare ordinary guarded changesets for coordinated authoring operations."""

from __future__ import annotations

from copy import deepcopy

from jsonschema import Draft202012Validator

from home_design.errors import ChangeConflictError, HomeDesignError
from home_design.inspection import ModelInspection
from home_design.json_types import JsonObject, JsonPointer, JsonValue
from home_design.loader import ModelLoader


class ChangePreparation:
    """Generate explicit operations and preconditions without modifying a model."""

    def __init__(self, source: JsonObject, loader: ModelLoader | None = None) -> None:
        """Keep the inspected source snapshot and its typed reference index."""
        self.source: JsonObject = source
        self.inspection: ModelInspection = ModelInspection(source)
        self.loader: ModelLoader = loader or ModelLoader()

    def local_type(
        self, identity: str, new_type: str, fields: tuple[tuple[str, JsonValue], ...]
    ) -> JsonObject:
        """Copy a shared type, edit its parameters and assign only one occurrence."""
        registry, occurrence = self.inspection.locate(identity, "elements")
        identity_schema = JsonPointer.get(self.loader.schema, "/$defs/Id")
        if not isinstance(identity_schema, dict):
            raise HomeDesignError(
                "The authoring schema has no object identity definition"
            )
        if not Draft202012Validator(identity_schema).is_valid(new_type):
            raise HomeDesignError(
                "New type ID must use the canonical ID format",
                code="change.invalid-identity",
            )
        type_id = occurrence.get("type")
        if not isinstance(type_id, str):
            raise HomeDesignError(f"Element {identity} has no reusable type")
        _, definition = self.inspection.locate(type_id, "types")
        if any(
            new_type in objects for objects in self.inspection.index.registries.values()
        ):
            raise ChangeConflictError(
                f"New type ID {new_type} already exists",
                code="change.identity-conflict",
            )
        updated = deepcopy(definition)
        for pointer, value in fields:
            if pointer in {"", "/kind"}:
                raise HomeDesignError(
                    "Local type edits must preserve the component kind"
                )
            try:
                JsonPointer.set(updated, pointer, value)
            except (KeyError, IndexError, ValueError, TypeError) as error:
                raise HomeDesignError(
                    f"Cannot edit type field {pointer}: {error}", path=pointer
                ) from error
        return self._change(
            "local-type",
            identity,
            f"Give {identity} its own reusable type {new_type}; preserve other type users.",
            [
                {"path": f"/types/{new_type}", "exists": False},
                self._condition("types", type_id),
                self._condition(registry, identity),
            ],
            [
                self._put("types", new_type, updated),
                {"op": "set", "path": f"/elements/{identity}/type", "value": new_type},
            ],
        )

    def remove(self, identity: str, included: tuple[str, ...] = ()) -> JsonObject:
        """Remove an explicitly selected set only after exposing external references."""
        selected = {identity, *included}
        objects = {item: self.inspection.locate(item) for item in selected}
        incoming = [
            reference
            for item in sorted(selected)
            for reference in self.inspection.index.incoming.get(item, [])
            if reference.owner_id not in selected
        ]
        if incoming:
            raise ChangeConflictError(
                "Removal has incoming references outside the selected set; revise those fields or explicitly include their owning objects.",
                code="change.removal-references",
                subject_id=identity,
                details={"incoming": [reference.to_dict() for reference in incoming]},
            )
        return self._change(
            "remove",
            identity,
            f"Remove the explicitly selected objects: {', '.join(sorted(selected))}.",
            [self._condition(objects[item][0], item) for item in sorted(selected)],
            [
                {"op": "removeObject", "registry": objects[item][0], "objectId": item}
                for item in sorted(selected)
            ],
        )

    def rehost(
        self,
        identity: str,
        new_host: str,
        old_host: str | None = None,
        included: tuple[str, ...] = (),
    ) -> JsonObject:
        """Rebind selected host references and owned cuts while retaining local coordinates."""
        self.inspection.locate(new_host, "elements")
        _, source = self.inspection.locate(identity, "elements")
        previous = old_host or self._mount_host(identity, source)
        self.inspection.locate(previous, "elements")
        if previous == new_host:
            raise HomeDesignError("The new host must differ from the current host")
        selected = {identity, *included}
        elements = self.inspection.index.registries["elements"]
        selected.update(
            key
            for key, value in elements.items()
            if value.get("kind") == "penetration"
            and isinstance(value.get("owner"), str)
            and value.get("owner") in selected
        )
        for item in tuple(selected):
            for reference in self.inspection.index.incoming.get(item, []):
                relationship = self.inspection.index.registries["relationships"].get(
                    reference.owner_id
                )
                if relationship is not None and relationship.get("kind") in {
                    "voids",
                    "attaches",
                    "supports",
                }:
                    selected.add(reference.owner_id)
        result = deepcopy(self.source)
        changed: set[str] = set()
        for item in sorted(selected):
            self.inspection.locate(item)
            for reference in self.inspection.index.outgoing.get(item, []):
                if reference.target_id == previous and reference.registry == "elements":
                    JsonPointer.set(result, reference.path, new_host)
                    changed.add(item)
        if not changed:
            raise HomeDesignError(f"Selected objects do not reference host {previous}")
        inspection = ModelInspection(result)
        operations: list[JsonValue] = []
        preconditions: list[JsonValue] = [
            self._condition("elements", previous),
            self._condition("elements", new_host),
        ]
        for item in sorted(changed):
            registry, value = inspection.locate(item)
            preconditions.append(self._condition(registry, item))
            operations.append(self._put(registry, item, value))
        return self._change(
            "rehost",
            identity,
            f"Rehost {identity} and selected integrations from {previous} to {new_host}, retaining authored local coordinates and stock dimensions.",
            preconditions,
            operations,
        )

    def _mount_host(self, identity: str, source: JsonObject) -> str:
        if source.get("kind") == "opening":
            host = self.inspection.index.host_for_opening(identity)
            if host is not None:
                return host
        candidates = {
            reference.target_id
            for reference in self.inspection.index.outgoing.get(identity, [])
            if reference.role == "placement"
            and reference.registry == "elements"
            and (
                reference.path == f"/elements/{identity}/host"
                or "/host/element" in reference.path
            )
        }
        if len(candidates) != 1:
            raise HomeDesignError(
                "Select --from-host ID when the component has no single host locator"
            )
        return candidates.pop()

    def _condition(self, registry: str, identity: str) -> JsonObject:
        return {
            "path": f"/{registry}/{identity}",
            "equals": deepcopy(self.inspection.index.registries[registry][identity]),
        }

    @staticmethod
    def _put(registry: str, identity: str, value: JsonObject) -> JsonObject:
        return {
            "op": "putObject",
            "registry": registry,
            "objectId": identity,
            "value": value,
        }

    def _change(
        self,
        action: str,
        identity: str,
        description: str,
        preconditions: list[JsonValue],
        operations: list[JsonValue],
    ) -> JsonObject:
        return {
            "changeVersion": "0.1",
            "id": f"change.{action}.{identity}",
            "description": description,
            "baseRevision": self.source.get("revision"),
            "preconditions": preconditions,
            "operations": operations,
        }
