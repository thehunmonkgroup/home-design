"""Prepared operations preserve shared definitions and explicit integration intent."""

from __future__ import annotations

from copy import deepcopy

import pytest

from home_design.change_preparation import ChangePreparation
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import ChangeConflictError, HomeDesignError
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader


def test_local_type_changes_one_occurrence_and_guards_source(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """A local construction edit preserves the shared stock and all other users."""
    original = deepcopy(reference_model)
    change = ChangePreparation(reference_model, loader).local_type(
        "wall.north",
        "type.north",
        (("/name", "North wall specification"), ("/layers/0/thickness", 25)),
    )
    result = ChangeEngine(loader).apply(reference_model, change)
    elements = Authoring.object(result["elements"])
    assert Authoring.object(elements["wall.north"])["type"] == "type.north"
    for identity in ("wall.south", "wall.east", "wall.west"):
        assert elements[identity] == Authoring.object(original["elements"])[identity]
    assert reference_model == original
    original_type = str(
        Authoring.object(Authoring.object(original["elements"])["wall.north"])["type"]
    )
    assert (
        Authoring.object(result["types"])[original_type]
        == Authoring.object(original["types"])[original_type]
    )
    Authoring.object(reference_model["types"])["type.north"] = {}
    with pytest.raises(ChangeConflictError, match="absent path"):
        ChangeEngine(loader).apply(reference_model, change)


def test_preparation_rejects_bad_identity_and_pointer(
    reference_model: JsonObject,
) -> None:
    preparation = ChangePreparation(reference_model)
    with pytest.raises(HomeDesignError, match="ID format"):
        preparation.local_type("wall.north", "bad/id", ())
    with pytest.raises(HomeDesignError, match="component kind"):
        preparation.local_type("wall.north", "type.new", (("/kind", "windowType"),))
    with pytest.raises(HomeDesignError, match="Cannot edit type field"):
        preparation.local_type("wall.north", "type.new", (("/name/child", "invalid"),))


class MountedGraph:
    """Minimal source graph for explicit rehosting and removal behavior."""

    @staticmethod
    def source() -> JsonObject:
        return {
            "revision": 1,
            "elements": {
                "wall.old": {"kind": "wall", "name": "Old host"},
                "wall.new": {"kind": "wall", "name": "New host"},
                "accessory.box": {
                    "kind": "accessory",
                    "name": "wall.old",
                    "properties": {"manufacturerLabel": "wall.old"},
                    "placement": {
                        "origin": {
                            "host": {
                                "kind": "wall",
                                "element": "wall.old",
                                "station": 1200,
                                "height": 900,
                                "surface": "interior",
                            }
                        }
                    },
                    "occupies": {"regions": [{"host": "wall.old", "layer": 1}]},
                },
                "cut.box": {
                    "kind": "penetration",
                    "host": "wall.old",
                    "owner": "accessory.box",
                    "placement": {
                        "origin": {
                            "host": {
                                "kind": "wall",
                                "element": "wall.old",
                                "station": 1200,
                                "height": 900,
                                "surface": "interior",
                            }
                        }
                    },
                },
                "accessory.other": {
                    "kind": "accessory",
                    "placement": {
                        "origin": {
                            "host": {
                                "kind": "wall",
                                "element": "wall.old",
                                "station": 2400,
                                "height": 900,
                                "surface": "interior",
                            }
                        }
                    },
                },
            },
            "relationships": {
                "connection.box": {
                    "kind": "attaches",
                    "primary": "wall.old",
                    "attached": "accessory.box",
                }
            },
        }


def test_rehost_updates_mount_ownership_cuts_and_durable_connection(
    loader: ModelLoader,
) -> None:
    """Rehosting uses typed paths and preserves unrelated placements and labels."""
    source = MountedGraph.source()
    original = deepcopy(source)
    change = ChangePreparation(source, loader).rehost("accessory.box", "wall.new")
    candidate = ChangeEngine(loader).candidate(source, change)
    elements = Authoring.object(candidate["elements"])
    box = Authoring.object(elements["accessory.box"])
    assert (
        Authoring.object(
            Authoring.object(Authoring.object(box["placement"])["origin"])["host"]
        )["element"]
        == "wall.new"
    )
    assert (
        Authoring.object(
            Authoring.array(Authoring.object(box["occupies"])["regions"])[0]
        )["host"]
        == "wall.new"
    )
    assert Authoring.object(elements["cut.box"])["host"] == "wall.new"
    assert (
        Authoring.object(
            Authoring.object(candidate["relationships"])["connection.box"]
        )["primary"]
        == "wall.new"
    )
    assert box["name"] == "wall.old"
    assert box["properties"] == {"manufacturerLabel": "wall.old"}
    assert (
        elements["accessory.other"]
        == Authoring.object(original["elements"])["accessory.other"]
    )
    assert source == original


def test_removal_exposes_incoming_paths_and_requires_explicit_selection(
    loader: ModelLoader,
) -> None:
    """No cascade silently removes a connected cut or relationship."""
    source = MountedGraph.source()
    preparation = ChangePreparation(source, loader)
    with pytest.raises(ChangeConflictError) as caught:
        preparation.remove("accessory.box")
    assert caught.value.code == "change.removal-references"
    incoming = Authoring.array(caught.value.details["incoming"])
    assert {str(Authoring.object(item)["ownerId"]) for item in incoming} == {
        "cut.box",
        "connection.box",
    }
    change = preparation.remove("accessory.box", ("cut.box", "connection.box"))
    candidate = ChangeEngine(loader).candidate(source, change)
    assert "accessory.box" not in Authoring.object(candidate["elements"])
    assert Authoring.object(candidate["elements"])["accessory.other"]
    assert ModelIndex(candidate).diagnostics() == []
