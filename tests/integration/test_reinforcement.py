"""Foundation steel/grout ownership, host edits and native reinforcement interchange."""

from __future__ import annotations

import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class ReinforcementFixture:
    """Provide isolated foundation reinforcement with independently measured material volumes."""

    @staticmethod
    def point(x: float, y: float, cover: float) -> JsonObject:
        """Reference a point below the foundation top without inferring cover requirements."""
        return {
            "host": {
                "kind": "surface",
                "element": "footing.reinforced",
                "surface": "top",
                "point": [x, y],
                "offset": [0, 0, -cover],
            }
        }

    @classmethod
    def configure(cls, model: JsonObject) -> None:
        """Add a bent bar, closed tie, wire mesh and grout pocket in one explicit footing."""
        Authoring.object(model["materials"]).update(
            {
                "material.rebar": {"name": "Reinforcing steel"},
                "material.grout": {"name": "Grout"},
            }
        )
        types = Authoring.object(model["types"])
        types["type.reinforcedFooting"] = {
            "kind": "footingType",
            "name": "Explicit foundation",
            "depth": 500,
            "material": "material.concrete",
            "representation": "explicit",
        }
        types["type.bar"] = {
            "kind": "reinforcingBarType",
            "name": "Illustrative bar",
            "material": "material.rebar",
            "nominalDiameter": 20,
            "role": "main",
            "steelGrade": "Authored grade",
            "surface": "ribbed",
            "minimumBendRadius": 80,
        }
        types["type.tie"] = {
            **Authoring.object(types["type.bar"]),
            "name": "Illustrative tie",
            "role": "tie",
        }
        types["type.mesh"] = {
            "kind": "reinforcingMeshType",
            "name": "Illustrative mesh",
            "material": "material.rebar",
            "longitudinalDiameter": 8,
            "transverseDiameter": 8,
            "longitudinalSpacing": 200,
            "transverseSpacing": 200,
            "steelGrade": "Authored mesh grade",
        }
        types["type.grout"] = {
            "kind": "masonryPartType",
            "name": "Grout pocket",
            "role": "grout",
            "material": "material.grout",
            "solids": {
                "body": {
                    "section": {"kind": "rectangle", "width": 100, "depth": 100},
                    "depth": 100,
                }
            },
        }
        elements = Authoring.object(model["elements"])
        elements["footing.reinforced"] = {
            "kind": "footing",
            "name": "Reinforced foundation",
            "type": "type.reinforcedFooting",
            "shape": "pad",
            "storey": "level.ground",
            "datum": {"kind": "level", "level": "level.ground", "offset": 500},
            "footprint": {
                "outer": [
                    {"point": [0, -8000]},
                    {"point": [2000, -8000]},
                    {"point": [2000, -6000]},
                    {"point": [0, -6000]},
                ]
            },
        }
        owns: JsonObject = {"regions": [{"host": "footing.reinforced", "layer": 0}]}
        elements["bar.bent"] = {
            "kind": "reinforcingBar",
            "name": "Bent main bar",
            "type": "type.bar",
            "storey": "level.ground",
            "path": [
                cls.point(100, -7900, 100),
                cls.point(1900, -7900, 100),
                cls.point(1900, -6100, 100),
            ],
            "bendRadius": 100,
            "chordTolerance": 0.1,
            "occupies": owns,
        }
        elements["bar.tie"] = {
            "kind": "reinforcingBar",
            "name": "Closed tie",
            "type": "type.tie",
            "storey": "level.ground",
            "path": [
                cls.point(300, -7700, 200),
                cls.point(1700, -7700, 200),
                cls.point(1700, -6300, 200),
                cls.point(300, -6300, 200),
            ],
            "closed": True,
            "bendRadius": 100,
            "chordTolerance": 0.1,
            "occupies": owns,
        }
        elements["mesh.foundation"] = {
            "kind": "reinforcingMesh",
            "name": "Foundation mesh",
            "type": "type.mesh",
            "storey": "level.ground",
            "placement": {"origin": cls.point(100, -7900, 400)},
            "length": 1800,
            "width": 1800,
            "occupies": owns,
        }
        elements["grout.pocket"] = {
            "kind": "masonryPart",
            "name": "Grout pocket",
            "type": "type.grout",
            "storey": "level.ground",
            "placement": {"origin": cls.point(1000, -7000, 350)},
            "occupies": owns,
        }


