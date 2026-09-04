"""Transactional domain changes for AI-directed model modifications."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from home_design.constants import repository_root
from home_design.errors import (
    ChangeConflictError,
    ModelLoadError,
    ModelValidationError,
    ResolutionError,
)
from home_design.json_types import JsonObject, JsonPointer, JsonValue
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class ChangeEngine:
    """Apply revision-checked changes atomically to canonical models."""

    def __init__(
        self, loader: ModelLoader, validator: ModelValidator | None = None
    ) -> None:
        """Initialize the change engine.

        :param loader: Canonical model loader.
        :param validator: Optional coordinated validator.
        :raises ModelLoadError: If the change-set schema is unavailable.
        """
        self.loader: ModelLoader = loader
        self.validator: ModelValidator = validator or ModelValidator(loader)
        schema_path = repository_root() / "schema" / "change-set-0.1.schema.json"
        try:
            schema_value = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ModelLoadError(f"Cannot load change-set schema: {error}") from error
        if not isinstance(schema_value, dict):
            raise ModelLoadError("Change-set schema must be a JSON object")
        self.change_validator: Draft202012Validator = Draft202012Validator(schema_value)

    def load_change(self, change_path: Path) -> JsonObject:
        """Load and validate a change-set file.

        :param change_path: Change-set JSON path.
        :returns: Validated change object.
        :raises ModelLoadError: If JSON loading or schema validation fails.
        """
        try:
            value: JsonValue = json.loads(change_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ModelLoadError(
                f"Cannot load change set {change_path}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise ModelLoadError("Change set must be a JSON object")
        errors = sorted(
            self.change_validator.iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
        if errors:
            message = "; ".join(error.message for error in errors)
            raise ModelLoadError(f"Invalid change set: {message}")
        return value

    def apply(self, model: JsonObject, change: JsonObject) -> JsonObject:
        """Apply a change in memory and validate the complete result.

        :param model: Current canonical model.
        :param change: Schema-valid transactional change set.
        :returns: Validated next model revision.
        :raises ChangeConflictError: If revision or value preconditions fail.
        :raises ModelValidationError: If the resulting model is invalid.
        """
        errors = sorted(
            self.change_validator.iter_errors(change),
            key=lambda item: list(item.absolute_path),
        )
        if errors:
            message = "; ".join(error.message for error in errors)
            raise ModelLoadError(f"Invalid change set: {message}")
        expected_revision = change.get("baseRevision")
        actual_revision = model.get("revision")
        if expected_revision != actual_revision:
            raise ChangeConflictError(
                f"Change expects revision {expected_revision}, but model is revision {actual_revision}"
            )
        candidate = deepcopy(model)
        self._check_preconditions(candidate, change)
        operations = change.get("operations")
        if not isinstance(operations, list):
            raise ModelLoadError("Change operations must be an array")
        for operation in operations:
            if not isinstance(operation, dict):
                raise ModelLoadError("Each change operation must be an object")
            self._apply_operation(candidate, operation)
        candidate["revision"] = (
            int(actual_revision) + 1 if isinstance(actual_revision, int) else 1
        )
        report = self.validator.validate(candidate)
        if not report.is_valid:
            summary = "; ".join(
                f"{item.code}: {item.message}" for item in report.errors
            )
            raise ModelValidationError(f"Change rejected: {summary}")
        try:
            ModelResolver(candidate).resolve()
        except ResolutionError as error:
            raise ModelValidationError(
                f"Change rejected during geometry resolution: {error}"
            ) from error
        return candidate

    def apply_to_file(
        self, model_path: Path, change_path: Path, output_path: Path | None = None
    ) -> JsonObject:
        """Apply a change and atomically write the result.

        :param model_path: Current canonical model file.
        :param change_path: Transactional change-set file.
        :param output_path: Optional destination; defaults to replacing the source.
        :returns: Written next model revision.
        :raises OSError: If the validated result cannot be committed.
        """
        model = self.loader.load(model_path)
        change = self.load_change(change_path)
        candidate = self.apply(model, change)
        destination = (output_path or model_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(candidate, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return candidate

    def _check_preconditions(self, model: JsonObject, change: JsonObject) -> None:
        preconditions = change.get("preconditions", [])
        if not isinstance(preconditions, list):
            raise ModelLoadError("Change preconditions must be an array")
        for precondition in preconditions:
            if not isinstance(precondition, dict):
                raise ModelLoadError("Each precondition must be an object")
            path = precondition.get("path")
            if not isinstance(path, str):
                raise ModelLoadError("Precondition path must be a string")
            try:
                actual = JsonPointer.get(model, path)
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise ChangeConflictError(
                    f"Precondition path does not exist: {path}"
                ) from error
            if actual != precondition.get("equals"):
                raise ChangeConflictError(
                    f"Precondition failed at {path}: expected {precondition.get('equals')!r}, found {actual!r}"
                )

    def _apply_operation(self, model: JsonObject, operation: JsonObject) -> None:
        operation_kind = operation.get("op")
        if operation_kind == "set":
            JsonPointer.set(
                model, self._required_string(operation, "path"), operation.get("value")
            )
            return
        if operation_kind == "remove":
            JsonPointer.remove(model, self._required_string(operation, "path"))
            return
        if operation_kind == "moveAnchor":
            anchor_id = self._required_string(operation, "anchorId")
            anchor = self._registry_object(model, "anchors", anchor_id)
            if anchor.get("kind") not in {"point2", "point3"}:
                raise ChangeConflictError(
                    f"Anchor {anchor_id} cannot be moved by position"
                )
            anchor["position"] = deepcopy(operation.get("position"))
            return
        if operation_kind == "moveOpening":
            opening_id = self._required_string(operation, "openingId")
            opening = self._registry_object(model, "elements", opening_id)
            if opening.get("kind") != "opening":
                raise ChangeConflictError(f"Element {opening_id} is not an opening")
            placement = opening.get("placement")
            if not isinstance(placement, dict):
                raise ChangeConflictError(f"Opening {opening_id} has no placement")
            for field in ("station", "verticalOffset", "depthOffset"):
                if field in operation:
                    placement[field] = deepcopy(operation[field])
            return
        if operation_kind in {"putObject", "removeObject"}:
            registry_name = self._required_string(operation, "registry")
            object_id = self._required_string(operation, "objectId")
            registry = model.get(registry_name)
            if not isinstance(registry, dict):
                raise ChangeConflictError(f"Unknown registry {registry_name}")
            if operation_kind == "putObject":
                value = operation.get("value")
                if not isinstance(value, dict):
                    raise ModelLoadError("putObject value must be an object")
                registry[object_id] = deepcopy(value)
            else:
                if object_id not in registry:
                    raise ChangeConflictError(
                        f"Object {object_id} does not exist in {registry_name}"
                    )
                del registry[object_id]
            return
        raise ModelLoadError(f"Unsupported change operation {operation_kind}")

    @staticmethod
    def _registry_object(
        model: JsonObject, registry_name: str, object_id: str
    ) -> JsonObject:
        registry = model.get(registry_name)
        value = registry.get(object_id) if isinstance(registry, dict) else None
        if not isinstance(value, dict):
            raise ChangeConflictError(
                f"Object {object_id} does not exist in {registry_name}"
            )
        return value

    @staticmethod
    def _required_string(value: JsonObject, field: str) -> str:
        result = value.get(field)
        if not isinstance(result, str):
            raise ModelLoadError(f"Operation field {field} must be a string")
        return result
