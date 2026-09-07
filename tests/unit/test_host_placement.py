"""Host placement contracts for construction, accessories and service routing."""

from __future__ import annotations

import math
from copy import deepcopy

import pytest

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.json_types import JsonObject, JsonValue
from home_design.placement import HostPlacement, LocalFrame
from home_design.resolver import ModelResolver
from home_design.resolved import Vec3
from home_design.validation import ModelValidator


@pytest.fixture
def host_model(reference_model: JsonObject) -> JsonObject:
    """Create isolated public-material hosts with predictable dimensions."""
    model = deepcopy(reference_model)
    types = Authoring.object(model["types"])
    types["type.member"] = {
        "kind": "memberType",
        "name": "Rectangular timber",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 40, "depth": 100},
    }
    types["type.footing"] = {
        "kind": "footingType",
        "name": "Concrete footing",
        "material": "material.concrete",
        "depth": 300,
    }
    model["relationships"] = {}
    model["requirements"] = []
    model["elements"] = {
        "wall.host": {
            "kind": "wall",
            "name": "Host wall",
            "storey": "level.ground",
            "type": "wallType.exterior.wood-185",
            "locationLine": "center",
            "path": {
                "kind": "line",
                "start": {"point": [0, 0]},
                "end": {"point": [4000, 0]},
            },
            "base": {"kind": "level", "level": "level.ground", "offset": 0},
            "top": {"kind": "height", "height": 2700},
        },
        "slab.host": {
            "kind": "slab",
            "name": "Host slab",
            "storey": "level.ground",
            "role": "floor",
            "type": "slabType.concrete-200",
            "extrusionDirection": "down",
            "datum": {"kind": "level", "level": "level.ground", "offset": 0},
            "footprint": {
                "outer": [
                    {"point": [0, 0]},
                    {"point": [4000, 0]},
                    {"point": [4000, 4000]},
                    {"point": [0, 4000]},
                ],
                "holes": [
                    [
                        {"point": [1000, 1000]},
                        {"point": [1000, 2000]},
                        {"point": [2000, 2000]},
                        {"point": [2000, 1000]},
                    ]
                ],
            },
        },
        "roof.host": {
            "kind": "roof",
            "name": "Host shed roof",
            "storey": "level.ground",
            "type": "roofType.shingle-250",
            "geometry": {
                "kind": "faceSet",
                "faces": [
                    {
                        "id": "face.shed",
                        "boundary": {
                            "outer": [
                                [0, 0, 3000],
                                [4000, 0, 3000],
                                [4000, 4000, 5000],
                                [0, 4000, 5000],
                            ]
                        },
                    }
                ],
            },
        },
        "member.host": {
            "kind": "member",
            "name": "Rolled beam",
            "storey": "level.ground",
            "type": "type.member",
            "role": "beam",
            "axis": [{"point": [0, 0, 0]}, {"point": [2000, 0, 0]}],
            "roll": 90,
        },
        "footing.host": {
            "kind": "footing",
            "name": "Pier",
            "storey": "level.ground",
            "type": "type.footing",
            "shape": "pier",
            "center": [0, 0],
            "diameter": 500,
            "datum": {"kind": "level", "level": "level.ground", "offset": -500},
        },
    }
    return model


@pytest.mark.parametrize(
    ("surface", "layer", "expected_y", "normal_y"),
    [
        ("exterior", None, 92.5, 1),
        ("interior", None, -92.5, -1),
        ("layerExterior", 2, 60.5, 1),
        ("layerInterior", 2, -79.5, -1),
        ("layerCenter", 2, -9.5, 1),
    ],
)
def test_wall_faces_and_layers_follow_physical_boundaries(
    host_model: JsonObject,
    validator: ModelValidator,
    surface: str,
    layer: int | None,
    expected_y: float,
    normal_y: float,
) -> None:
    """Measure actual face/layer offsets, local up and right-handed orientation."""
    assert validator.validate(host_model).is_valid
    placement: JsonObject = {
        "kind": "wall",
        "element": "wall.host",
        "station": 1000,
        "height": 450,
        "surface": surface,
    }
    if layer is not None:
        placement["layer"] = layer
    frame = HostPlacement(ModelResolver(host_model)).resolve(placement)
    assert frame.origin == pytest.approx((1000, expected_y, 450))
    assert frame.y == (0, 0, 1)
    assert frame.z == (0, normal_y, 0)
    assert ConstructionGeometry.cross(frame.x, frame.y) == frame.z


