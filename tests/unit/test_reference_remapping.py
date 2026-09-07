"""Typed reference remapping preserves semantic overrides and unrelated text."""

from __future__ import annotations

from home_design.construction import Authoring
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject
from home_design.reference_remapping import ReferenceRemapping


def test_remapping_rebinds_opening_override_keys_and_their_nested_type_reference() -> (
    None
):
    """Cloning a wall package keeps its opening-specific stock decision on the cloned opening."""
    source: JsonObject = {
        "elements": {
            "frame": {
                "kind": "wallFraming",
                "host": "wall",
                "type": "layout",
                "openingOverrides": {"opening.old": {"headerType": "header.old"}},
                "properties": {"element": "opening.old"},
                "externalIds": {"element": "opening.old"},
            }
        }
    }
    index = ModelIndex(source)
    opening = next(
        reference
        for reference in index.references
        if reference.target_id == "opening.old"
    )
    assert opening.storage == "key"
    assert opening.expected_kinds == ("opening",)
    assert (
        len(
            [
                reference
                for reference in index.references
                if reference.target_id == "opening.old"
            ]
        )
        == 1
    )
    result = ReferenceRemapping.apply(
        source,
        {"opening.old": "opening.new", "header.old": "header.new", "wall": "wall.new"},
    )
    frame = Authoring.object(Authoring.object(result["elements"])["frame"])
    assert frame["openingOverrides"] == {"opening.new": {"headerType": "header.new"}}
    assert frame["host"] == "wall.new"
    assert frame["properties"] == {"element": "opening.old"}
    assert frame["externalIds"] == {"element": "opening.old"}
    assert (
        Authoring.object(Authoring.object(source["elements"])["frame"])["host"]
        == "wall"
    )
