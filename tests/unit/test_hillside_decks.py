"""Check the reference decks, bearing geometry and sheltered entry as a system."""

from __future__ import annotations

import pytest
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from home_design.construction import Authoring
from home_design.geometry import vector2
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedElement, ResolvedModel
from home_design.resolver import ModelResolver


class DeckChecks:
    """Small geometry and support-graph assertions for the reference model."""

    @staticmethod
    def footprint(element: ResolvedElement) -> Polygon:
        """Return the resolved outer boundary and its authored cutouts."""
        footprint = Authoring.object(element.data["footprint"])
        return Polygon(
            [
                vector2(point, "boundary")
                for point in Authoring.array(footprint["outer"])
            ],
            [
                [vector2(point, "cutout") for point in Authoring.array(loop)]
                for loop in Authoring.array(footprint.get("holes", []))
            ],
        )

    @staticmethod
    def z_bounds(element: ResolvedElement) -> tuple[float, float]:
        """Return actual mesh bottom and top elevations."""
        heights = [point[2] for mesh in element.meshes for point in mesh.vertices]
        return min(heights), max(heights)

    @classmethod
    def reaches_foundation(
        cls,
        element_id: str,
        resolved: ResolvedModel,
        supports: dict[str, list[str]],
        visiting: frozenset[str] | None = None,
    ) -> None:
        """Require every declared upstream support branch to terminate at a base."""
        visiting = visiting if visiting is not None else frozenset()
        assert element_id not in visiting
        element = resolved.element(element_id)
        if element.kind == "footing" or element.data.get("role") == "foundation":
            return
        assert supports.get(element_id), element_id
        for support in supports[element_id]:
            cls.reaches_foundation(support, resolved, supports, visiting | {element_id})


def test_south_decks_have_matching_two_foot_end_setbacks(
    construction_model: JsonObject,
) -> None:
    resolved = ModelResolver(construction_model).resolve()
    lower = DeckChecks.footprint(resolved.element("slab.lower"))
    porch = DeckChecks.footprint(resolved.element("slab.upper"))
    spa = DeckChecks.footprint(resolved.element("slab.spa"))
    assert lower.bounds == pytest.approx((609.6, -3048, 9390.4, 0))
    assert porch.intersection(spa).area == 0
    assert porch.union(spa).equals(Polygon(lower.exterior))
    house = DeckChecks.footprint(resolved.element("slab.house.upper"))
    assert lower.bounds[0] - house.bounds[0] == pytest.approx(609.6)
    assert house.bounds[2] - lower.bounds[2] == pytest.approx(609.6)
    for element in resolved.elements:
        if element.element_id.startswith(("post.porch.", "post.spa.")) or (
            element.element_id == "post.spa"
        ):
            vertices = [point for mesh in element.meshes for point in mesh.vertices]
            column = box(
                min(p[0] for p in vertices),
                min(p[1] for p in vertices),
                max(p[0] for p in vertices),
                max(p[1] for p in vertices),
            )
            assert lower.intersection(column).area == 0, element.element_id


@pytest.mark.parametrize(
    ("framing_id", "slab_id", "beam_ids"),
    [
        ("framing.porch", "slab.upper", ("beam.porch.south", "beam.porch.north")),
        ("framing.spa", "slab.spa", ("beam.spa.south", "beam.spa.north", "beam.spa")),
        ("framing.entry", "slab.entry", ("beam.entry.west", "beam.entry.east")),
    ],
)
def test_deck_joists_bear_on_beams_and_touch_deck_undersides(
    construction_model: JsonObject,
    framing_id: str,
    slab_id: str,
    beam_ids: tuple[str, ...],
) -> None:
    resolved = ModelResolver(construction_model).resolve()
    joists = resolved.element(framing_id)
    bottom, top = DeckChecks.z_bounds(joists)
    assert top == resolved.element(slab_id).data["bottomElevation"]
    for beam_id in beam_ids:
        assert DeckChecks.z_bounds(resolved.element(beam_id))[1] == bottom
    deck = DeckChecks.footprint(resolved.element(slab_id))
    for mesh in joists.meshes:
        assert deck.covers(Polygon([point[:2] for point in mesh.vertices]).convex_hull)


