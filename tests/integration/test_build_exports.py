"""Integration tests across resolution, IFC, GLB, and manifest adapters."""

from __future__ import annotations

import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest
import trimesh

from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService


@pytest.mark.integration
def test_build_produces_complete_cross_adapter_contract(
    model_file: Path, tmp_path: Path
) -> None:
    output = tmp_path / "build"
    web_assets = tmp_path / "web-assets"
    result = BuildService().build(model_file, output, web_assets)
    assert all(
        path.is_file()
        for path in (
            result.resolved_model,
            result.ifc_model,
            result.glb_model,
            result.render_manifest,
            result.diagnostics,
            result.metadata,
        )
    )
    assert (web_assets / "model.glb").read_bytes() == result.glb_model.read_bytes()
    assert (
        web_assets / "render-manifest.json"
    ).read_bytes() == result.render_manifest.read_bytes()

    manifest = json.loads(result.render_manifest.read_text(encoding="utf-8"))
    scene = trimesh.load_scene(result.glb_model)
    declared_nodes = {
        node for element in manifest["elements"].values() for node in element["nodes"]
    }
    assert declared_nodes <= set(scene.graph.nodes)
    assert all(
        not any(character in node for character in "[] .:/") for node in declared_nodes
    )
    assert manifest["elements"]["opening.window.north"]["nodes"] == []
    assert all(mesh.is_watertight for mesh in scene.geometry.values())
    assert all(mesh.is_winding_consistent for mesh in scene.geometry.values())
    assert all(mesh.volume > 0 for mesh in scene.geometry.values())

    ifc = ifcopenshell.open(result.ifc_model)
    assert ifc.schema == "IFC4"
    assert len(ifc.by_type("IfcWall")) == 4
    assert len(ifc.by_type("IfcOpeningElement")) == 2
    assert len(ifc.by_type("IfcRelVoidsElement")) == 2
    assert len(ifc.by_type("IfcRelFillsElement")) == 2
    assert len(ifc.by_type("IfcRelSpaceBoundary")) == 4
    assert len(ifc.by_type("IfcRelConnectsPathElements")) == 4
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []


@pytest.mark.integration
def test_build_is_semantically_deterministic(model_file: Path, tmp_path: Path) -> None:
    first = BuildService().build(model_file, tmp_path / "first")
    second = BuildService().build(model_file, tmp_path / "second")
    assert first.resolved_model.read_bytes() == second.resolved_model.read_bytes()
    assert first.render_manifest.read_bytes() == second.render_manifest.read_bytes()
    assert first.glb_model.read_bytes() == second.glb_model.read_bytes()
    assert first.metadata.read_bytes() == second.metadata.read_bytes()
    first_ifc = ifcopenshell.open(first.ifc_model)
    second_ifc = ifcopenshell.open(second.ifc_model)
    first_guids = sorted(entity.GlobalId for entity in first_ifc.by_type("IfcRoot"))
    second_guids = sorted(entity.GlobalId for entity in second_ifc.by_type("IfcRoot"))
    assert first_guids == second_guids
    assert IfcExporter.stable_guid("wall.north") in first_guids


@pytest.mark.integration
def test_every_canonical_relationship_reaches_ifc(
    model_file: Path, tmp_path: Path
) -> None:
    result = BuildService().build(model_file, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    root_by_guid = {entity.GlobalId: entity for entity in ifc.by_type("IfcRoot")}
    source = json.loads(model_file.read_text(encoding="utf-8"))
    for relationship_id in source["relationships"]:
        guid = IfcExporter.stable_guid(relationship_id)
        assert guid in root_by_guid, relationship_id
