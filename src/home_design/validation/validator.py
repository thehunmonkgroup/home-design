"""Coordinated schema, semantic, topology, and resolution validation."""

from __future__ import annotations

from home_design.diagnostics import Diagnostic, ValidationReport
from home_design.errors import ResolutionError
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.coordination import CoordinationValidator
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
                if not any(item.severity == "error" for item in diagnostics):
                    resolver = ModelResolver(model)
                    resolved = resolver.resolve()
                    diagnostics.extend(self._clearances(resolver))
                    diagnostics.extend(
                        CoordinationValidator(model, resolved).diagnostics()
                    )
            except ResolutionError as error:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="geometry.resolution-failed",
                        message=str(error),
                    )
                )
        return ValidationReport(tuple(diagnostics))

    @staticmethod
    def _clearances(resolver: ModelResolver) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for element_id, element in resolver.elements.items():
            clearances = element.get("clearances", [])
            if not isinstance(clearances, list):
                continue
            for clearance in clearances:
                if not isinstance(clearance, dict):
                    continue
                lower, upper = clearance.get("lower"), clearance.get("upper")
                minimum = clearance.get("minimum")
                if (
                    not isinstance(lower, dict)
                    or not isinstance(upper, dict)
                    or not isinstance(minimum, (int, float))
                ):
                    continue
                actual = resolver.elevation(upper) - resolver.elevation(lower)
                if actual < minimum - 0.01:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "clearance.insufficient",
                            f"{clearance.get('name')}: {actual:g} mm available, {minimum:g} mm required",
                            subject_id=element_id,
                        )
                    )
        return diagnostics
