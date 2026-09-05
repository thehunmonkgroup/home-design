"""Requirement results and diagnostics across resolution and export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from home_design.build import BuildService
from home_design.errors import ModelValidationError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


@pytest.mark.parametrize("severity", ["warning", "error"])
def test_requirement_failure_controls_build_and_matches_export(
    tmp_path: Path,
    reference_model: JsonObject,
    severity: str,
    validator: ModelValidator,
) -> None:
    reference_model["requirements"] = [
        {
            "id": "requirement.synthetic",
            "statement": "Check an unavailable numeric property.",
            "severity": severity,
            "appliesTo": ["wall.north"],
            "check": {"property": "missingWidth", "operator": "atLeast", "value": 1220},
        }
    ]
    resolved = ModelResolver(reference_model).resolve()
    assert resolved.requirement_results[0]["status"] == "violated"
    report = validator.validate(reference_model)
    failures = [
        item for item in report.diagnostics if item.code == "requirement.unsatisfied"
    ]
    assert len(failures) == 1
    assert failures[0].severity == severity
    source = tmp_path / "model.json"
    ModelLoader.write(reference_model, source)
    if severity == "error":
        with pytest.raises(ModelValidationError, match="requirement.unsatisfied"):
            BuildService().build(source, tmp_path / "build")
        assert not (tmp_path / "build").exists()
    else:
        build = BuildService().build(source, tmp_path / "build", tmp_path / "viewer")
        manifest = json.loads(build.render_manifest.read_text(encoding="utf-8"))
        assert manifest["requirementResults"] == list(resolved.requirement_results)
        assert manifest["requirements"] == reference_model["requirements"]
        assert manifest["sourceRevision"] == resolved.source_revision
        catalog = json.loads((tmp_path / "viewer" / "index.json").read_text())
        assert (
            tmp_path
            / "viewer"
            / catalog["models"][0]["baseUrl"]
            / "render-manifest.json"
        ).read_bytes() == build.render_manifest.read_bytes()
