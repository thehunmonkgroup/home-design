"""Explicit cavity ownership across geometry, quantities, IFC and browser output."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest
import trimesh

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class CavityFixture:
    """Author one explicit stud within a public reference wall cavity."""

    @staticmethod
    def configure(model: JsonObject) -> JsonObject:
        """Add infill material and a member with measured section dimensions."""
        Authoring.object(model["materials"])["material.infill"] = {
            "name": "Cavity insulation"
        }
        types = Authoring.object(model["types"])
        layers = Authoring.array(
            Authoring.object(types["wallType.exterior.wood-185"])["layers"]
        )
        Authoring.object(layers[2]).update(
            {"representation": "explicit", "material": "material.infill"}
        )
        types["type.stud"] = {
            "kind": "memberType",
            "name": "Stud",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 40, "depth": 140},
        }
        part: JsonObject = {
            "kind": "member",
            "name": "Explicit wall stud",
            "role": "stud",
            "type": "type.stud",
            "storey": "level.ground",
            "axis": [{"point": [9500, 9.5, 0]}, {"point": [9500, 9.5, 2400]}],
            "occupies": {"regions": [{"host": "wall.south", "layer": 2}]},
        }
        Authoring.object(model["elements"])["stud.explicit"] = part
        return part

    @staticmethod
    def material_volumes(model: JsonObject) -> dict[str, float]:
        """Read independently accumulated schedule material quantities."""
        rows = Authoring.array(
            ModelReports(ModelResolver(model).resolve()).schedules()["materials"]
        )
        return {
            Authoring.text(Authoring.object(row)["materialId"]): number(
                Authoring.object(row)["volumeM3"], "material volume"
            )
            for row in rows
        }


def test_explicit_framing_displaces_infill_without_double_counting(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Insulation and timber share one cavity volume with disjoint physical solids."""
    CavityFixture.configure(reference_model)
    baseline = deepcopy(reference_model)
    del Authoring.object(baseline["elements"])["stud.explicit"]
    old = CavityFixture.material_volumes(baseline)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolver = ModelResolver(reference_model)
    resolved = resolver.resolve()
    assert resolved.to_dict() == resolver.resolve().to_dict()
    part = resolved.element("stud.explicit")
    host = resolved.element("wall.south")
    expected = 40 * 140 * 2400
    assert part.data["netVolumeMm3"] == pytest.approx(expected)
    for mesh in host.meshes:
        assert SolidOperations.intersection(mesh, part.meshes[0]) is None
        geometry = trimesh.Trimesh(
            vertices=mesh.vertices, faces=mesh.faces, process=False
        )
        assert geometry.is_watertight and geometry.is_winding_consistent
    new = CavityFixture.material_volumes(reference_model)
    assert old["material.infill"] - new["material.infill"] == pytest.approx(
        expected / 1e9
    )
    assert new["material.timber"] - old["material.timber"] == pytest.approx(
        expected / 1e9
    )
    cavity = Authoring.object(Authoring.array(host.data["cavities"])[0])
    assert cavity["occupiedVolumeMm3"] == pytest.approx(expected)
    assert cavity["voidVolumeMm3"] == pytest.approx(0)
    assert number(cavity["grossVolumeMm3"], "gross") == pytest.approx(
        number(cavity["infillVolumeMm3"], "infill") + expected
    )


