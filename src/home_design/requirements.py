"""Shared requirement evaluation for validation and review exports."""

from __future__ import annotations

import math

from home_design.construction import Authoring
from home_design.diagnostics import Diagnostic, Severity
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import ResolvedElement, ResolvedModel


class RequirementEvaluator:
    """Evaluate numeric checks without certifying unchecked statements."""

    def __init__(self, resolved: ResolvedModel) -> None:
        """Index resolved inputs from one source revision.

        :param resolved: Model whose properties are checked.
        """
        self.resolved: ResolvedModel = resolved
        self.elements: dict[str, ResolvedElement] = {
            element.element_id: element for element in resolved.elements
        }

    def evaluate(self) -> tuple[JsonObject, ...]:
        """Return deterministic statuses and per-target measurements.

        :returns: Results keyed by authored requirement IDs.
        """
        return tuple(
            self._requirement(Authoring.object(value))
            for value in self.resolved.requirements
        )

    def _requirement(self, requirement: JsonObject) -> JsonObject:
        check = requirement.get("check")
        checks: list[JsonValue] = []
        if isinstance(check, dict):
            checks = [
                self._check(Authoring.text(element_id), check)
                for element_id in Authoring.array(requirement.get("appliesTo", []))
            ]
        status = "notChecked"
        if checks:
            status = (
                "violated"
                if any(
                    Authoring.object(item)["status"] == "violated" for item in checks
                )
                else "satisfied"
            )
        return {"id": requirement.get("id"), "status": status, "checks": checks}

    def _check(self, element_id: str, check: JsonObject) -> JsonObject:
        element = self.elements.get(element_id)
        actual: JsonValue = element.data if element else None
        property_name = Authoring.text(check.get("property"))
        for field in property_name.split("."):
            actual = actual.get(field) if isinstance(actual, dict) else None
        expected = number(check.get("value"), "requirement value")
        operator = check.get("operator")
        passed = False
        if isinstance(actual, (int, float)) and not isinstance(actual, bool):
            if operator == "atMost":
                passed = actual <= expected
            elif operator == "atLeast":
                passed = actual >= expected
            elif operator == "equals":
                passed = math.isclose(actual, expected, abs_tol=1e-6)
        return {
            "elementId": element_id,
            "property": property_name,
            "operator": operator,
            "expected": expected,
            "actual": actual,
            "status": "satisfied" if passed else "violated",
        }

    def diagnostics(self) -> list[Diagnostic]:
        """Translate evaluated failures into validation diagnostics.

        :returns: One diagnostic per violated target, using authored severity.
        """
        diagnostics: list[Diagnostic] = []
        results = self.resolved.requirement_results or self.evaluate()
        for source, result in zip(self.resolved.requirements, results, strict=True):
            requirement = Authoring.object(source)
            severity_value = requirement.get("severity")
            severity: Severity = (
                "error"
                if severity_value == "error"
                else "warning" if severity_value == "warning" else "info"
            )
            for value in Authoring.array(result.get("checks")):
                check = Authoring.object(value)
                if check.get("status") == "violated":
                    expected = number(check.get("expected"), "expected value")
                    diagnostics.append(
                        Diagnostic(
                            severity,
                            "requirement.unsatisfied",
                            f"{requirement.get('statement')}: {check.get('property')} is {check.get('actual')!r}; expected {check.get('operator')} {expected:g}",
                            subject_id=Authoring.text(check.get("elementId")),
                        )
                    )
        return diagnostics
