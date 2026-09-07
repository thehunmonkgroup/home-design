"""Duct stock classifications, signed pressure checks and native IFC properties."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class DuctFixture:
    """Provide matching stock specifications for a straight route or eccentric transition."""

    @staticmethod
    def configure(
        model: JsonObject, fitting: bool = False
    ) -> tuple[JsonObject, JsonObject]:
        """Use explicit illustrative sheet thickness independently of nominal stock data."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        section: JsonObject = {"kind": "rectangle", "width": 80, "height": 60}
        definition: JsonObject = {
            "kind": "serviceFittingType" if fitting else "serviceRouteType",
            "name": "Illustrative duct stock",
            "family": "duct",
            "material": "material.timber",
            "medium": "air",
            "connectionType": "illustrativeFlange",
            "wallThickness": 1,
            "duct": {
                "designation": "Illustrative sheet duct",
                "construction": "rigid",
                "positivePressureRatingPa": 1000,
                "negativePressureRatingPa": 750,
                "minimumTemperatureC": -10,
                "maximumTemperatureC": 60,
                "jointing": "Authored flange",
                "lining": "Authored lining specification",
                "leakageClass": "Illustrative class",
                "roughnessMm": 0.1,
            },
        }
        source: JsonObject = {
            "kind": "serviceFitting" if fitting else "serviceRoute",
            "name": "Duct under authored operating conditions",
            "type": "type.duct",
            "ductConditions": {
                "pressurePa": 500,
                "temperatureC": 20,
                "flowRateM3s": 0.03,
            },
            "portStates": {"start": "open", "end": "open"},
        }
        if fitting:
            definition["chordTolerance"] = 0.1
            definition["geometry"] = {
                "kind": "transition",
                "startSection": section,
                "endSection": {"kind": "rectangle", "width": 60, "height": 40},
                "length": 200,
                "offset": [20, 0],
            }
            source["placement"] = {
                "origin": {"point": [100, 200, 300]},
                "rotation": [0, 0, 90],
            }
        else:
            definition["section"] = section
            source["path"] = [{"point": [0, 0, 0]}, {"point": [1000, 0, 0]}]
            source["chordTolerance"] = 0.1
        Authoring.object(model["types"])["type.duct"] = definition
        model["elements"] = {
            "duct.test": source,
            "system.air": {
                "kind": "serviceSystem",
                "name": "Illustrative supply air",
                "systemType": "supplyAir",
                "members": [
                    {"element": "duct.test", "port": key} for key in ("start", "end")
                ],
            },
        }
        return definition, source


