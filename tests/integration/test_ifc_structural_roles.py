"""Native structural function and stock identities across reusable IFC type variants."""

from __future__ import annotations

import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.ifc import IfcExporter
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


@pytest.mark.parametrize(
    "role,native,predefined",
    [
        ("beam", "IfcBeam", "BEAM"),
        ("column", "IfcColumn", "COLUMN"),
        ("joist", "IfcBeam", "JOIST"),
        ("rafter", "IfcMember", "RAFTER"),
        ("stud", "IfcMember", "STUD"),
        ("decking", "IfcMember", "USERDEFINED"),
        ("stringer", "IfcMember", "STRINGER"),
        ("brace", "IfcMember", "BRACE"),
        ("other", "IfcMember", "USERDEFINED"),
    ],
)
def test_native_member_types_match_authored_occurrence_function(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    role: str,
    native: str,
    predefined: str,
) -> None:
    """Two occurrences reuse one matching role type and retain the original canonical stock ID."""
    (
        reference_model["relationships"],
        reference_model["requirements"],
        reference_model["solarStudies"],
    ) = ({}, [], [])
    Authoring.object(reference_model["types"])["type.stock"] = {
        "kind": "memberType",
        "name": "Reusable structural stock",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 100, "depth": 100},
    }
    reference_model["elements"] = {
        f"member.{key}": {
            "kind": "member",
            "name": key,
            "role": role,
            "type": "type.stock",
            "axis": [{"point": [offset, 0, 0]}, {"point": [offset, 0, 1000]}],
        }
        for key, offset in (("first", 0), ("second", 200))
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    path = tmp_path / "structural.ifc"
    IfcExporter().export(resolved, path)
    model = ifcopenshell.open(path)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger)
    assert not logger.statements
    first = model.by_guid(IfcExporter.stable_guid("member.first"))
    second = model.by_guid(IfcExporter.stable_guid("member.second"))
    assert first.is_a(native) and second.is_a(native)
    stock_type = first.IsTypedBy[0].RelatingType
    assert stock_type == second.IsTypedBy[0].RelatingType
    assert stock_type.is_a(native + "Type")
    assert stock_type.PredefinedType == predefined
    assert ifcopenshell.util.element.get_predefined_type(first) == (
        role if predefined == "USERDEFINED" else predefined
    )
    assert stock_type.ElementType == role
    properties = ifcopenshell.util.element.get_psets(stock_type)["Pset_HomeDesignType"]
    assert properties["canonicalTypeId"] == "type.stock"
    assert properties["constructionRole"] == role
    assert json.loads(properties["section"]) == {
        "kind": "rectangle",
        "width": 100,
        "depth": 100,
    }
    material = ifcopenshell.util.element.get_material(first)
    assert material is not None and material.Name == "Framing timber"
    quantities = ifcopenshell.util.element.get_psets(first, qtos_only=True)[
        f"Qto_{native.removeprefix('Ifc')}BaseQuantities"
    ]
    assert quantities["Length"] == 1000
    assert quantities["CrossSectionArea"] == pytest.approx(0.01)
    assert quantities["NetVolume"] == pytest.approx(0.01)
    identities = {item.GlobalId for item in model.by_type("IfcRoot")}
    IfcExporter().export(resolved, path)
    assert {
        item.GlobalId for item in ifcopenshell.open(path).by_type("IfcRoot")
    } == identities
