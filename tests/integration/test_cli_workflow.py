"""Integration tests for the supported AI and end-user CLI workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from home_design.cli import main
from home_design.resolver import ModelResolver


def test_migration_cli_prepares_a_guarded_changeset_without_writing_source(
    model_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Version migration uses the same preview and transaction interface as ordinary edits."""
    original = model_file.read_bytes()
    change_path = tmp_path / "migration.json"
    assert main(["migrate", str(model_file), "--output", str(change_path)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    change = json.loads(change_path.read_text())
    assert receipt["change"] == str(change_path)
    assert receipt["operationCount"] == len(change["operations"])
    assert model_file.read_bytes() == original
    assert main(["transact", str(model_file), str(change_path), "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["revision"] == json.loads(original)["revision"] + 1
    assert model_file.read_bytes() == original
    assert main(["migrate", str(model_file), "--output", str(model_file)]) == 1
    assert "must be separate" in capsys.readouterr().err
    assert model_file.read_bytes() == original
    assert main(["migrate", str(model_file), "--to", "0.3"]) == 1
    assert (
        json.loads(capsys.readouterr().err)["error"]["code"]
        == "migration.unsupported-transition"
    )


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


def test_source_inspection_repairs_invalid_models_without_geometry(
    model_file: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authors can discover a broken type and its source path without a build."""
    model = json.loads(model_file.read_text())
    model["elements"]["window.north"]["type"] = "type.missing"
    model_file.write_text(json.dumps(model))

    def reject_resolution(_self: ModelResolver) -> None:
        raise AssertionError("Source inspection must not resolve geometry")

    monkeypatch.setattr(ModelResolver, "resolve", reject_resolution)
    assert (
        main(
            [
                "inspect",
                str(model_file),
                "--object",
                "window.north",
                "--references",
                "--field",
                "/type",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["fields"] == {"/type": "type.missing"}
    assert output["outgoing"]["items"][0]["targetExists"] is False
    assert "meshes" not in output
    assert (
        main(
            [
                "inspect",
                str(model_file),
                "--registry",
                "types",
                "--kind",
                "wallType",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["objects"][0]["kind"] == "wallType"


def test_resolved_inspection_omits_meshes_unless_requested(
    model_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Measurement review is compact while explicit geometry access is retained."""
    arguments = [
        "inspect",
        str(model_file),
        "--object",
        "wall.north",
        "--view",
        "resolved",
    ]
    assert main(arguments) == 0
    compact = json.loads(capsys.readouterr().out)
    assert compact["data"]["thickness"] > 0
    assert compact["geometry"]["meshCount"] > 0
    assert "meshes" not in compact
    assert main([*arguments, "--meshes"]) == 0
    detailed = json.loads(capsys.readouterr().out)
    assert detailed["meshes"][0]["vertices"]
    assert compact["data"] == detailed["data"]


def test_inspection_rejects_inapplicable_options(
    model_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Incorrect query combinations receive actionable errors."""
    assert main(["inspect", str(model_file), "--references"]) == 1
    assert "--object ID" in capsys.readouterr().err
    wall_type = json.loads(model_file.read_text())["elements"]["wall.north"]["type"]
    assert (
        main(["inspect", str(model_file), "--object", wall_type, "--view", "resolved"])
        == 1
    )
    assert "requires an element" in capsys.readouterr().err


def test_prepare_preview_and_structured_conflict_workflow(
    model_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An AI can prepare a local edit, review propagation and identify a stale revision."""
    original = model_file.read_bytes()
    change_path = tmp_path / "local-window.json"
    report_path = tmp_path / "preview.json"
    assert (
        main(
            [
                "prepare",
                str(model_file),
                "local-type",
                "--object",
                "window.north",
                "--new-type",
                "windowType.local",
                "--set",
                "/nominalWidth=1400",
                "--output",
                str(change_path),
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    change = json.loads(change_path.read_text())
    assert receipt["change"] == str(change_path)
    assert receipt["operationCount"] == len(change["operations"])
    assert (
        main(
            ["preview", str(model_file), str(change_path), "--output", str(report_path)]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["report"] == str(report_path)
    assert summary["summary"] is True
    assert "items" not in summary["resolvedChanges"]
    preview = json.loads(report_path.read_text())
    assert preview["valid"] is True
    assert preview["written"] is False
    assert preview["resolvedChanges"]["items"][0]["id"] == "window.north"
    assert summary["resolvedChanges"]["total"] == preview["resolvedChanges"]["total"]
    assert model_file.read_bytes() == original
    change["baseRevision"] += 1
    change_path.write_text(json.dumps(change))
    assert main(["preview", str(model_file), str(change_path)]) == 1
    failure = json.loads(capsys.readouterr().err)
    assert failure["error"]["code"] == "change.revision-conflict"
    assert failure["error"]["path"] == "/revision"
    assert model_file.read_bytes() == original
