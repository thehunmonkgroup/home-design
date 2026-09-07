"""Declarative assembly recipe inputs reject ambiguous or underspecified edits."""

from __future__ import annotations

from copy import deepcopy

import pytest

from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject
from home_design.recipes import AssemblyRecipe
from home_design.assembly_instantiation import AssemblyInstantiation
from home_design.changes import ChangeEngine
from home_design.loader import ModelLoader
from home_design.migrations import ModelMigration
from home_design.assembly_updates import AssemblyUpdates
from home_design.assembly_duplication import AssemblyDuplication
from home_design.locators import LocatorResolver
from home_design.resolver import ModelResolver


class RecipeFixture:
    """Provide a minimal named assembly and parameterized shared construction anchor."""

    @staticmethod
    def source() -> JsonObject:
        """Return a generic package whose external storey must be bound explicitly."""
        return {
            "recipeVersion": "0.1",
            "modelVersion": "0.2",
            "id": "recipe.test",
            "name": "Test assembly",
            "assembly": "assembly.root",
            "parameters": {
                "origin": {
                    "valueType": "point2",
                    "description": "Plan origin in millimetres",
                    "default": [0, 0],
                    "targets": ["/anchors/anchor.origin/position"],
                }
            },
            "bindings": {
                "level.target": {
                    "registry": "levels",
                    "kind": "storey",
                    "description": "Target building storey",
                }
            },
            "objects": {
                "anchors": {
                    "anchor.origin": {
                        "kind": "point2",
                        "name": "Assembly origin",
                        "level": "level.target",
                        "position": [0, 0],
                    }
                },
                "elements": {
                    "assembly.root": {
                        "kind": "assembly",
                        "name": "Example",
                        "assemblyType": "other",
                    }
                },
            },
        }


def test_recipe_parameters_preserve_source_and_bind_digest_to_the_document() -> None:
    source = RecipeFixture.source()
    original = deepcopy(source)
    recipe = AssemblyRecipe(source)
    result, parameters = recipe.parameterized({"origin": [1500, 2500]})
    assert parameters == {"origin": [1500, 2500]}
    assert Authoring.object(Authoring.object(result["anchors"])["anchor.origin"])[
        "position"
    ] == [1500, 2500]
    assert source == original
    assert recipe.parameters({}) == {"origin": [0, 0]}
    changed = deepcopy(source)
    changed["description"] = "Changed recipe contract"
    assert AssemblyRecipe(changed).digest != recipe.digest


@pytest.mark.parametrize(
    "supplied",
    [
        {"missing": 2},
        {"origin": [1]},
        {"origin": [True, 2]},
        {"origin": [float("nan"), 2]},
    ],
)
def test_recipe_rejects_unknown_or_mistyped_parameters(supplied: JsonObject) -> None:
    with pytest.raises(HomeDesignError):
        AssemblyRecipe(RecipeFixture.source()).parameters(supplied)


def test_recipe_rejects_undeclared_external_references_and_overlapping_targets() -> (
    None
):
    source = RecipeFixture.source()
    source["bindings"] = {}
    with pytest.raises(HomeDesignError) as missing:
        AssemblyRecipe(source)
    assert missing.value.code == "recipe.undeclared-binding"
    source = RecipeFixture.source()
    parameters = Authoring.object(source["parameters"])
    parameters["xPosition"] = {
        "valueType": "length",
        "description": "Conflicting target",
        "targets": ["/anchors/anchor.origin/position/0"],
    }
    with pytest.raises(HomeDesignError) as overlap:
        AssemblyRecipe(source)
    assert overlap.value.code == "recipe.parameter-target"


