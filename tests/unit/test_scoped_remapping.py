"""Generated references follow copied owners while scoped authored aliases remain stable."""

from __future__ import annotations

from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.scoped_remapping import ScopedRemapping


def test_scoped_remapping_handles_default_roof_faces_and_opening_member_tokens() -> (
    None
):
    source: JsonObject = {
        "elements": {
            "roof.old": {"kind": "roof", "geometry": {"kind": "parametric"}},
            "roof.alias": {
                "kind": "roof",
                "geometry": {
                    "kind": "parametric",
                    "faceIds": {"face.shed": "roof.alias.face.local"},
                },
            },
            "opening.old": {"kind": "opening"},
            "frame.old": {
                "kind": "wallFraming",
                "memberIds": {
                    "run/top/roof.old.face.gable.south": "run/top/roof.old.face.gable.south"
                },
                "memberOverrides": {"run/opening/opening.old/header": {"omit": True}},
            },
            "rafter": {
                "kind": "planarFraming",
                "host": "roof.old",
                "face": "roof.old.face.gable.south",
            },
            "alias.rafter": {
                "kind": "planarFraming",
                "host": "roof.alias",
                "face": "roof.alias.face.local",
            },
            "hardware": {
                "kind": "connector",
                "placement": {
                    "host": {
                        "kind": "member",
                        "element": "frame.old",
                        "part": "run/opening/opening.old/header",
                    }
                },
                "properties": {"face": "roof.old.face.gable.south", "host": "roof.old"},
            },
        }
    }
    ScopedRemapping(
        source,
        {
            "roof.old": "roof.copy",
            "roof.alias": "roof.aliasCopy",
            "opening.old": "opening.copy",
        },
    ).apply()
    elements = Authoring.object(source["elements"])
    assert Authoring.object(elements["rafter"])["face"] == "roof.copy.face.gable.south"
    assert Authoring.object(elements["alias.rafter"])["face"] == "roof.alias.face.local"
    assert Authoring.object(elements["frame.old"])["memberIds"] == {
        "run/top/roof.copy.face.gable.south": "run/top/roof.copy.face.gable.south"
    }
    assert Authoring.object(elements["frame.old"])["memberOverrides"] == {
        "run/opening/opening.copy/header": {"omit": True}
    }
    hardware = Authoring.object(elements["hardware"])
    assert (
        Authoring.object(Authoring.object(hardware["placement"])["host"])["part"]
        == "run/opening/opening.copy/header"
    )
    assert (
        Authoring.object(hardware["properties"])["face"] == "roof.old.face.gable.south"
    )
