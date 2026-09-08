"""Check transient material sections independently of browser rasterization."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from home_design.geometry import extrude_polygon
from home_design.render_sections import RenderSections


def test_section_caps_preserve_holes_material_area_and_orientation() -> None:
    """A pipe-like stock section retains its bore and both keep-side orientations."""
    polygon = Polygon(
        [(0, 0), (100, 0), (100, 100), (0, 100)],
        [[(20, 20), (80, 20), (80, 80), (20, 80)]],
    )
    mesh = extrude_polygon(polygon, 0, 1000, "concrete", "layer:0")
    for below in (True, False):
        caps = RenderSections.caps(mesh, ((2, 500, below),))
        assert len(caps) == 1
        cap = caps[0]
        area = 0.0
        for face in cap.faces:
            a, b, c = [cap.vertices[index] for index in face]
            signed = ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2
            assert (signed > 0) == below
            area += abs(signed)
            assert not Polygon([(20, 20), (80, 20), (80, 80), (20, 80)]).contains(
                Polygon(
                    [(a[0], a[1]), (b[0], b[1]), (c[0], c[1])]
                ).representative_point()
            )
        assert area == pytest.approx(6400)
        assert cap.material_id == "concrete"
        assert cap.role == "layer:0"
    assert RenderSections.caps(mesh, ((2, 1100, True),)) == ()
