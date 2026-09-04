"""Coordinated schema, semantic, topology, and resolution validation."""

from __future__ import annotations

from home_design.diagnostics import Diagnostic, ValidationReport
from home_design.errors import ResolutionError
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.validation.semantic import SemanticValidator
from home_design.validation.topology import TopologyValidator


class ModelValidator:
    """Apply validation layers in dependency order."""

    def __init__(self, loader: ModelLoader) -> None:
        """Initialize the validator.

        :param loader: Schema-aware model loader.
        """
        self.loader: ModelLoader = loader

    def validate(
        self, model: JsonObject, include_geometry: bool = True
    ) -> ValidationReport:
        """Validate a canonical model.

        :param model: Canonical model object.
        :param include_geometry: Whether to run topology and geometry checks.
        :returns: Combined structured report.
        """
        schema_report = self.loader.validate_schema(model)
        if not schema_report.is_valid:
            return schema_report
        index = ModelIndex(model)
        diagnostics = index.diagnostics()
        if any(item.severity == "error" for item in diagnostics):
            return ValidationReport(tuple(diagnostics))
        diagnostics.extend(SemanticValidator(model, index).diagnostics())
        if include_geometry and not any(
            item.severity == "error" for item in diagnostics
        ):
            try:
                diagnostics.extend(TopologyValidator(model, index).diagnostics())
            except ResolutionError as error:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="geometry.resolution-failed",
                        message=str(error),
                    )
                )
        return ValidationReport(tuple(diagnostics))
