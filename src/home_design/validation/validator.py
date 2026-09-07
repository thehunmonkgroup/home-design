"""Coordinated schema, semantic, topology, and resolution validation."""

from __future__ import annotations

from dataclasses import dataclass

from home_design.diagnostics import Diagnostic, ValidationReport
from home_design.errors import ResolutionError
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.resolved import ResolvedModel
from home_design.mounted_parts import CoordinationVolumes
from home_design.service_coordination import ServiceCoordination
from home_design.cut_limits import CutLimits
from home_design.coordination import CoordinationValidator
from home_design.recipe_interfaces import RecipeInterfaces
from home_design.validation.semantic import SemanticValidator
from home_design.validation.topology import TopologyValidator


@dataclass(frozen=True, slots=True)
class ModelEvaluation:
    """Keep validation evidence and its resolved geometry from one evaluation."""

    report: ValidationReport
    resolved: ResolvedModel | None = None
    source_fingerprint: str = ""


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
        return self.evaluate(model, include_geometry).report

    def evaluate(
        self, model: JsonObject, include_geometry: bool = True
    ) -> ModelEvaluation:
        """Validate once and retain resolved geometry for previews and prepared builds.

        :param model: Canonical source snapshot.
        :param include_geometry: Whether to evaluate topology and physical coordination.
        :returns: Diagnostics and available geometry, including coordination failures.
        """
        fingerprint = ModelLoader.fingerprint(model)
        schema_report = self.loader.validate_schema(model)
        if not schema_report.is_valid:
            return ModelEvaluation(schema_report, source_fingerprint=fingerprint)
        index = ModelIndex(model)
        diagnostics = index.diagnostics()
        if any(item.severity == "error" for item in diagnostics):
            return ModelEvaluation(
                ValidationReport(tuple(diagnostics)), source_fingerprint=fingerprint
            )
        diagnostics.extend(SemanticValidator(model, index).diagnostics())
        resolved: ResolvedModel | None = None
        if include_geometry and not any(
            item.severity == "error" for item in diagnostics
        ):
            try:
                diagnostics.extend(TopologyValidator(model, index).diagnostics())
                if not any(item.severity == "error" for item in diagnostics):
                    resolver = ModelResolver(model)
                    resolved = resolver.resolve()
                    diagnostics.extend(CoordinationVolumes.diagnostics(resolved))
                    diagnostics.extend(ServiceCoordination.diagnostics(resolved))
                    diagnostics.extend(CutLimits.diagnostics(resolved))
                    diagnostics.extend(RecipeInterfaces.diagnostics(model, resolved))
                    diagnostics.extend(self._clearances(resolver))
                    diagnostics.extend(
                        CoordinationValidator(model, resolved).diagnostics()
                    )
            except ResolutionError as error:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code=(
                            error.code
                            if error.code != "workflow.failed"
                            else "geometry.resolution-failed"
                        ),
                        message=str(error),
                        path=error.path,
                        subject_id=error.subject_id,
                        details=error.details,
                    )
                )
        return ModelEvaluation(
            ValidationReport(tuple(diagnostics)), resolved, fingerprint
        )

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
