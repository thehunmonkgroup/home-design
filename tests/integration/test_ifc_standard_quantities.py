"""IFC4 template quantities preserve nominal stock and independently measured final material."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.pset
import ifcopenshell.validate
import pytest

from home_design.adapters.ifc import IfcExporter
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


def test_processed_member_quantity_keeps_nominal_length_and_final_net_volume(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """End trimming changes material volume without substituting net length for the template's nominal length."""
    (
        reference_model["relationships"],
        reference_model["requirements"],
        reference_model["solarStudies"],
    ) = ({}, [], [])
    Authoring.object(reference_model["types"])["type.stock"] = {
        "kind": "memberType",
        "name": "Cut stock",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 100, "depth": 100},
    }
    reference_model["elements"] = {
        "member.cut": {
            "kind": "member",
            "name": "Trimmed beam",
            "type": "type.stock",
            "role": "beam",
            "axis": [{"point": [0, 0, 0]}, {"point": [0, 0, 1000]}],
            "endCuts": {
                "start": {"normal": [0, 0, 1], "offset": 100},
                "end": {"normal": [0, 0, -1], "offset": 200},
            },
        }
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    path = tmp_path / "quantities.ifc"
    IfcExporter().export(resolved, path)
    model = ifcopenshell.open(path)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger)
    assert not logger.statements
    beam = model.by_type("IfcBeam")[0]
    quantities = ifcopenshell.util.element.get_psets(beam, qtos_only=True)[
        "Qto_BeamBaseQuantities"
    ]
    assert quantities["Length"] == 1000
    assert quantities["CrossSectionArea"] == pytest.approx(0.01)
    assert quantities["NetVolume"] == pytest.approx(0.007)
    assert "GrossWeight" not in quantities and "NetWeight" not in quantities
    schedules = ModelReports(resolved).schedules()
    assert Authoring.object(Authoring.array(schedules["framing"])[0])[
        "volumeM3"
    ] == pytest.approx(0.007)


def test_public_shell_standard_volume_quantities_match_material_schedules(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    """Every published standard quantity uses a real applicable template and preserves net wall/floor stock."""
    resolved = ModelResolver(reference_model).resolve()
    path = tmp_path / "shell.ifc"
    IfcExporter().export(resolved, path)
    native = ifcopenshell.open(path)
    templates = ifcopenshell.util.pset.get_template("IFC4")
    schedules = ModelReports(resolved).schedules()
    rows = {
        Authoring.text(Authoring.object(value)["id"]): Authoring.object(value)
        for value in Authoring.array(schedules["components"])
    }
    checked: set[str] = set()
    for quantity_set in native.by_type("IfcElementQuantity"):
        if quantity_set.Name.startswith("Qto_HomeDesign"):
            continue
        template = templates.get_by_name(quantity_set.Name)
        assert template is not None
        names = {field.Name for field in template.HasPropertyTemplates}
        assert all(quantity.Name in names for quantity in quantity_set.Quantities)
        product = quantity_set.DefinesOccurrence[0].RelatedObjects[0]
        assert quantity_set.Name in {
            value.Name
            for value in templates.get_applicable(product.is_a(), qto_only=True)
        }
        for quantity in quantity_set.Quantities:
            if quantity.Name == "NetVolume":
                assert quantity.VolumeValue == pytest.approx(
                    rows[product.Tag]["volumeM3"]
                )
                checked.add(product.Tag)
    assert checked == {
        "wall.north",
        "wall.south",
        "wall.east",
        "wall.west",
        "slab.ground",
        "slab.deck.south",
    }
