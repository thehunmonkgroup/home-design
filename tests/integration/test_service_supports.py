"""Analytic route-relative supports, fitting stations and durable construction connections."""

from __future__ import annotations

import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.errors import ModelValidationError
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.placement import HostPlacement
from home_design.reports import ModelReports
from home_design.resolved import Vec3
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class SupportFixture:
    """Author an illustrative fabricated strap with explicit support participants."""

    @staticmethod
    def configure(model: JsonObject, family: str = "pipe") -> JsonObject:
        """Place a hollow rectangular strap at an analytic bend station."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        types = Authoring.object(model["types"])
        medium = {
            "pipe": "water",
            "duct": "air",
            "cable": "electrical",
            "conduit": "electrical",
        }[family]
        types["type.route"] = {
            "kind": "serviceRouteType",
            "name": "Supported stock",
            "family": family,
            "material": "material.timber",
            "medium": medium,
            "connectionType": "illustrativeFace",
            "section": (
                {"kind": "rectangle", "width": 40, "height": 30}
                if family == "duct"
                else {"kind": "circle", "diameter": 40}
            ),
            **({"wallThickness": 2} if family != "cable" else {}),
        }
        types["type.support"] = {
            "kind": "hardwareType",
            "name": "Illustrative route strap",
            "role": "hanger",
            "material": "material.timber",
            "solids": {
                "body": {
                    "section": {"kind": "rectangle", "width": 60, "depth": 60},
                    "depth": 6,
                }
            },
            "cuts": {
                "passage": {
                    "section": {"kind": "rectangle", "width": 44, "depth": 44},
                    "depth": 6,
                }
            },
        }
        types["type.member"] = {
            "kind": "memberType",
            "name": "Support framing",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 80, "depth": 80},
        }
        for key, point in (
            ("start", [0, 0, 0]),
            ("corner", [1000, 0, 0]),
            ("end", [1000, 1000, 0]),
        ):
            Authoring.object(model["anchors"])[f"anchor.{key}"] = {
                "kind": "point3",
                "name": key,
                "position": list(point),
            }
        locator: JsonObject = {
            "kind": "route",
            "element": "service.test",
            "station": 900 + 25 * math.pi,
        }
        model["elements"] = {
            "service.test": {
                "kind": "serviceRoute",
                "name": "Supported route",
                "type": "type.route",
                "path": [
                    {"anchor": f"anchor.{key}"} for key in ("start", "corner", "end")
                ],
                "bendRadius": 100,
                "chordTolerance": 0.1,
                "portStates": {"start": "open", "end": "open"},
            },
            "member.support": {
                "kind": "member",
                "name": "Support framing",
                "role": "beam",
                "type": "type.member",
                "axis": [{"point": [0, 0, 500]}, {"point": [2000, 0, 500]}],
            },
            "hardware.support": {
                "kind": "hardware",
                "name": "Route strap",
                "type": "type.support",
                "discipline": "services",
                "placement": {"origin": {"host": locator}},
                "participants": [
                    {"element": "service.test"},
                    {"element": "member.support"},
                ],
            },
            "system.test": {
                "kind": "serviceSystem",
                "name": "Supported system",
                "systemType": "supplyAir" if medium == "air" else medium,
                "members": [
                    {"element": "service.test", "port": key} for key in ("start", "end")
                ],
            },
        }
        return locator

    @classmethod
    def fitting(cls, model: JsonObject, role: str) -> JsonObject:
        """Replace the route with a placed fitting while retaining the same support identity."""
        locator = cls.configure(model)
        section: JsonObject = {"kind": "circle", "diameter": 40}
        recipes: dict[str, JsonObject] = {
            "elbow": {
                "kind": "elbow",
                "section": section,
                "path": [[0, 0, 0], [0, 0, 200], [200, 0, 200]],
                "bendRadius": 60,
            },
            "branch": {
                "kind": "branch",
                "trunk": {"section": section, "path": [[0, 0, 0], [0, 0, 400]]},
                "branches": {
                    "side": {"section": section, "path": [[0, 0, 200], [200, 0, 200]]}
                },
            },
            "transition": {
                "kind": "transition",
                "startSection": section,
                "endSection": section,
                "length": 100,
                "offset": [40, 0],
            },
            "cap": {"kind": "cap", "section": section, "depth": 60},
            "trap": {
                "kind": "trap",
                "section": section,
                "path": [[0, 0, 200], [0, 0, 0], [200, 0, 0], [200, 0, 150]],
                "bendRadius": 60,
            },
        }
        medium = "waste" if role == "trap" else "water"
        Authoring.object(model["types"])["type.fitting"] = {
            "kind": "serviceFittingType",
            "name": "Supported fitting",
            "family": "pipe",
            "material": "material.timber",
            "medium": medium,
            "connectionType": "illustrativeFace",
            "geometry": recipes[role],
            "wallThickness": 2,
            "chordTolerance": 0.1,
        }
        ports = (
            ["start"]
            + ([] if role == "cap" else ["end"])
            + (["side"] if role == "branch" else [])
        )
        elements = Authoring.object(model["elements"])
        elements["service.test"] = {
            "kind": "serviceFitting",
            "name": "Supported fitting",
            "type": "type.fitting",
            "placement": {"origin": {"point": [100, 200, 300]}, "rotation": [0, 0, 90]},
            "portStates": {key: "open" for key in ports},
        }
        system = Authoring.object(elements["system.test"])
        system["systemType"] = medium
        system["members"] = [{"element": "service.test", "port": key} for key in ports]
        if role == "branch":
            locator["branch"] = "side"
        locator["station"] = {
            "elbow": 140 + 30 * math.pi,
            "branch": 100,
            "transition": math.hypot(40, 100) / 2,
            "cap": 30,
            "trap": 50,
        }[role]
        return locator


@pytest.mark.parametrize("family", ["pipe", "duct", "cable", "conduit"])
def test_route_support_has_exact_pose_quantity_connections_and_export(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    family: str,
) -> None:
    """A real strap follows the bend without adding route stock or losing construction intent."""
    locator = SupportFixture.configure(reference_model, family)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    support = result.element("hardware.support")
    diagonal = math.sqrt(0.5)
    frame = Authoring.object(support.data["placement"])
    assert frame["origin"] == pytest.approx(
        [900 + 100 * diagonal, 100 - 100 * diagonal, 0]
    )
    assert frame["z"] == pytest.approx([diagonal, diagonal, 0])
    assert support.data["hostPlacements"] == [locator]
    assert support.data["discipline"] == "services"
    volume = (60 * 60 - 44 * 44) * 6
    assert support.data["netVolumeMm3"] == pytest.approx(volume)
    assert (
        SolidOperations.intersection(
            support.meshes[0], result.element("service.test").meshes[0]
        )
        is None
    )
    output = tmp_path / "support.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("hardware.support"))
    assert product.is_a("IfcDiscreteAccessory")
    assert ifcopenshell.util.element.get_predefined_type(product) == "hanger"
    connection = ifc.by_type("IfcRelConnectsWithRealizingElements")[0]
    assert product in connection.RealizingElements
    assert {connection.RelatingElement.Tag, connection.RelatedElement.Tag} == {
        "service.test",
        "member.support",
    }
    manifest = GltfExporter().export(
        result, tmp_path / "support.glb", tmp_path / "manifest.json"
    )
    entry = Authoring.object(Authoring.object(manifest["elements"])["hardware.support"])
    assert entry["nodes"] and Authoring.object(entry["data"])[
        "netVolumeMm3"
    ] == pytest.approx(volume)
    schedules = ModelReports(result).schedules()
    assert "hardware.support" in str(schedules["hardware"])


@pytest.mark.parametrize(
    "role,origin,tangent",
    [
        ("elbow", (100, 260, 500), (0, 1, 0)),
        ("branch", (100, 300, 500), (0, 1, 0)),
        (
            "transition",
            (100, 220, 350),
            (0, 40 / math.hypot(40, 100), 100 / math.hypot(40, 100)),
        ),
        ("cap", (100, 200, 330), (0, 0, 1)),
        ("trap", (100, 200, 450), (0, 0, -1)),
    ],
)
def test_fitting_stations_transform_local_paths_into_world_coordinates(
    reference_model: JsonObject,
    validator: ModelValidator,
    role: str,
    origin: Vec3,
    tangent: Vec3,
) -> None:
    """Every fitting recipe exposes an unambiguous local axis or explicitly selected branch."""
    locator = SupportFixture.fitting(reference_model, role)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    frame = HostPlacement(ModelResolver(reference_model)).resolve(locator)
    assert frame.origin == pytest.approx(origin)
    assert frame.z == pytest.approx(tangent)


def test_route_support_follows_anchor_edits_and_tolerance_changes(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
) -> None:
    """Support placement uses the analytic route and preserves its own fabricated material."""
    SupportFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve().element("hardware.support")
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.support",
            "description": "Translate the supported route",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "moveAnchor",
                    "anchorId": f"anchor.{key}",
                    "position": list(point),
                }
                for key, point in (
                    ("start", [300, 400, 500]),
                    ("corner", [1300, 400, 500]),
                    ("end", [1300, 1400, 500]),
                )
            ],
        },
    )
    after = ModelResolver(changed).resolve().element("hardware.support")
    old = Authoring.array(Authoring.object(before.data["placement"])["origin"])
    new = Authoring.array(Authoring.object(after.data["placement"])["origin"])
    assert new == pytest.approx(
        [
            number(value, "support origin") + offset
            for value, offset in zip(old, (300, 400, 500))
        ]
    )
    assert before.data["netVolumeMm3"] == pytest.approx(after.data["netVolumeMm3"])
    Authoring.object(Authoring.object(changed["elements"])["service.test"])[
        "chordTolerance"
    ] = 1
    assert (
        ModelResolver(changed).resolve().element("hardware.support").data["placement"]
        == after.data["placement"]
    )
    with pytest.raises(ModelValidationError, match="outside its analytic centerline"):
        ChangeEngine(loader, validator).apply(
            reference_model,
            {
                "changeVersion": "0.1",
                "id": "change.shorten",
                "description": "Shorten below the support station",
                "baseRevision": reference_model["revision"],
                "operations": [
                    {
                        "op": "moveAnchor",
                        "anchorId": "anchor.corner",
                        "position": [200, 0, 0],
                    },
                    {
                        "op": "moveAnchor",
                        "anchorId": "anchor.end",
                        "position": [200, 200, 0],
                    },
                ],
            },
        )


@pytest.mark.parametrize(
    "invalid,message",
    [
        ("outside", "outside its analytic centerline"),
        ("branchOnRoute", "branched fitting"),
        ("unknownBranch", "Unknown fitting branch"),
        ("missingBranch", "fitting branch key"),
        ("wrongHost", "serviceRoute"),
        ("cycle", "cycle"),
    ],
)
def test_invalid_support_locators_fail_validation(
    reference_model: JsonObject,
    validator: ModelValidator,
    invalid: str,
    message: str,
) -> None:
    """Missing branch selections, invalid hosts and geometric dependency loops cannot resolve."""
    locator = (
        SupportFixture.fitting(reference_model, "branch")
        if invalid in {"unknownBranch", "missingBranch"}
        else SupportFixture.configure(reference_model)
    )
    if invalid == "outside":
        locator["station"] = 10000
    elif invalid == "missingBranch":
        del locator["branch"]
    elif invalid in {"unknownBranch", "branchOnRoute"}:
        locator["branch"] = "absent"
    elif invalid == "wrongHost":
        locator["element"] = "member.support"
    else:
        route = Authoring.object(
            Authoring.object(reference_model["elements"])["service.test"]
        )
        Authoring.array(route["path"])[0] = {
            "host": {"kind": "component", "element": "hardware.support"}
        }
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert message.lower() in str(report.to_dict()).lower()


@pytest.mark.parametrize(
    "family,fitting", [("pipe", False), ("duct", False), ("pipe", True)]
)
def test_insulated_supports_preserve_ownership_and_exports_after_host_edit(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
    family: str,
    fitting: bool,
) -> None:
    """Insulated runs and branches carry separate covers and straps through coordinated moves."""
    if fitting:
        SupportFixture.fitting(reference_model, "branch")
    else:
        SupportFixture.configure(reference_model, family)
    materials = Authoring.object(reference_model["materials"])
    materials["material.cover"] = {"name": "Illustrative insulation"}
    materials["material.strap"] = {"name": "Illustrative support stock"}
    types = Authoring.object(reference_model["types"])
    types["type.cover"] = {
        "kind": "serviceInsulationType",
        "name": "Separate ten millimetre cover",
        "material": "material.cover",
        "thickness": 10,
    }
    strap = Authoring.object(types["type.support"])
    strap["material"] = "material.strap"
    body = Authoring.object(Authoring.object(strap["solids"])["body"])
    body["section"] = {"kind": "rectangle", "width": 80, "depth": 80}
    passage = Authoring.object(Authoring.object(strap["cuts"])["passage"])
    passage["section"] = {"kind": "rectangle", "width": 64, "depth": 64}
    elements = Authoring.object(reference_model["elements"])
    elements["insulation.test"] = {
        "kind": "serviceInsulation",
        "name": "Supported insulation",
        "type": "type.cover",
        "host": "service.test",
        "chordTolerance": 0.1,
    }
    Authoring.array(
        Authoring.object(elements["hardware.support"])["participants"]
    ).append({"element": "insulation.test"})
    before = ModelResolver(reference_model).resolve()
    operations: list[JsonValue] = (
        [
            {
                "op": "set",
                "path": "/elements/service.test/placement/origin/point",
                "value": [400, 600, 800],
            }
        ]
        if fitting
        else [
            {
                "op": "moveAnchor",
                "anchorId": f"anchor.{key}",
                "position": list(point),
            }
            for key, point in (
                ("start", [300, 400, 500]),
                ("corner", [1300, 400, 500]),
                ("end", [1300, 1400, 500]),
            )
        ]
    )
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.insulated-support",
            "description": "Translate a service with its insulation and support",
            "baseRevision": reference_model["revision"],
            "operations": operations,
        },
    )
    after = ModelResolver(changed).resolve()
    ids = ("service.test", "insulation.test", "hardware.support")
    for element_id in ids:
        old, new = before.element(element_id), after.element(element_id)
        assert SolidOperations.volume(new.meshes[0]) == pytest.approx(
            SolidOperations.volume(old.meshes[0])
        )
        assert [
            min(point[i] for point in new.meshes[0].vertices) for i in range(3)
        ] == pytest.approx(
            [
                min(point[i] for point in old.meshes[0].vertices) + offset
                for i, offset in enumerate((300, 400, 500))
            ]
        )
    for index, first in enumerate(ids):
        for second in ids[index + 1 :]:
            assert (
                SolidOperations.intersection(
                    after.element(first).meshes[0], after.element(second).meshes[0]
                )
                is None
            )
    assert set(
        Authoring.array(after.element("hardware.support").data["participantIds"])
    ) == {"service.test", "member.support", "insulation.test"}
    rows = Authoring.array(ModelReports(after).schedules()["materials"])
    quantities = {
        Authoring.text(Authoring.object(row)["materialId"]): number(
            Authoring.object(row)["volumeM3"], "material quantity"
        )
        for row in rows
    }
    for element_id, material in (
        ("insulation.test", "material.cover"),
        ("hardware.support", "material.strap"),
    ):
        assert quantities[material] == pytest.approx(
            SolidOperations.volume(after.element(element_id).meshes[0]) / 1e9
        )
    output = tmp_path / "insulated-support.ifc"
    IfcExporter().export(after, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    cover = ifc.by_guid(IfcExporter.stable_guid("insulation.test"))
    support = ifc.by_guid(IfcExporter.stable_guid("hardware.support"))
    assert cover.is_a("IfcCovering")
    assert ifcopenshell.util.element.get_predefined_type(cover) == "INSULATION"
    connections = ifc.by_type("IfcRelConnectsWithRealizingElements")
    assert len(connections) == 3
    assert all(support in connection.RealizingElements for connection in connections)
    assert {
        part.Tag
        for connection in connections
        for part in (connection.RelatingElement, connection.RelatedElement)
    } == {"service.test", "member.support", "insulation.test"}
    manifest = GltfExporter().export(
        after, tmp_path / "assembly.glb", tmp_path / "manifest.json"
    )
    entries = Authoring.object(manifest["elements"])
    assert all(Authoring.object(entries[element_id])["nodes"] for element_id in ids)
