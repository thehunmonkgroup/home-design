"""General derived-space area, topology and full-wall-thickness regressions."""

from __future__ import annotations

from copy import deepcopy

import pytest

from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.migrations import ModelMigration
from home_design.resolved import Vec2
from home_design.resolver import ModelResolver
from home_design.space_geometry import SpaceGeometry, SpaceWallPlan


class SpaceCases:
    """Build synthetic closed wall plans independently of custom designs."""

    @staticmethod
    def loop(points: tuple[Vec2, ...], thickness: float = 100.0) -> list[SpaceWallPlan]:
        """Create independently authored square-ended wall segments."""
        return [
            SpaceWallPlan((start, end), thickness)
            for start, end in zip(points, (*points[1:], points[0]))
        ]

    @staticmethod
    def rectangle(
        width: float = 10000, depth: float = 8000, thickness: float = 185
    ) -> list[SpaceWallPlan]:
        """Return a counterclockwise rectangle with centerline walls."""
        return SpaceCases.loop(
            ((0, 0), (width, 0), (width, depth), (0, depth)), thickness
        )


@pytest.fixture
def current_space_model(reference_model: JsonObject, loader: ModelLoader) -> JsonObject:
    """Convert the public reference to the current schema in memory."""
    return ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )


@pytest.mark.parametrize("mode", [None, "axis", "interior"])
def test_space_boundary_mode_propagates_anchor_extension(
    current_space_model: JsonObject,
    loader: ModelLoader,
    mode: str | None,
) -> None:
    """Changing the north anchors updates either the gross or clear room area."""
    space = Authoring.object(
        Authoring.object(current_space_model["elements"])["space.living"]
    )
    geometry: JsonObject = {"kind": "derived", "seedPoint": [5000, 4000]}
    if mode is not None:
        geometry["boundaryMode"] = mode
    space["geometry"] = geometry
    assert loader.validate_schema(current_space_model).is_valid
    before = ModelResolver(current_space_model).resolve().element("space.living")
    expected = 76_704_225 if mode == "interior" else 80_000_000
    assert before.data["area"] == pytest.approx(expected)
    assert before.data["areaBasis"] == (mode or "axis")
    anchors = Authoring.object(current_space_model["anchors"])
    for identity, x in (("anchor.house.nw", 0), ("anchor.house.ne", 10000)):
        Authoring.object(anchors[identity])["position"] = [x, 9000]
    after = ModelResolver(current_space_model).resolve().element("space.living")
    expected = 86_519_225 if mode == "interior" else 90_000_000
    assert after.data["area"] == pytest.approx(expected)


def test_explicit_space_exposes_area_basis(reference_model: JsonObject) -> None:
    """Authored footprints remain distinguishable from both derived area bases."""
    assert (
        ModelResolver(reference_model)
        .resolve()
        .element("space.living")
        .data["areaBasis"]
        == "explicit"
    )


@pytest.mark.parametrize(
    "location_line,inset",
    [("center", 92.5), ("coreCenter", 92.5), ("interior", 0), ("exterior", 185)],
)
def test_resolver_applies_wall_location_lines_to_interior_space(
    current_space_model: JsonObject,
    location_line: str,
    inset: float,
) -> None:
    """Clockwise public walls pass their actual signed type extents into room geometry."""
    elements = Authoring.object(current_space_model["elements"])
    for value in elements.values():
        element = Authoring.object(value)
        if element["kind"] == "wall":
            element["locationLine"] = location_line
    Authoring.object(elements["space.living"])["geometry"] = {
        "kind": "derived",
        "seedPoint": [5000, 4000],
        "boundaryMode": "interior",
    }
    space = ModelResolver(current_space_model).resolve().element("space.living")
    assert space.data["area"] == pytest.approx((10000 - 2 * inset) * (8000 - 2 * inset))


@pytest.mark.parametrize("mode", ["net", 3, None])
def test_space_boundary_schema_rejects_invalid_modes(
    current_space_model: JsonObject,
    loader: ModelLoader,
    mode: str | int | None,
) -> None:
    """Only supported string modes are accepted in current-schema derived geometry."""
    space = Authoring.object(
        Authoring.object(current_space_model["elements"])["space.living"]
    )
    space["geometry"] = {
        "kind": "derived",
        "seedPoint": [5000, 4000],
        "boundaryMode": mode,
    }
    assert not loader.validate_schema(current_space_model).is_valid


@pytest.mark.parametrize(
    "location_line,inset",
    [("center", 50), ("coreCenter", 50), ("interior", 100), ("exterior", 0)],
)
def test_interior_wall_location_lines_and_reversed_paths(
    location_line: str, inset: float
) -> None:
    """Signed location-line offsets follow actual left-normal wall placement."""
    walls = SpaceCases.rectangle(thickness=100)
    offset = {"center": 0, "coreCenter": 0, "interior": 50, "exterior": -50}[
        location_line
    ]
    walls = [SpaceWallPlan(wall.path, 100, offset) for wall in walls]
    polygon = SpaceGeometry.derive("space.test", walls, (5000, 4000), "interior")
    assert polygon.area == pytest.approx((10000 - 2 * inset) * (8000 - 2 * inset))
    reversed_walls = [
        SpaceWallPlan(tuple(reversed(wall.path)), 100, -offset) for wall in walls
    ]
    reversed_polygon = SpaceGeometry.derive(
        "space.test", reversed_walls, (5000, 4000), "interior"
    )
    assert polygon.equals(reversed_polygon)


