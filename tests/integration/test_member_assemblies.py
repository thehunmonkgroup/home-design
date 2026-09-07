"""Authored truss networks, explicit joint trimming, mounting and native IFC connections."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.resolved import ResolvedElement
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class TrussFixture:
    """Author an illustrative four-member king-post truss with explicit trim interfaces."""

    @staticmethod
    def configure(model: JsonObject) -> JsonObject:
        """Place a local node network outside the public reference house."""
        Authoring.object(model["types"])["type.trussMember"] = {
            "kind": "memberType",
            "name": "Truss member",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 40, "depth": 120},
        }
        source: JsonObject = {
            "kind": "memberAssembly",
            "name": "Illustrative king-post truss",
            "assemblyType": "truss",
            "storey": "level.ground",
            "placement": {"origin": {"point": [0, -5000, 3000]}},
            "nodes": {
                "left": {"local": [0, 0, 0]},
                "right": {"local": [4000, 0, 0]},
                "apex": {"local": [2000, 0, 1500]},
                "middle": {"local": [2000, 0, 0]},
            },
            "members": {
                "bottom": {
                    "start": "left",
                    "end": "right",
                    "memberType": "type.trussMember",
                    "role": "bottomChord",
                },
                "left": {
                    "start": "left",
                    "end": "apex",
                    "memberType": "type.trussMember",
                    "role": "topChord",
                    "trimAgainst": ["bottom"],
                },
                "right": {
                    "start": "right",
                    "end": "apex",
                    "memberType": "type.trussMember",
                    "role": "topChord",
                    "trimAgainst": ["bottom", "left"],
                },
                "web": {
                    "start": "middle",
                    "end": "apex",
                    "memberType": "type.trussMember",
                    "role": "web",
                    "roll": 90,
                    "trimAgainst": ["bottom", "left", "right"],
                },
            },
        }
        Authoring.object(model["elements"])["truss.test"] = source
        return source

    @staticmethod
    def records(element: ResolvedElement) -> dict[str, JsonObject]:
        """Read member specifications using durable scoped keys."""
        return {
            str(Authoring.object(value)["key"]): Authoring.object(value)
            for value in Authoring.array(element.data["members"])
        }


def test_truss_joint_trimming_preserves_disjoint_member_solids(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Authored cuts make joints physically disjoint without erasing stock references."""
    TrussFixture.configure(reference_model)
    resolved = ModelResolver(reference_model).resolve()
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    assembly = resolved.element("truss.test")
    assert assembly.data["memberCount"] == 4
    records = TrussFixture.records(assembly)
    assert records["left"]["stockLengthMm"] == pytest.approx(2500)
    assert number(records["left"]["netVolumeMm3"], "net volume") < 2500 * 40 * 120
    for index, mesh in enumerate(assembly.meshes):
        for other in assembly.meshes[index + 1 :]:
            assert SolidOperations.intersection(mesh, other) is None
    assert resolved.to_dict() == ModelResolver(reference_model).resolve().to_dict()


