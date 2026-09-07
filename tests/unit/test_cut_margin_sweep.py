"""Directional reserve geometry preserves concave stock and through-holes."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from home_design.cut_limits import CutLimits
from home_design.geometry import extrude_polygon


def test_translation_sweep_preserves_l_shaped_stock_concavity() -> None:
    """Sweeping a concave section does not substitute its enclosing convex hull."""
    stock = extrude_polygon(
        Polygon([(0, 0), (100, 0), (100, 40), (40, 40), (40, 100), (0, 100)]),
        0,
        10,
        None,
        "test",
    )
    assert CutLimits.sweep(stock, (0, 0, 20)).volume() == pytest.approx(6400 * 30)
    assert CutLimits.sweep(stock, (20, 0, 0)).volume() == pytest.approx(8400 * 10)


def test_translation_sweep_retains_the_unswept_portion_of_an_internal_hole() -> None:
    """A ten-millimetre sweep reduces a sixty-millimetre passage instead of filling it entirely."""
    stock = extrude_polygon(
        Polygon(
            [(-50, -50), (50, -50), (50, 50), (-50, 50)],
            holes=[[(-30, -30), (-30, 30), (30, 30), (30, -30)]],
        ),
        0,
        10,
        None,
        "test",
    )
    assert CutLimits.sweep(stock, (10, 0, 0)).volume() == pytest.approx(
        (110 * 100 - 50 * 60) * 10
    )
