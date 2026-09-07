"""Expand declarative assembly recipes into ordinary guarded canonical changesets."""

from __future__ import annotations

import hashlib
from copy import deepcopy

from jsonschema import Draft202012Validator

from home_design.changes import ChangeEngine
from home_design.assembly_merge import AssemblyMerge
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
from home_design.scoped_remapping import ScopedRemapping
from home_design.validation import ModelValidator


class AssemblyInstantiation:
    """Bind and namespace one recipe while preserving explicit ownership and external objects."""

    def __init__(
        self,
        source: JsonObject,
        recipe: AssemblyRecipe,
        loader: ModelLoader | None = None,
    ) -> None:
        """Keep the source snapshot and recipe contract for reproducible expansion."""
        self.source: JsonObject = source
        self.recipe: AssemblyRecipe = recipe
        self.loader: ModelLoader = loader or ModelLoader()
        self.index: ModelIndex = ModelIndex(source)
        if source.get("modelVersion") != recipe.source["modelVersion"]:
            raise HomeDesignError(
                "Assembly recipes require a version 0.2 model; prepare and apply its migration first",
                code="recipe.model-version",
            )

    @staticmethod
    def object_id(instance: str, local: str) -> str:
        """Produce deterministic readable IDs within the canonical maximum length."""
        combined = f"{instance}.{local}"
        if len(combined) <= 160:
            return combined
        digest = hashlib.sha256(combined.encode()).hexdigest()[:24]
        return f"{instance[:70]}.{local[:60]}.{digest}"

    def _target(
        self, identity: str, registry: str, kind: str | None = None
    ) -> JsonObject:
        """Require a binding target in the declared registry and optional family."""
        target = self.index.registries[registry].get(identity)
        if target is None or (kind is not None and target.get("kind") != kind):
            raise HomeDesignError(
                f"Binding {identity} must identify {kind or 'an object'} in {registry}",
                code="recipe.binding-target",
                subject_id=identity,
            )
        return target

    def _bindings(
        self, supplied: JsonObject, check_targets: bool = True
    ) -> dict[str, str]:
        """Resolve every declared external symbol without guessing a project object."""
        declarations = Authoring.object(self.recipe.source.get("bindings", {}))
        if set(supplied) != set(declarations):
            missing: list[JsonValue] = []
            missing.extend(sorted(set(declarations) - set(supplied)))
            unknown: list[JsonValue] = []
            unknown.extend(sorted(set(supplied) - set(declarations)))
            details: JsonObject = {"missing": missing, "unknown": unknown}
            raise HomeDesignError(
                "Recipe bindings must supply exactly the declared names",
                code="recipe.binding-set",
                details=details,
            )
        result: dict[str, str] = {}
        for name, value in supplied.items():
            target = Authoring.text(value, "external binding ID")
            declaration = Authoring.object(declarations[name])
            if check_targets:
                self._target(
                    target,
                    Authoring.text(declaration["registry"]),
                    (
                        Authoring.text(declaration["kind"])
                        if "kind" in declaration
                        else None
                    ),
                )
            result[name] = target
        return result

    def _overrides(self, objects: JsonObject, overrides: JsonObject) -> None:
        """Apply only explicitly advertised override fields in the local recipe namespace."""
        allowed = [
            Authoring.text(value)
            for value in Authoring.array(self.recipe.source.get("overridePaths", []))
        ]
        for path, value in overrides.items():
            if not any(
                path == prefix or path.startswith(prefix + "/") for prefix in allowed
            ):
                raise HomeDesignError(
                    f"Recipe does not expose override {path}",
                    code="recipe.override-path",
                    path=path,
                )
            try:
                JsonPointer.set(objects, path, value)
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise HomeDesignError(
                    f"Cannot apply recipe override {path}: {error}",
                    code="recipe.override-path",
                    path=path,
                ) from error

    @staticmethod
    def remap_scoped_parts(objects: JsonObject, identities: dict[str, str]) -> None:
        """Rebind generated opening and default roof-face IDs in their scoped reference slots."""
        ScopedRemapping(objects, identities).apply()

    def render(
        self,
        instance: str,
        parameters: JsonObject,
        bindings: JsonObject,
        overrides: JsonObject | None = None,
        shared_types: JsonObject | None = None,
        check_external: bool = True,
    ) -> tuple[JsonObject, JsonObject]:
        """Render a namespaced package and its compact reproducible provenance.

        :returns: Canonical registries and assembly instance provenance. No source is modified.
        """
        schema = Authoring.object(JsonPointer.get(self.loader.schema, "/$defs/Id"))
        if not Draft202012Validator(schema).is_valid(instance):
            raise HomeDesignError(
                "Assembly instance must use a canonical ID", code="recipe.instance-id"
            )
        objects, selected = self.recipe.parameterized(parameters)
        overrides = overrides or {}
        shared_types = shared_types or {}
        self._overrides(objects, overrides)
        if check_external:
            self._check_shared_inputs(shared_types, parameters, overrides)
        external = self._bindings(bindings, check_external)
        mappings: JsonObject = {}
        identities = dict(external)
        local_index = ModelIndex(objects)
        if set(shared_types) - set(local_index.registries["types"]):
            raise HomeDesignError(
                "Only local recipe types can be shared with existing stock",
                code="recipe.shared-type",
            )
        for registry, values in local_index.registries.items():
            mapping: JsonObject = {}
            for local, definition in values.items():
                target = (
                    instance
                    if local == self.recipe.assembly
                    else self.object_id(instance, local)
                )
                if registry == "types" and local in shared_types:
                    target = Authoring.text(shared_types[local])
                    if check_external:
                        self._target(
                            target, "types", Authoring.text(definition["kind"])
                        )
                mapping[local] = target
                identities[local] = target
            mappings[registry] = mapping
        self.remap_scoped_parts(objects, identities)
        for reference in ModelIndex(objects).references:
            if reference.target_id not in identities:
                raise HomeDesignError(
                    f"Parameter or override introduces undeclared binding {reference.target_id}",
                    code="recipe.undeclared-binding",
                    path=reference.path,
                )
        rebound = ReferenceRemapping.apply(objects, identities)
        ReferenceRemapping.records(rebound, identities)
        result: JsonObject = {}
        for registry, mapping_value in mappings.items():
            mapping = Authoring.object(mapping_value)
            values = Authoring.object(rebound.get(registry, {}))
            result[registry] = {
                Authoring.text(target): values[local]
                for local, target in mapping.items()
                if not (registry == "types" and local in shared_types)
            }
        provenance: JsonObject = {
            "recipeId": self.recipe.identity,
            "recipeDigest": self.recipe.digest,
            "parameters": selected,
            "bindings": dict(external),
            "objectIds": mappings,
            "overrides": deepcopy(overrides),
            "sharedTypes": deepcopy(shared_types),
            "connectionPoints": {
                name: {
                    **Authoring.object(value),
                    "element": identities[
                        Authoring.text(Authoring.object(value)["element"])
                    ],
                }
                for name, value in Authoring.object(
                    self.recipe.source.get("connectionPoints", {})
                ).items()
            },
        }
        Authoring.object(Authoring.object(result["elements"])[instance])[
            "recipeInstance"
        ] = provenance
        return result, provenance

    def _check_shared_inputs(
        self, shared: JsonObject, parameters: JsonObject, overrides: JsonObject
    ) -> None:
        """Reject local stock configuration that an explicit external stock choice would discard."""
        for local in shared:
            prefix = f"/types/{local}"
            paths = list(overrides)
            definitions = Authoring.object(self.recipe.source.get("parameters", {}))
            paths.extend(
                target.path
                for name, targets in self.recipe.targets.items()
                if name in parameters
                and not AssemblyMerge.equal(
                    parameters[name], Authoring.object(definitions[name]).get("default")
                )
                for target in targets
            )
            if any(path == prefix or path.startswith(prefix + "/") for path in paths):
                raise HomeDesignError(
                    f"Local inputs target shared type {local}; make it local before changing its definition",
                    code="recipe.shared-type-input",
                    path=prefix,
                )

    def prepare(
        self,
        instance: str,
        parameters: JsonObject,
        bindings: JsonObject,
        overrides: JsonObject | None = None,
        shared_types: JsonObject | None = None,
    ) -> JsonObject:
        """Produce creation operations with absence and external-object preconditions."""
        objects, _ = self.render(
            instance, parameters, bindings, overrides, shared_types
        )
        conditions: list[JsonValue] = []
        operations: list[JsonValue] = []
        for registry, raw in objects.items():
            for identity, value in Authoring.object(raw).items():
                if any(identity in values for values in self.index.registries.values()):
                    raise ChangeConflictError(
                        f"Assembly object {identity} already exists",
                        code="recipe.identity-conflict",
                        subject_id=identity,
                    )
                conditions.append({"path": f"/{registry}/{identity}", "exists": False})
                operations.append(
                    {
                        "op": "putObject",
                        "registry": registry,
                        "objectId": identity,
                        "value": value,
                    }
                )
        used: set[tuple[str, str]] = set()
        for reference in ModelIndex(objects).references:
            if reference.target_id in self.index.registries[reference.registry]:
                used.add((reference.registry, reference.target_id))
        conditions.extend(
            {
                "path": f"/{registry}/{identity}",
                "equals": self.index.registries[registry][identity],
            }
            for registry, identity in sorted(used)
        )
        change: JsonObject = {
            "changeVersion": "0.1",
            "id": self.object_id("change.instantiate", instance),
            "description": f"Instantiate {self.recipe.identity} as {instance}",
            "baseRevision": self.source["revision"],
            "preconditions": conditions,
            "operations": operations,
        }
        candidate = ChangeEngine(self.loader).candidate(self.source, change)
        report = ModelValidator(self.loader).validate(candidate, include_geometry=False)
        if not report.is_valid:
            raise ModelValidationError(
                "Assembly expansion does not satisfy the authoring contract", report
            )
        return change
