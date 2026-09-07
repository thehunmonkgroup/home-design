"""Host-driven wall framing, coordinated opening edits and native IFC members."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolved import ResolvedElement
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator
from home_design.changes import ChangeEngine
from home_design.migrations import ModelMigration
from home_design.layers import LayerAssembly


class WallFramingFixture:
    """Add an isolated public synthetic wall with door and window rough openings."""

    @staticmethod
    def configure(model: JsonObject) -> JsonObject:
        """Provide explicit insulation, dimensional member types and a framing recipe."""
        types = Authoring.object(model["types"])
        definition = deepcopy(Authoring.object(types["wallType.exterior.wood-185"]))
        layers = Authoring.array(definition["layers"])
        Authoring.object(layers[2]).update(
            {"representation": "explicit", "material": "material.timber"}
        )
        types["type.framedWall"] = definition
        for name, width, depth in (
            ("stud", 40, 140),
            ("plate", 140, 40),
            ("header", 140, 240),
        ):
            types[f"type.{name}"] = {
                "kind": "memberType",
                "name": name,
                "material": "material.timber",
                "section": {"kind": "rectangle", "width": width, "depth": depth},
            }
        types["type.wallFraming"] = {
            "kind": "wallFramingType",
            "name": "Wall framing recipe",
            "studType": "type.stud",
            "plateType": "type.plate",
            "headerType": "type.header",
            "spacing": 400,
        }
        elements = Authoring.object(model["elements"])
        wall = deepcopy(Authoring.object(elements["wall.south"]))
        wall.update(
            {
                "name": "Framing test wall",
                "type": "type.framedWall",
                "path": {
                    "kind": "line",
                    "start": {"point": [0, -3000]},
                    "end": {"point": [6000, -3000]},
                },
                "base": {"kind": "level", "level": "level.ground", "offset": 0},
                "top": {"kind": "height", "height": 3000},
            }
        )
        elements["wall.framed"] = wall
        for name, station, bottom, width, height in (
            ("window", 2000, 1000, 1200, 1200),
            ("door", 4200, 0, 900, 2100),
        ):
            elements[f"opening.test.{name}"] = {
                "kind": "opening",
                "name": name,
                "geometry": {
                    "kind": "rectangle",
                    "width": width,
                    "height": height,
                    "depth": 300,
                },
                "placement": {
                    "station": station,
                    "stationReference": "start",
                    "verticalOffset": bottom,
                    "verticalReference": "bottom",
                    "depthOffset": 0,
                },
            }
            Authoring.object(model["relationships"])[f"void.test.{name}"] = {
                "kind": "voids",
                "host": "wall.framed",
                "opening": f"opening.test.{name}",
            }
        source: JsonObject = {
            "kind": "wallFraming",
            "name": "Test wall framing",
            "type": "type.wallFraming",
            "host": "wall.framed",
            "layer": 2,
            "blocking": {"row.mid": 1500},
        }
        elements["framing.wall"] = source
        return source

    @staticmethod
    def members(element: ResolvedElement) -> dict[str, JsonObject]:
        """Index generated part records by semantic key."""
        return {
            str(Authoring.object(value)["key"]): Authoring.object(value)
            for value in Authoring.array(element.data["members"])
        }


def test_wall_recipe_generates_disjoint_opening_framing(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Opening framing and real insulation reconcile against the host cavity."""
    WallFramingFixture.configure(reference_model)
    resolved = ModelResolver(reference_model).resolve()
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    framing = resolved.element("framing.wall")
    members = WallFramingFixture.members(framing)
    roles = {str(value["role"]) for value in members.values()}
    assert roles >= {
        "stud",
        "endStud",
        "kingStud",
        "jackStud",
        "header",
        "sill",
        "crippleStud",
        "blocking",
        "topPlate",
        "bottomPlate",
    }
    assert "opening/opening.test.window/header" in members
    assert "opening/opening.test.door/sill" not in members
    header = members["opening/opening.test.window/header"]
    assert header["netVolumeMm3"] == pytest.approx(1280 * 240 * 140)
    cavity = Authoring.object(
        Authoring.array(resolved.element("wall.framed").data["cavities"])[0]
    )
    assert number(cavity["occupiedVolumeMm3"], "occupied") == pytest.approx(
        sum(SolidOperations.volume(mesh) for mesh in framing.meshes)
    )
    assert number(cavity["infillVolumeMm3"], "infill") + number(
        cavity["occupiedVolumeMm3"], "occupied"
    ) == pytest.approx(cavity["grossVolumeMm3"])


