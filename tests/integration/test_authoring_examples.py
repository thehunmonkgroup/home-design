"""Executable public editing examples preserve coordinated intent across native exports."""

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

ROOT = Path(__file__).resolve().parents[2]


class AuthoringExample:
    """Inspect authored and resolved invariants for the public worked edits."""

    @staticmethod
    def assert_effects(
        name: str,
        source: JsonObject,
        candidate: JsonObject,
        before: ResolvedModel,
        after: ResolvedModel,
    ) -> None:
        """Check the intended edit alongside participants that must survive it."""
        old_elements = Authoring.object(source["elements"])
        elements = Authoring.object(candidate["elements"])
        assert before.element("mechanical.device.ahu") == after.element(
            "mechanical.device.ahu"
        )
        if name == "rotate-service-partition":
            assert (
                before.element("plumbing.pipe.supply").data["path"]
                != after.element("plumbing.pipe.supply").data["path"]
            )
            assert set(elements) == set(old_elements)
        elif name == "local-shared-window":
            assert elements["window.east"] == old_elements["window.east"]
            assert before.element("window.east") == after.element("window.east")
            assert Authoring.object(elements["window.north"])["type"] == (
                "windowType.north-1400x1200"
            )
            assert (
                before.element("window.north").meshes
                != after.element("window.north").meshes
            )
        elif name in {"insert-named-layer", "reorder-named-layers"}:
            framing = "assembly.partition.demo.framing.partition"
            assert [
                child.element_id
                for child in MemberAssemblies.children(before.element(framing))
            ] == [
                child.element_id
                for child in MemberAssemblies.children(after.element(framing))
            ]
            assert elements[framing] == old_elements[framing]
            layers = Authoring.array(
                Authoring.object(
                    Authoring.object(candidate["types"])[
                        "assembly.partition.demo.type.partition"
                    ]
                )["layers"]
            )
            ids = [Authoring.object(layer)["id"] for layer in layers]
            assert ids.index("cavity") == 2
            assert ids[:2] == (
                ["finish.additional", "finish.exterior"]
                if name == "insert-named-layer"
                else ["finish.exterior", "finish.additional"]
            )
        else:
            assert elements["assembly.deck.demo"] == old_elements["assembly.deck.demo"]
            assert before.element("assembly.deck.demo.slab.deck") == after.element(
                "assembly.deck.demo.slab.deck"
            )
            record = Authoring.object(
                Authoring.object(elements["assembly.deck.copy"])["recipeInstance"]
            )
            parameters = Authoring.object(record["parameters"])
            assert parameters["origin"] == [25000, -5000]
            assert parameters["width"] == 4800
            if name == "adapt-copied-deck":
                assert parameters["height"] == 2400
                assert parameters["length"] == 4800


@pytest.fixture(scope="module")
def authoring_source() -> tuple[JsonObject, ResolvedModel]:
    """Resolve the unchanged public source once for independent edit comparisons."""
    model = ModelLoader().load(ROOT / "examples/integrated-authoring-house.json")
    return model, ModelResolver(model).resolve()


@pytest.mark.parametrize(
    "sequence",
    [
        ("rotate-service-partition",),
        ("local-shared-window",),
        ("insert-named-layer",),
        ("insert-named-layer", "reorder-named-layers"),
        ("duplicate-deck",),
        ("duplicate-deck", "adapt-copied-deck"),
    ],
)
def test_public_changesets_build_with_retained_intent_and_native_identity(
    sequence: tuple[str, ...],
    authoring_source: tuple[JsonObject, ResolvedModel],
    tmp_path: Path,
) -> None:
    """Every documented sequence validates, builds, and rejects accidental replay."""
    source, before = authoring_source
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
    AuthoringExample.assert_effects(sequence[-1], source, candidate, before, after)
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
    for child in MemberAssemblies.children(
        after.element("assembly.partition.demo.framing.partition")
    ):
        assert child.element_id in entries
        assert native.by_guid(IfcExporter.stable_guid(child.element_id)) is not None
    shape = ifcopenshell.geom.create_shape(
        ifcopenshell.geom.settings(),
        native.by_guid(
            IfcExporter.stable_guid("assembly.partition.demo.wall.partition")
        ),
    )
    assert isinstance(shape, TriangulationElement)
    assert shape.geometry.verts
    assert result.glb_model.stat().st_size > 0
    assert result.schedules.is_file()
    assert result.diagnostics.is_file()
