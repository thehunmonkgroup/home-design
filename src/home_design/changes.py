"""Transactional domain changes for AI-directed model modifications."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from home_design.constants import resource_root
from home_design.diagnostics import ValidationReport
from home_design.errors import (
    ChangeConflictError,
    ModelLoadError,
    ModelValidationError,
)
from home_design.json_types import JsonObject, JsonPointer, JsonValue
from home_design.loader import ModelLoader
from home_design.schema_diagnostics import SchemaDiagnostics
from home_design.source_state import SourceState
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
        schema_path = resource_root() / "schema" / "change-set-0.1.schema.json"
        try:
            schema_value = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ModelLoadError(f"Cannot load change-set schema: {error}") from error
        if not isinstance(schema_value, dict):
            raise ModelLoadError("Change-set schema must be a JSON object")
        self.change_validator: Draft202012Validator = Draft202012Validator(schema_value)
        self.change_schema: JsonObject = schema_value

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
        self.validate_change(value)
        return value

    def validate_change(self, value: JsonObject) -> None:
        """Validate operations while retaining precise field-level diagnostics."""
        selector = SchemaDiagnostics(self.change_schema)
        diagnostics = tuple(
            diagnostic
            for error in self.change_validator.iter_errors(value)
            for diagnostic in selector.relevant(error)
        )
        if diagnostics:
            message = "; ".join(item.message for item in diagnostics)
            raise ModelLoadError(
                f"Invalid change set: {message}",
                code="change.schema-invalid",
                report=ValidationReport(diagnostics),
            )

    def apply(self, model: JsonObject, change: JsonObject) -> JsonObject:
        """Apply a change in memory and validate the complete result.

        :param model: Current canonical model.
        :param change: Schema-valid transactional change set.
        :returns: Validated next model revision.
        :raises ChangeConflictError: If revision or value preconditions fail.
        :raises ModelValidationError: If the resulting model is invalid.
        """
        candidate = self.candidate(model, change)
        report = self.validator.validate(candidate)
        if not report.is_valid:
            summary = "; ".join(
                f"{item.code}: {item.message}" for item in report.errors
            )
            raise ModelValidationError(f"Change rejected: {summary}", report)
        return candidate

    def candidate(self, model: JsonObject, change: JsonObject) -> JsonObject:
        """Apply guarded operations in memory for evaluation without asserting validity.

        :param model: Source model, which remains unchanged.
        :param change: Revision-checked operations and value preconditions.
        :returns: Unvalidated candidate for preview or final validation.
        :raises ChangeConflictError: If source assumptions do not hold.
        """
        self.validate_change(change)
        expected_revision = change.get("baseRevision")
        actual_revision = model.get("revision")
        if expected_revision != actual_revision:
            raise ChangeConflictError(
                f"Change expects revision {expected_revision}, but model is revision {actual_revision}",
                code="change.revision-conflict",
                path="/revision",
                details={"expected": expected_revision, "actual": actual_revision},
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
        source = SourceState.capture(model_path)
        destination = (output_path or model_path).resolve()
        previous_destination = (
            source
            if destination == source.path
            else SourceState.capture(destination, required=False)
        )
        change = self.load_change(change_path)
        candidate = self.apply(source.model, change)
        with SourceState.lock(destination):
            source.assert_unchanged()
            previous_destination.assert_unchanged()
            SourceState.write(destination, ModelLoader.serialize(candidate))
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
                if precondition.get("exists") is False:
                    continue
                raise ChangeConflictError(
                    f"Precondition path does not exist: {path}",
                    code="change.precondition-missing",
                    path=path,
                ) from error
            if "exists" in precondition:
                if precondition["exists"] is True:
                    continue
                raise ChangeConflictError(
                    f"Precondition requires an absent path: {path}",
                    code="change.precondition-exists",
                    path=path,
                )
            if actual != precondition.get("equals"):
                raise ChangeConflictError(
                    f"Precondition failed at {path}: expected {precondition.get('equals')!r}, found {actual!r}",
                    code="change.precondition-failed",
                    path=path,
                    details={"expected": precondition.get("equals"), "actual": actual},
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