def test_wall_framing_preserves_keys_after_opening_edit_and_honors_override(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Opening packages retain identity while geometry moves and stale overrides fail."""
    source = WallFramingFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve().element("framing.wall")
    elements = Authoring.object(reference_model["elements"])
    Authoring.object(Authoring.object(elements["opening.test.window"])["placement"])[
        "station"
    ] = 2100
    after = ModelResolver(reference_model).resolve().element("framing.wall")
    old = WallFramingFixture.members(before)
    new = WallFramingFixture.members(after)
    key = "opening/opening.test.window/header"
    assert old[key]["elevationProfile"] != new[key]["elevationProfile"]
    assert {key for key in old if key.startswith("opening/")} == {
        key for key in new if key.startswith("opening/")
    }
    source["memberOverrides"] = {"grid/0/full": {"omit": True}}
    omitted = WallFramingFixture.members(
        ModelResolver(reference_model).resolve().element("framing.wall")
    )
    assert "grid/0/full" not in omitted
    assert key in omitted
    source["memberOverrides"] = {"missing": {"omit": True}}
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert "Unknown wall framing member" in str(report.to_dict())


def test_wall_member_end_cut_reconciles_infill(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A shortened stud returns its removed end volume to the explicitly owned infill."""
    source = WallFramingFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve()
    key = "grid/0/full"
    source["memberOverrides"] = {
        key: {"endCuts": {"end": {"normal": [0, 0, -1], "offset": 100}}}
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve()
    old = WallFramingFixture.members(before.element("framing.wall"))[key]
    new = WallFramingFixture.members(after.element("framing.wall"))[key]
    assert number(old["netVolumeMm3"], "before") - number(
        new["netVolumeMm3"], "after"
    ) == pytest.approx(100 * 40 * 140)
    old_cavity = Authoring.object(
        Authoring.array(before.element("wall.framed").data["cavities"])[0]
    )
    new_cavity = Authoring.object(
        Authoring.array(after.element("wall.framed").data["cavities"])[0]
    )
    assert number(new_cavity["infillVolumeMm3"], "after") - number(
        old_cavity["infillVolumeMm3"], "before"
    ) == pytest.approx(100 * 40 * 140)


def test_wall_framing_exports_typed_individual_members(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """Native IFC assembly children retain each recipe member's own reusable type."""
    WallFramingFixture.configure(reference_model)
    source = tmp_path / "wall-framing.json"
    ModelLoader.write(reference_model, source)
    result = BuildService().build(source, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assembly = next(
        product
        for product in ifc.by_type("IfcElementAssembly")
        if product.Tag == "framing.wall"
    )
    children = assembly.IsDecomposedBy[0].RelatedObjects
    assert assembly.IsTypedBy[0].RelatingType.PredefinedType == "USERDEFINED"
    assert assembly.IsTypedBy[0].RelatingType.ElementType == "wallSystem"
    assert all(child.Tag.startswith("framing.wall/member/") for child in children)
    header = next(
        child for child in children if child.Tag.endswith("opening.test.window/header")
    )
    assert header.is_a("IfcBeam")
    assert header.IsTypedBy[0].RelatingType.is_a("IfcBeamType")
    assert header.IsTypedBy[0].RelatingType.PredefinedType == "LINTEL"
    for child in children:
        if child.IsTypedBy[0].RelatingType.ElementType in {
            "stud",
            "kingStud",
            "jackStud",
            "crippleStud",
        }:
            assert child.is_a("IfcMember")
            assert child.IsTypedBy[0].RelatingType.PredefinedType == "STUD"
        elif child.IsTypedBy[0].RelatingType.ElementType in {"topPlate", "bottomPlate"}:
            assert child.IsTypedBy[0].RelatingType.PredefinedType == "PLATE"
    assert len(children) == len(
        WallFramingFixture.members(
            ModelResolver(reference_model).resolve().element("framing.wall")
        )
    )


def test_wall_framing_follows_gable_top_and_corner_pack(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Top plates and stud cuts follow both roof slopes without overlapping boards."""
    source = WallFramingFixture.configure(reference_model)
    source.pop("blocking")
    wall = Authoring.object(
        Authoring.object(reference_model["elements"])["wall.framed"]
    )
    wall["path"] = {
        "kind": "line",
        "start": {"point": [1000, 0]},
        "end": {"point": [1000, 8000]},
    }
    wall["top"] = {
        "kind": "surface",
        "element": "roof.main",
        "surface": "underside",
        "offset": 0,
    }
    Authoring.object(Authoring.object(reference_model["types"])["type.wallFraming"])[
        "endStuds"
    ] = 3
    resolved = ModelResolver(reference_model).resolve()
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    framing = resolved.element("framing.wall")
    members = WallFramingFixture.members(framing)
    assert sum(record["role"] == "cornerStud" for record in members.values()) == 6
    assert sum(record["role"] == "topPlate" for record in members.values()) == 4
    assert members["grid/0/full"]["lengthMm"] != members["grid/1/full"]["lengthMm"]
    assert number(members["top/0/0"]["stockLengthMm"], "stock length") > 4000


def test_generated_member_host_follows_opening_and_rejects_missing_key(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A mounted part follows a stable header key through a hosted opening move."""
    WallFramingFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    host: JsonObject = {
        "kind": "member",
        "element": "framing.wall",
        "part": "opening/opening.test.window/header",
        "station": 200,
        "surface": "positiveX",
    }
    elements["member.mounted"] = {
        "kind": "member",
        "name": "Header-mounted part",
        "type": "type.stud",
        "role": "other",
        "axis": [{"host": host}, {"host": {**host, "station": 300}}],
    }
    assert validator.validate(reference_model).is_valid
    before = ModelResolver(reference_model).resolve().element("member.mounted")
    Authoring.object(Authoring.object(elements["opening.test.window"])["placement"])[
        "station"
    ] = 2100
    after = ModelResolver(reference_model).resolve().element("member.mounted")
    first = Authoring.array(Authoring.array(before.data["axis"])[0])
    second = Authoring.array(Authoring.array(after.data["axis"])[0])
    assert number(second[0], "x") - number(first[0], "x") == pytest.approx(100)
    host["part"] = "missing"
    assert not validator.validate(reference_model).is_valid


def test_named_cavity_framing_follows_layer_insertion_and_reordering(
    reference_model: JsonObject, loader: ModelLoader, validator: ModelValidator
) -> None:
    """A layout keeps its physical layer and generated IDs after stack positions change."""
    WallFramingFixture.configure(reference_model)
    candidate = ChangeEngine(loader).apply(
        reference_model, ModelMigration(loader).prepare(reference_model)
    )
    definition = Authoring.object(
        Authoring.object(candidate["types"])["type.framedWall"]
    )
    layers = Authoring.array(definition["layers"])
    source = Authoring.object(Authoring.object(candidate["elements"])["framing.wall"])
    before = ModelResolver(candidate).resolve().element("framing.wall")
    selected = source["layer"]
    first = deepcopy(Authoring.object(layers[0]))
    first.update({"id": "additional.skin", "thickness": 2})
    layers.insert(0, first)
    layers.append(layers.pop(1))
    report = validator.validate(candidate)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(candidate).resolve().element("framing.wall")
    assert after.data["memberIdentities"] == before.data["memberIdentities"]
    assert source["layer"] == selected
    assert (
        Authoring.object(layers[LayerAssembly.index(layers, selected)])[
            "representation"
        ]
        == "explicit"
    )
    layers.pop(LayerAssembly.index(layers, selected))
    report = validator.validate(candidate)
    assert not report.is_valid
    assert any(
        diagnostic.code == "layer.identity-unavailable" for diagnostic in report.errors
    )


def test_cut_generated_header_updates_member_schedule_and_cavity_balance(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Assembly cuts update the actual child volume and leave stable header identity."""
    WallFramingFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve().element("framing.wall")
    Authoring.object(reference_model["elements"])["cut.header"] = {
        "kind": "penetration",
        "name": "Header bore",
        "host": "framing.wall",
        "purpose": "service",
        "placement": {
            "origin": {"point": [2500, -3100, 2300]},
            "rotation": [-90, 0, 0],
        },
        "section": {"kind": "rectangle", "width": 40, "depth": 40},
        "depth": 200,
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    old = WallFramingFixture.members(before)["opening/opening.test.window/header"]
    new = WallFramingFixture.members(resolved.element("framing.wall"))[
        "opening/opening.test.window/header"
    ]
    assert number(old["netVolumeMm3"], "volume") - number(
        new["netVolumeMm3"], "volume"
    ) == pytest.approx(40 * 40 * 140)
    rows = Authoring.array(ModelReports(resolved).schedules()["generatedMembers"])
    header = next(
        Authoring.object(row)
        for row in rows
        if Authoring.object(row)["key"] == new["key"]
    )
    assert header["netVolumeMm3"] == new["netVolumeMm3"]


def test_wall_framing_selects_polyline_segment(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A bent host supports separate framing runs with locally measured stations."""
    source = WallFramingFixture.configure(reference_model)
    source.update({"segment": 1, "startInset": 100})
    source.pop("blocking")
    wall = Authoring.object(
        Authoring.object(reference_model["elements"])["wall.framed"]
    )
    wall["path"] = {
        "kind": "polyline",
        "points": [
            {"point": [0, -3000]},
            {"point": [6000, -3000]},
            {"point": [6000, 0]},
        ],
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    members = WallFramingFixture.members(
        ModelResolver(reference_model).resolve().element("framing.wall")
    )
    assert not any(key.startswith("opening/") for key in members)
    first = Authoring.array(Authoring.array(members["end/start/0"]["axis"])[0])
    assert first[1] == pytest.approx(-2880)
    source["segment"] = 2
    assert not validator.validate(reference_model).is_valid


def test_wall_backing_mounts_against_interior_cavity_face(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Shallow backing boards occupy the authored cavity depth without duplicate insulation."""
    source = WallFramingFixture.configure(reference_model)
    Authoring.object(reference_model["types"])["type.backing"] = {
        "kind": "memberType",
        "name": "Interior backing",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 40, "depth": 180},
    }
    source["blocking"] = {
        "shelf": {
            "height": 1500,
            "role": "backing",
            "memberType": "type.backing",
            "depthOffset": -50,
        }
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve().element("framing.wall")
    records = [
        value
        for value in WallFramingFixture.members(resolved).values()
        if value["role"] == "backing"
    ]
    assert records and all(value["depthOffset"] == -50 for value in records)
    meshes = [
        mesh for mesh in resolved.meshes if mesh.role.startswith("part:blocking/shelf/")
    ]
    assert all(
        max(point[1] for point in mesh.vertices) == pytest.approx(-3039.5)
        for mesh in meshes
    )


@pytest.mark.parametrize(
    "case", ["aggregate", "host", "type", "opening", "overlap", "shallow"]
)
def test_wall_framing_rejects_invalid_dependencies_and_packages(
    reference_model: JsonObject, validator: ModelValidator, case: str
) -> None:
    """Invalid framing fails as a model diagnostic before export."""
    source = WallFramingFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    if case == "aggregate":
        source["layer"] = 0
    elif case == "host":
        source["host"] = "slab.ground"
    elif case == "type":
        Authoring.object(types["type.wallFraming"])["studType"] = "type.framedWall"
    elif case == "opening":
        source["openingOverrides"] = {"opening.missing": {"jackStuds": 2}}
    elif case == "overlap":
        source["memberOverrides"] = {"grid/0/full": {"offset": [-360, 0]}}
    else:
        Authoring.object(Authoring.object(types["type.header"])["section"])[
            "depth"
        ] = 900
    assert not validator.validate(reference_model).is_valid
