"""Recipe discovery, ordinary changesets and guarded publication through the installed CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from home_design.changes import ChangeEngine
from home_design.cli import main
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.migrations import ModelMigration
from home_design.recipe_catalog import RecipeCatalog


def test_recipe_cli_discovers_instantiates_duplicates_and_adapts(
    reference_model: JsonObject,
    loader: ModelLoader,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same discover/prepare/transact/inspect commands work without direct recipe API use."""
    model = tmp_path / "home.json"
    ModelLoader.write(
        ChangeEngine(loader).apply(
            reference_model, ModelMigration(loader).prepare(reference_model)
        ),
        model,
    )
    assert main(["recipes"]) == 0
    recipes = json.loads(capsys.readouterr().out)["recipes"]
    assert len(recipes) == 11
    assert {"recipe.exterior-wall", "recipe.insulated-roof", "recipe.complete-deck"} <= {
        recipe["id"] for recipe in recipes
    }
    assert main(["recipes", "serviced-partition", "--object", "stock.stud"]) == 0
    assert json.loads(capsys.readouterr().out)["registry"] == "types"
    original = model.read_bytes()
    change = tmp_path / "instantiate.json"
    assert (
        main(
            [
                "prepare",
                str(model),
                "instantiate",
                "--object",
                "assembly.office",
                "--recipe",
                "serviced-partition",
                "--bind",
                "binding.storey=level.ground",
                "--output",
                str(change),
            ]
        )
        == 0
    )
    receipt = capsys.readouterr().out
    assert len(receipt) < 1000
    assert json.loads(receipt)["baseRevision"] == json.loads(original)["revision"]
    assert json.loads(receipt)["operationCount"] > 10
    assert "operations" in json.loads(change.read_text())
    assert model.read_bytes() == original
    assert main(["transact", str(model), str(change)]) == 0
    assert json.loads(capsys.readouterr().out)["published"] is True
    assert (
        main(
            [
                "inspect",
                str(model),
                "--object",
                "assembly.office",
                "--view",
                "assembly",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    inspection = json.loads(capsys.readouterr().out)
    assert "authored" not in inspection
    assert (
        inspection["assembly"]["connectionPoints"]["entry"]["element"]
        == "assembly.office.device.box"
    )
    assert inspection["assembly"]["objects"]["nextOffset"] == 1
    duplicate = tmp_path / "duplicate.json"
    assert (
        main(
            [
                "prepare",
                str(model),
                "duplicate",
                "--object",
                "assembly.office",
                "--new-object",
                "assembly.study",
                "--recipe",
                "serviced-partition",
                "--param",
                "origin=[18000,0]",
                "--output",
                str(duplicate),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["transact", str(model), str(duplicate)]) == 0
    assert json.loads(capsys.readouterr().out)["published"] is True
    adapted = tmp_path / "adapt.json"
    assert (
        main(
            [
                "prepare",
                str(model),
                "adapt",
                "--object",
                "assembly.study",
                "--param",
                "width=4800",
                "--output",
                str(adapted),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["transact", str(model), str(adapted), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["written"] is False
    current = model.read_bytes()
    assert (
        main(
            [
                "prepare",
                str(model),
                "adapt",
                "--object",
                "assembly.study",
                "--param",
                "width=4800",
                "--param",
                "width=5200",
            ]
        )
        == 1
    )
    assert (
        json.loads(capsys.readouterr().err)["error"]["code"] == "recipe.duplicate-input"
    )
    recipe_path = tmp_path / "recipe.json"
    ModelLoader.write(RecipeCatalog.load("serviced-partition").source, recipe_path)
    recipe_bytes = recipe_path.read_bytes()
    assert (
        main(
            [
                "prepare",
                str(model),
                "instantiate",
                "--object",
                "assembly.third",
                "--recipe",
                str(recipe_path),
                "--output",
                str(recipe_path),
            ]
        )
        == 1
    )
    assert (
        json.loads(capsys.readouterr().err)["error"]["code"] == "recipe.output-source"
    )
    assert recipe_path.read_bytes() == recipe_bytes
    assert model.read_bytes() == current
