"""Hollow masonry units, grout cells and mortar beds as disjoint material parts."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest

from home_design.build import BuildService
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


class MasonryFixture:
    """Create a generic hollow unit with explicit grout and a separate mortar bed."""

    @staticmethod
    def configure(model: JsonObject) -> None:
        """Place construction parts in an empty explicit wall layer."""
        Authoring.object(model["materials"]).update(
            {
                "material.block": {"name": "Masonry unit"},
                "material.grout": {"name": "Grout"},
                "material.mortar": {"name": "Mortar"},
            }
        )
        types = Authoring.object(model["types"])
        cells: JsonObject = {
            f"cell{index}": {
                "section": {"kind": "rectangle", "width": 150, "depth": 130},
                "depth": 190,
                "placement": {"origin": [x, 0, 10]},
            }
            for index, x in enumerate((-95, 95))
        }
        types["type.masonryWall"] = {
            "kind": "wallType",
            "name": "Explicit masonry wall",
            "layerOrder": "exteriorToInterior",
            "layers": [
                {
                    "name": "Masonry construction",
                    "function": "structure",
                    "thickness": 190,
                    "representation": "explicit",
                }
            ],
        }
        types["type.block"] = {
            "kind": "masonryPartType",
            "name": "Hollow unit",
            "role": "unit",
            "material": "material.block",
            "solids": {
                "body": {
                    "section": {"kind": "rectangle", "width": 390, "depth": 190},
                    "depth": 200,
                }
            },
            "cuts": cells,
        }
        types["type.grout"] = {
            "kind": "masonryPartType",
            "name": "Cell grout",
            "role": "grout",
            "material": "material.grout",
            "solids": cells,
        }
        types["type.mortar"] = {
            "kind": "masonryPartType",
            "name": "Mortar bed",
            "role": "mortar",
            "material": "material.mortar",
            "solids": {
                "bed": {
                    "section": {"kind": "rectangle", "width": 400, "depth": 190},
                    "depth": 10,
                }
            },
        }
        elements = Authoring.object(model["elements"])
        elements["wall.masonry"] = {
            "kind": "wall",
            "name": "Masonry test wall",
            "locationLine": "center",
            "type": "type.masonryWall",
            "storey": "level.ground",
            "path": {
                "kind": "line",
                "start": {"point": [0, -4000]},
                "end": {"point": [400, -4000]},
            },
            "base": {"kind": "level", "level": "level.ground", "offset": 0},
            "top": {"kind": "height", "height": 220},
        }
        for role in ("block", "grout", "mortar"):
            elements[f"masonry.{role}"] = {
                "kind": "masonryPart",
                "name": role,
                "type": f"type.{role}",
                "storey": "level.ground",
                "placement": {
                    "origin": {"point": [200, -4000, 0 if role == "mortar" else 10]}
                },
                "occupies": {"regions": [{"host": "wall.masonry", "layer": 0}]},
            }


def test_masonry_parts_reconcile_hollow_cells_and_mortar(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Hollow unit shells, grout and mortar keep separate materials and native IFC parts."""
    MasonryFixture.configure(reference_model)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    assert resolved.element("masonry.block").data["netVolumeMm3"] == pytest.approx(
        390 * 190 * 200 - 2 * 150 * 130 * 190
    )
    assert resolved.element("masonry.grout").data["netVolumeMm3"] == pytest.approx(
        2 * 150 * 130 * 190
    )
    assert resolved.element("masonry.mortar").data["netVolumeMm3"] == pytest.approx(
        400 * 190 * 10
    )
    cavity = Authoring.object(
        Authoring.array(resolved.element("wall.masonry").data["cavities"])[0]
    )
    assert cavity["infillVolumeMm3"] == 0
    assert cavity["occupiedVolumeMm3"] == pytest.approx(
        390 * 190 * 200 + 400 * 190 * 10
    )
    assert number(cavity["occupiedVolumeMm3"], "occupied") + number(
        cavity["voidVolumeMm3"], "void"
    ) == pytest.approx(400 * 190 * 220)
    source = tmp_path / "masonry.json"
    ModelLoader.write(reference_model, source)
    ifc = ifcopenshell.open(BuildService().build(source, tmp_path / "build").ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert {
        value.IsTypedBy[0].RelatingType.ElementType
        for value in ifc.by_type("IfcBuildingElementPart")
    } == {"unit", "grout", "mortar"}


def test_grout_cannot_overlap_masonry_webs(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """An incorrectly shifted grout shape fails physical ownership validation."""
    MasonryFixture.configure(reference_model)
    grout = Authoring.object(
        Authoring.object(reference_model["elements"])["masonry.grout"]
    )
    grout["placement"] = {"origin": {"point": [220, -4000, 10]}}
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert "owned by both" in str(report.to_dict())
