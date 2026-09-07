"""Typed plumbing stock, directional gravity checks and native pipe exports through edits."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import ModelValidationError
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.service_ports import ServicePorts
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class PipeFixture:
    """Use an isolated rounded pipe with authored nominal stock and installation inputs."""

    @staticmethod
    def configure(model: JsonObject, system: str = "waste") -> JsonObject:
        """Provide two falling tangent spans and independently declared working conditions."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        medium = "water" if system in {"coldWater", "hotWater"} else system
        definition: JsonObject = {
            "kind": "serviceRouteType",
            "name": "Illustrative pipe stock",
            "family": "pipe",
            "material": "material.timber",
            "section": {"kind": "circle", "diameter": 40},
            "wallThickness": 2,
            "medium": medium,
            "connectionType": "illustrativePipeFace",
            "flow": "forward",
            "pipe": {
                "designation": "Illustrative rated stock",
                "nominalSize": "Authored trade size",
                "construction": "rigid",
                "pressureRatingPa": 1000000,
                "minimumTemperatureC": -20,
                "maximumTemperatureC": 90,
                "roughnessMm": 0.01,
                "jointing": "Illustrative joint",
                "lining": "Illustrative lining",
                "potableWater": medium == "water",
            },
        }
        Authoring.object(model["types"])["type.pipe"] = definition
        route: JsonObject = {
            "kind": "serviceRoute",
            "name": "Falling pipe",
            "type": "type.pipe",
            "chordTolerance": 0.2,
            "bendRadius": 150,
            "path": [
                {"point": [0, 0, 1000]},
                {"point": [1000, 0, 980]},
                {"point": [1000, 1000, 960]},
            ],
            "fallCheck": {"minimumFall": 0.02, "direction": "startToEnd"},
            "conditions": {
                "pressurePa": 400000,
                "temperatureC": 20,
                "flowRateM3s": 0.0002,
            },
            "portStates": {"start": "open", "end": "open"},
        }
        model["elements"] = {
            "route.pipe": route,
            "system.pipe": {
                "kind": "serviceSystem",
                "name": "Pipe service",
                "systemType": system,
                "members": [
                    {"element": "route.pipe", "port": "start"},
                    {"element": "route.pipe", "port": "end"},
                ],
            },
        }
        return route