def test_unfilled_cavity_has_no_physical_infill_mesh(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """An explicit layer without an infill material records air space as void volume."""
    CavityFixture.configure(reference_model)
    layers = Authoring.array(
        Authoring.object(
            Authoring.object(reference_model["types"])["wallType.exterior.wood-185"]
        )["layers"]
    )
    del Authoring.object(layers[2])["material"]
    assert validator.validate(reference_model).is_valid
    host = ModelResolver(reference_model).resolve().element("wall.south")
    assert not any(mesh.role.endswith("layer:2") for mesh in host.meshes)
    cavity = Authoring.object(Authoring.array(host.data["cavities"])[0])
    assert cavity["infillVolumeMm3"] == 0
    assert number(cavity["voidVolumeMm3"], "void") > 0


@pytest.mark.parametrize("fit", ["clip", "intersect"])
def test_fit_modes_preserve_or_trim_outside_portions(
    reference_model: JsonObject, validator: ModelValidator, fit: str
) -> None:
    """Clipping changes physical geometry; intersect mode keeps the authored part."""
    part = CavityFixture.configure(reference_model)
    part["axis"] = [{"point": [9500, 9.5, -500]}, {"point": [9500, 9.5, 2400]}]
    Authoring.object(part["occupies"])["fit"] = fit
    assert validator.validate(reference_model).is_valid
    actual = ModelResolver(reference_model).resolve().element("stud.explicit")
    assert min(point[2] for mesh in actual.meshes for point in mesh.vertices) == (
        -500 if fit == "intersect" else 0
    )
    assert actual.data["netVolumeMm3"] == pytest.approx(
        40 * 140 * (2900 if fit == "intersect" else 2400)
    )
    contribution = Authoring.object(
        Authoring.array(actual.data["cavityContributions"])[0]
    )
    assert contribution["volumeMm3"] == pytest.approx(40 * 140 * 2400)


def test_array_clipping_preserves_surviving_indices(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """An array member outside its host is omitted without renumbering survivors."""
    part = CavityFixture.configure(reference_model)
    part.update(
        {"kind": "framing", "distribution": [1, 0, 0], "spacing": 1000, "count": 2}
    )
    Authoring.object(part["occupies"])["fit"] = "clip"
    assert validator.validate(reference_model).is_valid
    actual = ModelResolver(reference_model).resolve().element("stud.explicit")
    assert actual.data["memberCount"] == 1
    assert actual.data["memberIndices"] == [0]
    assert actual.meshes[0].role == "member:0"


@pytest.mark.parametrize(
    "failure",
    [
        "overlap",
        "arrayOverlap",
        "outside",
        "aggregate",
        "missing",
        "layer",
        "fractions",
        "duplicate",
        "nonphysical",
    ],
)
def test_invalid_cavity_ownership_fails_validation(
    reference_model: JsonObject, validator: ModelValidator, failure: str
) -> None:
    """Ownership rejects geometric conflict and ambiguous aggregate quantities."""
    part = CavityFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    specification = Authoring.object(part["occupies"])
    region = Authoring.object(Authoring.array(specification["regions"])[0])
    layer = Authoring.object(
        Authoring.array(
            Authoring.object(
                Authoring.object(reference_model["types"])["wallType.exterior.wood-185"]
            )["layers"]
        )[2]
    )
    if failure == "overlap":
        elements["stud.conflict"] = deepcopy(part)
    elif failure == "arrayOverlap":
        part.update(
            {"kind": "framing", "distribution": [1, 0, 0], "spacing": 10, "count": 2}
        )
    elif failure == "outside":
        part["axis"] = [{"point": [9500, 400, 0]}, {"point": [9500, 400, 2400]}]
    elif failure == "aggregate":
        layer["representation"] = "aggregate"
    elif failure == "missing":
        region["host"] = "wall.missing"
    elif failure == "layer":
        region["layer"] = 99
    elif failure == "fractions":
        layer["components"] = [
            {"material": "material.timber", "fraction": 0.2},
            {"material": "material.infill", "fraction": 0.8},
        ]
    elif failure == "duplicate":
        specification["regions"] = [region, deepcopy(region)]
    else:
        elements["assembly.invalid"] = {
            "kind": "assembly",
            "name": "Invalid occupant",
            "assemblyType": "wallSystem",
            "occupies": specification,
        }
    assert not validator.validate(reference_model).is_valid


def test_cavities_export_native_parts_connections_and_balanced_quantities(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """The browser and IFC receive disjoint solids and the same explicit composition."""
    part = CavityFixture.configure(reference_model)
    part["discipline"] = "services"
    source = tmp_path / "cavity.json"
    ModelLoader.write(reference_model, source)
    first = BuildService().build(source, tmp_path / "first")
    second = BuildService().build(source, tmp_path / "second")
    assert first.resolved_model.read_bytes() == second.resolved_model.read_bytes()
    assert first.glb_model.read_bytes() == second.glb_model.read_bytes()
    manifest = json.loads(first.render_manifest.read_text())
    assert manifest["elements"]["stud.explicit"]["data"]["discipline"] == "services"
    assert manifest["elements"]["stud.explicit"]["nodes"]
    schedules = json.loads((first.resolved_model.parent / "schedules.json").read_text())
    assert any(row["elementId"] == "wall.south" for row in schedules["cavities"])
    ifc = ifcopenshell.open(first.ifc_model)
    stud = next(
        item for item in ifc.by_type("IfcMember") if item.Tag == "stud.explicit"
    )
    connection = next(
        item
        for item in ifc.by_type("IfcRelConnectsElements")
        if item.RelatedElement == stud
    )
    assert connection.RelatingElement.Tag == "wall.south"
    host = connection.RelatingElement
    data = ifcopenshell.util.element.get_psets(host)["Pset_HomeDesignData"]
    cavity = json.loads(data["cavities"])[0]
    assert cavity["occupiedVolumeMm3"] == pytest.approx(40 * 140 * 2400)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []


@pytest.mark.parametrize("host", ["slab.ground", "roof.main"])
def test_floor_and_roof_cavities_resolve_actual_volume(
    reference_model: JsonObject, validator: ModelValidator, host: str
) -> None:
    """The same ownership contract applies to horizontal floors and sloped roofs."""
    part = CavityFixture.configure(reference_model)
    index = 0 if host == "slab.ground" else 2
    host_type = "slabType.concrete-200" if index == 0 else "roofType.shingle-250"
    layers = Authoring.array(
        Authoring.object(Authoring.object(reference_model["types"])[host_type])[
            "layers"
        ]
    )
    Authoring.object(layers[index]).update(
        {"representation": "explicit", "material": "material.infill"}
    )
    part["occupies"] = {"regions": [{"host": host, "layer": index}]}
    part["axis"] = [
        {
            "host": {
                "kind": "surface",
                "element": host,
                "surface": "layerCenter",
                "layer": index,
                "point": [2500, 1000],
            }
        },
        {
            "host": {
                "kind": "surface",
                "element": host,
                "surface": "layerCenter",
                "layer": index,
                "point": [3500, 1000],
            }
        },
    ]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    assert resolved.element("stud.explicit").data["netVolumeMm3"] == pytest.approx(
        40 * 140 * 1000
    )
    cavity = Authoring.object(
        Authoring.array(resolved.element(host).data["cavities"])[0]
    )
    assert cavity["occupiedVolumeMm3"] == pytest.approx(40 * 140 * 1000)


def test_penetrations_cut_disjoint_parts_and_reconcile_cavity_balance(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A bore through infill and timber counts each removed physical volume once."""
    CavityFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    for host in ("wall.south", "stud.explicit"):
        cut: JsonObject = {
            "kind": "penetration",
            "name": "Coordinated bore",
            "host": host,
            "owner": "stud.explicit",
            "purpose": "service",
            "placement": {
                "origin": {"point": [9500, -70, 1000]},
                "rotation": [-90, 0, 0],
            },
            "section": {"kind": "rectangle", "width": 100, "depth": 100},
            "depth": 160,
        }
        if host == "wall.south":
            cut["layers"] = [2]
        elements[f"cut.{host}"] = cut
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    assert resolved.element("cut.wall.south").data["cutVolumeMm3"] == pytest.approx(
        60 * 100 * 140
    )
    assert resolved.element("cut.stud.explicit").data["cutVolumeMm3"] == pytest.approx(
        40 * 100 * 140
    )
    cavity = Authoring.object(
        Authoring.array(resolved.element("wall.south").data["cavities"])[0]
    )
    assert cavity["occupiedVolumeMm3"] == pytest.approx(40 * 140 * 2300)
    assert cavity["voidVolumeMm3"] == pytest.approx(100 * 100 * 140)
    contribution = Authoring.object(
        Authoring.array(resolved.element("stud.explicit").data["cavityContributions"])[
            0
        ]
    )
    assert contribution["volumeMm3"] == cavity["occupiedVolumeMm3"]


def test_one_part_can_occupy_multiple_disjoint_layers(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Contributions across adjoining layers sum to the part's single physical volume."""
    part = CavityFixture.configure(reference_model)
    slab_type = Authoring.object(
        Authoring.object(reference_model["types"])["slabType.concrete-200"]
    )
    slab_type["layers"] = [
        {
            "name": "Upper cavity",
            "function": "structure",
            "representation": "explicit",
            "material": "material.infill",
            "thickness": 100,
        },
        {
            "name": "Lower cavity",
            "function": "structure",
            "representation": "explicit",
            "material": "material.infill",
            "thickness": 100,
        },
    ]
    part["axis"] = [{"point": [500, 500, -100]}, {"point": [1500, 500, -100]}]
    part["occupies"] = {
        "regions": [
            {"host": "slab.ground", "layer": 0},
            {"host": "slab.ground", "layer": 1},
        ]
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    contributions = Authoring.array(
        resolved.element("stud.explicit").data["cavityContributions"]
    )
    assert [
        Authoring.object(row)["volumeMm3"] for row in contributions
    ] == pytest.approx([2800000, 2800000])
    assert resolved.element("stud.explicit").data["netVolumeMm3"] == pytest.approx(
        5600000
    )
    elements = Authoring.object(reference_model["elements"])
    elements["slab.overlap"] = deepcopy(elements["slab.ground"])
    part["occupies"] = {
        "regions": [
            {"host": "slab.ground", "layer": 0},
            {"host": "slab.overlap", "layer": 0},
        ]
    }
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert any(
        "overlapping cavity regions" in diagnostic.message
        for diagnostic in report.diagnostics
    )
