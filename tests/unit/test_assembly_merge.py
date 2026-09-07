"""Recipe updates preserve independent occurrence edits and reject destructive overlap."""

from __future__ import annotations

import pytest

from home_design.assembly_merge import AssemblyMerge
from home_design.errors import ChangeConflictError
from home_design.json_types import JsonObject


def test_recipe_update_preserves_local_name_and_additions_while_changing_geometry() -> (
    None
):
    baseline: JsonObject = {
        "wall": {"name": "Partition", "height": 2400, "notes": None}
    }
    current: JsonObject = {
        "wall": {
            "name": "Office partition",
            "height": 2400,
            "notes": None,
            "finish": "paint",
        }
    }
    proposed: JsonObject = {
        "wall": {"name": "Partition", "height": 2700, "notes": None}
    }
    assert AssemblyMerge().merge(baseline, current, proposed) == {
        "wall": {
            "name": "Office partition",
            "height": 2700,
            "notes": None,
            "finish": "paint",
        }
    }


def test_recipe_update_preserves_local_deletion_when_recipe_leaves_that_object_unchanged() -> (
    None
):
    baseline: JsonObject = {"first": {"name": "First"}, "second": {"name": "Second"}}
    current: JsonObject = {"first": {"name": "First"}}
    proposed: JsonObject = {"first": {"name": "Updated"}, "second": {"name": "Second"}}
    assert AssemblyMerge().merge(baseline, current, proposed) == {
        "first": {"name": "Updated"}
    }


def test_recipe_update_reports_all_conflicts_and_does_not_align_reordered_arrays_by_position() -> (
    None
):
    baseline: JsonObject = {
        "height": 2400,
        "layers": ["finish", "cavity"],
        "optional": None,
    }
    current: JsonObject = {"height": 2500, "layers": ["cavity", "finish"]}
    proposed: JsonObject = {
        "height": 2700,
        "layers": ["finish", "cavity", "skin"],
        "optional": "changed",
    }
    with pytest.raises(ChangeConflictError) as error:
        AssemblyMerge().merge(baseline, current, proposed)
    assert error.value.details == {"paths": ["/height", "/layers", "/optional"]}
    assert current == {"height": 2500, "layers": ["cavity", "finish"]}


def test_recipe_update_distinguishes_boolean_metadata_from_numeric_metadata() -> None:
    """A boolean local edit cannot disappear through Python's equality with integer one."""
    with pytest.raises(ChangeConflictError):
        AssemblyMerge().merge({"property": 1}, {"property": True}, {"property": 2})