@pytest.mark.parametrize("fitting", [False, True])
@pytest.mark.parametrize("construction", ["rigid", "flexible"])
@pytest.mark.parametrize("pressure", [-500, 500])
def test_duct_limits_stock_quantities_and_native_exports(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    fitting: bool,
    construction: str,
    pressure: float,
) -> None:
    """Signed pressure selects its corresponding limit while stock metadata adds no material."""
    definition, source = DuctFixture.configure(reference_model, fitting)
    Authoring.object(definition["duct"])["construction"] = construction
    Authoring.object(source["ductConditions"])["pressurePa"] = pressure
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    element = result.element("duct.test")
    checks = [
        Authoring.object(value)
        for value in Authoring.array(element.data["ductRatingChecks"])
    ]
    assert [check["status"] for check in checks] == ["satisfied"] * 3 + ["notChecked"]
    assert checks[0]["limit"] == (-750 if pressure < 0 else 1000)
    assert element.data["duct"] == definition["duct"]
    assert element.data["ductConditions"] == source["ductConditions"]
    output = tmp_path / "duct.ifc"
    IfcExporter().export(result, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("duct.test"))
    assert product.is_a("IfcDuctFitting" if fitting else "IfcDuctSegment")
    expected = (
        "TRANSITION"
        if fitting
        else ("FLEXIBLESEGMENT" if construction == "flexible" else "RIGIDSEGMENT")
    )
    assert ifcopenshell.util.element.get_predefined_type(product) == expected
    assert product.IsTypedBy[0].RelatingType.PredefinedType == expected
    if not fitting:
        for stock in (product, product.IsTypedBy[0].RelatingType):
            standard = ifcopenshell.util.element.get_pset(
                stock, "Pset_DuctSegmentTypeCommon", should_inherit=False
            )
            assert standard["Reference"] == "type.duct"
            pset = ifc.by_id(standard["id"])
            assert pset is not None
            properties = {item.Name: item for item in pset.HasProperties}
            assert properties["PressureRange"].LowerBoundValue.wrappedValue == -750
            assert properties["PressureRange"].UpperBoundValue.wrappedValue == 1000
            assert "WorkingPressure" not in standard
    assert (
        ifcopenshell.util.element.get_pset(product, "Pset_HomeDesignDuctConditions")[
            "pressurePa"
        ]
        == pressure
    )
    assert (
        ifcopenshell.util.element.get_pset(
            product.IsTypedBy[0].RelatingType, "Pset_HomeDesignDuct"
        )["construction"]
        == construction
    )
    manifest = GltfExporter().export(
        result, tmp_path / "duct.glb", tmp_path / "manifest.json"
    )
    entry = Authoring.object(Authoring.object(manifest["elements"])["duct.test"])
    assert entry["nodes"]
    assert Authoring.object(entry["data"])["ductConditions"] == source["ductConditions"]
    quantities = ModelReports(result).schedules()["materials"]
    del definition["duct"]
    del source["ductConditions"]
    assert (
        ModelReports(ModelResolver(reference_model).resolve()).schedules()["materials"]
        == quantities
    )


@pytest.mark.parametrize("fitting", [False, True])
def test_missing_duct_limits_remain_unchecked(
    reference_model: JsonObject,
    validator: ModelValidator,
    fitting: bool,
) -> None:
    """Operating inputs remain useful without inventing ratings for unspecified stock."""
    definition, source = DuctFixture.configure(reference_model, fitting)
    del definition["duct"]
    Authoring.object(source["ductConditions"])["pressurePa"] = -500
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    checks = Authoring.array(
        ModelResolver(reference_model)
        .resolve()
        .element("duct.test")
        .data["ductRatingChecks"]
    )
    assert all(Authoring.object(value)["status"] == "notChecked" for value in checks)


@pytest.mark.parametrize("fitting", [False, True])
@pytest.mark.parametrize(
    "invalid",
    [
        "positivePressure",
        "negativePressure",
        "cold",
        "hot",
        "temperatureRange",
        "negativeRating",
        "negativeFlow",
        "emptyConditions",
        "wrongFamily",
        "missingDesignation",
    ],
)
def test_invalid_duct_conditions_and_specifications_fail(
    reference_model: JsonObject,
    validator: ModelValidator,
    fitting: bool,
    invalid: str,
) -> None:
    """Both routes and fittings reject incompatible inputs or nonduct operating metadata."""
    definition, source = DuctFixture.configure(reference_model, fitting)
    stock, conditions = Authoring.object(definition["duct"]), Authoring.object(
        source["ductConditions"]
    )
    if invalid == "positivePressure":
        conditions["pressurePa"] = 1001
    elif invalid == "negativePressure":
        conditions["pressurePa"] = -751
    elif invalid == "cold":
        conditions["temperatureC"] = -11
    elif invalid == "hot":
        conditions["temperatureC"] = 61
    elif invalid == "temperatureRange":
        stock["minimumTemperatureC"] = 70
    elif invalid == "negativeRating":
        stock["negativePressureRatingPa"] = -750
    elif invalid == "negativeFlow":
        conditions["flowRateM3s"] = -1
    elif invalid == "emptyConditions":
        source["ductConditions"] = {}
    elif invalid == "wrongFamily":
        del definition["duct"]
        definition["family"], definition["medium"] = "pipe", "water"
    else:
        del stock["designation"]
    report = validator.validate(reference_model)
    assert not report.is_valid
    if invalid == "wrongFamily":
        assert "require a duct" in str(report.to_dict())
