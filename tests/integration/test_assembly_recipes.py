"""Public reusable assemblies integrate physical hosts, stock, services and guarded updates."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from home_design.assembly_duplication import AssemblyDuplication
from home_design.assembly_instantiation import AssemblyInstantiation
from home_design.assembly_updates import AssemblyUpdates
from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.migrations import ModelMigration
from home_design.recipe_catalog import RecipeCatalog
from home_design.errors import HomeDesignError
from home_design.inspection import InspectionPage, ModelInspection
from home_design.resolver import ModelResolver
from home_design.recipes import AssemblyRecipe
from home_design.validation import ModelValidator


@pytest.mark.parametrize("name", ["serviced-partition", "coordinated-deck"])
def test_public_recipe_instantiates_builds_and_duplicates_with_coordinated_parameters(
    name: str,
    reference_model: JsonObject,
    loader: ModelLoader,
    validator: ModelValidator,
    tmp_path: Path,
) -> None:
    """A real recipe expands into independent construction with native exports and reusable provenance."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    recipe = RecipeCatalog.load(name)
    change = AssemblyInstantiation(model, recipe, loader).prepare(
        "assembly.first", {}, {"binding.storey": "level.ground"}
    )
    model = ChangeEngine(loader).apply(model, change)
    before = deepcopy(model)
    duplicate = AssemblyDuplication(model, loader).prepare(
        "assembly.first",
        "assembly.second",
        recipe,
        {"origin": [20000, 0], "width": 6400, "height": 2700},
    )
    model = ChangeEngine(loader).apply(model, duplicate)
    assert (
        Authoring.object(model["elements"])["assembly.first"]
        == Authoring.object(before["elements"])["assembly.first"]
    )
    assert Authoring.object(
        Authoring.object(model["anchors"])["assembly.second.anchor.origin"]
    )["position"] == [20000, 0]
    assert Authoring.object(
        Authoring.object(model["anchors"])["assembly.first.anchor.origin"]
    ) == Authoring.object(
        Authoring.object(before["anchors"])["assembly.first.anchor.origin"]
    )
    elements = Authoring.object(model["elements"])
    if name == "serviced-partition":
        source = Authoring.object(elements["assembly.second.framing.partition"])
        assert source["openingOverrides"] == {
            "assembly.second.opening.entry": {
                "headerType": "assembly.second.stock.header"
            }
        }
        cut = Authoring.object(elements["assembly.second.cut.box"])
        assert cut["owner"] == "assembly.second.device.box"
        assert cut["host"] == "assembly.second.wall.partition"
    else:
        for side in ("south", "north"):
            beam = Authoring.object(elements[f"assembly.second.beam.{side}"])
            assert Authoring.object(Authoring.array(beam["axis"])[1])["offset"] == [
                6325,
                75 if side == "south" else 3925,
                2380,
            ]
        assert Authoring.object(
            Authoring.array(
                Authoring.object(elements["assembly.second.post.north.east"])["axis"]
            )[1]
        )["offset"] == [6325, 3925, 2280]
    update = AssemblyUpdates(model, recipe, loader).prepare(
        "assembly.second", {"origin": [22000, 1000]}
    )
    model = ChangeEngine(loader).apply(model, update)
    source_path = tmp_path / "home.json"
    ModelLoader.write(model, source_path)
    result = BuildService(loader, validator).build(source_path, tmp_path / "build")
    assert result.ifc_model.exists()
    assert result.glb_model.exists()


