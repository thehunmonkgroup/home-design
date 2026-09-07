"""Adapt recorded assembly instances through reproducible three-way changesets."""

from __future__ import annotations

from copy import deepcopy

from home_design.assembly_instantiation import AssemblyInstantiation
from home_design.assembly_merge import AssemblyMerge
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import (
    ChangeConflictError,
    HomeDesignError,
    ModelValidationError,
)
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.recipes import AssemblyRecipe
from home_design.reference_remapping import ReferenceRemapping
from home_design.validation import ModelValidator


class AssemblyUpdates:
    """Preserve occurrence edits while changing a recipe's inputs or explicit version."""

    def __init__(
        self,
        source: JsonObject,
        recipe: AssemblyRecipe,
        loader: ModelLoader | None = None,
    ) -> None:
        """Use the supplied current recipe and canonical source snapshot."""
        self.source: JsonObject = source
        self.recipe: AssemblyRecipe = recipe
        self.loader: ModelLoader = loader or ModelLoader()
        self.index: ModelIndex = ModelIndex(source)

    def provenance(self, instance: str) -> JsonObject:
        """Require compact recipe provenance on the selected canonical assembly."""
        element = self.index.registries["elements"].get(instance)
        record = element.get("recipeInstance") if element is not None else None
        if (
            element is None
            or element.get("kind") != "assembly"
            or not isinstance(record, dict)
        ):
            raise HomeDesignError(
                "Select an assembly with recorded recipe provenance",
                code="recipe.instance-unavailable",
                subject_id=instance,
            )
        return deepcopy(record)

    @staticmethod
    def _retained_ids(
        objects: JsonObject, previous: JsonObject, instance: str
    ) -> JsonObject:
        """Retain recorded local-to-canonical identities even after an assembly is duplicated."""
        rendered = deepcopy(objects)
        root = Authoring.object(Authoring.object(rendered["elements"])[instance])
        record = Authoring.object(root["recipeInstance"])
        old_maps = Authoring.object(previous["objectIds"])
        new_maps = Authoring.object(record["objectIds"])
        old_shared = Authoring.object(previous["sharedTypes"])
        new_shared = Authoring.object(record["sharedTypes"])
        identities: dict[str, str] = {}
        for registry, mapping_value in new_maps.items():
            mapping = Authoring.object(mapping_value)
            old = Authoring.object(old_maps.get(registry, {}))
            for local, actual in mapping.items():
                identity = Authoring.text(actual)
                retained = old.get(local, actual)
                if registry == "types" and (local in old_shared or local in new_shared):
                    retained = actual
                identities[identity] = Authoring.text(retained)
                mapping[local] = retained
        AssemblyInstantiation.remap_scoped_parts(rendered, identities)
        rebound = ReferenceRemapping.apply(rendered, identities)
        ReferenceRemapping.records(rebound, identities)
        return {
            registry: {
                identities.get(identity, identity): value
                for identity, value in Authoring.object(values).items()
            }
            for registry, values in rebound.items()
        }

    def _current(self, baseline: JsonObject) -> JsonObject:
        """Read current owned objects, preserving deliberate local deletions as absence."""
        return {
            registry: {
                identity: deepcopy(self.index.registries[registry][identity])
                for identity in Authoring.object(values)
                if identity in self.index.registries[registry]
            }
            for registry, values in baseline.items()
        }

    def prepare(
        self,
        instance: str,
        parameters: JsonObject | None = None,
        bindings: JsonObject | None = None,
        overrides: JsonObject | None = None,
        shared_types: JsonObject | None = None,
        previous_recipe: AssemblyRecipe | None = None,
        clear_overrides: tuple[str, ...] = (),
        local_types: tuple[str, ...] = (),
    ) -> JsonObject:
        """Reconstruct the prior output, merge independent edits and emit explicit operations."""
        record = self.provenance(instance)
        previous = previous_recipe or self.recipe
        if (
            record["recipeId"] != self.recipe.identity
            or record["recipeDigest"] != previous.digest
        ):
            raise HomeDesignError(
                "Recipe provenance does not match; supply the exact previous recipe when updating its version",
                code="recipe.digest-mismatch",
                subject_id=instance,
                details={
                    "recordedDigest": record["recipeDigest"],
                    "providedDigest": previous.digest,
                },
            )
        old_rendered, _ = AssemblyInstantiation(
            self.source, previous, self.loader
        ).render(
            instance,
            Authoring.object(record["parameters"]),
            Authoring.object(record["bindings"]),
            Authoring.object(record["overrides"]),
            Authoring.object(record["sharedTypes"]),
            check_external=False,
        )
        baseline = self._retained_ids(old_rendered, record, instance)
        Authoring.object(Authoring.object(baseline["elements"])[instance])[
            "recipeInstance"
        ] = deepcopy(record)
        next_parameters = {
            name: value
            for name, value in Authoring.object(record["parameters"]).items()
            if name in Authoring.object(self.recipe.source.get("parameters", {}))
        }
        next_parameters.update(parameters or {})
        next_bindings = {
            name: value
            for name, value in Authoring.object(record["bindings"]).items()
            if name in Authoring.object(self.recipe.source.get("bindings", {}))
        }
        next_bindings.update(bindings or {})
        next_overrides = deepcopy(Authoring.object(record["overrides"]))
        for path in clear_overrides:
            if path not in next_overrides:
                raise HomeDesignError(
                    f"No recorded override {path}",
                    code="recipe.override-unavailable",
                    path=path,
                )
            del next_overrides[path]
        next_overrides.update(overrides or {})
        next_shared = {
            name: value
            for name, value in Authoring.object(record["sharedTypes"]).items()
            if name in self.recipe.index.registries["types"]
        }
        next_shared.update(shared_types or {})
        for local in local_types:
            if local not in next_shared:
                raise HomeDesignError(
                    f"Type {local} is not recorded as shared",
                    code="recipe.shared-type",
                    subject_id=local,
                )
            del next_shared[local]
        proposed, _ = AssemblyInstantiation(
            self.source, self.recipe, self.loader
        ).render(instance, next_parameters, next_bindings, next_overrides, next_shared)
        proposed = self._retained_ids(proposed, record, instance)
        current = self._current(baseline)
        merged = AssemblyMerge().merge(baseline, current, proposed)
        self._retain_external_definitions(baseline, current, merged)
        return self._changeset(instance, baseline, current, merged)

    def _retain_external_definitions(
        self, baseline: JsonObject, current: JsonObject, merged: JsonObject
    ) -> None:
        """Keep retired stock or anchors that another occurrence now uses."""
        owned = {
            identity
            for values in baseline.values()
            for identity in Authoring.object(values)
        }
        retained = {
            reference.target_id
            for reference in self.index.references
            if reference.owner_id not in owned
        }
        pending = True
        while pending:
            pending = False
            for registry in ("anchors", "types", "materials"):
                for identity, value in Authoring.object(
                    current.get(registry, {})
                ).items():
                    target = Authoring.object(merged.setdefault(registry, {}))
                    if identity in retained and identity not in target:
                        target[identity] = deepcopy(value)
                        retained.update(
                            reference.target_id
                            for reference in self.index.outgoing.get(identity, [])
                        )
                        pending = True

    def _changeset(
        self,
        instance: str,
        baseline: JsonObject,
        current: JsonObject,
        merged: JsonObject,
    ) -> JsonObject:
        """Protect changed objects and external participants before ordinary candidate validation."""
        conditions: list[JsonValue] = []
        operations: list[JsonValue] = []
        for registry, values in merged.items():
            after = Authoring.object(values)
            before = Authoring.object(current.get(registry, {}))
            for identity in sorted(set(before) | set(after)):
                if (
                    identity in before
                    and identity in after
                    and AssemblyMerge.equal(before[identity], after[identity])
                ):
                    continue
                if identity not in before:
                    if any(
                        identity in objects
                        for objects in self.index.registries.values()
                    ):
                        raise ChangeConflictError(
                            f"New recipe object {identity} already exists outside its recorded instance",
                            code="recipe.identity-conflict",
                            subject_id=identity,
                        )
                    conditions.append(
                        {"path": f"/{registry}/{identity}", "exists": False}
                    )
                else:
                    conditions.append(
                        {"path": f"/{registry}/{identity}", "equals": before[identity]}
                    )
                if identity in after:
                    operations.append(
                        {
                            "op": "putObject",
                            "registry": registry,
                            "objectId": identity,
                            "value": after[identity],
                        }
                    )
                else:
                    operations.append(
                        {
                            "op": "removeObject",
                            "registry": registry,
                            "objectId": identity,
                        }
                    )
        if not operations:
            raise HomeDesignError(
                "Assembly already has the requested configuration",
                code="recipe.unchanged",
                subject_id=instance,
            )
        owned = {
            identity
            for values in baseline.values()
            for identity in Authoring.object(values)
        }
        external = {
            (reference.registry, reference.target_id)
            for reference in ModelIndex(merged).references
            if reference.target_id not in owned
            and reference.target_id in self.index.registries[reference.registry]
        }
        conditions.extend(
            {
                "path": f"/{registry}/{identity}",
                "equals": self.index.registries[registry][identity],
            }
            for registry, identity in sorted(external)
        )
        change: JsonObject = {
            "changeVersion": "0.1",
            "id": AssemblyInstantiation.object_id("change.adapt", instance),
            "description": f"Adapt {instance} using {self.recipe.identity}; preserve independent occurrence edits",
            "baseRevision": self.source["revision"],
            "preconditions": conditions,
            "operations": operations,
        }
        candidate = ChangeEngine(self.loader).candidate(self.source, change)
        report = ModelValidator(self.loader).validate(candidate, include_geometry=False)
        if not report.is_valid:
            raise ModelValidationError(
                "Assembly adaptation does not satisfy the authoring contract", report
            )
        return change
