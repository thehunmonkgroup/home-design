"""Public worked edits preserve construction, unrelated stock and native exports."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.validate
from ifcopenshell.ifcopenshell_wrapper import TriangulationElement
import pytest

from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import ChangeConflictError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.member_assemblies import MemberAssemblies
from home_design.resolved import ResolvedModel
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations

ROOT = Path(__file__).resolve().parents[2]


class AuthoringExample:
    """Check edit outcomes independently of the changeset's operation list."""

    @staticmethod
    def assert_effects(
        name: str,
        source: JsonObject,
        candidate: JsonObject,
        before: ResolvedModel,
        after: ResolvedModel,
    ) -> str:
        """Assert affected and preserved construction; return a native geometry probe."""
        old_elements = Authoring.object(source["elements"])
        elements = Authoring.object(candidate["elements"])
        old_types = Authoring.object(source["types"])
        types = Authoring.object(candidate["types"])
        if name in {"local-shared-window", "narrow-one-window"}:
            selected = (
                "window.view" if name == "local-shared-window" else "window.north"
            )
            other = (
                "window.lower.view"
                if name == "local-shared-window"
                else "window.master"
            )
            old_type = str(Authoring.object(old_elements[selected])["type"])
            new_type = str(Authoring.object(elements[selected])["type"])
            assert new_type != old_type
            assert types[old_type] == old_types[old_type]
            assert Authoring.object(types[new_type])["nominalWidth"] == (
                800 if name == "local-shared-window" else 1400
            )
            assert before.element(selected).meshes != after.element(selected).meshes
            assert before.element(other) == after.element(other)
            assert all(
                elements[key] == value
                for key, value in old_elements.items()
                if key != selected
            )
            return selected
        if name == "move-window":
            for identity in (
                "window.north",
                "opening.window.north",
                "wall.north",
                "framing.wall.north",
            ):
                assert before.element(identity).meshes != after.element(identity).meshes
            assert before.element("window.master") == after.element("window.master")
            assert (
                Authoring.object(
                    Authoring.object(elements["opening.window.north"])["placement"]
                )["station"]
                == 6700
            )
            return "wall.north"
        independent = "assembly.ventilation-branch.mechanical.device.ahu"
        assert before.element(independent) == after.element(independent)
        if name.startswith("rotate-"):
            wet = name == "rotate-service-partition"
            wall = (
                "assembly.interior-wet-wall.electrical.wall.host"
                if wet
                else "assembly.exterior-wall.wall.exterior"
            )
            route = (
                "assembly.interior-wet-wall.plumbing.pipe.supply"
                if wet
                else "assembly.exterior-wall.cable"
            )
            assert set(elements) == set(old_elements)
            assert (
                before.element(route).data["path"] != after.element(route).data["path"]
            )
            for old in before.elements:
                assert sum(
                    SolidOperations.volume(mesh) for mesh in old.meshes
                ) == pytest.approx(
                    sum(
                        SolidOperations.volume(mesh)
                        for mesh in after.element(old.element_id).meshes
                    ),
                    rel=1e-7,
                    abs=0.01,
                ), old.element_id
            return wall
        if name in {"insert-named-layer", "reorder-named-layers"}:
            frame = "assembly.interior-wet-wall.framing.partition"
            assert [
                child.element_id
                for child in MemberAssemblies.children(before.element(frame))
            ] == [
                child.element_id
                for child in MemberAssemblies.children(after.element(frame))
            ]
            assert elements[frame] == old_elements[frame]
            changed_interfaces = {
                "assembly.interior-wet-wall.interface.cut.partition",
                "assembly.interior-wet-wall.interface.acousticSeal",
            }
            assert all(
                elements[key] == value
                for key, value in old_elements.items()
                if key not in changed_interfaces
            )
            assert (
                Authoring.object(
                    elements["assembly.interior-wet-wall.interface.cut.partition"]
                )["depth"]
                == 172
            )
            assert Authoring.object(
                Authoring.object(
                    types["assembly.interior-wet-wall.interface.type.sleeve"]
                )["solids"]
            )["body"] == {
                "section": {"kind": "rectangle", "width": 64, "depth": 64},
                "depth": 172,
            }
            layers = Authoring.array(
                Authoring.object(
                    types["assembly.interior-wet-wall.wallType.service.partition"]
                )["layers"]
            )
            ids = [Authoring.object(layer)["id"] for layer in layers]
            assert ids.index("layer.legacy.1") == 2
            assert ids[:2] == (
                ["finish.additional", "layer.legacy.0"]
                if name == "insert-named-layer"
                else ["layer.legacy.0", "finish.additional"]
            )
            return "assembly.interior-wet-wall.electrical.wall.host"
        if name == "move-catalog-entrance":
            anchor = Authoring.object(
                Authoring.object(candidate["anchors"])[
                    "assembly.screened-entrance.anchor.origin"
                ]
            )
            assert anchor["position"] == [7350, -12775]
            assert (
                before.element("assembly.screened-entrance.stair").meshes
                != after.element("assembly.screened-entrance.stair").meshes
            )
            return "assembly.screened-entrance.stair"
        assert all(elements[key] == value for key, value in old_elements.items())
        assert before.element("assembly.complete-deck.slab.deck") == after.element(
            "assembly.complete-deck.slab.deck"
        )
        record = Authoring.object(
            Authoring.object(elements["assembly.deck.copy"])["recipeInstance"]
        )
        parameters = Authoring.object(record["parameters"])
        assert parameters["origin"] == [21000, 0]
        assert parameters["width"] == 4800
        if name == "adapt-copied-deck":
            assert parameters["height"] == 2400
            assert parameters["length"] == 4800
        assert after.element("assembly.deck.copy.guard.east").meshes
        assert after.element("assembly.deck.copy.hardware.postCap.north.east").meshes
        return "assembly.deck.copy.beam.north"