def test_hosted_member_follows_wall_edits_and_retains_placement(
    host_model: JsonObject, validator: ModelValidator
) -> None:
    """A mounted part moves with wall location, base and layer thickness edits."""
    elements = Authoring.object(host_model["elements"])
    placement: JsonObject = {
        "kind": "wall",
        "element": "wall.host",
        "station": 1000,
        "height": 450,
        "surface": "interior",
        "offset": [0, 0, 25],
    }
    endpoint = deepcopy(placement)
    endpoint["offset"] = [100, 0, 25]
    elements["member.mounted"] = {
        "kind": "member",
        "name": "Mounted backing",
        "storey": "level.ground",
        "type": "type.member",
        "role": "other",
        "axis": [{"host": placement}, {"host": endpoint}],
    }
    assert validator.validate(host_model).is_valid
    before = ModelResolver(host_model).resolve().element("member.mounted")
    assert before.data["axis"] == [[1000, -117.5, 450], [1100, -117.5, 450]]
    assert before.data["hostPlacements"] == [placement, endpoint]
    wall = Authoring.object(elements["wall.host"])
    wall["path"] = {
        "kind": "line",
        "start": {"point": [200, 300]},
        "end": {"point": [4200, 300]},
    }
    Authoring.object(wall["base"])["offset"] = 100
    layers = Authoring.array(
        Authoring.object(
            Authoring.object(host_model["types"])["wallType.exterior.wood-185"]
        )["layers"]
    )
    Authoring.object(layers[2])["thickness"] = 240
    assert validator.validate(host_model).is_valid
    after = ModelResolver(host_model).resolve().element("member.mounted")
    assert after.data["axis"] == [[1200, 132.5, 550], [1300, 132.5, 550]]
    assert after.element_id == before.element_id


@pytest.mark.parametrize(
    ("host", "surface", "layer", "point", "z"),
    [
        ("slab.host", "top", None, [500, 500], 0),
        ("slab.host", "bottom", None, [500, 500], -200),
        ("slab.host", "layerCenter", 0, [500, 500], -100),
        ("footing.host", "top", None, [0, 0], -500),
        ("footing.host", "bottom", None, [0, 0], -800),
    ],
)
def test_horizontal_surface_hosts(
    host_model: JsonObject,
    host: str,
    surface: str,
    layer: int | None,
    point: list[JsonValue],
    z: float,
) -> None:
    """Support floor and foundation surfaces using their actual resolved datums."""
    placement: JsonObject = {
        "kind": "surface",
        "element": host,
        "surface": surface,
        "point": point,
    }
    if layer is not None:
        placement["layer"] = layer
    frame = HostPlacement(ModelResolver(host_model)).resolve(placement)
    assert frame.origin == tuple([*point, z])
    assert frame.z[2] == (-1 if surface == "bottom" else 1)


@pytest.mark.parametrize(
    ("surface", "layer", "depth"),
    [
        ("top", None, 0),
        ("bottom", None, 250),
        ("layerTop", 2, 30),
        ("layerBottom", 1, 30),
        ("layerCenter", 2, 140),
    ],
)
def test_roof_placement_matches_normal_thickness(
    host_model: JsonObject, surface: str, layer: int | None, depth: float
) -> None:
    """Roof layers use normal distances and supply slope-oriented mounting axes."""
    placement: JsonObject = {
        "kind": "surface",
        "element": "roof.host",
        "point": [500, 500],
        "surface": surface,
        "face": "face.shed",
    }
    if layer is not None:
        placement["layer"] = layer
    frame = HostPlacement(ModelResolver(host_model)).resolve(placement)
    assert frame.origin == pytest.approx((500, 500, 3250 - depth * math.sqrt(1.25)))
    assert abs(frame.z[2]) == pytest.approx(1 / math.sqrt(1.25))
    assert ConstructionGeometry.cross(frame.x, frame.y) == pytest.approx(frame.z)