def test_nested_duplication_preserves_provenance_owned_cuts_and_requirements(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """Copy a generic parent containing a recipe and adapt the nested instance independently."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    recipe = RecipeCatalog.load("serviced-partition")
    model = ChangeEngine(loader).apply(
        model,
        AssemblyInstantiation(model, recipe, loader).prepare(
            "assembly.partition", {}, {"binding.storey": "level.ground"}
        ),
    )
    elements = Authoring.object(model["elements"])
    elements["assembly.parent"] = {
        "kind": "assembly",
        "name": "Parent package",
        "assemblyType": "other",
    }
    Authoring.object(model["relationships"])["parent.parts"] = {
        "kind": "aggregates",
        "assembly": "assembly.parent",
        "parts": ["assembly.partition"],
    }
    model["requirements"] = [
        {
            "id": "requirement.partition",
            "statement": "Retain the selected partition and its external context",
            "severity": "info",
            "appliesTo": ["assembly.partition.wall.partition", "wall.south"],
        }
    ]
    copied = ChangeEngine(loader).apply(
        model,
        AssemblyDuplication(model, loader).prepare("assembly.parent", "assembly.copy"),
    )
    nested = "assembly.copy.assembly.partition"
    record = Authoring.object(
        Authoring.object(Authoring.object(copied["elements"])[nested])["recipeInstance"]
    )
    anchor = Authoring.text(
        Authoring.object(Authoring.object(record["objectIds"])["anchors"])[
            "anchor.origin"
        ]
    )
    assert anchor == "assembly.copy.assembly.partition.anchor.origin"
    assert Authoring.object(Authoring.array(copied["requirements"])[1])[
        "appliesTo"
    ] == ["assembly.copy.assembly.partition.wall.partition", "wall.south"]
    update = AssemblyUpdates(copied, recipe, loader).prepare(
        nested, {"origin": [25000, 0]}
    )
    adapted = ChangeEngine(loader).apply(copied, update)
    assert Authoring.object(Authoring.object(adapted["anchors"])[anchor])[
        "position"
    ] == [25000, 0]
    assert Authoring.object(
        Authoring.object(adapted["anchors"])["assembly.partition.anchor.origin"]
    )["position"] == [-8000, 1000]
    interface = ModelInspection(adapted).assembly(nested, InspectionPage(2))
    assert (
        Authoring.object(Authoring.object(interface["connectionPoints"])["entry"])[
            "element"
        ]
        == "assembly.copy.assembly.partition.device.box"
    )
    assert Authoring.object(interface["objects"])["nextOffset"] == 2
    cut = Authoring.object(
        Authoring.object(adapted["elements"])[
            "assembly.copy.assembly.partition.cut.box"
        ]
    )
    assert cut["owner"] == "assembly.copy.assembly.partition.device.box"
    assert cut["host"] == "assembly.copy.assembly.partition.wall.partition"


def test_recipe_bindings_preserve_external_connections_and_validate_exposed_ports(
    reference_model: JsonObject, loader: ModelLoader, validator: ModelValidator
) -> None:
    """Binding remaps external participants and dry-run validation rejects a stale named interface."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    source = deepcopy(RecipeCatalog.load("serviced-partition").source)
    Authoring.object(source["bindings"])["binding.wall"] = {
        "registry": "elements",
        "kind": "wall",
        "description": "External wall connection intent",
    }
    Authoring.object(Authoring.object(source["objects"])["relationships"])[
        "external.attachment"
    ] = {
        "kind": "attaches",
        "primary": "binding.wall",
        "attached": "wall.partition",
        "connectionType": "other",
    }
    recipe = AssemblyRecipe(source)
    prepared = AssemblyInstantiation(model, recipe, loader).prepare(
        "assembly.bound",
        {},
        {"binding.storey": "level.ground", "binding.wall": "wall.south"},
    )
    assert any(
        Authoring.object(value)["path"] == "/elements/wall.south"
        for value in Authoring.array(prepared["preconditions"])
    )
    model = ChangeEngine(loader).apply(model, prepared)
    duplicated = ChangeEngine(loader).apply(
        model,
        AssemblyDuplication(model, loader).prepare("assembly.bound", "assembly.copy"),
    )
    relationship = Authoring.object(
        Authoring.object(duplicated["relationships"])[
            "assembly.copy.external.attachment"
        ]
    )
    assert relationship["primary"] == "wall.south"
    assert relationship["attached"] == "assembly.copy.wall.partition"
    record = Authoring.object(
        Authoring.object(Authoring.object(duplicated["elements"])["assembly.copy"])[
            "recipeInstance"
        ]
    )
    Authoring.object(Authoring.object(record["connectionPoints"])["entry"])[
        "port"
    ] = "missing.port"
    report = validator.validate(duplicated)
    assert any(
        item.code == "recipe.connection-point-unavailable"
        for item in report.diagnostics
    )


def test_generic_roof_package_duplication_rebinds_native_generated_faces(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """Roof-framing face references select the copied roof's actual default plane identities."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    elements = Authoring.object(model["elements"])
    roof = Authoring.object(elements["roof.main"])
    Authoring.object(roof["geometry"]).pop("faceIds", None)
    types = Authoring.object(model["types"])
    definition = Authoring.object(types[Authoring.text(roof["type"])])
    layer = Authoring.object(Authoring.array(definition["layers"])[2])
    layer["representation"] = "explicit"
    types["type.test.rafter"] = {
        "kind": "memberType",
        "name": "Rafter stock",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 40, "depth": 220},
    }
    types["type.test.rafters"] = {
        "kind": "planarFramingType",
        "name": "Rafters",
        "memberType": "type.test.rafter",
        "spacing": 600,
    }
    plane = Authoring.object(
        Authoring.array(
            ModelResolver(model).resolve().element("roof.main").data["planes"]
        )[0]
    )
    face = Authoring.text(plane["id"])
    boundary = Authoring.array(Authoring.object(plane["boundaryIds"])["outer"])[0]
    elements["framing.test"] = {
        "kind": "planarFraming",
        "name": "Named roof framing",
        "type": "type.test.rafters",
        "host": "roof.main",
        "face": face,
        "layer": layer["id"],
        "originBoundary": boundary,
        "direction": [1, 0],
    }
    for raw in Authoring.object(model["relationships"]).values():
        relationship = Authoring.object(raw)
        if relationship.get("assembly") == "assembly.roof-system":
            Authoring.array(relationship["parts"]).append("framing.test")
    report = ModelValidator(loader).validate(model, include_geometry=False)
    assert report.is_valid, report.to_dict()
    result = ChangeEngine(loader).apply(
        model,
        AssemblyDuplication(model, loader).prepare(
            "assembly.roof-system", "assembly.copy"
        ),
    )
    frame = Authoring.object(
        Authoring.object(result["elements"])["assembly.copy.framing.test"]
    )
    assert frame["face"] == "assembly.copy." + face
    resolved = ModelResolver(result).resolve()
    assert len(resolved.element("assembly.copy.framing.test").meshes) == len(
        resolved.element("framing.test").meshes
    )


def test_stock_can_be_shared_localized_and_retained_for_external_occurrences(
    reference_model: JsonObject, loader: ModelLoader
) -> None:
    """Explicit stock sharing rejects ignored overrides and never deletes another occurrence's stock."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    recipe = RecipeCatalog.load("coordinated-deck")
    external = "type.external.beam"
    Authoring.object(model["types"])[external] = deepcopy(
        recipe.index.registries["types"]["stock.beam"]
    )
    Authoring.object(Authoring.object(model["types"])[external])["material"] = next(
        iter(Authoring.object(model["materials"]))
    )
    created = AssemblyInstantiation(model, recipe, loader).prepare(
        "assembly.deck",
        {},
        {"binding.storey": "level.ground"},
        shared_types={"stock.beam": external},
    )
    model = ChangeEngine(loader).apply(model, created)
    assert "assembly.deck.stock.beam" not in Authoring.object(model["types"])
    with pytest.raises(HomeDesignError) as error:
        AssemblyUpdates(model, recipe, loader).prepare(
            "assembly.deck", overrides={"/types/stock.beam/section/width": 200}
        )
    assert error.value.code == "recipe.shared-type-input"
    localized = AssemblyUpdates(model, recipe, loader).prepare(
        "assembly.deck",
        local_types=("stock.beam",),
        overrides={"/types/stock.beam/section/width": 200},
    )
    model = ChangeEngine(loader).apply(model, localized)
    local = "assembly.deck.stock.beam"
    assert (
        Authoring.object(
            Authoring.object(Authoring.object(model["types"])[local])["section"]
        )["width"]
        == 200
    )
    outsider = deepcopy(
        Authoring.object(
            Authoring.object(model["elements"])["assembly.deck.beam.south"]
        )
    )
    Authoring.object(model["elements"])["beam.outside"] = outsider
    shared = AssemblyUpdates(model, recipe, loader).prepare(
        "assembly.deck",
        shared_types={"stock.beam": external},
        clear_overrides=("/types/stock.beam/section/width",),
    )
    result = ChangeEngine(loader).apply(model, shared)
    assert local in Authoring.object(result["types"])
    assert (
        Authoring.object(Authoring.object(result["elements"])["beam.outside"])["type"]
        == local
    )
    assert (
        Authoring.object(
            Authoring.object(result["elements"])["assembly.deck.beam.south"]
        )["type"]
        == external
    )
