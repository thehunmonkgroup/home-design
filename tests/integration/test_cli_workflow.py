"""Integration tests for the supported AI and end-user CLI workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from home_design.cli import main


@pytest.mark.integration
def test_validate_inspect_apply_build_workflow(
    model_file: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["validate", str(model_file), "--json"]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["valid"] is True

    assert (
        main(["inspect", str(model_file), "--element", "wall.north", "--relationships"])
        == 0
    )
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["id"] == "wall.north"
    assert len(inspected["relationships"]) >= 3

    change_path = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "change-sets"
        / "move-window.json"
    )
    source_revision = json.loads(model_file.read_text(encoding="utf-8"))["revision"]
    next_model = tmp_path / "next.json"
    assert (
        main(["apply", str(model_file), str(change_path), "--output", str(next_model)])
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["nextRevision"] == source_revision + 1

    output = tmp_path / "artifacts"
    web_assets = tmp_path / "public" / "model"
    assert (
        main(
            [
                "build",
                str(next_model),
                "--output",
                str(output),
                "--web-assets",
                str(web_assets),
            ]
        )
        == 0
    )
    built = json.loads(capsys.readouterr().out)
    assert len(built["models"]) == 1
    assert len(built["models"][0]["artifacts"]) == 9
    catalog = json.loads((web_assets / "index.json").read_text())
    assert (web_assets / catalog["models"][0]["baseUrl"] / "model.glb").is_file()


@pytest.mark.integration
def test_cli_returns_nonzero_for_invalid_model(
    model_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model = json.loads(model_file.read_text(encoding="utf-8"))
    model["elements"]["opening.window.north"]["placement"]["station"] = 20000
    model_file.write_text(json.dumps(model), encoding="utf-8")
    assert main(["validate", str(model_file)]) == 1
    output = capsys.readouterr().out
    assert "opening.outside-host-path" in output
