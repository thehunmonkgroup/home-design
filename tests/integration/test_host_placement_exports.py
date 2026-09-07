"""IFC and browser contracts for host-relative construction geometry."""

from __future__ import annotations

import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest
import trimesh

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader


def test_hosted_member_exports_geometry_identity_and_source_coordinates(
    reference_model: JsonObject,
    tmp_path: Path,
) -> None:
    """Both adapters receive actual mounted solids and retain the authored host."""
    Authoring.object(reference_model["types"])["type.backing"] = {
        "kind": "memberType",
        "name": "Timber backing",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 38, "depth": 89},
    }
    placement: JsonObject = {
        "kind": "wall",
        "element": "wall.south",
        "surface": "interior",
        "station": 500,
        "height": 450,
        "offset": [0, 0, 50],
    }
    endpoint: JsonObject = {**placement, "offset": [500, 0, 50]}
    Authoring.object(reference_model["elements"])["member.backing"] = {
        "kind": "member",
        "name": "Mounted backing",
        "role": "other",
        "storey": "level.ground",
        "type": "type.backing",
        "axis": [{"host": placement}, {"host": endpoint}],
    }
    source = tmp_path / "hosted.json"
    ModelLoader.write(reference_model, source)
    result = BuildService().build(source, tmp_path / "build")
    manifest = json.loads(result.render_manifest.read_text())
    mounted = manifest["elements"]["member.backing"]
    assert mounted["nodes"]
    assert mounted["data"]["memberLength"] == pytest.approx(500)
    assert mounted["data"]["hostPlacements"] == [placement, endpoint]
    scene = trimesh.load_scene(result.glb_model)
    assert set(mounted["nodes"]) <= set(scene.graph.nodes)
    ifc = ifcopenshell.open(result.ifc_model)
    product = next(
        item for item in ifc.by_type("IfcMember") if item.Tag == "member.backing"
    )
    properties = ifcopenshell.util.element.get_psets(product)
    assert properties["Pset_HomeDesignIdentity"]["CanonicalId"] == "member.backing"
    assert json.loads(properties["Pset_HomeDesignData"]["hostPlacements"]) == [
        placement,
        endpoint,
    ]
    assert product.Representation is not None
    coordinates = (
        product.Representation.Representations[0].Items[0].Coordinates.CoordList
    )
    assert min(point[2] for point in coordinates) == pytest.approx(450 - 89 / 2)
    assert max(point[2] for point in coordinates) == pytest.approx(450 + 89 / 2)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