def test_rolled_member_side_and_end_frames(host_model: JsonObject) -> None:
    """Mounting follows the host section roll and exposes outward face normals."""
    resolver = HostPlacement(ModelResolver(host_model))
    side = resolver.resolve(
        {
            "kind": "member",
            "element": "member.host",
            "station": 300,
            "surface": "positiveX",
        }
    )
    assert side.origin == pytest.approx((300, 0, 20))
    assert side.z == pytest.approx((0, 0, 1))
    assert side.y == (1, 0, 0)
    start = resolver.resolve(
        {"kind": "member", "element": "member.host", "station": 0, "surface": "start"}
    )
    assert start.z == (-1, 0, 0)
    end = resolver.resolve(
        {"kind": "member", "element": "member.host", "station": 2000, "surface": "end"}
    )
    assert end.origin == (2000, 0, 0)
    assert end.z == (1, 0, 0)


@pytest.mark.parametrize(
    "placement",
    [
        {
            "kind": "wall",
            "element": "wall.host",
            "station": 5000,
            "height": 450,
            "surface": "interior",
        },
        {
            "kind": "wall",
            "element": "wall.host",
            "station": 500,
            "height": 3000,
            "surface": "interior",
        },
        {
            "kind": "wall",
            "element": "wall.host",
            "station": 500,
            "height": 300,
            "surface": "layerCenter",
            "layer": 99,
        },
        {
            "kind": "surface",
            "element": "slab.host",
            "point": [1500, 1500],
            "surface": "top",
        },
        {
            "kind": "surface",
            "element": "slab.host",
            "point": [5000, 500],
            "surface": "bottom",
        },
        {
            "kind": "surface",
            "element": "roof.host",
            "point": [500, 500],
            "surface": "top",
            "face": "absent",
        },
        {
            "kind": "surface",
            "element": "footing.host",
            "point": [500, 500],
            "surface": "top",
        },
        {
            "kind": "surface",
            "element": "footing.host",
            "point": [0, 0],
            "surface": "layerCenter",
            "layer": 0,
        },
        {"kind": "member", "element": "member.host", "station": 2500},
        {
            "kind": "member",
            "element": "member.host",
            "station": 100,
            "surface": "start",
        },
    ],
)
def test_invalid_host_coordinates_reject_geometry(
    host_model: JsonObject, placement: JsonObject
) -> None:
    """Do not silently clamp out-of-range stations, layers, holes or footprints."""
    with pytest.raises(ResolutionError):
        HostPlacement(ModelResolver(host_model)).resolve(placement)


def test_round_member_side_mounts_use_the_physical_profile(
    host_model: JsonObject,
) -> None:
    """Circular sides mount on tessellated boundary edges with radial orientation."""
    member_type = Authoring.object(Authoring.object(host_model["types"])["type.member"])
    member_type["section"] = {"kind": "circle", "diameter": 100}
    frame = HostPlacement(ModelResolver(host_model)).resolve(
        {
            "kind": "member",
            "element": "member.host",
            "station": 300,
            "surface": "positiveX",
        }
    )
    assert frame.origin == pytest.approx((300, 0, 50))
    assert frame.z == pytest.approx((0, 0, 1))


def test_roof_crease_requires_an_explicit_face(host_model: JsonObject) -> None:
    """A shared ridge has two valid orientations and cannot silently select one."""
    roof = Authoring.object(Authoring.object(host_model["elements"])["roof.host"])
    roof["geometry"] = {
        "kind": "faceSet",
        "faces": [
            {
                "id": "face.south",
                "boundary": {
                    "outer": [
                        [0, 0, 3000],
                        [4000, 0, 3000],
                        [4000, 2000, 4000],
                        [0, 2000, 4000],
                    ]
                },
            },
            {
                "id": "face.north",
                "boundary": {
                    "outer": [
                        [0, 2000, 4000],
                        [4000, 2000, 4000],
                        [4000, 4000, 3000],
                        [0, 4000, 3000],
                    ]
                },
            },
        ],
    }
    placement: JsonObject = {
        "kind": "surface",
        "element": "roof.host",
        "point": [500, 2000],
        "surface": "top",
    }
    resolver = HostPlacement(ModelResolver(host_model))
    with pytest.raises(ResolutionError, match="2 faces"):
        resolver.resolve(placement)
    placement["face"] = "face.north"
    frame = resolver.resolve(placement)
    assert frame.origin == (500, 2000, 4000)
    assert frame.z[1] > 0


