"""Versioned reusable assembly documents with typed parameters and explicit bindings."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path

from jsonschema import Draft202012Validator

from home_design.constants import resource_root
from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject, JsonPointer, JsonValue
from home_design.loader import ModelLoader
from home_design.geometry import number


@dataclass(frozen=True)
class RecipeTarget:
    """One explicit field target with optional scalar scale and offset."""

    path: str
    affine: bool = False
    scale: float = 1
    offset: float = 0

    @classmethod
    def from_value(cls, value: JsonValue) -> RecipeTarget:
        """Read a pointer or a declarative scalar adjustment without interpreting code."""
        if isinstance(value, str):
            return cls(value)
        target = Authoring.object(value)
        return cls(
            Authoring.text(target["path"]),
            "scale" in target or "offset" in target,
            number(target.get("scale", 1), "parameter scale"),
            number(target.get("offset", 0), "parameter offset"),
        )

    def value(self, parameter: JsonValue) -> JsonValue:
        """Calculate an explicit scalar adjustment, rejecting nonnumeric or nonfinite intent."""
        if not self.affine:
            return deepcopy(parameter)
        if not isinstance(parameter, (int, float)) or isinstance(parameter, bool):
            raise HomeDesignError(
                "Affine recipe targets require a numeric parameter",
                code="recipe.parameter-target",
                path=self.path,
            )
        result = parameter * self.scale + self.offset
        if not math.isfinite(result):
            raise HomeDesignError(
                "Recipe parameter targets must produce finite values",
                code="recipe.parameter-target",
                path=self.path,
            )
        return result


class AssemblyRecipe:
    """Read declarative construction packages without executable template expressions."""

    def __init__(self, source: JsonObject) -> None:
        """Validate the package envelope and retain an isolated source snapshot."""
        self.source: JsonObject = deepcopy(source)
        self.source_path: Path | None = None
        schema = ModelLoader().load(
            resource_root() / "schema/assembly-recipe-0.1.schema.json"
        )
        errors = sorted(
            Draft202012Validator(schema).iter_errors(source),
            key=lambda item: str(item.json_path),
        )
        if errors:
            error = errors[0]
            raise HomeDesignError(
                error.message, code="recipe.schema", path=error.json_path
            )
        self.identity: str = Authoring.text(source["id"])
        self.assembly: str = Authoring.text(source["assembly"])
        self.objects: JsonObject = deepcopy(Authoring.object(source["objects"]))
        self.index: ModelIndex = ModelIndex(self.objects)
        assembly = self.index.registries["elements"].get(self.assembly)
        if assembly is None or assembly.get("kind") != "assembly":
            raise HomeDesignError(
                "Recipe assembly must identify a local assembly element",
                code="recipe.assembly",
            )
        self.targets: dict[str, tuple[RecipeTarget, ...]] = {
            name: tuple(
                RecipeTarget.from_value(value)
                for value in Authoring.array(Authoring.object(definition)["targets"])
            )
            for name, definition in Authoring.object(
                source.get("parameters", {})
            ).items()
        }
        self._check_targets()

    @classmethod
    def load(cls, path: Path) -> AssemblyRecipe:
        """Load a public or workspace recipe document from an explicit path."""
        result = cls(ModelLoader().load(path))
        result.source_path = path.resolve()
        return result

    @property
    def digest(self) -> str:
        """Bind instance provenance to this exact declarative recipe content."""
        return ModelLoader.fingerprint(self.source)

    def _check_targets(self) -> None:
        """Reject overlapping parameter slots and missing connection-point participants."""
        targets: list[str] = []
        for values in self.targets.values():
            for value in values:
                target = value.path
                if any(
                    target == existing
                    or target.startswith(existing + "/")
                    or existing.startswith(target + "/")
                    for existing in targets
                ):
                    raise HomeDesignError(
                        f"Recipe parameter targets overlap at {target}",
                        code="recipe.parameter-target",
                        path=target,
                    )
                try:
                    JsonPointer.get(self.objects, target)
                except (KeyError, IndexError, TypeError, ValueError) as error:
                    raise HomeDesignError(
                        f"Recipe parameter target {target} is unavailable",
                        code="recipe.parameter-target",
                        path=target,
                    ) from error
                targets.append(target)
        local_ids = {
            identity
            for registry in self.index.registries.values()
            for identity in registry
        }
        bindings = Authoring.object(self.source.get("bindings", {}))
        if local_ids & bindings.keys():
            raise HomeDesignError(
                "External binding IDs must be separate from local object IDs",
                code="recipe.binding-conflict",
            )
        for diagnostic in self.index.diagnostics():
            if diagnostic.code == "identity.duplicate":
                raise HomeDesignError(
                    diagnostic.message, code="recipe.duplicate-id", path=diagnostic.path
                )
        for reference in self.index.references:
            if reference.target_id in local_ids:
                continue
            binding = bindings.get(reference.target_id)
            if (
                not isinstance(binding, dict)
                or binding.get("registry") != reference.registry
            ):
                raise HomeDesignError(
                    f"Recipe reference {reference.target_id} needs an explicit {reference.registry} binding",
                    code="recipe.undeclared-binding",
                    path=reference.path,
                )
        for value in Authoring.object(self.source.get("connectionPoints", {})).values():
            point = Authoring.object(value)
            if point["element"] not in self.index.registries["elements"]:
                raise HomeDesignError(
                    "Recipe connection points must identify local elements",
                    code="recipe.connection-point",
                )

    @staticmethod
    def _parameter_schema(definition: JsonObject) -> JsonObject:
        """Translate author-facing dimension types to a small JSON value contract."""
        kind = Authoring.text(definition["valueType"])
        if kind in {"point2", "point3"}:
            count = 2 if kind == "point2" else 3
            return {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {"type": "number"},
            }
        result: JsonObject = {"type": "number" if kind in {"length", "angle"} else kind}
        for key in ("minimum", "maximum"):
            if key in definition:
                result[key] = definition[key]
        return result

    def parameters(self, supplied: JsonObject) -> JsonObject:
        """Resolve supplied values and defaults, rejecting missing or mistyped inputs."""
        definitions = Authoring.object(self.source.get("parameters", {}))
        unknown = set(supplied) - set(definitions)
        if unknown:
            raise HomeDesignError(
                f"Unknown recipe parameters: {sorted(unknown)}",
                code="recipe.unknown-parameter",
            )
        result: JsonObject = {}
        for name, raw in definitions.items():
            definition = Authoring.object(raw)
            if name not in supplied and "default" not in definition:
                raise HomeDesignError(
                    f"Recipe requires parameter {name}",
                    code="recipe.missing-parameter",
                    path=f"/parameters/{name}",
                )
            value = supplied.get(name, definition.get("default"))
            if not Draft202012Validator(self._parameter_schema(definition)).is_valid(
                value
            ) or not self._finite(value):
                raise HomeDesignError(
                    f"Recipe parameter {name} does not match its value type or limits",
                    code="recipe.parameter-value",
                    path=f"/parameters/{name}",
                )
            result[name] = deepcopy(value)
        return result

    @staticmethod
    def _finite(value: JsonValue) -> bool:
        """Reject nonfinite numeric parameters even when a permissive JSON parser accepts them."""
        if isinstance(value, list):
            return all(AssemblyRecipe._finite(item) for item in value)
        return not isinstance(value, (int, float)) or math.isfinite(value)

    def parameterized(self, supplied: JsonObject) -> tuple[JsonObject, JsonObject]:
        """Return canonical template objects with all declared parameter slots populated."""
        parameters = self.parameters(supplied)
        objects = deepcopy(self.objects)
        for name, value in parameters.items():
            for target in self.targets[name]:
                JsonPointer.set(objects, target.path, target.value(value))
        return objects, parameters