def test_recipe_instantiation_is_an_ordinary_guarded_changeset(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """Expansion namespaces canonical objects and records the exact external and parameter intent."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    original = deepcopy(model)
    recipe = AssemblyRecipe(RecipeFixture.source())
    expansion = AssemblyInstantiation(model, recipe, loader)
    change = expansion.prepare(
        "assembly.example", {"origin": [16000, 0]}, {"level.target": "level.ground"}
    )
    result = ChangeEngine(loader).apply(model, change)
    assert model == original
    assembly = Authoring.object(
        Authoring.object(result["elements"])["assembly.example"]
    )
    provenance = Authoring.object(assembly["recipeInstance"])
    assert provenance["recipeDigest"] == recipe.digest
    assert provenance["parameters"] == {"origin": [16000, 0]}
    anchor = Authoring.object(
        Authoring.object(result["anchors"])["assembly.example.anchor.origin"]
    )
    assert anchor["position"] == [16000, 0]
    assert anchor["level"] == "level.ground"
    with pytest.raises(HomeDesignError) as conflict:
        AssemblyInstantiation(result, recipe, loader).prepare(
            "assembly.example", {}, {"level.target": "level.ground"}
        )
    assert conflict.value.code == "recipe.identity-conflict"


def test_recipe_binding_rejects_a_target_of_the_wrong_registry(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """A recipe cannot reinterpret a wall ID as a construction datum."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    expansion = AssemblyInstantiation(
        model, AssemblyRecipe(RecipeFixture.source()), loader
    )
    with pytest.raises(HomeDesignError) as error:
        expansion.prepare("assembly.example", {}, {"level.target": "wall.north"})
    assert error.value.code == "recipe.binding-target"


