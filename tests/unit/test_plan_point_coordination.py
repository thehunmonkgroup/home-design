"""Literal and anchored plan points share coordinates without weakening legacy schemas."""

from __future__ import annotations

import pytest

from home_design.errors import ResolutionError
from home_design.json_types import JsonObject, JsonValue
from home_design.locators import LocatorResolver


@pytest.mark.parametrize(
    "value,expected",
    [
        ([100, 200], (100, 200)),
        ({"point": [100, 200]}, (100, 200)),
        ({"anchor": "origin"}, (1000, 2000)),
        ({"anchor": "origin", "offset": [100, -200]}, (1100, 1800)),
        ({"anchor": "spatial", "offset": [100, -200]}, (3100, 3800)),
    ],
)
def test_plan_points_resolve_literal_and_shared_origins(
    value: JsonValue, expected: tuple[float, float]
) -> None:
    """Plan sampling uses model XY and discards a spatial anchor's elevation."""
    source: JsonObject = {
        "anchors": {
            "origin": {"kind": "point2", "position": [1000, 2000]},
            "spatial": {"kind": "point3", "position": [3000, 4000, 5000]},
        }
    }
    assert LocatorResolver(source).plan_point(value) == expected


@pytest.mark.parametrize(
    "value", [{"anchor": "absent"}, [1, 2, 3], {"point": [1, 2, 3]}]
)
def test_plan_points_reject_unknown_anchors_and_malformed_coordinates(
    value: JsonValue,
) -> None:
    """New locator support retains explicit validation of missing and incompatible points."""
    with pytest.raises(ResolutionError):
        LocatorResolver({}).plan_point(value)
