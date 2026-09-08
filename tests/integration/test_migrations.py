"""Versioned authoring migrations preserve public designs and scoped construction intent."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import ifcopenshell
import pytest

from home_design.adapters.ifc import IfcExporter
from home_design.boundaries import BoundaryIdentity
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import ChangeConflictError, ResolutionError
from home_design.json_types import JsonObject
from home_design.layers import LayerAssembly
from home_design.loader import ModelLoader
from home_design.member_assemblies import MemberAssemblies
from home_design.migrations import ModelMigration
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


@pytest.mark.parametrize(
    "filename",
    [
        "tests/fixtures/basic-shell.json",
        "examples/hillside-deck-house.json",
    ],
)
def test_public_migration_preserves_geometry_and_ifc_identity(
    filename: str, loader: ModelLoader, validator: ModelValidator, tmp_path: Path
) -> None:
    """A guarded version transition retains every physical member and native IFC root GUID."""
    source = loader.load(Path(__file__).resolve().parents[2] / filename)
    original = deepcopy(source)
    migration = ModelMigration(loader)
    change = migration.prepare(source)
    assert change == migration.prepare(source)
    candidate = ChangeEngine(loader).candidate(source, change)
    assert source == original
    assert candidate["modelVersion"] == "0.2"
    assert candidate["revision"] == int(str(source["revision"])) + 1
    before = ModelResolver(source).resolve()
    evaluation = validator.evaluate(candidate)
    assert evaluation.report.is_valid, evaluation.report.to_dict()
    after = evaluation.resolved
    assert after is not None
    assert {element.element_id for element in before.elements} == {
        element.element_id for element in after.elements
    }
    for element in before.elements:
        migrated = after.element(element.element_id)
        if element.kind == "terrain":
            assert migrated.meshes == element.meshes
            continue
        assert sum(
            SolidOperations.volume(mesh) for mesh in migrated.meshes
        ) == pytest.approx(
            sum(SolidOperations.volume(mesh) for mesh in element.meshes), abs=0.1
        )
        if element.kind in MemberAssemblies.CHILD_KINDS:
            assert {
                child.element_id for child in MemberAssemblies.children(element)
            } == {child.element_id for child in MemberAssemblies.children(migrated)}
    native_before = tmp_path / "before.ifc"
    native_after = tmp_path / "after.ifc"
    IfcExporter().export(before, native_before)
    IfcExporter().export(after, native_after)
    assert {
        str(entity.GlobalId)
        for entity in ifcopenshell.open(native_before).by_type("IfcRoot")
    } == {
        str(entity.GlobalId)
        for entity in ifcopenshell.open(native_after).by_type("IfcRoot")
    }
    changed = deepcopy(source)
    first_type = next(
        value
        for value in Authoring.object(changed["types"]).values()
        if "layers" in Authoring.object(value)
    )
    Authoring.object(first_type)["name"] = "Concurrent edit"
    with pytest.raises(ChangeConflictError):
        ChangeEngine(loader).candidate(changed, change)


def test_named_layer_survives_insertion_reorder_and_rejects_removal() -> None:
    """Layer selection follows authored identity and never falls back to an array position."""
    first: JsonObject = {"id": "finish", "thickness": 10}
    cavity: JsonObject = {"id": "cavity", "thickness": 140}
    assert LayerAssembly.index([first, cavity], "cavity") == 1
    assert LayerAssembly.index([cavity, {"id": "membrane"}, first], "cavity") == 0
    with pytest.raises(ResolutionError) as error:
        LayerAssembly.index([first], "cavity")
    assert error.value.code == "layer.identity-unavailable"


def test_named_boundary_requires_complete_unique_topology() -> None:
    """Malformed names fail before a follow or framing selection can retarget."""
    profile: JsonObject = {
        "outer": [[0, 0], [1, 0], [1, 1]],
        "boundaryIds": {"outer": ["south", "east", "diagonal"]},
    }
    names = BoundaryIdentity.profile(profile)[0]
    assert BoundaryIdentity.select(names, "east") == 1
    assert BoundaryIdentity.select(("diagonal", "south", "east"), "east") == 2
    with pytest.raises(ResolutionError):
        BoundaryIdentity.select(names, "removed")
    Authoring.object(profile["boundaryIds"])["outer"] = ["south", "south", "east"]
    with pytest.raises(ResolutionError):
        BoundaryIdentity.profile(profile)


def test_roof_plane_ids_survive_boundary_reordering_with_named_overhangs(
    reference_model: JsonObject, loader: ModelLoader, validator: ModelValidator
) -> None:
    """A polygon's first vertex cannot choose a different generated roof face or edge offset."""
    model = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    geometry = Authoring.object(
        Authoring.object(Authoring.object(model["elements"])["roof.main"])["geometry"]
    )
    footprint = Authoring.object(geometry["footprint"])
    outer = Authoring.array(footprint["outer"])
    names = Authoring.object(footprint["boundaryIds"])
    ids = Authoring.array(names["outer"])
    geometry["edgeOverhangs"] = {Authoring.text(identity): 600 for identity in ids}
    before = ModelResolver(model).resolve().element("roof.main")
    footprint["outer"] = outer[1:] + outer[:1]
    names["outer"] = ids[1:] + ids[:1]
    evaluation = validator.evaluate(model)
    assert evaluation.report.is_valid, evaluation.report.to_dict()
    assert evaluation.resolved is not None
    after = evaluation.resolved.element("roof.main")
    assert before.data["faceIdentities"] == after.data["faceIdentities"]
    assert {
        mesh.role: SolidOperations.volume(mesh) for mesh in before.meshes
    } == pytest.approx(
        {mesh.role: SolidOperations.volume(mesh) for mesh in after.meshes}
    )


def test_followed_edge_survives_reordering_and_requires_an_explicit_name(
    construction_model: JsonObject, loader: ModelLoader, validator: ModelValidator
) -> None:
    """An enclosure stays on the intended deck edge and cannot use an implicit positional fallback."""
    model = ChangeEngine(loader).apply(
        construction_model, ModelMigration(loader).prepare(construction_model)
    )
    elements = Authoring.object(model["elements"])
    identity, follower = next(
        (identity, Authoring.object(value))
        for identity, value in elements.items()
        if isinstance(Authoring.object(value).get("follow"), dict)
        and "edge" in Authoring.object(Authoring.object(value)["follow"])
    )
    follow = Authoring.object(follower["follow"])
    host = Authoring.object(elements[Authoring.text(follow["element"])])
    profile = Authoring.object(host["footprint"])
    outer = Authoring.array(profile["outer"])
    names = Authoring.object(profile["boundaryIds"])
    ids = Authoring.array(names["outer"])
    before = ModelResolver(model).resolve().element(identity)
    profile["outer"] = outer[1:] + outer[:1]
    names["outer"] = ids[1:] + ids[:1]
    after = ModelResolver(model).resolve().element(identity)
    assert after.meshes == before.meshes
    follow.pop("edge")
    report = validator.validate(model)
    assert not report.is_valid
    assert any(item.code == "boundary.required-edge" for item in report.errors)
