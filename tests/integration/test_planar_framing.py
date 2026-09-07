"""Boundary-fitted floor, deck and roof framing across physical and IFC contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import ifcopenshell.validate
import pytest
from ifcopenshell.ifcopenshell_wrapper import TriangulationElement

from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.resolved import ResolvedElement
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class PlanarFixture:
    """Create an irregular slab with a hole and a fully explicit framing layer."""

    @staticmethod
    def configure(model: JsonObject) -> JsonObject:
        """Use public materials and synthetic geometry outside the reference house."""
        types = Authoring.object(model["types"])
        types["type.deck"] = {
            "kind": "slabType",
            "layerOrder": "topToBottom",
            "name": "Framed deck layer",
            "layers": [
                {
                    "name": "Framing cavity",
                    "thickness": 180,
                    "function": "structure",
                    "representation": "explicit",
                }
            ],
        }
        types["type.joist"] = {
            "kind": "memberType",
            "name": "Joist",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 40, "depth": 180},
        }
        types["type.layout"] = {
            "kind": "planarFramingType",
            "name": "Deck framing layout",
            "memberType": "type.joist",
            "rimType": "type.joist",
            "spacing": 400,
        }
        elements = Authoring.object(model["elements"])
        outer: list[JsonValue] = [
            {"point": [x, y]}
            for x, y in (
                (0, -8000),
                (6000, -8000),
                (6000, -6000),
                (4000, -4000),
                (0, -4000),
            )
        ]
        hole: list[JsonValue] = [
            {"point": [x, y]}
            for x, y in ((1000, -7000), (2000, -7000), (2000, -6000), (1000, -6000))
        ]
        elements["slab.framed"] = {
            "kind": "slab",
            "name": "Irregular deck",
            "type": "type.deck",
            "role": "deck",
            "storey": "level.ground",
            "footprint": {
                "outer": outer,
                "holes": [hole],
            },
            "datum": {"kind": "level", "level": "level.ground", "offset": 0},
            "extrusionDirection": "down",
        }
        source: JsonObject = {
            "kind": "planarFraming",
            "name": "Deck framing",
            "type": "type.layout",
            "host": "slab.framed",
            "layer": 0,
            "direction": [1, 0],
            "blocking": {"mid": 3000},
        }
        elements["framing.deck"] = source
        return source

    @staticmethod
    def members(element: ResolvedElement) -> dict[str, JsonObject]:
        """Read generated member records by their stable local key."""
        return {
            str(Authoring.object(value)["key"]): Authoring.object(value)
            for value in Authoring.array(element.data["members"])
        }


def test_opposing_roof_rims_preserve_cavity_material_through_serialization(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Coincident rim interfaces on two sloped faces retain disjoint framing and the exact cavity balance."""
    types = Authoring.object(reference_model["types"])
    roof_type = Authoring.object(types["roofType.shingle-250"])
    Authoring.object(Authoring.array(roof_type["layers"])[2])[
        "representation"
    ] = "explicit"
    types["type.roofJoist"] = {
        "kind": "memberType",
        "name": "Illustrative roof stock",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 40, "depth": 220},
    }
    types["type.roofLayout"] = {
        "kind": "planarFramingType",
        "name": "Roof layout with boundary rims",
        "memberType": "type.roofJoist",
        "rimType": "type.roofJoist",
        "spacing": 600,
    }
    roof = Authoring.object(reference_model["elements"])["roof.main"]
    elements: JsonObject = {"roof.main": roof}
    for index in (1, 2):
        elements[f"framing.roof.{index}"] = {
            "kind": "planarFraming",
            "name": f"Roof face {index}",
            "type": "type.roofLayout",
            "host": "roof.main",
            "layer": 2,
            "face": f"roof.main.face-{index}",
            "direction": [0, 1],
        }
    reference_model["elements"] = elements
    (
        reference_model["relationships"],
        reference_model["requirements"],
        reference_model["solarStudies"],
    ) = ({}, [], [])
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    host = resolved.element("roof.main")
    cavity = Authoring.object(Authoring.array(host.data["cavities"])[0])
    assert number(cavity["grossVolumeMm3"], "gross") == pytest.approx(
        number(cavity["occupiedVolumeMm3"], "occupied")
        + number(cavity["infillVolumeMm3"], "infill"),
        rel=1e-9,
    )
    for mesh in host.meshes:
        solid = SolidOperations.solid(mesh)
        assert SolidOperations.mesh(solid, mesh.material_id, mesh.role) is not None
    output = tmp_path / "roof-infill.ifc"
    IfcExporter().export(resolved, output)
    native = ifcopenshell.open(output)
    shape = ifcopenshell.geom.create_shape(
        ifcopenshell.geom.settings(),
        native.by_guid(IfcExporter.stable_guid("roof.main")),
    )
    assert isinstance(shape, TriangulationElement)
    assert ifcopenshell.util.shape.get_volume(shape.geometry) == pytest.approx(
        sum(SolidOperations.volume(mesh) for mesh in host.meshes) / 1e9, rel=1e-7
    )


