"""Typed stock, layer, port and quantity boundary behavior."""

from __future__ import annotations

import pytest

from home_design.errors import ResolutionError
from home_design.json_types import JsonObject
from home_design.layers import LayerAssembly
from home_design.part_contracts import GeneratedMember
from home_design.port_contracts import ResolvedPort
from home_design.quantities import Quantity


def test_dimensioned_quantities_convert_without_crossing_dimensions() -> None:
    assert Quantity(2500, "mm").in_unit("m").value == 2.5
    assert Quantity(2_500_000, "mm2").in_unit("m2").value == 2.5
    assert Quantity(2_500_000_000, "mm3").in_unit("m3").value == 2.5
    with pytest.raises(ResolutionError, match="Cannot convert"):
        Quantity(2500, "mm").in_unit("m3")
    with pytest.raises(ResolutionError, match="finite"):
        Quantity(float("nan"), "mm")


def test_cut_quantity_update_preserves_stock_identity_and_supplementary_intent() -> (
    None
):
    source: JsonObject = {
        "key": "stud.example",
        "typeId": "memberType.example",
        "role": "stud",
        "axis": [[0, 0, 0], [0, 0, 1000]],
        "sectionFrame": {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]},
        "section": {"kind": "rectangle", "width": 50, "depth": 100},
        "lengthMm": 1000,
        "stockLengthMm": 1000,
        "netVolumeMm3": 5_000_000,
        "endCuts": {"start": {"normal": [0, 0, 1]}},
        "properties": {"supplierNote": "Retain this detail"},
    }
    member = GeneratedMember.from_dict(source)
    cut = member.with_volume(4_000_000)
    result = cut.to_dict()
    assert result == {**source, "netVolumeMm3": 4_000_000}
    assert member.net_volume.in_unit("m3").value == 0.005
    assert cut.net_volume.in_unit("m3").value == 0.004
    assert cut.stock_length.value == 1000


def test_layer_contract_preserves_one_thickness_for_concurrent_materials() -> None:
    layers = LayerAssembly.layers(
        {
            "layers": [
                {
                    "thickness": 140,
                    "name": "Framed cavity",
                    "function": "structure",
                    "components": [
                        {"material": "material.timber", "fraction": 0.1},
                        {"material": "material.infill", "fraction": 0.9},
                    ],
                }
            ]
        }
    )
    assert layers[0].thickness == 140
    assert layers[0].material == "material.infill"
    assert [(share.material_id, share.fraction) for share in layers[0].components] == [
        ("material.timber", 0.1),
        ("material.infill", 0.9),
    ]
    with pytest.raises(ResolutionError, match="sum to one"):
        LayerAssembly.layers({"layers": [{"thickness": 140, "components": []}]})


def test_resolved_port_retains_oriented_interface_and_network_metadata() -> None:
    source: JsonObject = {
        "frame": {
            "origin": [50, 60, 70],
            "x": [0, 1, 0],
            "y": [0, 0, 1],
            "z": [1, 0, 0],
        },
        "section": {"kind": "rectangle", "width": 100, "height": 50},
        "medium": "air",
        "flow": "source",
        "connectionType": "flange",
        "systemId": "system.supply",
        "state": "connected",
    }
    port = ResolvedPort.from_dict(source)
    assert port.frame.point((10, 20, 30)) == (80, 70, 90)
    assert port.section.width.in_unit("m").value == 0.1
    assert port.source["systemId"] == "system.supply"
    source["flow"] = "unknown"
    with pytest.raises(ResolutionError, match="Unsupported service port flow"):
        ResolvedPort.from_dict(source)
