"""Portable named-view discovery, publication and source guards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
import shutil

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.validate
from ifcopenshell.ifcopenshell_wrapper import TriangulationElement
import pytest

from home_design.build import BuildService
from home_design.errors import HomeDesignError
from home_design.named_views import NamedViews
from home_design.transactions import DesignTransaction


def make_library(root: Path, model_file: Path) -> Path:
    """Create a portable public model and a minimal companion tour."""
    model = root / "house.json"
    shutil.copyfile(model_file, model)
    views = root / "views/house"
    views.mkdir(parents=True)
    (views / "index.json").write_text(
        json.dumps(
            {
                "views": [
                    {
                        "id": "plan",
                        "title": "Plan",
                        "description": "A horizontal section",
                        "file": "plan.json",
                    }
                ]
            }
        )
    )
    (views / "plan.json").write_text(
        json.dumps(
            {
                "camera": {"projection": "orthographic", "preset": "top"},
                "sections": [{"axis": "z", "position": 1200}],
            }
        )
    )
    return model


def test_companion_views_publish_with_owned_caps(
    tmp_path: Path, model_file: Path
) -> None:
    model = make_library(tmp_path, model_file)
    library = NamedViews(model)
    assert library.get("plan")["camera"] == {
        "projection": "orthographic",
        "preset": "top",
    }
    result = BuildService().build(model, tmp_path / "build", tmp_path / "web")
    manifest = json.loads(result.render_manifest.read_text())
    assert manifest["namedViews"] == library.entries
    caps = [mesh for mesh in manifest["meshes"].values() if mesh.get("inspectionCap")]
    assert caps
    for cap in caps:
        assert cap["section"] == {"axis": "z", "position": 1200, "keep": "below"}
        assert manifest["meshes"][cap["capOf"]]["elementId"] == cap["elementId"]
    catalog = json.loads((tmp_path / "web/index.json").read_text())
    published = tmp_path / "web" / catalog["models"][0]["baseUrl"]
    assert (
        published / "render-manifest.json"
    ).read_bytes() == result.render_manifest.read_bytes()
    assert len(json.loads(result.metadata.read_text())["namedViewSources"]) == 2
    before = catalog["models"][0]["version"]
    index = tmp_path / "views/house/index.json"
    data = json.loads(index.read_text())
    data["views"][0]["description"] = "A revised tour description"
    index.write_text(json.dumps(data))
    BuildService().build(model, tmp_path / "build", tmp_path / "web")
    after = json.loads((tmp_path / "web/index.json").read_text())
    assert after["models"][0]["version"] != before
    assert (
        after["models"][0]["sourceRevision"] == catalog["models"][0]["sourceRevision"]
    )


def test_transaction_retains_destination_tour(tmp_path: Path, model_file: Path) -> None:
    model = make_library(tmp_path, model_file)
    change = (
        Path(__file__).resolve().parents[2] / "tests/fixtures/move-window.json"
    )
    receipt = DesignTransaction().apply(
        model, change, build_directory=tmp_path / "build"
    )
    assert receipt["published"] is True
    manifest = json.loads((tmp_path / "build/house/render-manifest.json").read_text())
    assert manifest["namedViews"] == NamedViews(model).entries


def test_duplicate_missing_and_changed_views_fail(
    tmp_path: Path, model_file: Path
) -> None:
    model = make_library(tmp_path, model_file)
    library = NamedViews(model)
    with pytest.raises(HomeDesignError, match="Unknown named view"):
        library.get("missing")
    view = tmp_path / "views/house/plan.json"
    view.write_text("{}")
    with pytest.raises(HomeDesignError, match="Source changed"):
        library.assert_unchanged()
    index = tmp_path / "views/house/index.json"
    data = json.loads(index.read_text())
    data["views"].append(data["views"][0])
    index.write_text(json.dumps(data))
    with pytest.raises(HomeDesignError, match="Duplicate named view"):
        NamedViews(model)
    data["views"] = [dict(data["views"][0], file="../outside.json")]
    index.write_text(json.dumps(data))
    with pytest.raises(HomeDesignError, match="Invalid named-view index"):
        NamedViews(model)


def test_stale_view_references_preserve_previous_build(
    tmp_path: Path, model_file: Path
) -> None:
    model = make_library(tmp_path, model_file)
    service = BuildService()
    result = service.build(model, tmp_path / "build")
    original = result.glb_model.read_bytes()
    (tmp_path / "views/house/plan.json").write_text(
        json.dumps({"isolate": {"ids": ["wall.missing"]}})
    )
    with pytest.raises(HomeDesignError, match="unknown component"):
        service.build(model, tmp_path / "build")
    assert result.glb_model.read_bytes() == original


def test_public_master_suite_tour_is_complete() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "examples/master-suite-gable-house.json"
    library = NamedViews(source)
    assert len(library.entries) == 15
    assert {str(entry["id"]) for entry in library.entries} == {
        "overview",
        "plan",
        "interior",
        "interior-nw",
        "bedroom",
        "bathroom",
        "wall-framing",
        "roof-framing",
        "services",
        "bath-services",
        "utility-services",
        "bedroom-wall-contents",
        "living",
        "utility",
        "deck",
    }
    assert json.loads(source.read_text())["revision"] == 9


@pytest.mark.integration
def test_master_suite_exports_preserve_coordinated_construction(tmp_path: Path) -> None:
    """Exercise the public house's full service checks and native IFC geometry."""
    source = (
        Path(__file__).resolve().parents[2] / "examples/master-suite-gable-house.json"
    )
    result = BuildService().build(source, tmp_path / "build")
    diagnostics = json.loads(result.diagnostics.read_text())
    assert diagnostics["counts"]["error"] == 0
    assert diagnostics["counts"]["warning"] == 0
    resolved = json.loads(result.resolved_model.read_text())
    services = [
        element
        for element in resolved["elements"]
        if element["kind"] in {"serviceDevice", "serviceRoute", "serviceFitting"}
    ]
    assert services
    assert all(
        element["data"]["serviceCoordination"]["interference"]["status"] == "clear"
        for element in services
    )
    manifest = json.loads(result.render_manifest.read_text())
    assert len(manifest["namedViews"]) == 15
    model = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger)
    assert not logger.statements
    for name in (
        "IfcWall",
        "IfcMember",
        "IfcBeam",
        "IfcColumn",
        "IfcOutlet",
        "IfcCableSegment",
        "IfcPipeSegment",
        "IfcPipeFitting",
        "IfcElectricDistributionBoard",
        "IfcSpace",
    ):
        assert model.by_type(name), name
    settings = ifcopenshell.geom.settings()
    for product in model.by_type("IfcProduct"):
        if product.Representation:
            shape = ifcopenshell.geom.create_shape(settings, product)
            assert isinstance(shape, TriangulationElement)
            assert len(shape.geometry.verts) >= 9, product.Name


