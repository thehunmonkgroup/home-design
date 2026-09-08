"""Public construction packages retain coordinated geometry and complete assembly ownership."""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from pathlib import Path

import pytest

from home_design.assembly_instantiation import AssemblyInstantiation
from home_design.assembly_updates import AssemblyUpdates
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.graph import ModelIndex
from home_design.geometry import vector2, vector3
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.recipes import AssemblyRecipe
from home_design.resolved import ResolvedModel
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = (
    "exterior-wall",
    "insulated-roof",
    "complete-deck",
    "insulated-floor",
    "interior-wet-wall",
    "ventilation-branch",
    "reinforced-foundation",
    "screened-entrance",
    "king-post-truss",
)


class CatalogChecks:
    """Compare physical consequences rather than serialized recipe implementation details."""

    @staticmethod
    def interfaces(model: ResolvedModel, prefix: str) -> None:
        """Require individual material bodies to retain their volume when neighboring stock is subtracted."""
        ignored = {"opening", "penetration", "space", "terrain", "barrierCheck", "clearanceZone", "detail", "load"}
        owners = [
            (element.element_id, [SolidOperations.solid(mesh) for mesh in element.meshes])
            for element in model.elements
            if element.element_id.startswith(prefix + ".")
            and element.kind not in ignored and element.meshes
        ]
        for (first, a_parts), (second, b_parts) in combinations(owners, 2):
            for a in a_parts:
                aa = a.bounding_box()
                for b in b_parts:
                    bb = b.bounding_box()
                    if any(min(aa[i + 3], bb[i + 3]) - max(aa[i], bb[i]) <= 1e-6 for i in range(3)):
                        continue
                    for source, cutter in ((a, b), (b, a)):
                        original = source.volume()
                        retained = (source - cutter).volume()
                        assert retained == pytest.approx(original, rel=1e-9, abs=1e-4), (first, second)

    @staticmethod
    def translation(before: ResolvedModel, after: ResolvedModel, prefix: str) -> None:
        """Require every package mesh to translate and every other package to remain fixed."""
        moved = 0
        for old in before.elements:
            new = after.element(old.element_id)
            assert len(old.meshes) == len(new.meshes), old.element_id
            belongs = old.element_id.startswith(prefix + ".")
            if not belongs:
                assert old.meshes == new.meshes, old.element_id
                continue
            for old_mesh, new_mesh in zip(old.meshes, new.meshes):
                expected = SolidOperations.solid(old_mesh).translate((350, 225, 0))
                actual = SolidOperations.solid(new_mesh)
                assert actual.bounding_box() == pytest.approx(
                    expected.bounding_box(), abs=1e-5
                ), old.element_id
                tolerance = max(1e-5, expected.volume() * 1e-9)
                assert abs((expected - actual).volume()) <= tolerance, old.element_id
                assert abs((actual - expected).volume()) <= tolerance, old.element_id
                moved += 1
        assert moved > 5


@pytest.fixture(scope="module")
def catalog() -> tuple[JsonObject, ResolvedModel]:
    """Resolve the distributed public catalog once for independent edits."""
    source = ModelLoader().load(ROOT / "examples/assemblies.json")
    evaluation = ModelValidator(ModelLoader()).evaluate(source)
    assert evaluation.report.is_valid, evaluation.report.to_dict()
    assert evaluation.resolved is not None
    return source, evaluation.resolved


def test_catalog_contains_distinct_complete_packages(
    catalog: tuple[JsonObject, ResolvedModel],
) -> None:
    """Every canonical part belongs to exactly one advertised, independently reusable assembly."""
    source, resolved = catalog
    elements = Authoring.object(source["elements"])
    roots = {f"assembly.{key}" for key in PACKAGES}
    assert {
        key
        for key, value in elements.items()
        if Authoring.object(value)["kind"] == "assembly"
    } == roots
    memberships: list[str] = []
    for raw in Authoring.object(source["relationships"]).values():
        relationship = Authoring.object(raw)
        if relationship["kind"] == "aggregates":
            assert relationship["assembly"] in roots
            memberships.extend(
                str(value) for value in Authoring.array(relationship["parts"])
            )
    assert len(memberships) == len(set(memberships))
    assert set(memberships) == set(elements) - roots
    assert ModelIndex(source).diagnostics() == []
    for key in PACKAGES:
        root = Authoring.object(elements[f"assembly.{key}"])
        record = Authoring.object(root["recipeInstance"])
        recipe = AssemblyRecipe.load(ROOT / "recipes" / f"{key}.json")
        rendered, _ = AssemblyInstantiation(source, recipe).render(
            f"assembly.{key}",
            Authoring.object(record["parameters"]),
            Authoring.object(record["bindings"]),
        )
        for registry, objects in rendered.items():
            actual = Authoring.object(source[registry])
            for identity, definition in Authoring.object(objects).items():
                assert actual[identity] == definition
    assert resolved.element("assembly.exterior-wall.cable").meshes
    assert resolved.element("assembly.exterior-wall.conduit").construction_volumes
    for side in ("south", "north"):
        for role in ("inlet", "outlet"):
            cut = resolved.element(f"assembly.insulated-roof.cut.{side}.{role}")
            assert float(str(cut.data["cutVolumeMm3"])) > 0
    assert (
        float(
            str(
                resolved.element("assembly.exterior-wall.cut.conduit").data[
                    "cutVolumeMm3"
                ]
            )
        )
        > 0
    )
    assert (
        resolved.element("assembly.reinforced-foundation.waterproofing.check").data[
            "status"
        ]
        == "continuous"
    )
    assert (
        resolved.element("assembly.ventilation-branch.mechanical.zone.access").data[
            "status"
        ]
        == "clear"
    )