def test_local_truss_placement_rotates_members_and_mounts(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Local assembly rotation also rotates a vertical web's section orientation."""
    source = TrussFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve().element("truss.test")
    Authoring.object(source["placement"])["rotation"] = [0, 0, 90]
    elements = Authoring.object(reference_model["elements"])
    host: JsonObject = {
        "kind": "member",
        "element": "truss.test",
        "part": "web",
        "station": 300,
        "surface": "positiveX",
    }
    elements["member.mounted"] = {
        "kind": "member",
        "name": "Mounted member",
        "role": "other",
        "type": "type.trussMember",
        "axis": [{"host": host}, {"host": {**host, "station": 400}}],
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    after = resolved.element("truss.test")
    first = TrussFixture.records(before)["web"]
    second = TrussFixture.records(after)["web"]
    assert first["sectionFrame"] != second["sectionFrame"]
    assert first["netVolumeMm3"] == pytest.approx(second["netVolumeMm3"])
    assert resolved.element("member.mounted").data["memberLength"] == pytest.approx(100)


def test_assembly_export_omits_connections_to_removed_members(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """A cut that consumes one whole member leaves valid surviving IFC connections."""
    TrussFixture.configure(reference_model)
    Authoring.object(reference_model["elements"])["cut.web"] = {
        "kind": "penetration",
        "name": "Remove center web",
        "purpose": "recess",
        "host": "truss.test",
        "placement": {"origin": {"point": [2000, -5000, 3050]}},
        "section": {"kind": "rectangle", "width": 160, "depth": 80},
        "depth": 1500,
    }
    source = tmp_path / "cut-truss.json"
    ModelLoader.write(reference_model, source)
    result = BuildService().build(source, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    products = {product.Tag for product in ifc.by_type("IfcElement")}
    assert "truss.test/member/web" not in products
    assert "truss.test/member/left" in products
    assert (
        len(
            [
                value
                for value in ifc.by_type("IfcRelConnectsElements")
                if value.Name.startswith("Authored node")
            ]
        )
        == 3
    )


def test_cross_bridging_follows_member_host_edits(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Staggered diagonal bridging stays connected to authored points on two joists."""
    source = TrussFixture.configure(reference_model)
    source["assemblyType"] = "bracing"
    elements = Authoring.object(reference_model["elements"])
    first: JsonObject = {
        "kind": "member",
        "name": "Joist A",
        "type": "type.trussMember",
        "role": "joist",
        "axis": [{"point": [0, -5000, 3000]}, {"point": [4000, -5000, 3000]}],
    }
    second: JsonObject = {
        **first,
        "name": "Joist B",
        "axis": [{"point": [0, -4500, 3000]}, {"point": [4000, -4500, 3000]}],
    }
    elements["member.a"], elements["member.b"] = first, second
    nodes: JsonObject = {}
    for key, host, station, height in (
        ("aa", "member.a", 1900, -40),
        ("bb", "member.b", 1900, 40),
        ("cc", "member.a", 2100, 40),
        ("dd", "member.b", 2100, -40),
    ):
        nodes[key] = {
            "host": {
                "kind": "member",
                "element": host,
                "station": station,
                "offset": [0, height, 0],
            }
        }
    source["nodes"] = nodes
    source["members"] = {
        "forward": {
            "start": "aa",
            "end": "bb",
            "memberType": "type.trussMember",
            "role": "bridging",
        },
        "backward": {
            "start": "cc",
            "end": "dd",
            "memberType": "type.trussMember",
            "role": "bridging",
        },
    }
    assert validator.validate(reference_model).is_valid
    before = TrussFixture.records(
        ModelResolver(reference_model).resolve().element("truss.test")
    )
    second["axis"] = [{"point": [0, -4300, 3000]}, {"point": [4000, -4300, 3000]}]
    assert validator.validate(reference_model).is_valid
    after = TrussFixture.records(
        ModelResolver(reference_model).resolve().element("truss.test")
    )
    assert before.keys() == after.keys()
    for key in before:
        assert before[key]["stockLengthMm"] == pytest.approx((500**2 + 80**2) ** 0.5)
        assert after[key]["stockLengthMm"] == pytest.approx((700**2 + 80**2) ** 0.5)


@pytest.mark.parametrize("role", ["hip", "valley", "tie"])
def test_roof_members_follow_authored_surface_nodes(
    reference_model: JsonObject, validator: ModelValidator, role: str
) -> None:
    """Roof-member endpoint heights and lengths update from their selected roof faces."""
    source = TrussFixture.configure(reference_model)
    source["assemblyType"] = "roofSystem"
    source["nodes"] = {
        "lower": {
            "host": {
                "kind": "surface",
                "element": "roof.main",
                "surface": "top",
                "face": "roof.main.face-1",
                "point": [1000, 1000],
                "offset": [0, 0, -60],
            }
        },
        "upper": {
            "host": {
                "kind": "surface",
                "element": "roof.main",
                "surface": "top",
                "face": "roof.main.face-1",
                "point": [3000, 2000],
                "offset": [0, 0, -60],
            }
        },
    }
    source["members"] = {
        "roofMember": {
            "start": "lower",
            "end": "upper",
            "memberType": "type.trussMember",
            "role": role,
        }
    }
    assert validator.validate(reference_model).is_valid
    before = TrussFixture.records(
        ModelResolver(reference_model).resolve().element("truss.test")
    )["roofMember"]
    roof = Authoring.object(Authoring.object(reference_model["elements"])["roof.main"])
    Authoring.object(roof["geometry"])["pitch"] = 40
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = TrussFixture.records(
        ModelResolver(reference_model).resolve().element("truss.test")
    )["roofMember"]
    assert before["axis"] != after["axis"]
    assert number(after["stockLengthMm"], "after length") > number(
        before["stockLengthMm"], "before length"
    )
    assert after["role"] == role


@pytest.mark.parametrize(
    "role,edge_height,outer_height", [("hip", 3000, 2000), ("valley", 2000, 3000)]
)
def test_crease_member_owns_material_across_adjoining_roof_faces(
    reference_model: JsonObject,
    validator: ModelValidator,
    role: str,
    edge_height: int,
    outer_height: int,
) -> None:
    """A diagonal hip or valley fits both roof domains and follows a crease elevation edit."""
    source = TrussFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    types["type.creaseRoof"] = {
        "kind": "roofType",
        "name": "Explicit roof cavity",
        "layerOrder": "topToBottom",
        "layers": [
            {
                "name": "Structure",
                "function": "structure",
                "thickness": 250,
                "representation": "explicit",
            }
        ],
    }
    first: list[JsonValue] = [
        [0, -8000, edge_height],
        [4000, -4000, edge_height + 500],
        [0, -4000, outer_height],
    ]
    second: list[JsonValue] = [
        [0, -8000, edge_height],
        [4000, -8000, outer_height],
        [4000, -4000, edge_height + 500],
    ]
    Authoring.object(reference_model["elements"])["roof.crease"] = {
        "kind": "roof",
        "name": "Creased roof",
        "type": "type.creaseRoof",
        "storey": "level.ground",
        "geometry": {
            "kind": "faceSet",
            "faces": [
                {"id": "face.first", "boundary": {"outer": first}},
                {"id": "face.second", "boundary": {"outer": second}},
            ],
        },
    }
    source["assemblyType"] = "roofSystem"
    source["nodes"] = {
        "lower": {
            "host": {
                "kind": "surface",
                "element": "roof.crease",
                "surface": "top",
                "face": "face.first",
                "point": [1000, -7000],
                "offset": [0, 0, -20],
            }
        },
        "upper": {
            "host": {
                "kind": "surface",
                "element": "roof.crease",
                "surface": "top",
                "face": "face.first",
                "point": [3000, -5000],
                "offset": [0, 0, -20],
            }
        },
    }
    source["members"] = {
        "crease": {
            "start": "lower",
            "end": "upper",
            "memberType": "type.trussMember",
            "role": role,
        }
    }
    source["occupies"] = {
        "regions": [{"host": "roof.crease", "layer": 0}],
        "fit": "clip",
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    before = ModelResolver(reference_model).resolve()
    member = before.element("truss.test")
    volume = SolidOperations.volume(member.meshes[0])
    assert volume > 0
    record = TrussFixture.records(member)["crease"]
    assert volume < number(record["stockLengthMm"], "stock length") * 40 * 120
    cavity = Authoring.object(
        Authoring.array(before.element("roof.crease").data["cavities"])[0]
    )
    assert cavity["occupiedVolumeMm3"] == pytest.approx(volume)
    signed_distances = [x - (y + 8000) for x, y, _ in member.meshes[0].vertices]
    assert min(signed_distances) < -1 and max(signed_distances) > 1
    Authoring.array(first[1])[2] = edge_height + 800
    Authoring.array(second[2])[2] = edge_height + 800
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve().element("truss.test")
    assert record["axis"] != TrussFixture.records(after)["crease"]["axis"]
    assert member.meshes != after.meshes


def test_truss_exports_native_members_and_joint_points(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """IFC preserves individually typed boards and explicit shared-node connections."""
    TrussFixture.configure(reference_model)
    path = tmp_path / "truss.json"
    ModelLoader.write(reference_model, path)
    result = BuildService().build(path, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assembly = next(
        value
        for value in ifc.by_type("IfcElementAssembly")
        if value.Tag == "truss.test"
    )
    assert len(assembly.IsDecomposedBy[0].RelatedObjects) == 4
    assert assembly.PredefinedType == "TRUSS"
    joints = [
        value
        for value in ifc.by_type("IfcRelConnectsElements")
        if value.Name.startswith("Authored node")
    ]
    assert len(joints) == 5
    assert all(
        value.ConnectionGeometry.is_a("IfcConnectionPointGeometry") for value in joints
    )
    assert all(
        value.RelatingElement.Tag.startswith("truss.test/member/") for value in joints
    )


@pytest.mark.parametrize(
    "case", ["node", "unused", "type", "trim", "cycle", "overlap", "disconnected"]
)
def test_invalid_truss_network_is_rejected(
    reference_model: JsonObject, validator: ModelValidator, case: str
) -> None:
    """Invalid scoped references and unexplained joint intersections fail validation."""
    source = TrussFixture.configure(reference_model)
    members = Authoring.object(source["members"])
    left = Authoring.object(members["left"])
    if case == "node":
        left["start"] = "missing"
    elif case == "unused":
        Authoring.object(source["nodes"])["unused"] = {"local": [0, 10, 0]}
    elif case == "type":
        left["memberType"] = "wallType.exterior.wood-185"
    elif case == "trim":
        left["trimAgainst"] = ["missing"]
    elif case == "cycle":
        Authoring.object(members["bottom"])["trimAgainst"] = ["left"]
    elif case == "overlap":
        left.pop("trimAgainst")
    else:
        Authoring.object(source["nodes"]).update(
            {"remoteA": {"local": [0, 1000, 0]}, "remoteB": {"local": [1000, 1000, 0]}}
        )
        members["remote"] = {
            "start": "remoteA",
            "end": "remoteB",
            "memberType": "type.trussMember",
            "role": "tie",
        }
    assert not validator.validate(reference_model).is_valid
