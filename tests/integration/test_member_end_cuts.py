"""Authored square and beveled end treatments across members, arrays and layouts."""

from __future__ import annotations

import math

import pytest

from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class CutFixture:
    """Provide stock with analytic cut volumes."""

    @staticmethod
    def configure(model: JsonObject) -> JsonObject:
        """Use a square vertical member located away from the reference house."""
        Authoring.object(model["types"])["type.cutStock"] = {
            "kind": "memberType",
            "name": "Cut stock",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 100, "depth": 100},
        }
        source: JsonObject = {
            "kind": "member",
            "name": "Cut member",
            "type": "type.cutStock",
            "role": "other",
            "axis": [{"point": [0, -2000, 0]}, {"point": [0, -2000, 1000]}],
            "endCuts": {
                "start": {"normal": [0, 0, 1], "offset": 100},
                "end": {"normal": [0, 0, -1], "offset": 200},
            },
        }
        Authoring.object(model["elements"])["member.cut"] = source
        return source


def test_end_offsets_cut_real_stock_and_preserve_nominal_length(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Start and end setbacks remove exactly the specified end volumes."""
    source = CutFixture.configure(reference_model)
    assert validator.validate(reference_model).is_valid
    member = ModelResolver(reference_model).resolve().element("member.cut")
    assert SolidOperations.volume(member.meshes[0]) == pytest.approx(700 * 100 * 100)
    assert member.data["memberLength"] == 1000
    assert member.data["endCuts"] == source["endCuts"]
    source.update(
        {
            "kind": "framing",
            "role": "joist",
            "distribution": [1, 0, 0],
            "spacing": 200,
            "count": 3,
        }
    )
    assert validator.validate(reference_model).is_valid
    framing = ModelResolver(reference_model).resolve().element("member.cut")
    assert all(
        SolidOperations.volume(mesh) == pytest.approx(7000000)
        for mesh in framing.meshes
    )


def test_beveled_end_retains_analytic_wedge_volume(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """An inclined start plane makes a bevel instead of shortening a bounding box."""
    source = CutFixture.configure(reference_model)
    source["endCuts"] = {"start": {"normal": [math.sqrt(0.5), 0, math.sqrt(0.5)]}}
    assert validator.validate(reference_model).is_valid
    mesh = ModelResolver(reference_model).resolve().element("member.cut").meshes[0]
    assert SolidOperations.volume(mesh) == pytest.approx(10000000 - 50 * 50 * 100 / 2)


@pytest.mark.parametrize(
    "cut",
    [
        {"normal": [0, 0, -1]},
        {"normal": [0, 0, 0.5]},
        {"normal": [0, 0, 1], "offset": 1200},
    ],
)
def test_invalid_end_cut_is_a_diagnostic(
    reference_model: JsonObject, validator: ModelValidator, cut: JsonObject
) -> None:
    """Outward normals, non-unit normals and complete removal fail before export."""
    source = CutFixture.configure(reference_model)
    source["endCuts"] = {"start": cut}
    assert not validator.validate(reference_model).is_valid
