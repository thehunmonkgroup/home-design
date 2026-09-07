"""Host-frame cut dimensions and exact directional margins through authored construction."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import math

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import ModelValidationError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class LimitFixture:
    """Author a square transverse hole in illustrative stock, with no inferred engineering inputs."""

    @staticmethod
    def configure(model: JsonObject) -> JsonObject:
        """Use a 100 by 200 by 1000 member and a central 40 by 40 through-hole."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        Authoring.object(model["types"])["type.host"] = {
            "kind": "memberType",
            "name": "Illustrative stock",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 100, "depth": 200},
        }
        locator: JsonObject = {
            "kind": "member",
            "element": "member.host",
            "surface": "axis",
            "station": 500,
        }
        limit: JsonObject = {
            "host": deepcopy(locator),
            "reference": "Illustrative authored limits",
            "maximumExtent": {"y": 40, "z": 40},
            "maximumExtentFraction": {"y": 0.2, "z": 0.04},
            "minimumEdgeDistance": {
                "positiveY": 80,
                "negativeY": 80,
                "positiveZ": 480,
                "negativeZ": 480,
            },
        }
        model["elements"] = {
            "member.host": {
                "kind": "member",
                "name": "Hole host",
                "type": "type.host",
                "role": "column",
                "axis": [{"point": [0, 0, 0]}, {"point": [0, 0, 1000]}],
            },
            "cut.hole": {
                "kind": "penetration",
                "name": "Checked hole",
                "host": "member.host",
                "purpose": "service",
                "placement": {
                    "origin": {"host": {**locator, "offset": [-60, 0, 0]}},
                    "rotation": [0, 90, 0],
                },
                "section": {"kind": "rectangle", "width": 40, "depth": 40},
                "depth": 120,
                "limits": {"hole": limit},
            },
        }
        return limit

    @staticmethod
    def layered(model: JsonObject, kind: str) -> JsonObject:
        """Cut a selected sixty-millimetre layer of a wall, slab or inclined roof plane."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        Authoring.object(model["types"])["type.host"] = {
            "kind": kind + "Type",
            "name": "Layered host",
            "layerOrder": "exteriorToInterior" if kind == "wall" else "topToBottom",
            "layers": [
                {
                    "name": name,
                    "material": "material.timber",
                    "thickness": depth,
                    "function": "structure",
                }
                for name, depth in (("outer", 60), ("inner", 40))
            ],
        }
        host: JsonObject = {
            "kind": kind,
            "name": "Layered host",
            "type": "type.host",
            "storey": "level.ground",
        }
        locator: JsonObject = {
            "kind": "surface",
            "element": "host.test",
            "point": [0, 0],
            "surface": "layerTop",
            "layer": 0,
        }
        if kind == "wall":
            host.update(
                {
                    "locationLine": "center",
                    "path": {
                        "kind": "line",
                        "start": {"point": [-500, 0]},
                        "end": {"point": [500, 0]},
                    },
                    "base": {"kind": "level", "level": "level.ground", "offset": 0},
                    "top": {"kind": "height", "height": 1000},
                }
            )
            locator = {
                "kind": "wall",
                "element": "host.test",
                "surface": "layerExterior",
                "layer": 0,
                "station": 500,
                "height": 500,
            }
        elif kind == "slab":
            host.update(
                {
                    "role": "floor",
                    "extrusionDirection": "down",
                    "datum": {"kind": "level", "level": "level.ground", "offset": 100},
                }
            )
            host["footprint"] = {
                "outer": [
                    {"point": [-500, -500]},
                    {"point": [500, -500]},
                    {"point": [500, 500]},
                    {"point": [-500, 500]},
                ]
            }
        else:
            host["geometry"] = {
                "kind": "faceSet",
                "faces": [
                    {
                        "id": "face.main",
                        "boundary": {
                            "outer": [
                                [-400, -500, -200],
                                [400, -500, 400],
                                [400, 500, 400],
                                [-400, 500, -200],
                            ]
                        },
                    }
                ],
            }
            locator["face"] = "face.main"
        limit: JsonObject = {
            "host": deepcopy(locator),
            "maximumExtent": {"x": 40, "y": 20, "z": 60},
            "maximumExtentFraction": {"z": 1},
            "minimumEdgeDistance": {
                "positiveX": 480,
                "negativeX": 480,
                "positiveY": 490,
                "negativeY": 490,
            },
        }
        model["elements"] = {
            "host.test": host,
            "cut.test": {
                "kind": "penetration",
                "name": "Selected layer cut",
                "host": "host.test",
                "purpose": "recess",
                "layers": [0],
                "placement": {"origin": {"host": locator}, "rotation": [180, 0, 0]},
                "section": {"kind": "rectangle", "width": 40, "depth": 20},
                "depth": 60,
                "limits": {"layer": limit},
            },
        }
        return limit


@pytest.mark.parametrize(
    "roll,sloped", [(0, False), (31, False), (0, True), (47, True)]
)
def test_cut_extents_and_exact_boundary_margins_follow_member_frame(
    reference_model: JsonObject, validator: ModelValidator, roll: float, sloped: bool
) -> None:
    """Inclined and rolled stock keeps its section dimensions rather than model-axis bounding boxes."""
    LimitFixture.configure(reference_model)
    member = Authoring.object(
        Authoring.object(reference_model["elements"])["member.host"]
    )
    member["roll"] = roll
    if sloped:
        member["axis"] = [{"point": [300, 400, 500]}, {"point": [900, 400, 1300]}]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    result = Authoring.object(
        Authoring.object(resolved.element("cut.hole").data["limitResults"])["hole"]
    )
    assert result["status"] == "satisfied"
    assert result["cutExtentMm"] == pytest.approx({"x": 100, "y": 40, "z": 40})
    assert result["hostExtentMm"] == pytest.approx({"x": 100, "y": 200, "z": 1000})
    assert len(Authoring.array(result["checks"])) == 8


@pytest.mark.parametrize(
    "measure,axis,value",
    [
        ("maximumExtent", "y", 39),
        ("maximumExtent", "z", 39),
        ("maximumExtentFraction", "y", 0.19),
        ("maximumExtentFraction", "z", 0.039),
        ("minimumEdgeDistance", "positiveY", 81),
        ("minimumEdgeDistance", "negativeY", 81),
        ("minimumEdgeDistance", "positiveZ", 481),
        ("minimumEdgeDistance", "negativeZ", 481),
        ("minimumEdgeDistance", "positiveX", 1),
        ("minimumEdgeDistance", "negativeX", 1),
    ],
)
def test_only_authored_dimension_or_edge_limit_is_reported(
    reference_model: JsonObject,
    validator: ModelValidator,
    measure: str,
    axis: str,
    value: float,
) -> None:
    """The exact failed check is retained without supplying additional engineering limits."""
    limit = LimitFixture.configure(reference_model)
    Authoring.object(limit[measure])[axis] = value
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert len(report.diagnostics) == 1, report.to_dict()
    diagnostic = report.diagnostics[0]
    assert diagnostic.code == "penetration.limit-violated"
    assert diagnostic.subject_id == "cut.hole"
    assert diagnostic.path == f"/elements/cut.hole/limits/hole/{measure}/{axis}"


def test_neighboring_cut_is_a_material_boundary_regardless_of_cut_order(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Restoring the checked hole preserves other holes rather than testing against untouched stock."""
    limit = LimitFixture.configure(reference_model)
    limit["minimumEdgeDistance"] = {"positiveZ": 41}
    elements = Authoring.object(reference_model["elements"])
    neighbor = deepcopy(Authoring.object(elements["cut.hole"]))
    del neighbor["limits"]
    Authoring.object(
        Authoring.object(Authoring.object(neighbor["placement"])["origin"])["host"]
    )["station"] = 580
    for identity in ("cut.aaa", "cut.zzz"):
        elements[identity] = neighbor
        report = validator.validate(reference_model)
        assert [item.code for item in report.diagnostics] == [
            "penetration.limit-violated"
        ], report.to_dict()
        del elements[identity]
    limit["minimumEdgeDistance"] = {"positiveZ": 40}
    elements["cut.neighbor"] = neighbor
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()