def test_irregular_deck_layout_fits_hole_and_perimeter(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Joists have real variable lengths, framed hole rims, and separate blocking boards."""
    PlanarFixture.configure(reference_model)
    resolved = ModelResolver(reference_model).resolve()
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    framing = resolved.element("framing.deck")
    records = PlanarFixture.members(framing)
    assert {str(record["role"]) for record in records.values()} == {
        "joist",
        "rim",
        "blocking",
    }
    assert "grid/3/0" in records and "grid/3/1" in records
    assert records["grid/1/0"]["lengthMm"] != records["grid/8/0"]["lengthMm"]
    assert any(key.startswith("rim/1/") for key in records)
    for mesh in framing.meshes:
        record = records[mesh.role.removeprefix("part:")]
        across = [
            number(value, "section axis")
            for value in Authoring.array(Authoring.object(record["sectionFrame"])["x"])
        ]
        positions = [
            sum(point[index] * across[index] for index in range(3))
            for point in mesh.vertices
        ]
        assert max(positions) - min(positions) <= 40 + 1e-6
    cavity = Authoring.object(
        Authoring.array(resolved.element("slab.framed").data["cavities"])[0]
    )
    assert cavity["infillVolumeMm3"] == 0
    assert cavity["occupiedVolumeMm3"] == pytest.approx(
        sum(SolidOperations.volume(mesh) for mesh in framing.meshes)
    )
    assert not resolved.element("slab.framed").meshes
    assert resolved.to_dict() == ModelResolver(reference_model).resolve().to_dict()


def test_planar_layout_preserves_member_keys_on_boundary_edit(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A far-edge edit changes member lengths while retaining regular grid identities."""
    source = PlanarFixture.configure(reference_model)
    source.pop("blocking")
    before = PlanarFixture.members(
        ModelResolver(reference_model).resolve().element("framing.deck")
    )
    slab = Authoring.object(
        Authoring.object(reference_model["elements"])["slab.framed"]
    )
    boundary = Authoring.array(Authoring.object(slab["footprint"])["outer"])
    Authoring.object(boundary[1])["point"] = [6400, -8000]
    Authoring.object(boundary[2])["point"] = [6400, -6000]
    after = PlanarFixture.members(
        ModelResolver(reference_model).resolve().element("framing.deck")
    )
    assert before["grid/1/0"]["lengthMm"] != after["grid/1/0"]["lengthMm"]
    source["memberOverrides"] = {"grid/1/0": {"omit": True}}
    assert validator.validate(reference_model).is_valid
    assert "grid/1/0" not in PlanarFixture.members(
        ModelResolver(reference_model).resolve().element("framing.deck")
    )
    source["memberOverrides"] = {"missing": {"omit": True}}
    assert not validator.validate(reference_model).is_valid


def test_planar_member_end_cut_updates_physical_cavity_volume(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A selected joist setback changes its solid and cavity balance by the same amount."""
    source = PlanarFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve()
    key = "grid/1/0"
    old = PlanarFixture.members(before.element("framing.deck"))[key]
    source["memberOverrides"] = {
        key: {"endCuts": {"start": {"normal": [0, 0, 1], "offset": 100}}}
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve()
    new = PlanarFixture.members(after.element("framing.deck"))[key]
    assert number(old["netVolumeMm3"], "before") - number(
        new["netVolumeMm3"], "after"
    ) == pytest.approx(100 * 40 * 180)
    assert old["stockLengthMm"] == new["stockLengthMm"]
    old_cavity = Authoring.object(
        Authoring.array(before.element("slab.framed").data["cavities"])[0]
    )
    new_cavity = Authoring.object(
        Authoring.array(after.element("slab.framed").data["cavities"])[0]
    )
    assert number(old_cavity["occupiedVolumeMm3"], "before") - number(
        new_cavity["occupiedVolumeMm3"], "after"
    ) == pytest.approx(100 * 40 * 180)


def test_roof_face_layout_follows_slope(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Rafters use the sloped layer plane and retain surface-normal section depth."""
    source = PlanarFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    roof_type = deepcopy(Authoring.object(types["type.deck"]))
    roof_type["kind"] = "roofType"
    types["type.framedRoof"] = roof_type
    elements = Authoring.object(reference_model["elements"])
    roof = deepcopy(Authoring.object(elements["roof.main"]))
    roof["type"] = "type.framedRoof"
    elements["roof.framed"] = roof
    source.update(
        {"host": "roof.framed", "face": "roof.framed.face-1", "direction": [0, 1]}
    )
    source.pop("blocking")
    resolved = ModelResolver(reference_model).resolve()
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    framing = resolved.element("framing.deck")
    rafters = [
        record
        for record in PlanarFixture.members(framing).values()
        if record["role"] == "rafter"
    ]
    assert rafters
    axis = Authoring.array(rafters[0]["axis"])
    assert Authoring.array(axis[0])[2] != Authoring.array(axis[1])[2]
    assert all(
        record["section"] == {"kind": "rectangle", "width": 40, "depth": 180}
        for record in rafters
    )
    assert number(
        Authoring.array(Authoring.object(framing.data["plane"])["z"])[2], "normal Z"
    ) == pytest.approx(0.866025403784)
    elements["framing.roof.other"] = {
        **source,
        "name": "Other roof face",
        "face": "roof.framed.face-2",
    }
    paired = ModelResolver(reference_model).resolve()
    assert paired.element("framing.roof.other").meshes
    assert validator.validate(reference_model).is_valid
    path = tmp_path / "roof-framing.ifc"
    IfcExporter().export(paired, path)
    native = ifcopenshell.open(path)
    for identity in ("framing.deck", "framing.roof.other"):
        assembly = native.by_guid(IfcExporter.stable_guid(identity))
        assert assembly.IsTypedBy[0].RelatingType.PredefinedType == "USERDEFINED"
        assert assembly.IsTypedBy[0].RelatingType.ElementType == "roofSystem"


def test_planar_framing_exports_individual_ifc_members(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """A fitted deck exports one native assembly with typed, selectable member geometry."""
    PlanarFixture.configure(reference_model)
    source = tmp_path / "planar.json"
    ModelLoader.write(reference_model, source)
    result = BuildService().build(source, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assembly = next(
        item for item in ifc.by_type("IfcElementAssembly") if item.Tag == "framing.deck"
    )
    children = assembly.IsDecomposedBy[0].RelatedObjects
    assert assembly.IsTypedBy[0].RelatingType.PredefinedType == "USERDEFINED"
    assert assembly.IsTypedBy[0].RelatingType.ElementType == "floorSystem"
    assert children and all(
        (child.is_a("IfcMember") or child.is_a("IfcBeam")) and child.Representation
        for child in children
    )
    assert any(child.Tag == "framing.deck/member/grid/3/1" for child in children)
    joist = next(
        child for child in children if child.Tag == "framing.deck/member/grid/3/1"
    )
    assert joist.is_a("IfcBeam")
    assert joist.IsTypedBy[0].RelatingType.is_a("IfcBeamType")
    assert joist.IsTypedBy[0].RelatingType.PredefinedType == "JOIST"


def test_separated_roofs_do_not_miter_at_projected_edges(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Roof planes at different elevations do not acquire an invented framing joint."""
    source = PlanarFixture.configure(reference_model)
    source.pop("blocking")
    types = Authoring.object(reference_model["types"])
    types["type.roof"] = {**Authoring.object(types["type.deck"]), "kind": "roofType"}
    first: JsonObject = {
        "id": "face.lower",
        "boundary": {
            "outer": [
                [0, -8000, 1000],
                [6000, -8000, 1000],
                [6000, -6000, 2000],
                [0, -6000, 2000],
            ]
        },
    }
    faces: list[JsonValue] = [first]
    Authoring.object(reference_model["elements"])["roof.test"] = {
        "kind": "roof",
        "name": "Separated roof planes",
        "type": "type.roof",
        "storey": "level.ground",
        "geometry": {"kind": "faceSet", "faces": faces},
    }
    source.update({"host": "roof.test", "face": "face.lower", "direction": [0, 1]})
    before = ModelResolver(reference_model).resolve().element("framing.deck")
    faces.append(
        {
            "id": "face.upper",
            "boundary": {
                "outer": [
                    [0, -6000, 3000],
                    [6000, -6000, 3000],
                    [6000, -4000, 2000],
                    [0, -4000, 2000],
                ]
            },
        }
    )
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve().element("framing.deck")
    assert before.meshes == after.meshes
    assert before.data["members"] == after.data["members"]


@pytest.mark.parametrize(
    "case", ["layer", "host", "direction", "face", "depth", "spacing", "type"]
)
def test_invalid_planar_framing_is_diagnostic(
    reference_model: JsonObject, validator: ModelValidator, case: str
) -> None:
    """Reject incompatible hosts, missing layers, invalid sections and overlapping grids."""
    source = PlanarFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    if case == "layer":
        source["layer"] = 1
    elif case == "host":
        source["host"] = "wall.south"
    elif case == "direction":
        source["direction"] = [0, 0]
    elif case == "face":
        source["face"] = "unused"
    elif case == "depth":
        Authoring.object(Authoring.object(types["type.joist"])["section"])[
            "depth"
        ] = 200
    elif case == "spacing":
        Authoring.object(types["type.layout"])["spacing"] = 20
    else:
        Authoring.object(types["type.layout"])["rimType"] = "type.deck"
    assert not validator.validate(reference_model).is_valid