def test_recipe_adaptation_preserves_local_names_and_recorded_overrides(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """A parameter update changes its intended anchor while retaining occurrence edits."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    definition = RecipeFixture.source()
    definition["overridePaths"] = ["/elements/assembly.root/name"]
    recipe = AssemblyRecipe(definition)
    created = AssemblyInstantiation(model, recipe, loader).prepare(
        "assembly.example",
        {},
        {"level.target": "level.ground"},
        {"/elements/assembly.root/name": "Configured name"},
    )
    model = ChangeEngine(loader).apply(model, created)
    anchor = Authoring.object(
        Authoring.object(model["anchors"])["assembly.example.anchor.origin"]
    )
    anchor["name"] = "Local origin label"
    original = deepcopy(model)
    change = AssemblyUpdates(model, recipe, loader).prepare(
        "assembly.example", {"origin": [16000, 2500]}
    )
    result = ChangeEngine(loader).apply(model, change)
    assert model == original
    anchor = Authoring.object(
        Authoring.object(result["anchors"])["assembly.example.anchor.origin"]
    )
    assert anchor["name"] == "Local origin label"
    assert anchor["position"] == [16000, 2500]
    assembly = Authoring.object(
        Authoring.object(result["elements"])["assembly.example"]
    )
    assert assembly["name"] == "Configured name"
    cleared = AssemblyUpdates(result, recipe, loader).prepare(
        "assembly.example", clear_overrides=("/elements/assembly.root/name",)
    )
    result = ChangeEngine(loader).apply(result, cleared)
    assert (
        Authoring.object(Authoring.object(result["elements"])["assembly.example"])[
            "name"
        ]
        == "Example"
    )


def test_recipe_upgrade_requires_previous_digest_and_reports_local_overlap(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """An updated template cannot overwrite a renamed occurrence under an unrelated recipe digest."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    old_recipe = AssemblyRecipe(RecipeFixture.source())
    model = ChangeEngine(loader).apply(
        model,
        AssemblyInstantiation(model, old_recipe, loader).prepare(
            "assembly.example", {}, {"level.target": "level.ground"}
        ),
    )
    Authoring.object(Authoring.object(model["elements"])["assembly.example"])[
        "name"
    ] = "User name"
    definition = RecipeFixture.source()
    Authoring.object(
        Authoring.object(Authoring.object(definition["objects"])["elements"])[
            "assembly.root"
        ]
    )["name"] = "New template name"
    updated = AssemblyRecipe(definition)
    with pytest.raises(HomeDesignError) as mismatch:
        AssemblyUpdates(model, updated, loader).prepare("assembly.example")
    assert mismatch.value.code == "recipe.digest-mismatch"
    with pytest.raises(HomeDesignError) as conflict:
        AssemblyUpdates(model, updated, loader).prepare(
            "assembly.example", previous_recipe=old_recipe
        )
    assert conflict.value.code == "recipe.update-conflict"
    assert "/elements/assembly.example/name" in Authoring.array(
        conflict.value.details["paths"]
    )


def test_recipe_duplication_changes_only_the_copy_and_remains_adaptable(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """A parameterized clone retains local labels and binds future updates to its own object IDs."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    recipe = AssemblyRecipe(RecipeFixture.source())
    model = ChangeEngine(loader).apply(
        model,
        AssemblyInstantiation(model, recipe, loader).prepare(
            "assembly.original", {}, {"level.target": "level.ground"}
        ),
    )
    Authoring.object(Authoring.object(model["elements"])["assembly.original"])[
        "name"
    ] = "Office assembly"
    original = deepcopy(model)
    change = AssemblyDuplication(model, loader).prepare(
        "assembly.original", "assembly.copy", recipe, {"origin": [15000, 0]}
    )
    duplicated = ChangeEngine(loader).apply(model, change)
    assert model == original
    assert (
        Authoring.object(Authoring.object(duplicated["elements"])["assembly.copy"])[
            "name"
        ]
        == "Office assembly"
    )
    assert Authoring.object(
        Authoring.object(duplicated["anchors"])["assembly.original.anchor.origin"]
    )["position"] == [0, 0]
    assert Authoring.object(
        Authoring.object(duplicated["anchors"])["assembly.copy.anchor.origin"]
    )["position"] == [15000, 0]
    update = AssemblyUpdates(duplicated, recipe, loader).prepare(
        "assembly.copy", {"origin": [17000, 2000]}
    )
    result = ChangeEngine(loader).apply(duplicated, update)
    assert Authoring.object(
        Authoring.object(result["anchors"])["assembly.copy.anchor.origin"]
    )["position"] == [17000, 2000]
    assert Authoring.object(
        Authoring.object(result["anchors"])["assembly.original.anchor.origin"]
    )["position"] == [0, 0]


def test_affine_recipe_targets_express_half_spans_and_fixed_construction_offsets() -> (
    None
):
    """A dimensional parameter can drive related fabrication coordinates without executable expressions."""
    definition = RecipeFixture.source()
    definition["parameters"] = {
        "span": {
            "valueType": "length",
            "description": "Clear span",
            "minimum": 1000,
            "default": 4000,
            "targets": [
                {
                    "path": "/anchors/anchor.origin/position/0",
                    "scale": 0.5,
                    "offset": -150,
                }
            ],
        }
    }
    recipe = AssemblyRecipe(definition)
    objects, _ = recipe.parameterized({"span": 5000})
    assert Authoring.object(Authoring.object(objects["anchors"])["anchor.origin"])[
        "position"
    ] == [2350, 0]
    with pytest.raises(HomeDesignError):
        recipe.parameters({"span": 500})


def test_anchor_offsets_keep_plan_and_spatial_recipe_geometry_on_one_origin(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """Canonical version 0.2 exposes shared anchor offsets in model axes for all geometry consumers."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    locator = LocatorResolver(model)
    base = locator.point2({"anchor": "anchor.house.sw"})
    assert locator.point2({"anchor": "anchor.house.sw", "offset": [150, 300]}) == (
        base[0] + 150,
        base[1] + 300,
    )
    spatial = locator.point3_anchor("anchor.house.sw")
    assert ModelResolver(model).construction.point(
        {"anchor": "anchor.house.sw", "offset": [150, 300, 500]}
    ) == (spatial[0] + 150, spatial[1] + 300, spatial[2] + 500)
    wall = Authoring.object(Authoring.object(model["elements"])["wall.south"])
    Authoring.object(wall["path"])["start"] = {
        "anchor": "anchor.house.sw",
        "offset": [150, 300],
    }
    assert loader.validate_schema(model).is_valid
