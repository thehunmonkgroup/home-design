"""Duplicate canonical assemblies with explicit scope and safely remapped identities."""

from __future__ import annotations

from copy import deepcopy

from jsonschema import Draft202012Validator

from home_design.assembly_instantiation import AssemblyInstantiation
from home_design.assembly_scope import AssemblyScope
from home_design.assembly_updates import AssemblyUpdates
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import (
    ChangeConflictError,
    HomeDesignError,
    ModelValidationError,
)
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonPointer, JsonValue
from home_design.loader import ModelLoader
from home_design.recipes import AssemblyRecipe
from home_design.reference_remapping import ReferenceRemapping
from home_design.validation import ModelValidator


class AssemblyDuplication:
    """Clone owned construction, preserving shared stock and external connection intent."""

    def __init__(self, source: JsonObject, loader: ModelLoader | None = None) -> None:
        """Keep source snapshots untouched until an ordinary transaction applies the result."""
        self.source: JsonObject = source
        self.loader: ModelLoader = loader or ModelLoader()

    def prepare(
        self,
        instance: str,
        new_instance: str,
        recipe: AssemblyRecipe | None = None,
        parameters: JsonObject | None = None,
        bindings: JsonObject | None = None,
        overrides: JsonObject | None = None,
    ) -> JsonObject:
        """Expand optional recipe adaptations on a copy, then duplicate its complete owned scope."""
        report = ModelValidator(self.loader).validate(
            self.source, include_geometry=False
        )
        if not report.is_valid:
            raise ModelValidationError(
                "Assembly duplication requires a valid authoring source", report
            )
        if not Draft202012Validator(
            Authoring.object(JsonPointer.get(self.loader.schema, "/$defs/Id"))
        ).is_valid(new_instance):
            raise HomeDesignError(
                "New assembly instance must use a canonical ID",
                code="recipe.instance-id",
            )
        candidate = deepcopy(self.source)
        if parameters or bindings or overrides:
            if recipe is None:
                raise HomeDesignError(
                    "Parameterized duplication requires the recorded recipe",
                    code="recipe.required",
                )
            try:
                adaptation = AssemblyUpdates(candidate, recipe, self.loader).prepare(
                    instance, parameters, bindings, overrides
                )
            except HomeDesignError as error:
                if error.code != "recipe.unchanged":
                    raise
            else:
                candidate = ChangeEngine(self.loader).candidate(candidate, adaptation)
        scope = AssemblyScope(candidate)
        root = scope.index.registries["elements"].get(instance)
        raw_record = root.get("recipeInstance") if root is not None else None
        record = Authoring.object(raw_record) if isinstance(raw_record, dict) else None
        selected = scope.collect(instance, record)
        originals = {identity for values in selected.values() for identity in values}
        local_names: dict[str, str] = {}
        if record is not None:
            for mapping in Authoring.object(record["objectIds"]).values():
                local_names.update(
                    {
                        Authoring.text(actual): local
                        for local, actual in Authoring.object(mapping).items()
                        if actual in originals
                    }
                )
        identities: dict[str, str] = {}
        occupied = {
            identity
            for registry in ModelIndex(self.source).registries.values()
            for identity in registry
        }
        for identity in sorted(originals):
            local = local_names.get(identity, identity.removeprefix(instance + "."))
            replacement = (
                new_instance
                if identity == instance
                else AssemblyInstantiation.object_id(new_instance, local)
            )
            if replacement in occupied or replacement in identities.values():
                raise ChangeConflictError(
                    f"Duplicate assembly object ID {replacement} already exists or is ambiguous",
                    code="recipe.identity-conflict",
                    subject_id=replacement,
                )
            identities[identity] = replacement
        objects: JsonObject = {
            registry: {
                identity: deepcopy(scope.index.registries[registry][identity])
                for identity in sorted(values)
            }
            for registry, values in selected.items()
        }
        AssemblyInstantiation.remap_scoped_parts(objects, identities)
        rebound = ReferenceRemapping.apply(objects, identities)
        ReferenceRemapping.records(rebound, identities)
        renamed: JsonObject = {
            registry: {
                identities[identity]: value
                for identity, value in Authoring.object(values).items()
            }
            for registry, values in rebound.items()
        }
        return self._changeset(instance, new_instance, renamed, selected, identities)

    def _changeset(
        self,
        instance: str,
        new_instance: str,
        objects: JsonObject,
        selected: dict[str, set[str]],
        identities: dict[str, str],
    ) -> JsonObject:
        """Guard the copied source, absent target IDs and every retained external reference."""
        source_index = ModelIndex(self.source)
        conditions: list[JsonValue] = []
        operations: list[JsonValue] = []
        for registry, values in selected.items():
            conditions.extend(
                {
                    "path": f"/{registry}/{identity}",
                    "equals": source_index.registries[registry][identity],
                }
                for identity in sorted(values)
                if identity in source_index.registries[registry]
            )
        for registry, values in objects.items():
            for identity, value in Authoring.object(values).items():
                conditions.append({"path": f"/{registry}/{identity}", "exists": False})
                operations.append(
                    {
                        "op": "putObject",
                        "registry": registry,
                        "objectId": identity,
                        "value": value,
                    }
                )
        self._requirements(new_instance, identities, conditions, operations)
        external = {
            (reference.registry, reference.target_id)
            for reference in ModelIndex(objects).references
            if reference.target_id in source_index.registries[reference.registry]
        }
        conditions.extend(
            {
                "path": f"/{registry}/{identity}",
                "equals": source_index.registries[registry][identity],
            }
            for registry, identity in sorted(external)
        )
        change: JsonObject = {
            "changeVersion": "0.1",
            "id": AssemblyInstantiation.object_id("change.duplicate", new_instance),
            "description": f"Duplicate {instance} as {new_instance}, preserving external bindings and private/shared definitions",
            "baseRevision": self.source["revision"],
            "preconditions": conditions,
            "operations": operations,
        }
        candidate = ChangeEngine(self.loader).candidate(self.source, change)
        report = ModelValidator(self.loader).validate(candidate, include_geometry=False)
        if not report.is_valid:
            raise ModelValidationError(
                "Assembly duplication does not satisfy the authoring contract", report
            )
        return change

    def _requirements(
        self,
        instance: str,
        identities: dict[str, str],
        conditions: list[JsonValue],
        operations: list[JsonValue],
    ) -> None:
        """Copy applicable project requirements while preserving original requests and external targets."""
        requirements = Authoring.array(self.source.get("requirements", []))
        selected = [
            Authoring.object(value)
            for value in requirements
            if any(
                target in identities
                for target in Authoring.array(
                    Authoring.object(value).get("appliesTo", [])
                )
            )
        ]
        if not selected:
            return
        conditions.append({"path": "/requirements", "equals": deepcopy(requirements)})
        occupied = {
            Authoring.text(Authoring.object(value)["id"]) for value in requirements
        }
        occupied.update(
            identity
            for values in ModelIndex(self.source).registries.values()
            for identity in values
        )
        for source in selected:
            requirement = deepcopy(source)
            identity = AssemblyInstantiation.object_id(
                instance, Authoring.text(source["id"])
            )
            if identity in occupied or identity in identities.values():
                raise ChangeConflictError(
                    f"Duplicated requirement {identity} already exists",
                    code="recipe.identity-conflict",
                    subject_id=identity,
                )
            occupied.add(identity)
            requirement["id"] = identity
            requirement["appliesTo"] = [
                identities.get(Authoring.text(target), Authoring.text(target))
                for target in Authoring.array(source["appliesTo"])
            ]
            operations.append(
                {"op": "set", "path": "/requirements/-", "value": requirement}
            )
