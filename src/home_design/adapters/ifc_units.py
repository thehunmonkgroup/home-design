"""Explicit IFC project units and conversions from canonical millimetre geometry."""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api.unit

from home_design.quantities import Quantity


class IfcUnits:
    """Keep geometry lengths in millimetres and native areas/volumes in square/cubic metres."""

    @staticmethod
    def assign(ifc: ifcopenshell.file) -> None:
        """Declare supported project units explicitly rather than depending on API defaults."""
        units = [
            ifcopenshell.api.unit.add_si_unit(ifc, unit_type=kind, prefix=prefix)
            for kind, prefix in (
                ("LENGTHUNIT", "MILLI"),
                ("AREAUNIT", None),
                ("VOLUMEUNIT", None),
                ("ELECTRICCURRENTUNIT", None),
                ("ELECTRICVOLTAGEUNIT", None),
                ("PRESSUREUNIT", None),
                ("THERMODYNAMICTEMPERATUREUNIT", None),
                ("TIMEUNIT", None),
            )
        ]
        metre = ifcopenshell.api.unit.add_si_unit(ifc, unit_type="LENGTHUNIT")
        second = next(unit for unit in units if unit.UnitType == "TIMEUNIT")
        units.append(
            ifc.create_entity(
                "IfcDerivedUnit",
                Elements=[
                    ifc.create_entity("IfcDerivedUnitElement", Unit=metre, Exponent=3),
                    ifc.create_entity(
                        "IfcDerivedUnitElement", Unit=second, Exponent=-1
                    ),
                ],
                UnitType="VOLUMETRICFLOWRATEUNIT",
            )
        )
        ifcopenshell.api.unit.assign_unit(ifc, units=units)

    @staticmethod
    def area(square_millimetres: float) -> float:
        """Convert a canonical area to the declared native square-metre unit."""
        return Quantity(square_millimetres, "mm2").in_unit("m2").value

    @staticmethod
    def volume(cubic_millimetres: float) -> float:
        """Convert a canonical volume to the declared native cubic-metre unit."""
        return Quantity(cubic_millimetres, "mm3").in_unit("m3").value