def test_interior_uses_each_wall_thickness() -> None:
    """Unequal wall types offset each room face independently."""
    walls = [
        SpaceWallPlan(wall.path, thickness)
        for wall, thickness in zip(SpaceCases.rectangle(), (100, 200, 300, 400))
    ]
    polygon = SpaceGeometry.derive("space.test", walls, (5000, 4000), "interior")
    assert polygon.bounds == (200, 50, 9900, 7850)
    assert polygon.area == pytest.approx(9700 * 7800)


def test_interior_concave_loop_retains_square_wall_ends() -> None:
    """Concave corners follow actual wall segment stock without inventing miters."""
    walls = SpaceCases.loop(
        ((0, 0), (6000, 0), (6000, 3000), (3000, 3000), (3000, 6000), (0, 6000))
    )
    polygon = SpaceGeometry.derive("space.test", walls, (1000, 1000), "interior")
    assert polygon.is_valid
    assert polygon.area == pytest.approx(25_812_500)


def test_interior_retains_holes_and_seed_selects_room_facing_side() -> None:
    """A nested loop grows the hole for the outside room and shrinks the inside room."""
    walls = SpaceCases.rectangle(10000, 10000, 100)
    walls.extend(
        SpaceCases.loop(((4000, 4000), (6000, 4000), (6000, 6000), (4000, 6000)))
    )
    outside = SpaceGeometry.derive("space.outer", walls, (1000, 1000), "interior")
    inside = SpaceGeometry.derive("space.inner", walls, (5000, 5000), "interior")
    assert len(outside.interiors) == 1
    assert outside.area == pytest.approx(93_610_000)
    assert inside.area == pytest.approx(1900 * 1900)


@pytest.mark.parametrize(
    "seed,message",
    [
        ((-10, 4000), "exactly one closed"),
        ((0, 4000), "strictly inside"),
        ((50, 4000), "full wall thickness"),
        ((92.5, 4000), "full wall thickness"),
    ],
)
def test_interior_rejects_invalid_seed(seed: Vec2, message: str) -> None:
    """Outside points, wall-axis points and points touching occupied stock fail."""
    with pytest.raises(ResolutionError, match=message):
        SpaceGeometry.derive("space.test", SpaceCases.rectangle(), seed, "interior")


def test_interior_rejects_empty_room() -> None:
    """A loop entirely consumed by wall stock has no valid clear floor footprint."""
    with pytest.raises(ResolutionError, match="interior is empty"):
        SpaceGeometry.derive(
            "space.test", SpaceCases.rectangle(100, 100, 200), (50, 50), "interior"
        )


def test_interior_rejects_disconnected_room() -> None:
    """A narrow neck consumed by wall thickness cannot silently discard a region."""
    walls = SpaceCases.loop(
        (
            (0, 0),
            (3000, 0),
            (3000, 1400),
            (6000, 1400),
            (6000, 0),
            (9000, 0),
            (9000, 3000),
            (6000, 3000),
            (6000, 1600),
            (3000, 1600),
            (3000, 3000),
            (0, 3000),
        ),
        300,
    )
    with pytest.raises(ResolutionError, match="multiple disconnected"):
        SpaceGeometry.derive("space.test", walls, (1000, 1000), "interior")


def test_interior_ignores_opening_cuts_and_element_side_metadata(
    current_space_model: JsonObject,
) -> None:
    """Door cuts and relationship side labels do not enlarge a room's plan."""
    elements = Authoring.object(current_space_model["elements"])
    space = Authoring.object(elements["space.living"])
    space["geometry"] = {
        "kind": "derived",
        "seedPoint": [5000, 4000],
        "boundaryMode": "interior",
    }
    before = ModelResolver(current_space_model).resolve().element("space.living")
    uncut = deepcopy(current_space_model)
    uncut_elements = Authoring.object(uncut["elements"])
    relationships = Authoring.object(uncut["relationships"])
    for identity in list(relationships):
        relation = Authoring.object(relationships[identity])
        if relation["kind"] in {"voids", "fills"}:
            del relationships[identity]
        elif relation["kind"] == "bounds":
            relation["elementSide"] = "exterior"
    for identity in list(uncut_elements):
        if Authoring.object(uncut_elements[identity])["kind"] in {
            "opening",
            "door",
            "window",
        }:
            del uncut_elements[identity]
    after = ModelResolver(uncut).resolve().element("space.living")
    assert before.data["footprint"] == after.data["footprint"]
    assert before.data["area"] == pytest.approx(76_704_225)