@pytest.mark.parametrize("stem,room_views", [
    ("master-suite-gable-house", {
        "space.master": "bedroom", "space.ensuite": "bathroom",
        "space.living": "living", "space.utility": "utility",
        "slab.deck.south": "deck",
    }),
    ("hillside-deck-house", {
        "space.lower": "lower-room", "space.upper": "upper-room",
        "slab.lower": "lower-deck", "slab.upper": "upper-deck",
        "slab.spa": "spa-deck", "slab.entry": "entry-landing",
    }),
])
def test_public_room_viewpoints_cover_every_space(
    stem: str, room_views: dict[str, str]
) -> None:
    """Every public room/deck has a nondegenerate interior look viewpoint."""
    from shapely.geometry import Point, Polygon
    from home_design.resolver import ModelResolver

    source = Path(__file__).resolve().parents[2] / "examples" / f"{stem}.json"
    model = json.loads(source.read_text())
    resolved = ModelResolver(model).resolve()
    library = NamedViews(source)
    expected = {
        element.element_id for element in resolved.elements
        if element.kind == "space" or (
            element.kind == "slab"
            and element.data.get("role") in {"deck", "landing"}
        )
    }
    assert set(room_views) == expected
    for element in resolved.elements:
        if element.element_id not in room_views:
            continue
        view = library.get(room_views[element.element_id])
        assert view["navigation"] == "look"
        camera = view["camera"]
        assert isinstance(camera, dict)
        position, target = camera["position"], camera["target"]
        assert isinstance(position, list) and isinstance(target, list)
        assert position != target
        footprint = element.data["footprint"]
        assert isinstance(footprint, dict)
        polygon = Polygon(
            cast(list[list[float]], footprint["outer"]),
            cast(list[list[list[float]]], footprint.get("holes", [])),
        )
        coordinates = cast(list[float], position)
        assert polygon.contains(Point(coordinates[:2]))
        assert polygon.boundary.distance(Point(coordinates[:2])) >= 250
        heights = [point[2] for mesh in element.meshes for point in mesh.vertices]
        floor = (min(heights) if element.kind == "space"
                 else cast(float, element.data["topElevation"]))
        assert 1400 <= coordinates[2] - floor <= 1800
        assert view.get("sections", []) == []


@pytest.mark.parametrize("view", [
    {"navigation": "fly"},
    {"navigation": "look", "camera": {"preset": "top"}},
    {"navigation": "look", "camera": {
        "projection": "orthographic", "position": [0, 0, 1600],
        "target": [1000, 0, 1600],
    }},
])
def test_invalid_navigation_view_rejected(tmp_path: Path, view: dict[str, object]) -> None:
    """Saved look navigation requires an explicit perspective pose."""
    from home_design.visual_render import VisualRenderer

    path = tmp_path / "view.json"
    path.write_text(json.dumps(view))
    with pytest.raises(HomeDesignError):
        VisualRenderer.view(path)
