"""Exercise real image capture, semantic selection and source/output preservation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct

import pytest

from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject
from home_design.visual_render import VisualRenderer


@pytest.fixture
def inspection_model(reference_model: JsonObject, tmp_path: Path) -> Path:
    """Use a minimal public-derived layered wall with no hidden modeling dependencies."""
    source = reference_model
    wall = Authoring.object(Authoring.object(source["elements"])["wall.south"])
    wall["base"] = {"kind": "level", "level": "level.ground", "offset": 0}
    wall["top"] = {"kind": "height", "height": 2700}
    source["elements"] = {"wall.south": wall}
    source["relationships"] = {}
    source["requirements"] = []
    path = tmp_path / "wall.json"
    path.write_text(json.dumps(source) + "\n")
    return path


def test_view_schema_rejects_ambiguous_camera_and_unknown_options(
    tmp_path: Path,
) -> None:
    """Reject conflicting camera conventions and misspelled controls before rendering."""
    for value in (
        {"hideRoof": True},
        {"camera": {"position": [0, 0, 0]}},
        {"camera": {"position": [0, 0, 0], "target": [1, 0, 0], "preset": "top"}},
        {"width": 0},
        {"isolate": {"ids": []}},
    ):
        view = tmp_path / "view.json"
        view.write_text(json.dumps(value))
        with pytest.raises(HomeDesignError, match="Invalid render view"):
            VisualRenderer.view(view)


def test_render_output_does_not_replace_sources_or_unmanaged_files(
    tmp_path: Path,
) -> None:
    """Protect source-containing directories and unrelated existing output content."""
    source = tmp_path / "source.json"
    source.write_text("{}")
    with pytest.raises(ValueError, match="separate"):
        VisualRenderer.check_output(tmp_path, [source])
    output = tmp_path / "output"
    output.mkdir()
    (output / "notes.txt").write_text("Retain these notes")
    with pytest.raises(ValueError, match="previous render"):
        VisualRenderer.check_output(output, [source])
    assert (output / "notes.txt").read_text() == "Retain these notes"


@pytest.mark.integration
@pytest.mark.skipif(
    importlib.util.find_spec("playwright") is None,
    reason="Install the render extra to exercise Chromium capture",
)
def test_real_capture_layer_cutaway_and_failed_view_preserve_source_and_image(
    inspection_model: Path,
    tmp_path: Path,
) -> None:
    """Render actual pixels and distinguish layer visibility from camera occlusion."""
    renderer = VisualRenderer()
    source = inspection_model.read_bytes()
    output = tmp_path / "image"
    view = tmp_path / "view.json"
    view.write_text(
        json.dumps(
            {
                "width": 640,
                "height": 480,
                "camera": {"preset": "top", "projection": "orthographic"},
                "sections": [{"axis": "z", "position": 1200}],
                "isolate": {"layers": [{"elementId": "wall.south", "layerId": 2}]},
            }
        )
    )
    receipt = renderer.render(inspection_model, view, output)
    image = (output / "image.png").read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", image[16:24]) == (640, 480)
    objects = json.loads((output / "objects.json").read_text())
    assert len(objects) == 1
    assert objects[0]["id"] == "wall.south"
    assert objects[0]["pixels"] > 100
    report = json.loads((output / "render.json").read_text())
    assert any("section" in node for node in report["retainedNodes"])
    assert receipt["sourceRevision"] == 1
    assert inspection_model.read_bytes() == source
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    for invalid in (
        {"hide": [{"ids": ["wall.south"]}]},
        {"sections": [{"axis": "z", "position": -1000}]},
        {"isolate": {"ids": ["missing"]}},
    ):
        view.write_text(json.dumps(invalid))
        with pytest.raises(HomeDesignError, match="Visual capture failed"):
            renderer.render(inspection_model, view, output)
        assert {path.name: path.read_bytes() for path in output.iterdir()} == before
        assert inspection_model.read_bytes() == source


@pytest.mark.integration
@pytest.mark.skipif(
    importlib.util.find_spec("playwright") is None,
    reason="Install the render extra to exercise Chromium capture",
)
def test_concealed_member_edges_do_not_show_through_an_opaque_wall(
    inspection_model: Path, tmp_path: Path
) -> None:
    """An angled beauty capture hides stock and its outlines behind opaque finishes."""
    renderer = VisualRenderer()
    view = tmp_path / "angled.json"
    view.write_text(
        json.dumps({"camera": {"preset": "ne"}, "width": 640, "height": 480})
    )
    output = tmp_path / "opaque-wall"
    renderer.render(inspection_model, view, output)
    before = (output / "image.png").read_bytes()
    source = json.loads(inspection_model.read_text())
    source["types"]["type.concealed"] = {
        "kind": "memberType",
        "name": "Concealed stock",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 38, "depth": 38},
    }
    for station in range(1000, 10000, 1000):
        source["elements"][f"member.{station}"] = {
            "kind": "member",
            "name": "Concealed stud",
            "type": "type.concealed",
            "role": "stud",
            "axis": [{"point": [station, 0, 100]}, {"point": [station, 0, 2600]}],
        }
    inspection_model.write_text(json.dumps(source))
    renderer.render(inspection_model, view, output)
    assert (output / "image.png").read_bytes() == before
    objects = json.loads((output / "objects.json").read_text())
    concealed = [item for item in objects if item["id"].startswith("member.")]
    assert len(concealed) == 9
    assert all(item["pixels"] == 0 for item in concealed)
