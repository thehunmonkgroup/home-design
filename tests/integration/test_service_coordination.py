"""Service material clashes, scoped clearance allowances and exported coordination evidence."""

from __future__ import annotations

import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class ClashFixture:
    """Author isolated service routes and framing with exactly known intersection dimensions."""

    @staticmethod
    def configure(model: JsonObject, family: str = "duct") -> JsonObject:
        """Place a long framing member within the route's outside surface and clearance."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        medium = {
            "duct": "air",
            "pipe": "water",
            "cable": "electrical",
            "conduit": "electrical",
        }[family]
        types = Authoring.object(model["types"])
        types["type.route"] = {
            "kind": "serviceRouteType",
            "name": "Checked route",
            "family": family,
            "medium": medium,
            "connectionType": "illustrativeFace",
            "material": "material.timber",
            "section": (
                {"kind": "rectangle", "width": 40, "height": 40}
                if family == "duct"
                else {"kind": "circle", "diameter": 40}
            ),
            **({"wallThickness": 2} if family != "cable" else {}),
        }
        types["type.member"] = {
            "kind": "memberType",
            "name": "Coordination obstacle",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 4, "depth": 4},
        }
        route: JsonObject = {
            "kind": "serviceRoute",
            "name": "Checked route",
            "type": "type.route",
            "path": [{"point": [0, 0, 0]}, {"point": [0, 0, 400]}],
            "up": [0, 1, 0],
            "chordTolerance": 0.1,
            "bendRadius": 100,
            "clearance": 10,
            "portStates": {"start": "open", "end": "open"},
            "coordinationChecks": {
                "interference": "error",
                "clearance": {"severity": "error"},
            },
        }
        model["elements"] = {
            "route.run": route,
            "member.obstacle": {
                "kind": "member",
                "name": "Framing obstacle",
                "type": "type.member",
                "role": "stud",
                "axis": [{"point": [19, 0, 50]}, {"point": [19, 0, 350]}],
            },
            "system.run": {
                "kind": "serviceSystem",
                "name": "Checked system",
                "systemType": "supplyAir" if medium == "air" else medium,
                "members": [
                    {"element": "route.run", "port": key} for key in ("start", "end")
                ],
            },
        }
        return route

    @staticmethod
    def assembly(model: JsonObject) -> None:
        """Use two individually identified members outside stock but inside the clearance envelope."""
        elements = Authoring.object(model["elements"])
        del elements["member.obstacle"]
        elements["framing.test"] = {
            "kind": "memberAssembly",
            "name": "Clearance framing",
            "assemblyType": "other",
            "placement": {"origin": {"point": [0, 0, 0]}},
            "nodes": {
                "leftBottom": {"local": [-25, 0, 50]},
                "leftTop": {"local": [-25, 0, 350]},
                "rightBottom": {"local": [25, 0, 50]},
                "rightTop": {"local": [25, 0, 350]},
            },
            "members": {
                side: {
                    "start": f"{side}Bottom",
                    "end": f"{side}Top",
                    "memberType": "type.member",
                    "role": "column",
                }
                for side in ("left", "right")
            },
        }


@pytest.mark.parametrize("family", ["pipe", "duct", "cable", "conduit"])
def test_service_material_intersections_are_not_hidden_by_clearance_allowances(
    reference_model: JsonObject, validator: ModelValidator, family: str
) -> None:
    """A declared clearance allowance cannot suppress real overlap with pipe, duct or electrical stock."""
    route = ClashFixture.configure(reference_model, family)
    Authoring.object(Authoring.object(route["coordinationChecks"])["clearance"])[
        "allow"
    ] = [{"element": "member.obstacle"}]
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert [item.code for item in report.diagnostics] == ["service.interference"]
    diagnostic = report.diagnostics[0]
    assert (
        diagnostic.subject_id == "route.run" and "member.obstacle" in diagnostic.message
    )
    assert diagnostic.path == "/elements/route.run/coordinationChecks/interference"
    result = Authoring.object(
        ModelResolver(reference_model)
        .resolve()
        .element("route.run")
        .data["serviceCoordination"]
    )
    assert Authoring.object(result["clearance"])["obstructions"] == []
    assert (
        len(Authoring.array(Authoring.object(result["interference"])["collisions"]))
        == 1
    )


@pytest.mark.parametrize(
    "allowance,count", [("none", 2), ("scoped", 1), ("assembly", 0)]
)
def test_clearance_reports_individual_members_without_container_duplicates(
    reference_model: JsonObject, validator: ModelValidator, allowance: str, count: int
) -> None:
    """Scoped exceptions affect one member; an explicitly allowed assembly includes all surviving members."""
    route = ClashFixture.configure(reference_model)
    ClashFixture.assembly(reference_model)
    clearance = Authoring.object(
        Authoring.object(route["coordinationChecks"])["clearance"]
    )
    if allowance != "none":
        clearance["allow"] = [
            {
                "element": "framing.test",
                **({"part": "left"} if allowance == "scoped" else {}),
            }
        ]
    report = validator.validate(reference_model)
    assert report.is_valid == (count == 0)
    assert len(report.diagnostics) == count
    assert all(
        item.code == "service.clearance-obstructed" and "/member/" in item.message
        for item in report.diagnostics
    )
    data = Authoring.object(
        ModelResolver(reference_model)
        .resolve()
        .element("route.run")
        .data["serviceCoordination"]
    )
    obstacles = Authoring.array(Authoring.object(data["clearance"])["obstructions"])
    assert len(obstacles) == count
    assert all(
        Authoring.object(value)["volumeMm3"] == pytest.approx(4 * 4 * 300)
        for value in obstacles
    )


def test_owned_clearance_cut_resolves_material_and_clearance_clashes(
    reference_model: JsonObject, validator: ModelValidator, loader: ModelLoader
) -> None:
    """Final surviving framing geometry is checked after an owned construction-volume cut."""
    ClashFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    Authoring.object(elements["member.obstacle"])["axis"] = [
        {"point": [-100, 0, 100]},
        {"point": [100, 0, 100]},
    ]
    assert any(
        item.code == "service.interference"
        for item in validator.validate(reference_model).diagnostics
    )
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.clearance",
            "description": "Cut the authored route clearance through framing",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "putObject",
                    "registry": "elements",
                    "objectId": "cut.service",
                    "value": {
                        "kind": "penetration",
                        "name": "Owned service clearance",
                        "host": "member.obstacle",
                        "owner": "route.run",
                        "purpose": "service",
                        "geometrySource": {
                            "element": "route.run",
                            "volume": "clearance",
                        },
                        "limits": {
                            "beamHole": {
                                "host": {
                                    "kind": "member",
                                    "element": "member.obstacle",
                                    "surface": "axis",
                                    "station": 100,
                                },
                                "maximumExtent": {"x": 4, "y": 4, "z": 60},
                                "maximumExtentFraction": {"z": 0.3},
                                "minimumEdgeDistance": {
                                    "positiveZ": 70,
                                    "negativeZ": 70,
                                },
                            }
                        },
                    },
                }
            ],
        },
    )
    report = validator.validate(changed)
    assert report.is_valid, report.to_dict()
    cut_data = ModelResolver(changed).resolve().element("cut.service").data
    assert (
        Authoring.object(Authoring.object(cut_data["limitResults"])["beamHole"])[
            "status"
        ]
        == "satisfied"
    )
    data = Authoring.object(
        ModelResolver(changed)
        .resolve()
        .element("route.run")
        .data["serviceCoordination"]
    )
    assert (
        Authoring.object(data["interference"])["status"]
        == Authoring.object(data["clearance"])["status"]
        == "clear"
    )


def test_touching_clearance_boundary_is_not_a_positive_volume_obstruction(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """An obstacle starting at the declared clearance boundary leaves that volume unoccupied."""
    ClashFixture.configure(reference_model)
    Authoring.object(Authoring.object(reference_model["elements"])["member.obstacle"])[
        "axis"
    ] = [{"point": [32, 0, 50]}, {"point": [32, 0, 350]}]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()


def test_connected_cover_and_support_are_clearance_exceptions_with_retained_reasons(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Explicit cover hosts and hardware participants permit close installation without erasing stock checks."""
    ClashFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    types["type.cover"] = {
        "kind": "serviceInsulationType",
        "name": "Cover",
        "material": "material.timber",
        "thickness": 5,
    }
    types["type.strap"] = {
        "kind": "hardwareType",
        "name": "Support strap",
        "role": "hanger",
        "material": "material.timber",
        "solids": {
            "stock": {
                "section": {"kind": "rectangle", "width": 56, "depth": 56},
                "depth": 4,
            }
        },
        "cuts": {
            "passage": {
                "section": {"kind": "rectangle", "width": 52, "depth": 52},
                "depth": 4,
            }
        },
    }
    elements = Authoring.object(reference_model["elements"])
    del elements["member.obstacle"]
    elements["cover.run"] = {
        "kind": "serviceInsulation",
        "name": "Route cover",
        "type": "type.cover",
        "host": "route.run",
        "chordTolerance": 0.1,
        "coordinationChecks": {"interference": "error"},
    }
    elements["support.run"] = {
        "kind": "hardware",
        "name": "Route strap",
        "type": "type.strap",
        "placement": {
            "origin": {
                "host": {"kind": "route", "element": "route.run", "station": 200}
            }
        },
        "participants": [{"element": "cover.run"}],
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    data = Authoring.object(resolved.element("route.run").data["serviceCoordination"])
    assert Authoring.object(data["clearance"])["exclusions"] == [
        {"element": "cover.run", "reason": "hostedInsulation"},
        {"element": "support.run", "reason": "serviceSupport"},
    ]
    Authoring.object(Authoring.object(elements["cover.run"])["coordinationChecks"])[
        "clearance"
    ] = {"severity": "error"}
    assert "require a route or fitting" in str(
        validator.validate(reference_model).to_dict()
    )


@pytest.mark.parametrize("bad", ["missing", "nonphysical", "missingPart"])
def test_clearance_allowances_require_valid_surviving_parts(
    reference_model: JsonObject, validator: ModelValidator, bad: str
) -> None:
    """Stale and nonphysical exceptions cannot silently disable service clearance evidence."""
    route = ClashFixture.configure(reference_model)
    ClashFixture.assembly(reference_model)
    reference: JsonObject = {
        "element": (
            "missing"
            if bad == "missing"
            else "system.run" if bad == "nonphysical" else "framing.test"
        )
    }
    if bad == "missingPart":
        reference["part"] = "missing"
    Authoring.object(Authoring.object(route["coordinationChecks"])["clearance"])[
        "allow"
    ] = [reference]
    assert not validator.validate(reference_model).is_valid


def test_warning_check_exports_exact_collision_context_without_diagnostic_material(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """Build diagnostics, schedules, IFC properties and scene metadata carry the same measured conflict."""
    route = ClashFixture.configure(reference_model)
    Authoring.object(route["coordinationChecks"])["interference"] = "warning"
    source = tmp_path / "coordination.json"
    source.write_text(json.dumps(reference_model), encoding="utf-8")
    result = BuildService().build(source, tmp_path / "build")
    diagnostics = json.loads(result.diagnostics.read_text(encoding="utf-8"))
    assert diagnostics["counts"] == {"error": 0, "warning": 1, "info": 0}
    manifest = json.loads(result.render_manifest.read_text(encoding="utf-8"))
    data = manifest["elements"]["route.run"]["data"]["serviceCoordination"]
    assert data["interference"]["collisions"] == [
        {"element": "member.obstacle", "volumeMm3": pytest.approx(2400)}
    ]
    assert len(manifest["elements"]) == 3
    schedules = json.loads(result.schedules.read_text(encoding="utf-8"))
    assert (
        schedules["serviceRoutes"][0]["dimensionsAndSpecifications"][
            "serviceCoordination"
        ]
        == data
    )
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert not logger.statements
    route_product = next(
        item for item in ifc.by_type("IfcDuctSegment") if item.Tag == "route.run"
    )
    properties = ifcopenshell.util.element.get_psets(route_product)[
        "Pset_HomeDesignData"
    ]
    assert json.loads(properties["serviceCoordination"]) == data
    assert not ifc.by_type("IfcVirtualElement")


@pytest.mark.parametrize("kind", ["serviceDevice", "serviceFitting"])
def test_device_and_fitting_stock_use_the_same_final_geometry_clash_contract(
    reference_model: JsonObject, validator: ModelValidator, kind: str
) -> None:
    """Device fabrication and fitting transitions reject real stock conflicts and accept separation."""
    ClashFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    definition: JsonObject = {
        "kind": kind + "Type",
        "name": "Checked component",
        "material": "material.timber",
    }
    if kind == "serviceDevice":
        definition.update(
            {
                "role": "equipment",
                "solids": {
                    "stock": {
                        "section": {"kind": "rectangle", "width": 40, "depth": 40},
                        "depth": 400,
                    }
                },
                "ports": {
                    key: {
                        "position": [0, 0, z],
                        "direction": [0, 0, direction],
                        "flow": "bidirectional",
                        "medium": "air",
                        "connectionType": "illustrativeFace",
                        "section": {"kind": "rectangle", "width": 40, "height": 40},
                    }
                    for key, z, direction in (("start", 0, -1), ("end", 400, 1))
                },
                "portGroups": [["start", "end"]],
            }
        )
    else:
        definition.update(
            {
                "family": "duct",
                "medium": "air",
                "connectionType": "illustrativeFace",
                "wallThickness": 2,
                "geometry": {
                    "kind": "transition",
                    "startSection": {"kind": "rectangle", "width": 40, "height": 40},
                    "endSection": {"kind": "rectangle", "width": 40, "height": 40},
                    "length": 400,
                },
                "chordTolerance": 0.1,
            }
        )
    types["type.route"] = definition
    elements = Authoring.object(reference_model["elements"])
    elements["route.run"] = {
        "kind": kind,
        "name": "Checked component",
        "type": "type.route",
        "placement": {"origin": {"point": [0, 0, 0]}},
        "portStates": {"start": "open", "end": "open"},
        "coordinationChecks": {"interference": "error"},
        **({"clearance": 10} if kind == "serviceFitting" else {}),
    }
    if kind == "serviceFitting":
        Authoring.object(Authoring.object(elements["route.run"])["coordinationChecks"])[
            "clearance"
        ] = {"severity": "error"}
    report = validator.validate(reference_model)
    assert [diagnostic.code for diagnostic in report.diagnostics] == [
        "service.interference"
    ], report.to_dict()
    Authoring.object(elements["member.obstacle"])["axis"] = [
        {"point": [60, 0, 50]},
        {"point": [60, 0, 350]},
    ]
    separated = validator.validate(reference_model)
    assert separated.is_valid, separated.to_dict()
