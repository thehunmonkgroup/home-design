"""End-to-end authoring import and consultant-facing artifact acceptance."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

import ifcopenshell
import ifcopenshell.util.element

from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.cli import HomeDesignCli
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.terrain import TerrainSurface


def test_survey_import_generates_valid_revision_checked_change_without_writing_model(
    model_file: Path, tmp_path: Path
) -> None:
    source_bytes = model_file.read_bytes()
    survey = Path(__file__).parents[1] / "fixtures" / "survey.csv"
    change_path = tmp_path / "survey-change.json"
    assert (
        HomeDesignCli().run(
            [
                "import-survey",
                str(model_file),
                str(survey),
                "--id",
                "terrain.survey",
                "--units",
                "m",
                "--origin",
                "1000",
                "2000",
                "0",
                "--output",
                str(change_path),
            ]
        )
        == 0
    )
    assert model_file.read_bytes() == source_bytes
    loader = ModelLoader()
    engine = ChangeEngine(loader)
    result = engine.apply(loader.load(model_file), engine.load_change(change_path))
    terrain = Authoring.object(Authoring.object(result["elements"])["terrain.survey"])
    assert terrain["points"] == [
        [0, 0, 0],
        [10000, 0, 1000],
        [10000, 10000, 2000],
        [0, 10000, 1000],
    ]
    assert TerrainSurface.from_element(terrain).height((5000, 5000)) == 1000
    assert result["revision"] == json.loads(source_bytes)["revision"] + 1


def test_specs_solar_drawings_and_material_layers_survive_complete_build(
    construction_model: JsonObject, tmp_path: Path
) -> None:
    layers = Authoring.array(
        Authoring.object(Authoring.object(construction_model["types"])["type.wall"])[
            "layers"
        ]
    )
    Authoring.object(layers[1])["components"] = [
        {"material": "mat.wood", "fraction": 0.2},
        {"material": "mat.white", "fraction": 0.8},
    ]
    source = tmp_path / "construction.json"
    ModelLoader.write(construction_model, source)
    result = BuildService().build(source, tmp_path / "build", tmp_path / "web")
    ifc = ifcopenshell.open(result.ifc_model)
    assert (
        len(
            [
                item
                for item in ifc.by_type("IfcBeam")
                if ifcopenshell.util.element.get_predefined_type(item) == "BEAM"
            ]
        )
        == 11
    )
    assert len(ifc.by_type("IfcColumn")) == 23
    assert (
        len(ifc.by_type("IfcMember"))
        + len(
            [
                item
                for item in ifc.by_type("IfcBeam")
                if ifcopenshell.util.element.get_predefined_type(item) == "JOIST"
            ]
        )
        == 33
    )
    assert any(layer.LayerThickness == 140 for layer in ifc.by_type("IfcMaterialLayer"))
    assert any(
        properties.Name == "Pset_HomeDesignComposition"
        for properties in ifc.by_type("IfcMaterialProperties")
    )
    slider = next(door for door in ifc.by_type("IfcDoor") if door.Tag == "door.slider")
    data = ifcopenshell.util.element.get_psets(slider)["Pset_HomeDesignData"]
    assert json.loads(data["performance"])["uFactorWm2K"] == 1.4
    assert data["operation"] == "sliding"
    project_data = ifcopenshell.util.element.get_psets(ifc.by_type("IfcProject")[0])[
        "Pset_HomeDesignProject"
    ]
    manifest = json.loads(result.render_manifest.read_text(encoding="utf-8"))
    assert (
        json.loads(project_data["requirements"])
        == manifest["requirements"]
        == construction_model["requirements"]
    )
    assert (
        json.loads(project_data["relationships"]) == construction_model["relationships"]
    )
    schedules = json.loads(result.schedules.read_text(encoding="utf-8"))
    assert len(schedules["openings"]) == 6
    envelope = json.loads(result.envelope.read_text(encoding="utf-8"))
    assert envelope["units"]["geometry"] == "mm"
    assert len(envelope["solarStudies"]) == 2
    assert all(len(study["openings"]) == 6 for study in envelope["solarStudies"])
    assert any(mesh["kind"] == "roof" for mesh in envelope["shadingGeometry"])
    svg = ElementTree.parse(result.drawings)
    assert svg.getroot().tag.endswith("svg")
    assert any(node.text and "South elevation" in node.text for node in svg.iter())
    catalog = json.loads((tmp_path / "web" / "index.json").read_text())
    for name in ("schedules.json", "envelope.json", "drawings.svg"):
        assert (
            tmp_path / "web" / catalog["models"][0]["baseUrl"] / name
        ).read_bytes() == (result.output_directory / name).read_bytes()


def test_solar_cli_uses_explicit_time_and_writes_a_consistent_report(
    construction_model: JsonObject, tmp_path: Path
) -> None:
    source = tmp_path / "construction.json"
    ModelLoader.write(construction_model, source)
    destination = tmp_path / "solar.json"
    assert (
        HomeDesignCli().run(
            [
                "solar",
                str(source),
                "--at",
                "2026-12-21T12:30:00-05:00",
                "--samples",
                "3",
                "--output",
                str(destination),
            ]
        )
        == 0
    )
    study = json.loads(destination.read_text(encoding="utf-8"))
    assert study["samplesPerSide"] == 3
    assert study["altitudeDegrees"] > 0
    assert {opening["sampleCount"] for opening in study["openings"]} == {9}