def test_catalog_entrance_inward_swing_stays_over_the_landing(
    catalog: tuple[JsonObject, ResolvedModel],
) -> None:
    """The closed door's full opening envelope points into the enclosure, clear of the stair."""
    resolved = catalog[1]
    prefix = "assembly.screened-entrance."
    screen = resolved.element(prefix + "screen.south")
    path = [vector3(point, "screen point") for point in Authoring.array(screen.data["path"])]
    assert path[0][0] > path[1][0]
    door = resolved.element(prefix + "door")
    assert door.data["swingDirection"] == "inward"
    envelope = [vector3(point, "swing point") for point in Authoring.array(door.data["swingEnvelope"])]
    assert envelope
    slab = resolved.element(prefix + "slab.deck")
    footprint = Authoring.object(slab.data["footprint"])
    vertices = [vector2(point, "landing point") for point in Authoring.array(footprint["outer"])]
    for axis in (0, 1):
        assert min(point[axis] for point in envelope) >= min(p[axis] for p in vertices)
        assert max(point[axis] for point in envelope) <= max(p[axis] for p in vertices)
    assert min(point[1] for point in envelope) == pytest.approx(path[0][1])
    assert max(point[1] for point in envelope) > path[0][1] + 800


@pytest.mark.parametrize("key", PACKAGES)
def test_catalog_material_interfaces_are_disjoint(
    key: str, catalog: tuple[JsonObject, ResolvedModel],
) -> None:
    """All physical owners fit without duplicate material at roof, stair, guard or service joints."""
    CatalogChecks.interfaces(catalog[1], f"assembly.{key}")


@pytest.mark.parametrize("key", PACKAGES)
def test_shared_origin_moves_every_package_part_and_preserves_neighbors(
    key: str, catalog: tuple[JsonObject, ResolvedModel]
) -> None:
    """A guarded canonical anchor edit carries the complete package, including services and cuts."""
    source, before = catalog
    identity = f"assembly.{key}"
    anchor = f"{identity}.anchor.origin"
    point = Authoring.array(
        Authoring.object(Authoring.object(source["anchors"])[anchor])["position"]
    )
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": f"change.move.{key}",
        "baseRevision": source["revision"],
        "description": "Move one complete public package without changing its neighbors.",
        "preconditions": [{"path": f"/anchors/{anchor}/position", "equals": point}],
        "operations": [
            {
                "op": "moveAnchor",
                "anchorId": anchor,
                "position": [float(str(point[0])) + 350, float(str(point[1])) + 225],
            }
        ],
    }
    candidate = ChangeEngine(ModelLoader()).candidate(source, change)
    evaluation = ModelValidator(ModelLoader()).evaluate(candidate)
    assert evaluation.report.is_valid, evaluation.report.to_dict()
    assert evaluation.resolved is not None
    CatalogChecks.translation(before, evaluation.resolved, identity)


@pytest.mark.parametrize("key", ("complete-deck", "insulated-floor"))
def test_platform_resizing_keeps_hardware_guards_and_ceiling_fitted(
    key: str, catalog: tuple[JsonObject, ResolvedModel]
) -> None:
    """Width, span and height adaptation keeps additions attached to their support geometry."""
    source, before = catalog
    snapshot = deepcopy(source)
    recipe = AssemblyRecipe.load(ROOT / "recipes" / f"{key}.json")
    change = AssemblyUpdates(source, recipe).prepare(
        f"assembly.{key}", {"width": 4600, "length": 3400, "height": 1500}
    )
    candidate = ChangeEngine(ModelLoader()).candidate(source, change)
    evaluation = ModelValidator(ModelLoader()).evaluate(candidate)
    assert evaluation.report.is_valid, evaluation.report.to_dict()
    assert evaluation.resolved is not None
    after = evaluation.resolved
    assert source == snapshot
    assert after.element("assembly.exterior-wall.wall.exterior") == before.element(
        "assembly.exterior-wall.wall.exterior"
    )
    assert after.element(f"assembly.{key}.slab.deck").data["topElevation"] == 1500
    assert after.element(f"assembly.{key}.post.north.east").data["memberLength"] == 1072
    assert after.element(f"assembly.{key}.hardware.postCap.north.east").meshes