@pytest.mark.parametrize("system", ["coldWater", "waste", "vent", "gas"])
def test_connected_insulated_plumbing_boundaries_follow_edits_and_export(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
    system: str,
) -> None:
    """Supply, waste, vent and gas routes retain connected caps, falls and distinct covering stock."""
    route = PipeFixture.configure(reference_model, system)
    types = Authoring.object(reference_model["types"])
    pipe = Authoring.object(types["type.pipe"])
    types["type.cap"] = {
        "kind": "serviceFittingType",
        "name": "Illustrative terminal cap",
        "family": "pipe",
        "material": "material.timber",
        "medium": pipe["medium"],
        "connectionType": pipe["connectionType"],
        "wallThickness": 2,
        "chordTolerance": 0.2,
        "pipe": deepcopy(pipe["pipe"]),
        "geometry": {
            "kind": "cap",
            "section": deepcopy(pipe["section"]),
            "depth": 60,
        },
    }
    Authoring.object(reference_model["materials"])["material.cover"] = {
        "name": "Illustrative pipe insulation"
    }
    types["type.cover"] = {
        "kind": "serviceInsulationType",
        "name": "Ten millimetre covering",
        "material": "material.cover",
        "thickness": 10,
    }
    route["portStates"] = {"start": "open"}
    elements = Authoring.object(reference_model["elements"])
    elements["fitting.cap"] = {
        "kind": "serviceFitting",
        "name": "Connected pipe termination",
        "type": "type.cap",
        "placement": {"origin": {"port": {"element": "route.pipe", "port": "end"}}},
    }
    for host in ("route.pipe", "fitting.cap"):
        elements[f"insulation.{host}"] = {
            "kind": "serviceInsulation",
            "name": f"Covering for {host}",
            "type": "type.cover",
            "host": host,
            "chordTolerance": 0.1,
        }
    Authoring.array(Authoring.object(elements["system.pipe"])["members"]).append(
        {"element": "fitting.cap", "port": "start"}
    )
    Authoring.object(reference_model["relationships"])["connection.cap"] = {
        "kind": "connectsPorts",
        "a": {"element": "route.pipe", "port": "end"},
        "b": {"element": "fitting.cap", "port": "start"},
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    translated_path: list[JsonValue] = [
        {"point": [300, 400, 1500]},
        {"point": [1300, 400, 1480]},
        {"point": [1300, 1400, 1460]},
    ]
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.plumbing-assembly",
            "description": "Translate a connected insulated plumbing assembly",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "set",
                    "path": "/elements/route.pipe/path",
                    "value": translated_path,
                }
            ],
        },
    )
    before, after = (
        ModelResolver(reference_model).resolve(),
        ModelResolver(changed).resolve(),
    )
    for identity in (
        "route.pipe",
        "fitting.cap",
        "insulation.route.pipe",
        "insulation.fitting.cap",
    ):
        assert SolidOperations.volume(
            before.element(identity).meshes[0]
        ) == pytest.approx(SolidOperations.volume(after.element(identity).meshes[0]))
    cap_ports = Authoring.object(after.element("fitting.cap").data["ports"])
    route_ports = Authoring.object(after.element("route.pipe").data["ports"])
    assert ServicePorts.frame(
        Authoring.object(cap_ports["start"])
    ).origin == pytest.approx(
        ServicePorts.frame(Authoring.object(route_ports["end"])).origin
    )
    assert (
        Authoring.object(after.element("route.pipe").data["fallCheck"])["status"]
        == "satisfied"
    )
    schedules = ModelReports(after).schedules()
    assert len(Authoring.array(schedules["serviceInsulation"])) == 2
    output = tmp_path / "connected-plumbing.ifc"
    IfcExporter().export(after, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert len(ifc.by_type("IfcRelConnectsPorts")) == 1
    assert len(ifc.by_type("IfcDistributionPort")) == 3
    assert len(ifc.by_type("IfcCovering")) == 2
    assert (
        ifcopenshell.util.element.get_predefined_type(ifc.by_type("IfcPipeFitting")[0])
        == "cap"
    )
    manifest = GltfExporter().export(
        after, tmp_path / "assembly.glb", tmp_path / "manifest.json"
    )
    entries = Authoring.object(manifest["elements"])
    assert Authoring.object(entries["insulation.route.pipe"])["nodes"]
    invalid = deepcopy(changed)
    Authoring.object(Authoring.object(invalid["types"])["type.cap"])["medium"] = (
        "gas" if pipe["medium"] == "water" else "water"
    )
    assert not validator.validate(invalid).is_valid


@pytest.mark.parametrize(
    "system,native_system",
    [
        ("coldWater", "DOMESTICCOLDWATER"),
        ("hotWater", "DOMESTICHOTWATER"),
        ("waste", "WASTEWATER"),
        ("vent", "VENT"),
        ("gas", "GAS"),
        ("condensate", "DRAINAGE"),
    ],
)
@pytest.mark.parametrize(
    "construction,native_construction",
    [("rigid", "RIGIDSEGMENT"), ("flexible", "FLEXIBLESEGMENT")],
)
def test_pipe_stock_conditions_falls_and_native_system_classifications(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    system: str,
    native_system: str,
    construction: str,
    native_construction: str,
) -> None:
    """Pipe service identity, declared ratings and real hollow stock survive native export."""
    source = PipeFixture.configure(reference_model, system)
    definition = Authoring.object(
        Authoring.object(reference_model["types"])["type.pipe"]
    )
    Authoring.object(definition["pipe"])["construction"] = construction
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    route = result.element("route.pipe")
    check = Authoring.object(route.data["fallCheck"])
    assert check["status"] == "satisfied" and check[
        "minimumObservedFall"
    ] == pytest.approx(0.02)
    assert len(Authoring.array(check["segments"])) == 2
    assert (
        route.data["pipe"] == definition["pipe"]
        and route.data["conditions"] == source["conditions"]
    )
    checks = Authoring.array(route.data["pipeRatingChecks"])
    assert [Authoring.object(value)["status"] for value in checks] == [
        "satisfied",
        "satisfied",
        "satisfied",
        "notChecked",
    ]
    path = tmp_path / "pipe.ifc"
    IfcExporter().export(result, path)
    ifc = ifcopenshell.open(path)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("route.pipe"))
    assert product.is_a("IfcPipeSegment") and product.IsTypedBy[0].RelatingType.is_a(
        "IfcPipeSegmentType"
    )
    assert ifcopenshell.util.element.get_predefined_type(product) == native_construction
    for stock in (product, product.IsTypedBy[0].RelatingType):
        standard = ifcopenshell.util.element.get_pset(
            stock, "Pset_PipeSegmentTypeCommon", should_inherit=False
        )
        assert standard["Reference"] == "type.pipe"
        assert standard["OuterDiameter"] == 40 and standard["InnerDiameter"] == 36
        assert "NominalDiameter" not in standard and "WorkingPressure" not in standard
    assert {port.SystemType for port in ifc.by_type("IfcDistributionPort")} == {
        native_system
    }
    assert {port.PredefinedType for port in ifc.by_type("IfcDistributionPort")} == {
        "PIPE"
    }
    assert (
        ifcopenshell.util.element.get_pset(product, "Pset_HomeDesignPipe")[
            "pressureRatingPa"
        ]
        == 1000000
    )
    assert (
        ifcopenshell.util.element.get_pset(product, "Pset_HomeDesignPipeConditions")[
            "temperatureC"
        ]
        == 20
    )
    assert ifcopenshell.util.element.get_pset(product, "Pset_HomeDesignFallCheck")[
        "minimumObservedFall"
    ] == pytest.approx(0.02)
    materials = ModelReports(result).schedules()["materials"]
    del definition["pipe"]
    del source["conditions"]
    del source["fallCheck"]
    assert (
        ModelReports(ModelResolver(reference_model).resolve()).schedules()["materials"]
        == materials
    )


