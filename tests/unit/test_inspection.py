"""Authoring inspection remains compact and useful for incomplete models."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import ifcopenshell

from home_design.adapters.ifc import IfcExporter
from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.inspection import InspectionPage, ModelInspection
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver


def test_inspection_reads_invalid_source_and_missing_references(
    reference_model: JsonObject,
) -> None:
    """A broken type remains inspectable without resolving building geometry."""
    wall = Authoring.object(Authoring.object(reference_model["elements"])["wall.north"])
    wall["type"] = "type.missing"
    inspection = ModelInspection(reference_model)
    inspected = inspection.source("wall.north", fields=("/type", "/top"))
    assert Authoring.object(inspected["fields"])["/type"] == "type.missing"
    outgoing = Authoring.array(
        inspection.references("wall.north", InspectionPage(), "outgoing")["items"]
    )
    edge = next(
        Authoring.object(item)
        for item in outgoing
        if Authoring.object(item)["role"] == "type"
    )
    assert edge["targetExists"] is False
    assert edge["path"] == "/elements/wall.north/type"
    assert "meshes" not in inspected


def test_public_partition_incoming_edges_include_hosts_ownership_and_interfaces(
    loader: ModelLoader,
) -> None:
    """The public serviced wall exposes its entire authored reference neighborhood."""
    source = Path(__file__).resolve().parents[2] / "examples/assemblies.json"
    inspection = ModelInspection(loader.load(source))
    incoming = inspection.references(
        "assembly.interior-wet-wall.electrical.wall.host",
        InspectionPage(100),
        "incoming",
    )
    assert int(str(incoming["total"])) >= 10
    edges = [Authoring.object(item) for item in Authoring.array(incoming["items"])]
    assert {str(edge["role"]) for edge in edges} >= {
        "placement",
        "ownership",
        "connection",
        "requirement",
    }
    assert any(
        edge["ownerId"] == "assembly.interior-wet-wall.accessory.service.ledge"
        for edge in edges
    )
    assert any(
        edge["ownerId"] == "assembly.interior-wet-wall.interface.sleeve"
        and edge["role"] == "connection"
        for edge in edges
    )
    assert any(edge.get("scope") == {"layer": "layer.legacy.1"} for edge in edges)


def test_resolved_framing_defers_member_details_to_bounded_pages(
    loader: ModelLoader,
) -> None:
    """Default framing measurements stay compact while every member remains discoverable."""
    source = Path(__file__).resolve().parents[2] / "examples/assemblies.json"
    resolved = ModelResolver(loader.load(source)).resolve()
    identity = "assembly.exterior-wall.framing.wall"
    summary = ModelInspection.resolved(resolved.element(identity))
    assert "members" not in Authoring.object(summary["data"])
    assert Authoring.object(summary["generatedParts"])["total"] == 18
    page = ModelInspection.parts(resolved, identity, InspectionPage(3))
    assert page["total"] == 18
    assert page["nextOffset"] == 3
    assert len(Authoring.array(page["items"])) == 3
    assert "members" in Authoring.object(
        ModelInspection.resolved(resolved.element(identity), True)["data"]
    )


def test_dependency_queries_distinguish_semantics_and_handle_cycles() -> None:
    """Connection loops do not become geometry cycles or unbounded traversal."""
    model: JsonObject = {
        "elements": {
            "part.a": {"kind": "hardware", "participants": [{"element": "part.b"}]},
            "part.b": {"kind": "hardware", "participants": [{"element": "part.a"}]},
            "part.c": {
                "kind": "accessory",
                "placement": {
                    "origin": {"host": {"kind": "component", "element": "part.a"}}
                },
            },
            "part.d": {
                "kind": "accessory",
                "placement": {
                    "origin": {"host": {"kind": "component", "element": "part.c"}}
                },
            },
        }
    }
    inspection = ModelInspection(model)
    assert inspection.index.dependency_cycles() == []
    dependents = inspection.closure(
        "part.a", InspectionPage(), "incoming", 1, "placement"
    )
    assert [
        Authoring.object(item)["id"] for item in Authoring.array(dependents["items"])
    ] == ["part.c"]
    assert dependents["depthLimited"] is True
    deep = inspection.closure("part.a", InspectionPage(), "incoming", 2, "placement")
    assert {
        str(Authoring.object(item)["id"]) for item in Authoring.array(deep["items"])
    } == {"part.c", "part.d"}
    all_edges = inspection.closure("part.a", InspectionPage(), "incoming", 64)
    assert all_edges["total"] == 3
    assert all_edges["depthLimited"] is False


def test_shared_type_users_include_stock_and_occurrences(
    reference_model: JsonObject,
) -> None:
    """Type edits expose every direct user while source queries preserve identity."""
    elements = Authoring.object(reference_model["elements"])
    elements["window.second"] = deepcopy(elements["window.north"])
    inspection = ModelInspection(reference_model)
    users = inspection.type_users("window.north", InspectionPage())
    assert users["typeId"] == "windowType.casement-1500x1200"
    assert {
        str(Authoring.object(item)["id"]) for item in Authoring.array(users["items"])
    } == {"window.north", "window.second"}
    with pytest.raises(HomeDesignError, match="no reusable type"):
        inspection.type_users("opening.window.north", InspectionPage())


def test_inspection_pagination_filters_and_ambiguity(
    reference_model: JsonObject,
) -> None:
    """Bounded discovery makes omitted matches and duplicate IDs explicit."""
    inspection = ModelInspection(reference_model)
    summary = inspection.summary(InspectionPage(2), kind="wall", query="wall")
    assert len(Authoring.array(summary["elements"])) == 2
    page = Authoring.object(summary["page"])
    assert page["total"] == 4
    assert page["nextOffset"] == 2
    second = inspection.summary(InspectionPage(2, 2), kind="wall", query="wall")
    assert Authoring.object(second["page"])["nextOffset"] is None
    assert summary["elements"] != second["elements"]
    Authoring.object(reference_model["types"])["wall.north"] = {"kind": "wallType"}
    ambiguous = ModelInspection(reference_model)
    with pytest.raises(HomeDesignError, match="ambiguous"):
        ambiguous.source("wall.north")
    assert ambiguous.source("wall.north", "elements")["kind"] == "wall"
    with pytest.raises(HomeDesignError, match="selected field"):
        inspection.source("wall.north", fields=("/unknown",))
    with pytest.raises(HomeDesignError, match="depth"):
        inspection.closure("wall.north", InspectionPage(), "incoming", 0)
    with pytest.raises(HomeDesignError, match="limit"):
        InspectionPage(0)


def test_generated_inspection_uses_ifc_child_identity(
    reference_model: JsonObject,
    tmp_path: Path,
) -> None:
    """Array members use the same scoped identities in inspection and IFC expansion."""
    Authoring.object(reference_model["types"])["type.joist"] = {
        "kind": "memberType",
        "name": "Joist stock",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 40, "depth": 140},
    }
    Authoring.object(reference_model["elements"])["framing.test"] = {
        "kind": "framing",
        "name": "Test joists",
        "type": "type.joist",
        "role": "joist",
        "axis": [{"point": [0, 0, 0]}, {"point": [1000, 0, 0]}],
        "count": 3,
        "omit": [1],
        "spacing": 600,
        "distribution": [0, 1, 0],
    }
    resolved = ModelResolver(reference_model).resolve()
    inspected = ModelInspection.parts(resolved, "framing.test", InspectionPage())
    identities = {
        str(Authoring.object(item)["id"])
        for item in Authoring.array(inspected["items"])
    }
    destination = tmp_path / "members.ifc"
    IfcExporter().export(resolved, destination)
    exported = ifcopenshell.open(str(destination))
    native = {
        str(element.Tag)
        for element in exported.by_type("IfcElement")
        if str(element.Tag).startswith("framing.test/member/")
    }
    assert identities == native == {"framing.test/member/0", "framing.test/member/2"}
    assert (
        ModelInspection.parts(resolved, "framing.test", InspectionPage(), "2")["id"]
        == "framing.test/member/2"
    )
    assert all(
        "meshes" not in Authoring.object(item)
        for item in Authoring.array(inspected["items"])
    )
    assert "meshes" in ModelInspection.parts(
        resolved, "framing.test", InspectionPage(), "2", True
    )
    with pytest.raises(HomeDesignError, match="no scoped"):
        ModelInspection.parts(resolved, "wall.north", InspectionPage())
