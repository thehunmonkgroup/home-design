"""Synthetic requirement checks shared by validation and review results."""

from __future__ import annotations

from dataclasses import replace

import pytest

from home_design.json_types import JsonObject, JsonValue
from home_design.requirements import RequirementEvaluator
from home_design.resolved import ResolvedElement, ResolvedModel


class RequirementFixture:
    """Build small adapter-neutral inputs without a private design dependency."""

    @staticmethod
    def resolve(
        requirements: tuple[JsonValue, ...], actual: JsonValue
    ) -> ResolvedModel:
        """Evaluate requirements against two synthetic component records."""
        model = ResolvedModel(
            model_version="0.1",
            source_revision=7,
            project={},
            coordinate_system={},
            levels={},
            materials={},
            types={},
            relationships={},
            elements=(
                ResolvedElement(
                    "component.a",
                    "stair",
                    "A",
                    None,
                    data={"dimensions": {"clearWidth": actual}},
                ),
                ResolvedElement(
                    "component.b",
                    "stair",
                    "B",
                    None,
                    data={"dimensions": {"clearWidth": 1300}},
                ),
            ),
            requirements=requirements,
        )
        return replace(
            model, requirement_results=RequirementEvaluator(model).evaluate()
        )

    @staticmethod
    def requirement(operator: str = "atLeast", severity: str = "error") -> JsonObject:
        """Return an authored minimum-width rule."""
        return {
            "id": "requirement.width",
            "statement": "Preserve width.",
            "severity": severity,
            "appliesTo": ["component.a"],
            "check": {
                "property": "dimensions.clearWidth",
                "operator": operator,
                "value": 1220,
            },
        }


@pytest.mark.parametrize(
    ("operator", "actual", "status"),
    [
        ("atLeast", 1220, "satisfied"),
        ("atLeast", 1219, "violated"),
        ("atMost", 1220, "satisfied"),
        ("atMost", 1221, "violated"),
        ("equals", 1220.0000001, "satisfied"),
        ("equals", 1221, "violated"),
        ("atLeast", None, "violated"),
        ("atLeast", "1300", "violated"),
        ("atLeast", True, "violated"),
    ],
)
def test_numeric_result_and_diagnostic_agree(
    operator: str, actual: JsonValue, status: str
) -> None:
    model = RequirementFixture.resolve(
        (RequirementFixture.requirement(operator),), actual
    )
    result = model.requirement_results[0]
    assert result["status"] == status
    assert result["checks"] == [
        {
            "elementId": "component.a",
            "property": "dimensions.clearWidth",
            "operator": operator,
            "expected": 1220,
            "actual": actual,
            "status": status,
        }
    ]
    diagnostics = RequirementEvaluator(model).diagnostics()
    assert len(diagnostics) == (1 if status == "violated" else 0)
    if diagnostics:
        assert diagnostics[0].severity == "error"
        assert diagnostics[0].code == "requirement.unsatisfied"
        assert diagnostics[0].subject_id == "component.a"


@pytest.mark.parametrize("severity", ["info", "warning", "error"])
def test_violation_status_is_independent_of_severity(severity: str) -> None:
    model = RequirementFixture.resolve(
        (RequirementFixture.requirement(severity=severity),), 1200
    )
    assert model.requirement_results[0]["status"] == "violated"
    assert RequirementEvaluator(model).diagnostics()[0].severity == severity


def test_notes_and_checks_without_targets_are_not_automatically_checked() -> None:
    note: JsonObject = {
        "id": "note",
        "statement": "Obtain engineering review.",
        "severity": "info",
    }
    empty = {**RequirementFixture.requirement(), "appliesTo": []}
    model = RequirementFixture.resolve((note, empty), 1220)
    assert all(result["status"] == "notChecked" for result in model.requirement_results)
    assert RequirementEvaluator(model).diagnostics() == []
    assert model.requirements == (note, empty)


def test_multiple_targets_retain_individual_results_and_aggregate_failure() -> None:
    requirement: JsonObject = {
        **RequirementFixture.requirement(),
        "appliesTo": ["component.a", "component.b"],
    }
    model = RequirementFixture.resolve((requirement,), 1200)
    result = model.requirement_results[0]
    assert result["status"] == "violated"
    checks = result["checks"]
    assert isinstance(checks, list)
    assert [item["status"] for item in checks if isinstance(item, dict)] == [
        "violated",
        "satisfied",
    ]
    assert len(RequirementEvaluator(model).diagnostics()) == 1
    assert RequirementEvaluator(model).evaluate() == model.requirement_results
    assert model.to_dict()["requirementResults"] == list(model.requirement_results)