@pytest.mark.parametrize(
    "points,minimum,valid",
    [
        ([[0, 0, 1000], [1000, 0, 980]], 0.02, True),
        ([[0, 0, 1000], [1000, 0, 990]], 0.02, False),
        ([[0, 0, 1000], [1000, 0, 900], [2000, 0, 950]], 0.02, False),
        ([[0, 0, 1000], [0, 0, 900]], 1000000, True),
        ([[0, 0, 900], [0, 0, 1000]], 0, False),
        ([[0, 0, 1000], [1000, 0, 1000]], 0, True),
    ],
)
def test_gravity_checks_use_each_tangent_span_and_handle_vertical_drops(
    reference_model: JsonObject,
    validator: ModelValidator,
    points: list[list[int]],
    minimum: float,
    valid: bool,
) -> None:
    """An overall endpoint drop cannot hide a rising leg, and a vertical drop has no finite grade ratio."""
    route = PipeFixture.configure(reference_model)
    route["path"] = [{"point": [p[0], p[1], p[2]]} for p in points]
    Authoring.object(route["fallCheck"])["minimumFall"] = minimum
    report = validator.validate(reference_model)
    assert report.is_valid == valid, report.to_dict()
    if not valid:
        assert "specified minimum" in str(report.to_dict())
    elif minimum == 1000000:
        check = Authoring.object(
            ModelResolver(reference_model)
            .resolve()
            .element("route.pipe")
            .data["fallCheck"]
        )
        assert check["minimumObservedFall"] is None
        segment = Authoring.object(Authoring.array(check["segments"])[0])
        assert (
            segment["vertical"] is True
            and segment["fallRatio"] is None
            and segment["dropMm"] == 100
        )


