"""IFC standard service measures, optional bounds and project units retain authored meaning."""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api.root
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest
from ifcopenshell.entity_instance import entity_instance

from home_design.adapters.ifc import IfcExporter
from home_design.adapters.ifc_standard_services import IfcStandardServices
from home_design.adapters.ifc_units import IfcUnits
from home_design.json_types import JsonObject


class NativeServiceFixture:
    """Exercise standard property encoding independently of route tessellation."""

    @staticmethod
    def create(
        native: str, specification: JsonObject
    ) -> tuple[ifcopenshell.file, entity_instance]:
        """Build a schema-valid minimal project and native product with declared geometry dimensions."""
        model = ifcopenshell.file(schema="IFC4")
        ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Units")
        IfcUnits.assign(model)
        product = ifcopenshell.api.root.create_entity(
            model, ifc_class=native, name="Stock"
        )
        IfcStandardServices.apply(
            model,
            product,
            "type.stock",
            {"section": {"kind": "circle", "diameter": 40}, "wallThickness": 2},
            specification,
            IfcExporter.stable_guid,
        )
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(model, logger)
        assert not logger.statements
        return model, product


@pytest.mark.parametrize("native", ["IfcPipeSegment", "IfcPipeSegmentType"])
def test_pipe_actual_dimensions_and_one_sided_limits(native: str) -> None:
    """Missing limits stay absent; trade size and operating pressure do not become nominal IFC values."""
    model, product = NativeServiceFixture.create(
        native,
        {
            "pressureRatingPa": 1000000,
            "maximumTemperatureC": 90,
            "nominalSize": "Trade size",
        },
    )
    values = ifcopenshell.util.element.get_pset(product, "Pset_PipeSegmentTypeCommon")
    assert values["OuterDiameter"] == 40 and values["InnerDiameter"] == 36
    assert "NominalDiameter" not in values and "WorkingPressure" not in values
    properties = {item.Name: item for item in model.by_id(values["id"]).HasProperties}
    pressure = properties["PressureRange"]
    assert pressure.LowerBoundValue is None
    assert pressure.UpperBoundValue.is_a("IfcPressureMeasure")
    assert pressure.UpperBoundValue.wrappedValue == 1000000
    temperature = properties["TemperatureRange"]
    assert temperature.LowerBoundValue is None
    assert temperature.UpperBoundValue.is_a("IfcThermodynamicTemperatureMeasure")
    assert temperature.UpperBoundValue.wrappedValue == pytest.approx(363.15)


@pytest.mark.parametrize(
    "native", ["IfcDuctSegment", "IfcDuctFitting", "IfcDuctFittingType"]
)
def test_duct_signed_pressure_and_absolute_temperature_ranges(native: str) -> None:
    """Suction is negative gauge pressure and authored Celsius temperatures become kelvin."""
    model, product = NativeServiceFixture.create(
        native,
        {
            "negativePressureRatingPa": 750,
            "positivePressureRatingPa": 1000,
            "minimumTemperatureC": -10,
            "maximumTemperatureC": 60,
        },
    )
    values = ifcopenshell.util.element.get_pset(
        product, f"Pset_{native.removesuffix('Type')[3:]}TypeCommon"
    )
    assert "NominalDiameterOrWidth" not in values and "WorkingPressure" not in values
    properties = {item.Name: item for item in model.by_id(values["id"]).HasProperties}
    assert properties["PressureRange"].LowerBoundValue.wrappedValue == -750
    assert properties["PressureRange"].UpperBoundValue.wrappedValue == 1000
    assert properties["TemperatureRange"].LowerBoundValue.wrappedValue == pytest.approx(
        263.15
    )
    assert properties["TemperatureRange"].UpperBoundValue.wrappedValue == pytest.approx(
        333.15
    )


@pytest.mark.parametrize(
    "native,field,value,measure",
    [
        ("IfcBoiler", "WaterStorageCapacity", 0.2, "IfcVolumeMeasure"),
        ("IfcTank", "NominalCapacity", 0.2, "IfcVolumeMeasure"),
        ("IfcFan", "NominalAirFlowRate", 0.1, "IfcVolumetricFlowRateMeasure"),
        ("IfcDamper", "NominalAirFlowRate", 0.1, "IfcVolumetricFlowRateMeasure"),
    ],
)
def test_equipment_capacity_flow_and_units(
    native: str, field: str, value: float, measure: str
) -> None:
    """Litre capacity converts to cubic metres and native flow uses metres cubed per second."""
    model, product = NativeServiceFixture.create(
        native, {"capacityL": 200, "airflowRateM3s": 0.1, "pressureRatingPa": 1000000}
    )
    values = ifcopenshell.util.element.get_pset(product, f"Pset_{native[3:]}TypeCommon")
    assert values[field] == pytest.approx(value)
    assert (
        "PressureRating" not in values
    )  # Authored data does not declare agency certification.
    properties = {item.Name: item for item in model.by_id(values["id"]).HasProperties}
    assert properties[field].NominalValue.is_a(measure)
    units = {
        unit.UnitType: unit
        for unit in model.by_type("IfcProject")[0].UnitsInContext.Units
    }
    assert units["LENGTHUNIT"].Prefix == "MILLI"
    assert units["VOLUMEUNIT"].Name == "CUBIC_METRE"
    assert units["PRESSUREUNIT"].Name == "PASCAL"
    assert units["THERMODYNAMICTEMPERATUREUNIT"].Name == "KELVIN"
    flow_units = units["VOLUMETRICFLOWRATEUNIT"].Elements
    assert {
        (unit.Unit.Name, unit.Unit.Prefix, unit.Exponent) for unit in flow_units
    } == {("METRE", None, 3), ("SECOND", None, -1)}
