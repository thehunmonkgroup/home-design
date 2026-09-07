"""Canonical JSON model loading and schema validation."""

from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from home_design.constants import (
    MODEL_VERSION,
    SUPPORTED_MODEL_VERSIONS,
    default_schema_path,
    resource_root,
)
from home_design.diagnostics import Diagnostic, ValidationReport
from home_design.errors import ModelLoadError
from home_design.json_types import JsonObject, JsonValue
from home_design.schema_diagnostics import SchemaDiagnostics


class ModelLoader:
    """Load and validate canonical home design documents."""

    def __init__(self, schema_path: Path | None = None) -> None:
        """Initialize the loader.

        :param schema_path: Optional path overriding the bundled project schema.
        :raises ModelLoadError: If the schema cannot be loaded or is invalid.
        """
        self.schema_path: Path = (schema_path or default_schema_path()).resolve()
        self.schema: JsonObject = self._read_object(self.schema_path)
        try:
            Draft202012Validator.check_schema(self.schema)
        except SchemaError as error:
            raise ModelLoadError(f"Invalid JSON Schema: {error.message}") from error
        self.validator: Draft202012Validator = Draft202012Validator(self.schema)
        self._explicit_schema: bool = schema_path is not None
        self._versions: dict[str, tuple[JsonObject, Draft202012Validator]] = {
            MODEL_VERSION: (self.schema, self.validator)
        }

    def schema_for(self, version: str) -> tuple[JsonObject, Draft202012Validator]:
        """Read legacy versions explicitly without silently migrating source documents."""
        if self._explicit_schema or version not in SUPPORTED_MODEL_VERSIONS:
            return self.schema, self.validator
        if version not in self._versions:
            schema = self._read_object(
                resource_root() / "schema" / f"home-model-{version}.schema.json"
            )
            Draft202012Validator.check_schema(schema)
            self._versions[version] = schema, Draft202012Validator(schema)
        return self._versions[version]

    def load(self, model_path: Path) -> JsonObject:
        """Load a model without silently modifying it.

        :param model_path: Canonical model JSON path.
        :returns: Deep-copied model object.
        :raises ModelLoadError: If the file is unavailable, invalid JSON, or not an object.
        """
        return deepcopy(self._read_object(model_path.resolve()))

    @staticmethod
    def parse(source: bytes, label: str = "model") -> JsonObject:
        """Parse a single captured source snapshot without reading the file again."""
        try:
            value: JsonValue = json.loads(source.decode("utf-8"))
        except (ValueError, UnicodeError) as error:
            raise ModelLoadError(
                f"Cannot load JSON object from {label}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise ModelLoadError(f"Expected a JSON object in {label}")
        return value

    @staticmethod
    def serialize(model: JsonObject) -> bytes:
        """Return the exact canonical bytes used when saving a model revision."""
        return (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    @staticmethod
    def fingerprint(model: JsonObject) -> str:
        """Fingerprint source values independently of whitespace and key ordering."""
        return hashlib.sha256(
            json.dumps(model, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def validate_schema(self, model: JsonObject) -> ValidationReport:
        """Validate model structure and version against JSON Schema.

        :param model: Canonical model object.
        :returns: Structured schema validation report.
        """
        diagnostics: list[Diagnostic] = []
        version = model.get("modelVersion")
        if (
            isinstance(version, str)
            and version.split(".", maxsplit=1)[0] != MODEL_VERSION.split(".")[0]
        ):
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="schema.unsupported-major-version",
                    message=f"Model version {version!r} is not supported by this reader",
                    path="/modelVersion",
                )
            )
        schema, validator = self.schema_for(str(version))
        errors = sorted(
            validator.iter_errors(model), key=lambda item: list(item.absolute_path)
        )
        selector = SchemaDiagnostics(schema)
        for error in errors:
            diagnostics.extend(selector.relevant(error))
        return ValidationReport(tuple(diagnostics))

    @staticmethod
    def write(model: JsonObject, model_path: Path) -> None:
        """Write a canonical model deterministically.

        :param model: Model to serialize.
        :param model_path: Destination JSON path.
        """
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_bytes(ModelLoader.serialize(model))

    @staticmethod
    def _read_object(path: Path) -> JsonObject:
        try:
            value: JsonValue = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ModelLoadError(
                f"Cannot load JSON object from {path}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise ModelLoadError(f"Expected a JSON object in {path}")
        return value

    @staticmethod
    def _escape_pointer_token(token: str) -> str:
        return token.replace("~", "~0").replace("/", "~1")
