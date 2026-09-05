"""Cross-adapter verification for the hillside construction example."""

from __future__ import annotations

import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate

from home_design.build import BuildService
from home_design.loader import ModelLoader
from home_design.json_types import JsonObject


def test_construction_components_export_with_valid_ifc_and_selectable_nodes(
    tmp_path: Path, construction_model: JsonObject
) -> None:
    source = tmp_path / "construction.json"
    ModelLoader.write(construction_model, source)
    result = BuildService().build(source, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert len(ifc.by_type("IfcStairFlight")) == 1
    assert len(ifc.by_type("IfcRailing")) == 6
    assert len(ifc.by_type("IfcFooting")) == 16
    assert len(ifc.by_type("IfcGeographicElement")) == 1
    screen = next(
        item for item in ifc.by_type("IfcElement") if item.Tag == "screen.porch.east"
    )
    screen_door = next(
        item for item in ifc.by_type("IfcDoor") if item.Tag == "door.porch.screen"
    )
    assert (
        screen.HasOpenings[0]
        .RelatedOpeningElement.HasFillings[0]
        .RelatedBuildingElement
        == screen_door
    )
    manifest = json.loads(result.render_manifest.read_text(encoding="utf-8"))
    screen_nodes: set[str] = set()
    for screen_id in (
        "screen.porch",
        "screen.porch.west",
        "screen.porch.east",
        "door.porch.screen",
    ):
        nodes = manifest["elements"][screen_id]["nodes"]
        assert nodes and screen_nodes.isdisjoint(nodes)
        screen_nodes.update(nodes)
    for element_id, element in manifest["elements"].items():
        if element["kind"] not in {"load", "detail", "opening"}:
            assert element["nodes"], element_id
    assert manifest["elements"]["stair.entry"]["data"]["clearWidth"] == 1220
    requirement_results = {item["id"]: item for item in manifest["requirementResults"]}
    assert requirement_results["requirement.engineer"]["status"] == "notChecked"
    width_result = requirement_results["requirement.entry-width"]
    assert width_result["status"] == "satisfied"
    assert width_result["checks"][0]["actual"] == 1220
    assert width_result["checks"][0]["expected"] == 1220
    wall_nodes: set[str] = set()
    for storey in ("level.lower", "level.upper"):
        walls = [
            value
            for value in manifest["elements"].values()
            if value["kind"] == "wall" and value["storeyId"] == storey
        ]
        assert len(walls) == 4
        for wall in walls:
            assert wall["defaultVisible"] is True
            assert wall["nodes"]
            assert wall_nodes.isdisjoint(wall["nodes"])
            wall_nodes.update(wall["nodes"])
    for floor_id in ("slab.house.lower", "slab.house.upper"):
        assert manifest["elements"][floor_id]["defaultVisible"] is True
        assert manifest["elements"][floor_id]["nodes"]
