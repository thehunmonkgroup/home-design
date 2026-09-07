"""Separate physical service insulation, material ownership and native IFC covering exports."""

from __future__ import annotations

import math
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
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class InsulationFixture:
    """Author independently identified service stock and insulation using public materials."""

    @staticmethod
    def configure(
        model: JsonObject, family: str = "pipe", bent: bool = False
    ) -> JsonObject:
        """Make a route with outside dimensions independent of its physical covering."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        Authoring.object(model["materials"])["material.cover"] = {
            "name": "Service insulation",
            "category": "insulation",
            "appearance": {"color": "#d7c394"},
        }
        types = Authoring.object(model["types"])
        types["type.cover"] = {
            "kind": "serviceInsulationType",
            "name": "Ten millimetre insulation",
            "material": "material.cover",
            "thickness": 10,
        }
        medium = "water" if family == "pipe" else "air"
        types["type.route"] = {
            "kind": "serviceRouteType",
            "name": "Insulated stock",
            "family": family,
            "material": "material.timber",
            "medium": medium,
            "connectionType": "illustrativeFace",
            "section": (
                {"kind": "circle", "diameter": 40}
                if family == "pipe"
                else {"kind": "rectangle", "width": 40, "height": 30}
            ),
            "wallThickness": 2,
        }
        cover: JsonObject = {
            "kind": "serviceInsulation",
            "name": "Physical insulation",
            "type": "type.cover",
            "host": "service.test",
            "chordTolerance": 0.1,
        }
        path: list[JsonValue] = [{"point": [0, 0, 0]}, {"point": [300, 0, 0]}]
        if bent:
            path.append({"point": [300, 300, 0]})
        model["elements"] = {
            "service.test": {
                "kind": "serviceRoute",
                "name": "Insulated route",
                "type": "type.route",
                "storey": "level.ground",
                "path": path,
                "bendRadius": 80,
                "chordTolerance": 0.1,
                "portStates": {"start": "open", "end": "open"},
            },
            "insulation.test": cover,
            "system.test": {
                "kind": "serviceSystem",
                "name": "Insulated system",
                "systemType": "water" if family == "pipe" else "supplyAir",
                "members": [
                    {"element": "service.test", "port": key} for key in ("start", "end")
                ],
            },
        }
        return cover

    @classmethod
    def fitting(cls, model: JsonObject, role: str, family: str = "pipe") -> None:
        """Use a local fitting recipe with nontrivial translation and rotation."""
        cls.configure(model, family)
        section: JsonObject = (
            {"kind": "circle", "diameter": 40}
            if family == "pipe"
            else {"kind": "rectangle", "width": 40, "height": 30}
        )
        recipes: dict[str, JsonObject] = {
            "elbow": {
                "kind": "elbow",
                "section": section,
                "path": [[0, 0, 0], [0, 0, 200], [200, 0, 200]],
                "bendRadius": 80,
            },
            "branch": {
                "kind": "branch",
                "trunk": {"section": section, "path": [[0, 0, 0], [0, 0, 400]]},
                "branches": {
                    "side": {
                        "section": section,
                        "path": [[0, 0, 200], [200, 0, 200]],
                        "up": [0, 1, 0],
                    }
                },
            },
            "transition": {
                "kind": "transition",
                "startSection": section,
                "endSection": {"kind": "circle", "diameter": 20},
                "length": 100,
                "offset": [20, 0],
            },
            "cap": {"kind": "cap", "section": section, "depth": 60},
            "trap": {
                "kind": "trap",
                "section": section,
                "path": [[0, 0, 200], [0, 0, 0], [200, 0, 0], [200, 0, 150]],
                "bendRadius": 60,
            },
        }
        medium = "waste" if role == "trap" else "water" if family == "pipe" else "air"
        Authoring.object(model["types"])["type.fitting"] = {
            "kind": "serviceFittingType",
            "name": "Insulated fitting",
            "family": family,
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
            "name": "Insulated fitting",
            "type": "type.fitting",
            "placement": {"origin": {"point": [100, 200, 300]}, "rotation": [0, 0, 90]},
            "portStates": {key: "open" for key in ports},
        }
        system = Authoring.object(elements["system.test"])
        system["systemType"] = "supplyAir" if medium == "air" else medium
        system["members"] = [{"element": "service.test", "port": key} for key in ports]


@pytest.mark.parametrize("family", ["pipe", "duct"])
@pytest.mark.parametrize("bent", [False, True])
def test_insulation_has_separate_stock_quantities_and_native_exports(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    family: str,
    bent: bool,
) -> None:
    """The covering adds only annular material and exports as independently selectable native insulation."""
    InsulationFixture.configure(reference_model, family, bent)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    cover, host = result.element("insulation.test"), result.element("service.test")
    length = 600 - 160 + 40 * math.pi if bent else 300
    area = math.pi * (30**2 - 20**2) if family == "pipe" else 60 * 50 - 40 * 30
    assert cover.data["netVolumeMm3"] == pytest.approx(area * length, rel=0.01)
    assert (
        SolidOperations.partition(
            cover.meshes[0], host.construction_volumes["envelope"]
        )[1]
        is None
    )
    assert cover.storey_id == host.storey_id and cover.data["discipline"] == "services"
    rows = Authoring.array(ModelReports(result).schedules()["materials"])
    materials = {
        Authoring.text(Authoring.object(row)["materialId"]): number(
            Authoring.object(row)["volumeM3"], "quantity"
        )
        for row in rows
    }
    assert materials["material.cover"] == pytest.approx(
        number(cover.data["netVolumeMm3"], "cover volume") / 1e9
    )
    assert materials["material.timber"] == pytest.approx(
        SolidOperations.volume(host.meshes[0]) / 1e9
    )
    output = tmp_path / "insulation.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("insulation.test"))
    assert product.is_a("IfcCovering") and product.IsTypedBy[0].RelatingType.is_a(
        "IfcCoveringType"
    )
    assert ifcopenshell.util.element.get_predefined_type(product) == "INSULATION"
    assert len(ifc.by_type("IfcDistributionPort")) == 2
    qto = ifcopenshell.util.element.get_pset(product, "Qto_HomeDesignMountedPart")
    assert qto["NetVolume"] == pytest.approx(materials["material.cover"])
    relation = ifc.by_guid(IfcExporter.stable_guid("rel.mount.insulation.test"))
    assert (
        relation.RelatingElement.Tag == "service.test"
        and relation.RelatedElement == product
    )
    manifest = GltfExporter().export(
        result, tmp_path / "insulation.glb", tmp_path / "manifest.json"
    )
    entry = Authoring.object(Authoring.object(manifest["elements"])["insulation.test"])
    assert entry["nodes"] and entry["kind"] == "serviceInsulation"


@pytest.mark.parametrize(
    "family,role",
    [
        (family, role)
        for family in ("pipe", "duct")
        for role in ("elbow", "branch", "transition", "cap", "trap")
        if family == "pipe" or role != "trap"
    ],
)
def test_insulation_follows_fitting_geometry_and_covers_closed_caps(
    reference_model: JsonObject,
    validator: ModelValidator,
    family: str,
    role: str,
) -> None:
    """Branched and variable-section coverings enclose the original fitting without occupying its stock."""
    InsulationFixture.fitting(reference_model, role, family)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    host, cover = result.element("service.test"), result.element("insulation.test")
    assert (
        SolidOperations.difference(
            host.construction_volumes["envelope"],
            [cover.construction_volumes["envelope"]],
        )
        is None
    )
    assert (
        SolidOperations.partition(
            cover.meshes[0], host.construction_volumes["envelope"]
        )[1]
        is None
    )
    assert number(cover.data["netVolumeMm3"], "volume") > 0
    if role == "cap":
        assert max(vertex[2] for vertex in cover.meshes[0].vertices) == pytest.approx(
            370
        )
        assert cover.data["netVolumeMm3"] == pytest.approx(
            (
                math.pi * (30**2 * 70 - 20**2 * 60)
                if family == "pipe"
                else 60 * 50 * 70 - 40 * 30 * 60
            ),
            rel=0.01,
        )


@pytest.mark.parametrize(
    "invalid",
    [
        "duplicate",
        "wrongHost",
        "wrongFamily",
        "tooThick",
        "negativeThickness",
        "missingMaterial",
        "cycle",
    ],
)
def test_invalid_insulation_ownership_and_geometry_are_rejected(
    reference_model: JsonObject,
    validator: ModelValidator,
    invalid: str,
) -> None:
    """Insulation cannot double-count material or silently cover incompatible or invalid geometry."""
    cover = InsulationFixture.configure(reference_model, bent=True)
    elements = Authoring.object(reference_model["elements"])
    types = Authoring.object(reference_model["types"])
    if invalid == "duplicate":
        elements["insulation.duplicate"] = deepcopy(cover)
    elif invalid == "wrongHost":
        cover["host"] = "system.test"
    elif invalid == "wrongFamily":
        route_type = Authoring.object(types["type.route"])
        route_type.update({"family": "conduit", "medium": "electrical"})
        Authoring.object(elements["system.test"])["systemType"] = "electrical"
    elif invalid in {"tooThick", "negativeThickness"}:
        Authoring.object(types["type.cover"])["thickness"] = (
            100 if invalid == "tooThick" else -1
        )
    elif invalid == "missingMaterial":
        Authoring.object(types["type.cover"])["material"] = "material.absent"
    else:
        Authoring.array(Authoring.object(elements["service.test"])["path"])[0] = {
            "host": {"kind": "component", "element": "insulation.test"}
        }
    report = validator.validate(reference_model)
    assert not report.is_valid
    messages = {
        "duplicate": "overlap on their host",
        "wrongFamily": "pipe or duct",
        "tooThick": "Bend radius",
        "cycle": "cycle",
    }
    if invalid in messages:
        assert messages[invalid].lower() in str(report.to_dict()).lower()


@pytest.mark.parametrize("cut_cover", [False, True])
def test_insulation_and_pipe_share_a_cavity_without_duplicate_material(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    cut_cover: bool,
) -> None:
    """Infill, pipe, insulation and empty passage reconcile after an optional insulation-only cut."""
    cover = InsulationFixture.configure(reference_model)
    slab_type = Authoring.object(
        Authoring.object(reference_model["types"])["slabType.concrete-200"]
    )
    Authoring.object(Authoring.array(slab_type["layers"])[0])[
        "representation"
    ] = "explicit"
    elements = Authoring.object(reference_model["elements"])
    elements["slab.cavity"] = {
        "kind": "slab",
        "name": "Coordination cavity",
        "storey": "level.ground",
        "role": "floor",
        "type": "slabType.concrete-200",
        "extrusionDirection": "down",
        "datum": {"kind": "level", "level": "level.ground", "offset": 100},
        "footprint": {
            "outer": [
                {"point": [-100, -100]},
                {"point": [400, -100]},
                {"point": [400, 100]},
                {"point": [-100, 100]},
            ]
        },
    }
    ownership: JsonObject = {"regions": [{"host": "slab.cavity", "layer": 0}]}
    cover["occupies"] = deepcopy(ownership)
    Authoring.object(elements["service.test"])["occupies"] = ownership
    elements["cut.bore"] = {
        "kind": "penetration",
        "name": "Empty pipe passage",
        "purpose": "service",
        "host": "slab.cavity",
        "owner": "service.test",
        "geometrySource": {"element": "service.test", "volume": "bore"},
    }
    if cut_cover:
        elements["cut.insulation"] = {
            "kind": "penetration",
            "name": "Authored insulation break",
            "purpose": "service",
            "host": "insulation.test",
            "placement": {"origin": {"point": [100, 0, 0]}, "rotation": [0, 90, 0]},
            "section": {"kind": "rectangle", "width": 100, "depth": 100},
            "depth": 100,
        }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    host, pipe, insulation = (
        result.element(key)
        for key in ("slab.cavity", "service.test", "insulation.test")
    )
    cavity = Authoring.object(Authoring.array(host.data["cavities"])[0])
    assert cavity["grossVolumeMm3"] == pytest.approx(500 * 200 * 200)
    assert sum(
        number(cavity[key], key)
        for key in ("infillVolumeMm3", "occupiedVolumeMm3", "voidVolumeMm3")
    ) == pytest.approx(cavity["grossVolumeMm3"])
    for component in (pipe, insulation):
        assert all(
            SolidOperations.partition(mesh, part)[1] is None
            for mesh in host.meshes
            for part in component.meshes
        )
    covered_length = 200 if cut_cover else 300
    assert insulation.data["netVolumeMm3"] == pytest.approx(
        math.pi * (30**2 - 20**2) * covered_length, rel=0.01
    )
    expected_void = SolidOperations.volume(pipe.construction_volumes["bore"])
    if cut_cover:
        expected_void += number(
            result.element("cut.insulation").data["cutVolumeMm3"], "cover cut"
        )
    assert cavity["voidVolumeMm3"] == pytest.approx(expected_void)
    output = tmp_path / "cavity.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    if cut_cover:
        assert any(
            relation.RelatingBuildingElement.Tag == "insulation.test"
            for relation in ifc.by_type("IfcRelVoidsElement")
        )


def test_insulation_follows_route_edits_and_builds_deterministically(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
) -> None:
    """Changing a shared endpoint lengthens both materials and retains native covering identity."""
    InsulationFixture.configure(reference_model)
    Authoring.object(reference_model["anchors"])["anchor.routeEnd"] = {
        "kind": "point3",
        "name": "Route endpoint",
        "position": [300, 0, 0],
    }
    source = Authoring.object(
        Authoring.object(reference_model["elements"])["service.test"]
    )
    Authoring.array(source["path"])[1] = {"anchor": "anchor.routeEnd"}
    before = ModelResolver(reference_model).resolve().element("insulation.test")
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.insulation",
            "description": "Extend the insulated route",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "moveAnchor",
                    "anchorId": "anchor.routeEnd",
                    "position": [600, 0, 0],
                }
            ],
        },
    )
    after = ModelResolver(changed).resolve().element("insulation.test")
    assert after.data["netVolumeMm3"] == pytest.approx(
        2 * number(before.data["netVolumeMm3"], "previous volume")
    )
    model_path = tmp_path / "insulated.json"
    ModelLoader.write(changed, model_path)
    first = BuildService().build(model_path, tmp_path / "first")
    second = BuildService().build(model_path, tmp_path / "second")
    assert first.glb_model.read_bytes() == second.glb_model.read_bytes()
    assert {
        root.GlobalId for root in ifcopenshell.open(first.ifc_model).by_type("IfcRoot")
    } == {
        root.GlobalId for root in ifcopenshell.open(second.ifc_model).by_type("IfcRoot")
    }


def test_cut_curved_insulation_retains_mesh_volume_and_host_separation(
    reference_model: JsonObject,
    validator: ModelValidator,
) -> None:
    """A cut through the return's curved material remains consistent after Boolean serialization."""
    InsulationFixture.configure(reference_model, bent=True)
    before = ModelResolver(reference_model).resolve().element("insulation.test")
    Authoring.object(reference_model["elements"])["cut.curvedInsulation"] = {
        "kind": "penetration",
        "name": "Curved insulation access",
        "purpose": "service",
        "host": "insulation.test",
        "placement": {"origin": {"point": [250, 75, 0]}, "rotation": [0, 90, 0]},
        "section": {"kind": "rectangle", "width": 200, "depth": 150},
        "depth": 100,
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    cover, cut = result.element("insulation.test"), result.element(
        "cut.curvedInsulation"
    )
    expected = number(before.data["netVolumeMm3"], "before") - number(
        cut.data["cutVolumeMm3"], "removed"
    )
    assert number(cut.data["cutVolumeMm3"], "removed") > 0
    assert cover.data["netVolumeMm3"] == pytest.approx(expected)
    assert ModelReports.mesh_volume(cover.meshes[0]) == pytest.approx(expected)
    assert (
        SolidOperations.partition(
            cover.meshes[0],
            result.element("service.test").construction_volumes["envelope"],
        )[1]
        is None
    )


def test_separate_insulation_sections_can_share_one_service_without_overlap(
    reference_model: JsonObject,
    validator: ModelValidator,
) -> None:
    """Complementary owned cuts permit distinct material sections on the same service host."""
    original = InsulationFixture.configure(reference_model)
    expected = (
        ModelResolver(reference_model)
        .resolve()
        .element("insulation.test")
        .data["netVolumeMm3"]
    )
    elements = Authoring.object(reference_model["elements"])
    elements["insulation.second"] = deepcopy(original)
    for identity, start in (("insulation.test", 150), ("insulation.second", 0)):
        elements[f"cut.{identity}"] = {
            "kind": "penetration",
            "name": "Insulation section limit",
            "purpose": "service",
            "host": identity,
            "placement": {"origin": {"point": [start, 0, 0]}, "rotation": [0, 90, 0]},
            "section": {"kind": "rectangle", "width": 100, "depth": 100},
            "depth": 150,
        }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    assert sum(
        number(result.element(identity).data["netVolumeMm3"], "section volume")
        for identity in ("insulation.test", "insulation.second")
    ) == pytest.approx(expected)