def test_foundation_steel_and_grout_displace_concrete_once(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """All independently owned parts reconcile with the remaining foundation infill."""
    ReinforcementFixture.configure(reference_model)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    footing = resolved.element("footing.reinforced")
    parts = [
        resolved.element(key)
        for key in ("bar.bent", "bar.tie", "mesh.foundation", "grout.pocket")
    ]
    occupied = sum(
        SolidOperations.volume(mesh) for part in parts for mesh in part.meshes
    )
    cavity = Authoring.object(Authoring.array(footing.data["cavities"])[0])
    assert cavity["grossVolumeMm3"] == pytest.approx(2000 * 2000 * 500)
    assert cavity["occupiedVolumeMm3"] == pytest.approx(occupied)
    assert number(cavity["infillVolumeMm3"], "infill") + occupied == pytest.approx(
        2000 * 2000 * 500
    )
    for part in parts:
        for mesh in part.meshes:
            assert SolidOperations.intersection(footing.meshes[0], mesh) is None
    schedules = ModelReports(resolved).schedules()
    steel = next(
        Authoring.object(row)
        for row in Authoring.array(schedules["materials"])
        if Authoring.object(row)["materialId"] == "material.rebar"
    )
    assert steel["volumeM3"] == pytest.approx((occupied - 1000000) / 1e9)
    assert len(Authoring.array(schedules["reinforcement"])) == 3
    assert len(Authoring.array(schedules["masonry"])) == 1
    assert resolved.element("bar.bent").data["centerlineLengthMm"] == pytest.approx(
        3600 - 200 + 50 * math.pi
    )
    assert resolved.element("bar.tie").data["centerlineLengthMm"] == pytest.approx(
        5600 - 800 + 200 * math.pi
    )


def test_welded_mesh_intersections_count_steel_once(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Coincident wire layers union their crossings instead of duplicating steel volume."""
    ReinforcementFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve()
    mesh = Authoring.object(
        Authoring.object(reference_model["elements"])["mesh.foundation"]
    )
    mesh["layerSeparation"] = 0
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve()
    first, second = before.element("mesh.foundation"), after.element("mesh.foundation")
    area = 32 * 4**2 * math.sin(math.pi / 32)
    assert first.data["netVolumeMm3"] == pytest.approx(area * 36000)
    assert number(second.data["netVolumeMm3"], "welded volume") < number(
        first.data["netVolumeMm3"], "separated volume"
    )
    assert second.data["totalWireLengthMm"] == first.data["totalWireLengthMm"] == 36000
    old_cavity = Authoring.object(
        Authoring.array(before.element("footing.reinforced").data["cavities"])[0]
    )
    new_cavity = Authoring.object(
        Authoring.array(after.element("footing.reinforced").data["cavities"])[0]
    )
    assert number(new_cavity["infillVolumeMm3"], "new infill") - number(
        old_cavity["infillVolumeMm3"], "old infill"
    ) == pytest.approx(
        number(first.data["netVolumeMm3"], "old steel")
        - number(second.data["netVolumeMm3"], "new steel")
    )


def test_owned_bar_notch_changes_steel_and_foundation_void_quantities(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A bar-only cut removes metal and leaves concrete infill intact around the owned void."""
    ReinforcementFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve()
    Authoring.object(reference_model["elements"])["cut.bar"] = {
        "kind": "penetration",
        "name": "Authored bar notch",
        "host": "bar.bent",
        "purpose": "notch",
        "placement": {"origin": {"point": [500, -7900, 400]}},
        "section": {"kind": "rectangle", "width": 100, "depth": 40},
        "depth": 20,
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve()
    removed = (
        100
        * number(before.element("bar.bent").data["sectionAreaMm2"], "section area")
        / 2
    )
    assert number(
        before.element("bar.bent").data["netVolumeMm3"], "old steel"
    ) - number(
        after.element("bar.bent").data["netVolumeMm3"], "new steel"
    ) == pytest.approx(
        removed
    )
    assert (
        after.element("bar.bent").data["centerlineLengthMm"]
        == before.element("bar.bent").data["centerlineLengthMm"]
    )
    first = Authoring.object(
        Authoring.array(before.element("footing.reinforced").data["cavities"])[0]
    )
    second = Authoring.object(
        Authoring.array(after.element("footing.reinforced").data["cavities"])[0]
    )
    assert second["infillVolumeMm3"] == pytest.approx(first["infillVolumeMm3"])
    assert number(second["voidVolumeMm3"], "new void") - number(
        first["voidVolumeMm3"], "old void"
    ) == pytest.approx(removed, abs=0.01)


def test_explicit_foundation_layer_center_is_a_host_coordinate(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """The explicit foundation body exposes the same selectable layer frame as layered hosts."""
    ReinforcementFixture.configure(reference_model)
    bar = Authoring.object(Authoring.object(reference_model["elements"])["bar.bent"])
    bar["path"] = [
        {
            "host": {
                "kind": "surface",
                "element": "footing.reinforced",
                "surface": "layerCenter",
                "layer": 0,
                "point": [x, -7900],
            }
        }
        for x in (100, 1900)
    ]
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve().element("bar.bent")
    assert Authoring.array(resolved.data["path"])[0] == pytest.approx([100, -7900, 250])
    assert resolved.data["centerlineLengthMm"] == pytest.approx(1800)


def test_foundation_datum_edit_moves_steel_and_grout(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Host-based cover offsets follow a foundation edit while retaining material quantities."""
    ReinforcementFixture.configure(reference_model)
    before = ModelResolver(reference_model).resolve()
    footing = Authoring.object(
        Authoring.object(reference_model["elements"])["footing.reinforced"]
    )
    Authoring.object(footing["datum"])["offset"] = 550
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    after = ModelResolver(reference_model).resolve()
    for key in ("bar.bent", "bar.tie", "mesh.foundation", "grout.pocket"):
        first, second = before.element(key), after.element(key)
        assert min(point[2] for point in second.meshes[0].vertices) - min(
            point[2] for point in first.meshes[0].vertices
        ) == pytest.approx(50)
        assert second.data["netVolumeMm3"] == pytest.approx(first.data["netVolumeMm3"])


def test_reinforcement_and_grout_export_native_ifc_dimensions(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """IFC retains real steel classes, nominal bend lengths and final net material quantities."""
    ReinforcementFixture.configure(reference_model)
    path = tmp_path / "reinforcement.json"
    ModelLoader.write(reference_model, path)
    result = BuildService().build(path, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    bars = {value.Tag: value for value in ifc.by_type("IfcReinforcingBar")}
    assert bars["bar.tie"].IsTypedBy[0].RelatingType.PredefinedType == "LIGATURE"
    assert bars["bar.bent"].BarLength == pytest.approx(3600 - 200 + 50 * math.pi)
    assert bars["bar.bent"].NominalDiameter == 20
    assert bars["bar.bent"].CrossSectionArea == pytest.approx(math.pi * 0.01**2)
    assert bars["bar.bent"].BarSurface == "TEXTURED"
    standard = ifcopenshell.util.element.get_psets(bars["bar.bent"], qtos_only=True)[
        "Qto_ReinforcingElementBaseQuantities"
    ]
    assert standard["Count"] == 1
    assert standard["Length"] == pytest.approx(3600 - 200 + 50 * math.pi)
    assert "Weight" not in standard
    mesh = next(
        value
        for value in ifc.by_type("IfcReinforcingMesh")
        if value.Tag == "mesh.foundation"
    )
    assert mesh.LongitudinalBarSpacing == 200 and mesh.MeshLength == 1800
    assert mesh.LongitudinalBarCrossSectionArea == pytest.approx(
        math.pi * (mesh.LongitudinalBarNominalDiameter / 2000) ** 2
    )
    assert mesh.TransverseBarCrossSectionArea == pytest.approx(
        math.pi * (mesh.TransverseBarNominalDiameter / 2000) ** 2
    )
    assert mesh.IsTypedBy[0].RelatingType.is_a("IfcReinforcingMeshType")
    grout = next(
        value
        for value in ifc.by_type("IfcBuildingElementPart")
        if value.Tag == "grout.pocket"
    )
    assert grout.IsTypedBy[0].RelatingType.ElementType == "grout"
    quantities = [
        quantity
        for relation in grout.IsDefinedBy
        if relation.RelatingPropertyDefinition.is_a("IfcElementQuantity")
        for quantity in relation.RelatingPropertyDefinition.Quantities
    ]
    assert next(
        quantity for quantity in quantities if quantity.Name == "NetVolume"
    ).VolumeValue == pytest.approx(0.001)


@pytest.mark.parametrize(
    "case", ["aggregate", "layer", "bendMinimum", "spacing", "type"]
)
def test_invalid_reinforcement_intent_is_rejected(
    reference_model: JsonObject, validator: ModelValidator, case: str
) -> None:
    """Reject aggregate ownership, missing regions, authored limit violations and wrong types."""
    ReinforcementFixture.configure(reference_model)
    types, elements = Authoring.object(reference_model["types"]), Authoring.object(
        reference_model["elements"]
    )
    if case == "aggregate":
        Authoring.object(types["type.reinforcedFooting"])[
            "representation"
        ] = "aggregate"
    elif case == "layer":
        Authoring.object(elements["bar.bent"])["occupies"] = {
            "regions": [{"host": "footing.reinforced", "layer": 1}]
        }
    elif case == "bendMinimum":
        Authoring.object(elements["bar.bent"])["bendRadius"] = 50
    elif case == "spacing":
        Authoring.object(types["type.mesh"])["longitudinalSpacing"] = 4
    else:
        Authoring.object(elements["bar.bent"])["type"] = "type.grout"
    assert not validator.validate(reference_model).is_valid
