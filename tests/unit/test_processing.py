"""Construction stage prerequisites and shared placement-frame boundaries."""

from __future__ import annotations

import pytest

from home_design.errors import ResolutionError
from home_design.frames import LocalFrame
from home_design.json_types import JsonObject
from home_design.processing import (
    ConstructionPipeline,
    ProcessingContext,
    ProcessingStage,
)
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


def test_reordered_cut_stage_fails_before_any_processing() -> None:
    stages = ConstructionPipeline.standard().stages
    with pytest.raises(ResolutionError) as caught:
        ConstructionPipeline((stages[1], stages[0], *stages[2:]))
    assert caught.value.code == "pipeline.missing-prerequisite"
    assert caught.value.details == {"stage": "cuts", "missing": ["cavities"]}


def test_missing_network_prerequisite_is_explicit() -> None:
    stages = ConstructionPipeline.standard().stages
    with pytest.raises(ResolutionError, match="networks"):
        ConstructionPipeline(stages[:-2] + stages[-1:])


def test_processing_failure_retains_stage_and_subject() -> None:
    def fail(_state: ProcessingContext) -> None:
        raise ResolutionError("Cannot reconcile material", subject_id="wall.example")

    pipeline = ConstructionPipeline(
        (ProcessingStage("material-check", frozenset({"geometry"}), fail),)
    )
    with pytest.raises(ResolutionError) as caught:
        pipeline.run({}, {})
    assert caught.value.subject_id == "wall.example"
    assert caught.value.details["stage"] == "material-check"


def test_stage_context_survives_structured_validation(
    reference_model: JsonObject,
    monkeypatch: pytest.MonkeyPatch,
    validator: ModelValidator,
) -> None:
    def fail(_state: ProcessingContext) -> None:
        raise ResolutionError("Cannot reconcile material", subject_id="wall.north")

    pipeline = ConstructionPipeline(
        (ProcessingStage("material-check", frozenset({"geometry"}), fail),)
    )
    monkeypatch.setattr(ConstructionPipeline, "standard", lambda: pipeline)
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert report.errors[0].to_dict()["details"] == {"stage": "material-check"}
    assert report.errors[0].subject_id == "wall.north"


def test_standard_pipeline_retains_completed_evidence(
    reference_model: JsonObject,
) -> None:
    resolved = ModelResolver(reference_model).resolve()
    state = ConstructionPipeline.standard().run(
        {element.element_id: element for element in resolved.elements},
        resolved.relationships,
    )
    assert state.completed[0] == "cavities"
    assert state.completed[-1] == "circuits"
    assert state.cavity_regions is not None
    assert state.networks is not None


@pytest.mark.parametrize(
    "axes",
    [
        {"x": [2, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]},
        {"x": [1, 0, 0], "y": [1, 0, 0], "z": [0, 0, 1]},
        {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, -1]},
    ],
)
def test_frame_boundary_rejects_distorted_or_left_handed_axes(axes: JsonObject) -> None:
    with pytest.raises(ResolutionError) as caught:
        LocalFrame.from_dict({"origin": [0, 0, 0], **axes})
    assert caught.value.code == "contract.invalid-frame"


def test_frame_contract_roundtrips_rotated_transforms() -> None:
    frame = LocalFrame((100, 200, 300), (1, 0, 0), (0, 1, 0), (0, 0, 1)).adjusted(
        (10, 20, 30), (12, 23, 34)
    )
    restored = LocalFrame.from_dict(frame.to_dict())
    assert restored.point((50, 60, 70)) == pytest.approx(frame.point((50, 60, 70)))