@pytest.fixture(scope="module")
def authoring_sources() -> dict[str, tuple[JsonObject, ResolvedModel]]:
    """Resolve each teaching source once for independent edit sequences."""
    sources: dict[str, tuple[JsonObject, ResolvedModel]] = {}
    for name in ("assemblies", "hillside-deck-house", "master-suite-gable-house"):
        source = ModelLoader().load(ROOT / "examples" / f"{name}.json")
        sources[name] = source, ModelResolver(source).resolve()
    return sources


@pytest.mark.parametrize(
    "model_name,sequence",
    [
        ("assemblies", ("rotate-service-partition",)),
        ("assemblies", ("rotate-electrical-wall",)),
        ("assemblies", ("insert-named-layer",)),
        ("assemblies", ("insert-named-layer", "reorder-named-layers")),
        ("assemblies", ("duplicate-deck",)),
        ("assemblies", ("duplicate-deck", "adapt-copied-deck")),
        ("assemblies", ("move-catalog-entrance",)),
        ("hillside-deck-house", ("local-shared-window",)),
        ("master-suite-gable-house", ("move-window",)),
        ("master-suite-gable-house", ("narrow-one-window",)),
    ],
)
def test_public_changesets_build_with_retained_intent_and_native_identity(
    model_name: str,
    sequence: tuple[str, ...],
    authoring_sources: dict[str, tuple[JsonObject, ResolvedModel]],
    tmp_path: Path,
) -> None:
    """Every documented sequence validates, exports and rejects accidental replay."""
    source, before = authoring_sources[model_name]
    snapshot = deepcopy(source)
    candidate = source
    engine = ChangeEngine(ModelLoader())
    last_change: JsonObject = {}
    for name in sequence:
        last_change = engine.load_change(ROOT / "examples/change-sets" / f"{name}.json")
        candidate = engine.candidate(candidate, last_change)
    service = BuildService()
    prepared = service.prepare(candidate)
    after = prepared.evaluation.resolved
    assert after is not None
    probe = AuthoringExample.assert_effects(
        sequence[-1], source, candidate, before, after
    )
    result = service.export_prepared(prepared, tmp_path / "build")
    assert source == snapshot
    with pytest.raises(ChangeConflictError):
        engine.candidate(candidate, last_change)
    native = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(native, logger)
    assert logger.statements == []
    manifest = ModelLoader().load(result.render_manifest)
    entries = Authoring.object(manifest["elements"])
    for element in after.elements:
        if element.kind not in MemberAssemblies.CHILD_KINDS:
            continue
        for child in MemberAssemblies.children(element):
            assert child.element_id in entries
            assert native.by_guid(IfcExporter.stable_guid(child.element_id)) is not None
    shape = ifcopenshell.geom.create_shape(
        ifcopenshell.geom.settings(),
        native.by_guid(IfcExporter.stable_guid(probe)),
    )
    assert isinstance(shape, TriangulationElement)
    assert shape.geometry.verts
    assert result.glb_model.stat().st_size > 0
    assert result.schedules.is_file()
    assert result.diagnostics.is_file()