def test_notch_depth_and_retained_opposite_edge_use_actual_removed_geometry(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A surface notch is measured at the clipped stock boundary, not the oversized cutter extent."""
    limit = LimitFixture.configure(reference_model)
    cut = Authoring.object(Authoring.object(reference_model["elements"])["cut.hole"])
    cut["purpose"] = "notch"
    Authoring.object(
        Authoring.object(Authoring.object(cut["placement"])["origin"])["host"]
    )["offset"] = [-60, 90, 0]
    limit["maximumExtentFraction"] = {"y": 0.15}
    limit["minimumEdgeDistance"] = {"negativeY": 170}
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    limit["maximumExtentFraction"] = {"y": 0.149}
    assert [item.code for item in validator.validate(reference_model).diagnostics] == [
        "penetration.limit-violated"
    ]


def test_sloped_end_margin_uses_real_surface_instead_of_an_axis_bounding_box(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A bevel intrudes on the margin even when the projected global end position is far enough away."""
    limit = LimitFixture.configure(reference_model)
    member = Authoring.object(
        Authoring.object(reference_model["elements"])["member.host"]
    )
    member["endCuts"] = {
        "end": {"normal": [0, math.sqrt(0.5), -math.sqrt(0.5)], "offset": 0}
    }
    limit["maximumExtentFraction"] = {"y": 0.2}
    limit["minimumEdgeDistance"] = {"positiveZ": 470}
    report = validator.validate(reference_model)
    assert [item.code for item in report.diagnostics] == [
        "penetration.limit-violated"
    ], report.to_dict()
    limit["minimumEdgeDistance"] = {"positiveZ": 460}
    assert validator.validate(reference_model).is_valid


def test_stock_resize_rechecks_authored_fraction_and_rejects_transaction(
    reference_model: JsonObject, validator: ModelValidator, loader: ModelLoader
) -> None:
    """Changing section depth re-evaluates the same authored hole limit in the updated host."""
    limit = LimitFixture.configure(reference_model)
    limit["minimumEdgeDistance"] = {"positiveY": 50, "negativeY": 50}
    with pytest.raises(ModelValidationError, match="maximumExtentFraction"):
        ChangeEngine(loader, validator).apply(
            reference_model,
            {
                "changeVersion": "0.1",
                "id": "change.stock",
                "description": "Reduce illustrative host depth",
                "baseRevision": reference_model["revision"],
                "operations": [
                    {
                        "op": "set",
                        "path": "/types/type.host/section/depth",
                        "value": 180,
                    }
                ],
            },
        )


def test_warning_limit_evidence_is_preserved_in_every_build_handoff(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """Warnings preserve limits, local dimensions and failed margin volume across IFC, reports and preview."""
    limit = LimitFixture.configure(reference_model)
    limit["severity"] = "warning"
    limit["minimumEdgeDistance"] = {"positiveY": 81}
    source = tmp_path / "limited-cut.json"
    source.write_text(json.dumps(reference_model), encoding="utf-8")
    built = BuildService().build(source, tmp_path / "build")
    diagnostics = json.loads(built.diagnostics.read_text(encoding="utf-8"))
    assert diagnostics["counts"] == {"error": 0, "warning": 1, "info": 0}
    scene = json.loads(built.render_manifest.read_text(encoding="utf-8"))
    data = scene["elements"]["cut.hole"]["data"]["limitResults"]
    checks = data["hole"]["checks"]
    assert checks[-1]["outsideVolumeMm3"] == pytest.approx(100 * 40 * 1)
    schedules = json.loads(built.schedules.read_text(encoding="utf-8"))
    assert (
        schedules["penetrations"][0]["dimensionsAndSpecifications"]["limitResults"]
        == data
    )
    ifc = ifcopenshell.open(built.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert not logger.statements
    opening = ifc.by_type("IfcOpeningElement")[0]
    assert (
        json.loads(
            ifcopenshell.util.element.get_psets(opening)["Pset_HomeDesignData"][
                "limitResults"
            ]
        )
        == data
    )


@pytest.mark.parametrize("kind", ["wall", "slab", "roof"])
def test_selected_layer_limits_use_actual_wall_floor_or_roof_plane(
    reference_model: JsonObject, validator: ModelValidator, kind: str
) -> None:
    """Surface frames follow the slope and selected layer instead of whole-host/model-Z thickness."""
    limit = LimitFixture.layered(reference_model, kind)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = Authoring.object(
        Authoring.object(
            ModelResolver(reference_model)
            .resolve()
            .element("cut.test")
            .data["limitResults"]
        )["layer"]
    )
    assert result["cutExtentMm"] == pytest.approx({"x": 40, "y": 20, "z": 60})
    assert result["hostExtentMm"] == pytest.approx({"x": 1000, "y": 1000, "z": 60})
    Authoring.object(limit["host"])["layer"] = 1
    invalid = validator.validate(reference_model)
    assert not invalid.is_valid and "material affected" in str(invalid.to_dict())


def test_generated_member_limit_keeps_scoped_stock_extent_and_identity(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A nearby assembly member cannot enlarge the measured section or satisfy missing edge material."""
    limit = LimitFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    elements["member.host"] = {
        "kind": "memberAssembly",
        "name": "Checked framing",
        "assemblyType": "other",
        "placement": {"origin": {"point": [0, 0, 0]}},
        "nodes": {
            "leftBottom": {"local": [0, 0, 0]},
            "leftTop": {"local": [0, 0, 1000]},
            "rightBottom": {"local": [500, 0, 0]},
            "rightTop": {"local": [500, 0, 1000]},
        },
        "members": {
            side: {
                "start": f"{side}Bottom",
                "end": f"{side}Top",
                "memberType": "type.host",
                "role": "column",
            }
            for side in ("left", "right")
        },
    }
    Authoring.object(limit["host"])["part"] = "left"
    Authoring.object(
        Authoring.object(
            Authoring.object(Authoring.object(elements["cut.hole"])["placement"])[
                "origin"
            ]
        )["host"]
    )["part"] = "left"
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = Authoring.object(
        Authoring.object(
            ModelResolver(reference_model)
            .resolve()
            .element("cut.hole")
            .data["limitResults"]
        )["hole"]
    )
    assert result["host"] == "member.host/member/left"
    assert result["hostExtentMm"] == pytest.approx({"x": 100, "y": 200, "z": 1000})
    Authoring.object(limit["host"])["part"] = "right"
    assert "material affected" in str(validator.validate(reference_model).to_dict())


@pytest.mark.parametrize(
    "failure", ["differentHost", "missingFace", "emptyChecks", "badFraction"]
)
def test_limit_frames_and_authored_values_cannot_be_silently_ignored(
    reference_model: JsonObject, validator: ModelValidator, failure: str
) -> None:
    """Incorrect scope and undefined numerical controls reject the source before producing passing evidence."""
    limit = LimitFixture.layered(reference_model, "roof")
    if failure == "differentHost":
        elements = Authoring.object(reference_model["elements"])
        elements["host.other"] = deepcopy(elements["host.test"])
        Authoring.object(limit["host"])["element"] = "host.other"
    elif failure == "missingFace":
        del Authoring.object(limit["host"])["face"]
    elif failure == "emptyChecks":
        for key in ("maximumExtent", "maximumExtentFraction", "minimumEdgeDistance"):
            del limit[key]
    else:
        limit["maximumExtentFraction"] = {"z": 1.01}
    assert not validator.validate(reference_model).is_valid