def test_reverse_fall_reference_keeps_bidirectional_vent_interfaces(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Geometric fall direction remains independent of the transport port's source/sink classification."""
    route = PipeFixture.configure(reference_model, "vent")
    route["path"] = list(reversed(Authoring.array(route["path"])))
    Authoring.object(route["fallCheck"])["direction"] = "endToStart"
    Authoring.object(Authoring.object(reference_model["types"])["type.pipe"])[
        "flow"
    ] = "bidirectional"
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    pipe = ModelResolver(reference_model).resolve().element("route.pipe")
    assert {
        Authoring.text(Authoring.object(value)["flow"])
        for value in Authoring.object(pipe.data["ports"]).values()
    } == {"bidirectional"}
    assert Authoring.object(pipe.data["fallCheck"])[
        "minimumObservedFall"
    ] == pytest.approx(0.02)


@pytest.mark.parametrize(
    "invalid",
    [
        "pressure",
        "temperatureLow",
        "temperatureHigh",
        "invertedRange",
        "unknownPipeField",
        "missingDirection",
        "negativeMinimum",
        "wrongFamily",
        "splitSystem",
    ],
)
def test_invalid_pipe_specs_and_service_separation_fail(
    reference_model: JsonObject, validator: ModelValidator, invalid: str
) -> None:
    """Known rating contradictions and incompatible service assignments fail before export."""
    route = PipeFixture.configure(reference_model)
    definition = Authoring.object(
        Authoring.object(reference_model["types"])["type.pipe"]
    )
    conditions, stock = Authoring.object(route["conditions"]), Authoring.object(
        definition["pipe"]
    )
    if invalid == "pressure":
        conditions["pressurePa"] = 2000000
    elif invalid == "temperatureLow":
        conditions["temperatureC"] = -30
    elif invalid == "temperatureHigh":
        conditions["temperatureC"] = 100
    elif invalid == "invertedRange":
        stock["minimumTemperatureC"] = 100
    elif invalid == "unknownPipeField":
        stock["automaticSizing"] = True
    elif invalid == "missingDirection":
        del Authoring.object(route["fallCheck"])["direction"]
    elif invalid == "negativeMinimum":
        Authoring.object(route["fallCheck"])["minimumFall"] = -0.01
    elif invalid == "wrongFamily":
        definition["family"], definition["medium"] = "duct", "air"
    else:
        Authoring.object(Authoring.object(reference_model["elements"])["system.pipe"])[
            "systemType"
        ] = "gas"
    assert not validator.validate(reference_model).is_valid


def test_missing_pipe_ratings_stay_unchecked(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Unknown pressure/temperature limits and authored flow rates do not become verified capacity."""
    PipeFixture.configure(reference_model)
    del Authoring.object(Authoring.object(reference_model["types"])["type.pipe"])[
        "pipe"
    ]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    checks = Authoring.array(
        ModelResolver(reference_model)
        .resolve()
        .element("route.pipe")
        .data["pipeRatingChecks"]
    )
    assert len(checks) == 4 and all(
        Authoring.object(value)["status"] == "notChecked" for value in checks
    )


@pytest.mark.parametrize("kind", ["serviceRoute", "serviceFitting"])
def test_one_pipe_cannot_bridge_hot_and_cold_system_assignments(
    reference_model: JsonObject, validator: ModelValidator, kind: str
) -> None:
    """A single uninterrupted passage cannot acquire distinct system identities at its ends."""
    PipeFixture.configure(reference_model, "coldWater")
    elements = Authoring.object(reference_model["elements"])
    if kind == "serviceFitting":
        Authoring.object(reference_model["types"])["type.fitting"] = {
            "kind": "serviceFittingType",
            "name": "Water transition",
            "family": "pipe",
            "material": "material.timber",
            "medium": "water",
            "connectionType": "illustrativePipeFace",
            "wallThickness": 2,
            "chordTolerance": 0.2,
            "geometry": {
                "kind": "transition",
                "startSection": {"kind": "circle", "diameter": 40},
                "endSection": {"kind": "circle", "diameter": 40},
                "length": 100,
            },
        }
        elements["route.pipe"] = {
            "kind": "serviceFitting",
            "name": "Water transition",
            "type": "type.fitting",
            "placement": {"origin": {"point": [0, 0, 0]}},
            "portStates": {"start": "open", "end": "open"},
        }
    Authoring.object(elements["system.pipe"])["members"] = [
        {"element": "route.pipe", "port": "start"}
    ]
    elements["system.hot"] = {
        "kind": "serviceSystem",
        "name": "Hot supply",
        "systemType": "hotWater",
        "members": [{"element": "route.pipe", "port": "end"}],
    }
    report = validator.validate(reference_model)
    assert not report.is_valid and "cannot span different systems" in str(
        report.to_dict()
    )


def test_located_pipe_fall_and_exports_follow_a_transaction(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
) -> None:
    """A located endpoint edit updates fall/length data and preserves deterministic IFC/GLB identity."""
    route = PipeFixture.configure(reference_model)
    anchors = Authoring.object(reference_model["anchors"])
    anchors["anchor.pipe.end"] = {
        "kind": "point3",
        "name": "Pipe endpoint",
        "position": [1000, 1000, 960],
    }
    Authoring.array(route["path"])[-1] = {"anchor": "anchor.pipe.end"}
    change: JsonObject = {
        "changeVersion": "0.1",
        "id": "change.pipeEndpoint",
        "description": "Lower the pipe endpoint",
        "baseRevision": reference_model["revision"],
        "operations": [
            {
                "op": "moveAnchor",
                "anchorId": "anchor.pipe.end",
                "position": [1000, 1000, 940],
            }
        ],
    }
    changed = ChangeEngine(loader, validator).apply(reference_model, change)
    pipe = ModelResolver(changed).resolve().element("route.pipe")
    segments = Authoring.array(Authoring.object(pipe.data["fallCheck"])["segments"])
    assert [
        Authoring.object(segment)["fallRatio"] for segment in segments
    ] == pytest.approx([0.02, 0.04])
    source = tmp_path / "pipe.json"
    source.write_text(json.dumps(changed), encoding="utf-8")
    builder = BuildService(loader, validator)
    first, second = builder.build(source, tmp_path / "first"), builder.build(
        source, tmp_path / "second"
    )
    assert first.glb_model.read_bytes() == second.glb_model.read_bytes()
    assert first.schedules.read_bytes() == second.schedules.read_bytes()
    assert {
        r.GlobalId for r in ifcopenshell.open(first.ifc_model).by_type("IfcRoot")
    } == {r.GlobalId for r in ifcopenshell.open(second.ifc_model).by_type("IfcRoot")}
    bad_change = deepcopy(change)
    Authoring.object(Authoring.array(bad_change["operations"])[0])["position"] = [
        1000,
        1000,
        990,
    ]
    with pytest.raises(ModelValidationError, match="specified minimum"):
        ChangeEngine(loader, validator).apply(reference_model, bad_change)
