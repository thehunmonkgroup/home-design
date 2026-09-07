"""Changeset previews reveal actual propagation and preserve rejected candidates."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from home_design.change_preview import ChangePreview, JsonChanges
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import ModelValidationError, ChangeConflictError
from home_design.inspection import InspectionPage
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.resolved import ResolvedModel
from home_design.validation import ModelValidator


def test_preview_reports_actual_opening_host_and_fill_propagation(
    reference_model: JsonObject, loader: ModelLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One authored station edit changes the opening, cut wall and filled window."""
    engine = ChangeEngine(loader)
    change = engine.load_change(Path("examples/change-sets/move-window.json"))
    original = deepcopy(reference_model)
    calls = 0
    resolve = ModelResolver.resolve

    def counted(instance: ModelResolver) -> ResolvedModel:
        nonlocal calls
        calls += 1
        return resolve(instance)

    monkeypatch.setattr(ModelResolver, "resolve", counted)
    result = ChangePreview(engine).evaluate(reference_model, change)
    assert calls == 2
    assert reference_model == original
    assert result.report["written"] is False
    assert result.report["valid"] is True
    authored = Authoring.array(
        Authoring.object(result.report["authoredChanges"])["items"]
    )
    assert len(authored) == 1
    assert (
        Authoring.object(authored[0])["path"]
        == "/elements/opening.window.north/placement/station"
    )
    effects = {
        str(Authoring.object(row)["id"]): Authoring.object(row)
        for row in Authoring.array(
            Authoring.object(result.report["resolvedChanges"])["items"]
        )
    }
    assert set(effects) == {"opening.window.north", "wall.north", "window.north"}
    assert effects["wall.north"]["authoredDirectly"] is False
    assert effects["window.north"]["geometryChanged"] is True
    assert Authoring.object(effects["wall.north"]["quantity"])["changed"] is False
    assert result.evaluation.resolved is not None


def test_preview_retains_invalid_candidate_and_structured_diagnostics(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """An invalid opening proposal stays reviewable while apply remains guarded."""
    engine = ChangeEngine(loader)
    change = engine.load_change(Path("examples/change-sets/move-window.json"))
    Authoring.object(Authoring.array(change["operations"])[0])["station"] = 20000
    preview = ChangePreview(engine).evaluate(reference_model, change)
    assert preview.report["valid"] is False
    assert preview.report["geometryComparison"] == "unavailable"
    failures = Authoring.array(
        Authoring.object(preview.report["coordinationRequired"])["items"]
    )
    assert any(
        Authoring.object(row)["code"] == "opening.outside-host-path" for row in failures
    )
    with pytest.raises(ModelValidationError) as caught:
        engine.apply(reference_model, change)
    payload = caught.value.to_dict()
    assert Authoring.object(payload["validation"])["valid"] is False
    assert caught.value.report is not None
    assert any(
        item.subject_id == "opening.window.north"
        for item in caught.value.report.diagnostics
    )


def test_invalid_source_can_be_repaired_and_previewed(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """A repair does not pretend that the invalid baseline had resolved geometry."""
    elements = Authoring.object(reference_model["elements"])
    Authoring.object(elements["window.north"])["type"] = "missing"
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": "repair.window",
        "description": "Restore window stock",
        "baseRevision": reference_model["revision"],
        "operations": [
            {
                "op": "set",
                "path": "/elements/window.north/type",
                "value": "windowType.casement-1500x1200",
            }
        ],
    }
    result = ChangePreview(ChangeEngine(loader)).evaluate(reference_model, change)
    assert result.report["valid"] is True
    assert Authoring.object(result.report["sourceValidation"])["valid"] is False
    assert result.report["geometryComparison"] == "unavailable"


def test_preview_lists_unchanged_users_of_an_occurrence_type(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """A local specification edit reports other occurrences whose geometry stays fixed."""
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": "change.local-wall",
        "description": "Label one wall",
        "baseRevision": reference_model["revision"],
        "operations": [
            {"op": "set", "path": "/elements/wall.north/name", "value": "North facade"}
        ],
    }
    result = ChangePreview(ChangeEngine(loader)).evaluate(reference_model, change)
    unchanged = {
        str(Authoring.object(row)["id"])
        for row in Authoring.array(
            Authoring.object(result.report["unchangedRelated"])["items"]
        )
    }
    assert {"wall.south", "wall.east", "wall.west"} <= unchanged
    limited = ChangePreview(ChangeEngine(loader)).evaluate(
        reference_model, change, InspectionPage(1)
    )
    assert Authoring.object(limited.report["unchangedRelated"])["nextOffset"] == 1


def test_presence_preconditions_guard_new_identifiers(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """Preparation can assert that a new reusable type ID is still unoccupied."""
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": "change.presence",
        "description": "Check reserved identity",
        "baseRevision": reference_model["revision"],
        "preconditions": [
            {"path": "/types/type.new", "exists": False},
            {"path": "/elements/wall.north", "exists": True},
        ],
        "operations": [
            {"op": "set", "path": "/project/description", "value": "Reviewed"}
        ],
    }
    engine = ChangeEngine(loader)
    engine.apply(reference_model, change)
    Authoring.object(reference_model["types"])["type.new"] = {}
    with pytest.raises(ChangeConflictError) as caught:
        engine.apply(reference_model, change)
    assert caught.value.code == "change.precondition-exists"
    assert caught.value.path == "/types/type.new"


def test_json_diff_preserves_existence_and_bounds_large_values() -> None:
    """Null, deletion and large source edits remain distinguishable in summaries."""
    changes = JsonChanges.compare({"null": None}, {"new": None})
    assert Authoring.object(changes[0])["beforeExists"] is False
    assert Authoring.object(changes[1])["afterExists"] is False
    large = JsonChanges.compact("text" * 1000)
    assert Authoring.object(large)["summarized"] is True
    assert Authoring.object(large)["items"] == 4000


def test_geometry_failure_keeps_subject_identity(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """A low-level resolution failure identifies the object to inspect next."""
    Authoring.object(reference_model["types"])["type.member"] = {
        "kind": "memberType",
        "name": "Member",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 40, "depth": 140},
    }
    Authoring.object(reference_model["elements"])["member.invalid"] = {
        "kind": "member",
        "name": "Zero length",
        "type": "type.member",
        "role": "beam",
        "axis": [{"point": [0, 0, 0]}, {"point": [0, 0, 0]}],
    }
    report = ModelValidator(loader).validate(reference_model)
    failure = next(
        item for item in report.errors if item.code == "geometry.resolution-failed"
    )
    assert failure.subject_id == "member.invalid"
    assert failure.path == "/elements/member.invalid"
