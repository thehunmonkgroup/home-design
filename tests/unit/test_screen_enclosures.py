"""Screen closure, hosted-door fit, infill semantics and porch coordination."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box

from home_design.construction import Authoring
from home_design.geometry import number, vector2, vector3
from home_design.json_types import JsonObject
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class ScreenChecks:
    """Read canonical fixtures and project mesh bounds for coordination checks."""

    @staticmethod
    def element(model: JsonObject, element_id: str) -> JsonObject:
        """Return the mutable canonical element for an isolated test fixture."""
        return Authoring.object(Authoring.object(model["elements"])[element_id])

    @staticmethod
    def footprint(element: JsonObject) -> Polygon:
        """Read a canonical polygon of literal plan locators."""
        footprint = Authoring.object(element["footprint"])
        return Polygon(
            [
                vector2(Authoring.object(point)["point"], "footprint point")
                for point in Authoring.array(footprint["outer"])
            ]
        )


def test_screen_profiles_close_to_roof_and_follow_roof_changes(
    construction_model: JsonObject,
) -> None:
    first = ModelResolver(construction_model)
    resolved = first.resolve()
    ids = ("screen.porch", "screen.porch.west", "screen.porch.east")
    for element_id in ids:
        screen = resolved.element(element_id)
        assert screen.data["isStructuralGuard"] is False
        for value in Authoring.array(screen.data["topProfile"]):
            x, y, z = vector3(value, "screen top")
            assert z == pytest.approx(
                first.roof_surfaces["roof.porch"].underside_height(x, y)
            )
        assert min(p[2] for mesh in screen.meshes for p in mesh.vertices) == 3000
    geometry = Authoring.object(
        ScreenChecks.element(construction_model, "roof.porch")["geometry"]
    )
    Authoring.object(geometry["eaveDatum"])["offset"] = -150
    second = ModelResolver(construction_model).resolve()
    for element_id in ids:
        before = resolved.element(element_id)
        after = second.element(element_id)
        assert number(before.data["height"], "height") - number(
            after.data["height"], "height"
        ) == pytest.approx(50)


def test_screen_door_is_cut_from_host_and_has_mesh_not_glazing(
    construction_model: JsonObject,
) -> None:
    resolved = ModelResolver(construction_model).resolve()
    screen = resolved.element("screen.porch.east")
    opening = resolved.element("opening.porch.screen-door")
    door = resolved.element("door.porch.screen")
    assert opening.data["hostId"] == "screen.porch.east"
    assert screen.data["hostedOpeningIds"] == ["opening.porch.screen-door"]
    assert door.data["nominalWidth"] == 914.4
    assert door.data["nominalHeight"] == 2032
    assert door.data["operation"] == "singleSwing"
    assert door.data["glazedArea"] == 0
    assert door.data["infillMaterial"] == "mat.screen"
    assert any(
        mesh.role == "door-infill" and mesh.material_id == "mat.screen"
        for mesh in door.meshes
    )
    assert not any(mesh.role == "door-glass" for mesh in door.meshes)
    cutout = box(1500 - 914.4 / 2, 0, 1500 + 914.4 / 2, 2032)
    for mesh in screen.meshes:
        for face in mesh.faces:
            triangle = Polygon(
                [(-mesh.vertices[i][1], mesh.vertices[i][2] - 3000) for i in face]
            )
            assert triangle.intersection(cutout).area == pytest.approx(0, abs=1e-6)
    swing = Polygon(
        [vector3(p, "swing")[:2] for p in Authoring.array(door.data["swingEnvelope"])]
    )
    deck = ScreenChecks.footprint(ScreenChecks.element(construction_model, "slab.spa"))
    porch = ScreenChecks.footprint(
        ScreenChecks.element(construction_model, "slab.upper")
    )
    assert deck.union(porch).covers(swing)
    assert (
        swing.intersection(
            ScreenChecks.footprint(ScreenChecks.element(construction_model, "load.spa"))
        ).area
        == 0
    )
    ScreenChecks.element(construction_model, "door.porch.screen")["swingAngle"] = 90
    opened = ModelResolver(construction_model).resolve().element("door.porch.screen")
    assert opened.meshes != door.meshes
    assert opened.data["swingEnvelope"] == door.data["swingEnvelope"]


def test_west_screen_clears_guard_and_structural_posts(
    construction_model: JsonObject,
) -> None:
    resolved = ModelResolver(construction_model).resolve()
    screen = resolved.element("screen.porch.west")
    screen_x = [p[0] for mesh in screen.meshes for p in mesh.vertices]
    guard = resolved.element("guard.porch.west")
    assert min(screen_x) > max(p[0] for mesh in guard.meshes for p in mesh.vertices)
    for element_id in ("post.roof.porch.south.0", "post.roof.porch.north.0"):
        post = resolved.element(element_id)
        assert max(screen_x) < min(p[0] for mesh in post.meshes for p in mesh.vertices)
    for element_id in ("beam.roof.porch.south", "beam.roof.porch.north"):
        beam = resolved.element(element_id)
        assert min(p[0] for mesh in beam.meshes for p in mesh.vertices) == max(screen_x)


@pytest.mark.parametrize(
    "fault",
    ["width", "height", "below", "overlap", "sloping", "outside-roof", "infill"],
)
def test_invalid_screen_enclosures_are_rejected(
    construction_model: JsonObject,
    validator: ModelValidator,
    fault: str,
) -> None:
    opening = ScreenChecks.element(construction_model, "opening.porch.screen-door")
    panel = ScreenChecks.element(construction_model, "screen.porch.east")
    if fault in {"width", "height"}:
        Authoring.object(opening["geometry"])[fault] = 10000
    elif fault == "below":
        Authoring.object(opening["placement"])["verticalOffset"] = -100
    elif fault == "overlap":
        panel["openings"] = [{"start": 1000, "end": 2000}]
    elif fault == "sloping":
        first = Authoring.object(Authoring.array(panel["path"])[0])
        Authoring.object(first["elevation"])["offset"] = 100
    elif fault == "outside-roof":
        first = Authoring.object(Authoring.array(panel["path"])[0])
        first["point"] = [10000, 0, 3000]
        del first["elevation"]
    else:
        door_type = Authoring.object(
            Authoring.object(construction_model["types"])["type.screen-door"]
        )
        door_type["infillMaterial"] = "material.missing"
    assert not validator.validate(construction_model).is_valid