def test_decks_and_canopies_have_complete_foundation_paths(
    construction_model: JsonObject,
) -> None:
    resolved = ModelResolver(construction_model).resolve()
    supports: dict[str, list[str]] = {}
    for value in Authoring.object(construction_model["relationships"]).values():
        relation = Authoring.object(value)
        if relation["kind"] == "supports":
            supported = Authoring.text(relation["supported"])
            supports.setdefault(supported, []).append(
                Authoring.text(relation["support"])
            )
    for element_id in (
        "slab.upper",
        "slab.spa",
        "slab.entry",
        "roof.porch",
        "roof.entry",
        "guard.porch",
        "guard.porch.west",
        "guard.spa.south",
        "guard.spa.east",
    ):
        DeckChecks.reaches_foundation(element_id, resolved, supports)


def test_canopy_covers_landing_and_posts_preserve_door_and_stair_approaches(
    construction_model: JsonObject,
) -> None:
    resolver = ModelResolver(construction_model)
    resolved = resolver.resolve()
    canopy = resolver.roof_surfaces["roof.entry"]
    landing = DeckChecks.footprint(resolved.element("slab.entry"))
    for x, y in landing.exterior.coords:
        assert canopy.underside_height(x, y) >= 5800
    for beam_id in (
        "beam.roof.entry.west",
        "beam.roof.entry.east",
        "beam.roof.porch.south",
    ):
        assert DeckChecks.z_bounds(resolved.element(beam_id))[0] - 3000 >= 2440
    assert canopy.underside_height(10000, 2100) > 5070
    south_door_approach = box(2090, -400, 3910, 0)
    stair_approach = box(10390, 1200, 11610, 3000)
    for element in resolved.elements:
        if element.kind != "member" or element.data.get("role") != "column":
            continue
        vertices = [point for mesh in element.meshes for point in mesh.vertices]
        column = Polygon([point[:2] for point in vertices]).convex_hull
        assert column.intersection(south_door_approach).area == 0
        assert column.intersection(stair_approach).area == 0


def test_upper_deck_guards_cover_exposed_edges_without_blocking_shared_access(
    construction_model: JsonObject,
) -> None:
    resolved = ModelResolver(construction_model).resolve()
    paths = []
    for guard_id in (
        "guard.porch",
        "guard.porch.west",
        "guard.spa.south",
        "guard.spa.east",
    ):
        guard = resolved.element(guard_id)
        assert guard.data["typeId"] == "type.guard"
        assert guard.data["isStructuralGuard"] is True
        assert guard.data["height"] == 1100
        assert guard.data["openings"] == []
        path = Authoring.array(guard.data["path"])
        points = [Authoring.array(point) for point in path]
        assert all(point[2] == 3000 for point in points)
        paths.append(LineString([vector2(point[:2], "guard path") for point in points]))
        assert guard.meshes
    perimeter = unary_union(paths)
    expected = LineString([(609.6, 0), (609.6, -3048), (9390.4, -3048), (9390.4, 0)])
    assert perimeter.equals(expected)
    assert perimeter.intersection(LineString([(6000, -3048), (6000, 0)])).length == 0
    assert resolved.element("screen.porch").data["openings"] == []


@pytest.mark.parametrize("zone", ["porch", "spa"])
def test_south_rim_framing_meets_joist_ends_without_overlapping_them(
    construction_model: JsonObject,
    zone: str,
) -> None:
    resolved = ModelResolver(construction_model).resolve()
    rim = resolved.element(f"rim.{zone}.south")
    joists = resolved.element(f"framing.{zone}")
    rim_vertices = [point for mesh in rim.meshes for point in mesh.vertices]
    assert min(point[1] for point in rim_vertices) == -3048
    rim_north = max(point[1] for point in rim_vertices)
    for mesh in joists.meshes:
        assert min(point[1] for point in mesh.vertices) == rim_north == -2998
    assert DeckChecks.z_bounds(rim) == DeckChecks.z_bounds(joists)
