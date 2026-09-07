"""Python-to-viewer relationship, property and generated-selection contracts."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace

import trimesh

from home_design.adapters.gltf import GltfExporter
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.member_assemblies import MemberAssemblies
from home_design.resolver import ModelResolver
from home_design.view_navigation import ViewNavigation
from home_design.view_properties import ViewProperties
from home_design.geometry import number, vector3
from home_design.solids import SolidOperations


def test_view_navigation_retains_direct_hosts_rooms_assemblies_and_systems(
    loader: ModelLoader,
) -> None:
    """Viewer links preserve explicit construction meanings without inferring geometric adjacency."""
    path = (
        Path(__file__).resolve().parents[2]
        / "examples/complete-shell-coordination-house.json"
    )
    model = ModelResolver(loader.load(path)).resolve()
    links = ViewNavigation(model).build()
    assert any(
        link.source_id == "electrical.device.flushBox"
        and link.target_id == "electrical.wall.host"
        and link.kind == "host"
        for link in links
    )
    assert any(
        link.source_id == "electrical.cut.flushBox"
        and link.target_id == "electrical.device.flushBox"
        and link.kind == "ownership"
        for link in links
    )
    assert any(
        link.source_id == "roof.main"
        and link.target_id == "assembly.roof-system"
        and link.kind == "assembly"
        for link in links
    )
    assert any(link.source_id == "wall.north" and link.kind == "room" for link in links)
    assert any(
        link.target_id == "electrical.system.test" and link.kind == "system"
        for link in links
    )
    assert any(link.kind == "connection" for link in links)
    assert len({(link.source_id, link.target_id, link.kind) for link in links}) == len(
        links
    )
    assert model.to_dict()["componentReferences"]
    assert model.element("electrical.wall.host").data["length"] == 4000
    child = MemberAssemblies.children(model.element("framing.partition"))[0]
    scoped = {
        "ownerId": "electrical.device.flushBox",
        "targetId": "framing.partition",
        "path": "/elements/electrical.device.flushBox/placement/origin/host/element",
        "role": "placement",
        "scope": {"part": child.data["key"]},
    }
    scoped_model = replace(model, component_references=(scoped,))
    assert any(
        link.source_id == "electrical.device.flushBox"
        and link.target_id == child.element_id
        and link.kind == "host"
        for link in ViewNavigation(scoped_model).build()
    )


def test_generated_members_share_ifc_ids_and_scene_geometry_with_their_parent(
    loader: ModelLoader, tmp_path: Path
) -> None:
    """Generated selection adds metadata and precise nodes without duplicating material meshes."""
    path = (
        Path(__file__).resolve().parents[2]
        / "examples/complete-shell-coordination-house.json"
    )
    model = ModelResolver(loader.load(path)).resolve()
    glb = tmp_path / "model.glb"
    manifest = GltfExporter().export(model, glb, tmp_path / "manifest.json")
    entries = Authoring.object(manifest["elements"])
    scene = trimesh.load_scene(glb)
    expected_meshes = sum(
        mesh.role != "void" for element in model.elements for mesh in element.meshes
    )
    assert len(scene.geometry) == expected_meshes
    count = 0
    for element in model.elements:
        if element.kind not in MemberAssemblies.CHILD_KINDS:
            continue
        parent = Authoring.object(entries[element.element_id])
        children = MemberAssemblies.children(element)
        assert parent["children"] == [child.element_id for child in children]
        all_nodes = set(Authoring.array(parent["nodes"]))
        for child in children:
            count += 1
            entry = Authoring.object(entries[child.element_id])
            assert entry["parentId"] == element.element_id
            assert set(Authoring.array(entry["nodes"])) <= all_nodes
            assert Authoring.array(entry["properties"])
    assert count > 20
    assert len(entries) == len(model.elements) + count
    assert (
        Authoring.object(manifest["navigation"])["format"]
        == "home-design-navigation-0.1"
    )
    assert manifest["propertyFormat"] == "home-design-view-properties-0.1"
    fixture = loader.load(
        Path(__file__).resolve().parents[2]
        / "web/tests/fixtures/component-navigation.json"
    )
    for identity, raw in Authoring.object(fixture["elements"]).items():
        expected = Authoring.object(raw)
        actual = Authoring.object(entries[identity])
        assert {key: value for key, value in actual.items() if key != "data"} == {
            key: value for key, value in expected.items() if key != "data"
        }


def test_repeated_members_expose_individual_axes_and_quantities(
    construction_model: JsonObject,
) -> None:
    """A selected surviving repeat describes its own placement and one stock item."""
    authored = Authoring.object(
        Authoring.object(construction_model["elements"])["framing.porch"]
    )
    authored["omit"] = [0, 1, 3]
    framing = ModelResolver(construction_model).resolve().element("framing.porch")
    child = MemberAssemblies.children(framing)[0]
    assert child.data["memberIndex"] == 2
    assert child.data["memberCount"] == 1
    base = vector3(Authoring.array(framing.data["axis"])[0], "parent axis")
    distribution = vector3(framing.data["distribution"], "distribution")
    spacing = number(framing.data["spacing"], "spacing")
    assert Authoring.array(child.data["axis"])[0] == [
        coordinate + 2 * spacing * distribution[index]
        for index, coordinate in enumerate(base)
    ]
    assert child.data["netVolumeMm3"] == SolidOperations.volume(child.meshes[0])


def test_property_contract_supplies_explicit_units_and_omits_undeclared_numbers() -> (
    None
):
    """Geometry measures cannot be displayed as unitless counts or guessed from arbitrary fields."""
    source: JsonObject = {
        "netVolumeMm3": 125000000,
        "centerlineLengthMm": 2450,
        "memberCount": 6,
        "role": "distributionPanel",
        "customDepth": 42,
        "section": {"width": 40, "depth": 140},
    }
    properties = {
        Authoring.object(value)["id"]: Authoring.object(value)
        for value in ViewProperties.describe(source)
    }
    assert properties["/netVolumeMm3"]["unit"] == "mm3"
    assert properties["/centerlineLengthMm"]["unit"] == "mm"
    assert properties["/memberCount"]["unit"] == "count"
    assert properties["/role"]["value"] == "Distribution panel"
    assert properties["/section/width"]["label"] == "Stock width"
    assert "/customDepth" not in properties