def test_polyline_wall_placement_uses_the_local_segment(host_model: JsonObject) -> None:
    """Stationing turns with the wall and offsets along that segment's normal."""
    wall = Authoring.object(Authoring.object(host_model["elements"])["wall.host"])
    wall["path"] = {
        "kind": "polyline",
        "points": [{"point": [0, 0]}, {"point": [2000, 0]}, {"point": [2000, 2000]}],
    }
    frame = HostPlacement(ModelResolver(host_model)).resolve(
        {
            "kind": "wall",
            "element": "wall.host",
            "station": 2500,
            "height": 450,
            "surface": "exterior",
        }
    )
    assert frame.origin == (1907.5, 500, 450)
    assert frame.z == (-1, 0, 0)


def test_wall_opening_is_not_a_mountable_surface(reference_model: JsonObject) -> None:
    """Mount points cannot attach to empty space inside a hosted window opening."""
    resolver = ModelResolver(reference_model)
    resolver.resolve()
    opening = resolver.openings["opening.window.north"]
    with pytest.raises(ResolutionError, match="outside a physical surface"):
        HostPlacement(resolver).resolve(
            {
                "kind": "wall",
                "element": opening.host_id,
                "surface": "exterior",
                "station": opening.start_station + opening.width / 2,
                "height": opening.bottom + opening.height / 2,
            }
        )


@pytest.mark.parametrize(
    ("target", "kind", "code"),
    [
        ("missing.host", "member", "reference.missing"),
        ("slab.host", "member", "reference.kind-mismatch"),
        ("member.host", "member", "dependency.cycle"),
    ],
)
def test_host_dependencies_are_validated_before_resolution(
    host_model: JsonObject, validator: ModelValidator, target: str, kind: str, code: str
) -> None:
    """Index hosted references for inspection, deletion safety and cycle checks."""
    member = Authoring.object(Authoring.object(host_model["elements"])["member.host"])
    member["axis"] = [
        {"host": {"kind": kind, "element": target, "station": 0}},
        {"point": [2000, 0, 0]},
    ]
    report = validator.validate(host_model)
    assert not report.is_valid
    assert code in {diagnostic.code for diagnostic in report.diagnostics}


@pytest.mark.parametrize(
    "placement",
    [
        {
            "kind": "wall",
            "element": "wall.host",
            "station": 100,
            "height": 100,
            "surface": "layerCenter",
        },
        {
            "kind": "wall",
            "element": "wall.host",
            "station": 100,
            "height": 100,
            "surface": "exterior",
            "layer": 0,
        },
        {"kind": "member", "element": "member.host", "station": -1},
        {"kind": "member", "element": "member.host", "station": 100, "height": 200},
    ],
)
def test_schema_rejects_ambiguous_host_controls(
    host_model: JsonObject, validator: ModelValidator, placement: JsonObject
) -> None:
    """Reject controls with no meaning in the selected host coordinate system."""
    member = Authoring.object(Authoring.object(host_model["elements"])["member.host"])
    member["axis"] = [{"host": placement}, {"point": [2000, 0, 0]}]
    assert not validator.loader.validate_schema(host_model).is_valid


def test_frame_offsets_rotations_and_meshes_are_rigid() -> None:
    """Local offsets precede intrinsic rotations without scale or handedness loss."""
    initial = LocalFrame((10, 20, 30), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    frame = initial.adjusted((1, 2, 3), (90, 0, 90))
    assert frame.origin == (11, 22, 33)
    assert frame.x == pytest.approx((0, 0, 1))
    assert frame.y == pytest.approx((-1, 0, 0))
    assert frame.z == pytest.approx((0, -1, 0))
    vertices: list[Vec3] = [(0, 0, 0), (1, 2, 3), (-3, 4, 5)]
    for a, b in zip(vertices, vertices[1:]):
        assert math.dist(frame.point(a), frame.point(b)) == pytest.approx(
            math.dist(a, b)
        )
    mesh = ConstructionGeometry.member(
        (0, 0, 0),
        (0, 0, 10),
        {"kind": "rectangle", "width": 2, "depth": 3},
        "timber",
        "test",
    )
    transformed = frame.mesh(mesh)
    assert transformed.material_id == mesh.material_id
    assert transformed.faces == mesh.faces
    assert frame.to_dict()["origin"] == [11, 22, 33]
