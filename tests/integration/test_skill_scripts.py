"""Integration tests for the guarded home-design skill scripts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TRANSACTION_SCRIPT = (
    ROOT / "skills" / "home-design" / "scripts" / "design_transaction.py"
)
CONVERSION_SCRIPT = ROOT / "skills" / "home-design" / "scripts" / "convert_length.py"
CHANGE_EXAMPLE = ROOT / "examples" / "change-sets" / "move-window.json"


def run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run one project skill script in its real command-line boundary.

    :param script: Script entry point.
    :param arguments: Command-line arguments.
    :return: Completed child process.
    """
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.integration
def test_transaction_dry_run_validates_without_writing_or_building(
    model_file: Path,
    tmp_path: Path,
) -> None:
    original = model_file.read_bytes()
    source_revision = json.loads(original)["revision"]
    build_directory = tmp_path / "build"
    result = run_script(
        TRANSACTION_SCRIPT,
        str(model_file),
        str(CHANGE_EXAMPLE),
        "--build-directory",
        str(build_directory),
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "valid": True,
        "revision": source_revision + 1,
        "written": False,
        "buildDirectory": None,
        "ifc": None,
        "viewerModel": None,
    }
    assert model_file.read_bytes() == original
    assert not build_directory.exists()


@pytest.mark.integration
def test_transaction_commit_writes_revision_and_all_adapter_outputs(
    model_file: Path,
    tmp_path: Path,
) -> None:
    output_model = tmp_path / "home-next-revision.json"
    build_directory = tmp_path / "build"
    web_assets = tmp_path / "viewer-model"
    source_revision = json.loads(model_file.read_text(encoding="utf-8"))["revision"]
    result = run_script(
        TRANSACTION_SCRIPT,
        str(model_file),
        str(CHANGE_EXAMPLE),
        "--output",
        str(output_model),
        "--build-directory",
        str(build_directory),
        "--web-assets",
        str(web_assets),
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["valid"] is True
    assert report["revision"] == source_revision + 1
    assert report["written"] is True
    assert (
        json.loads(output_model.read_text(encoding="utf-8"))["revision"]
        == source_revision + 1
    )
    model_directory = build_directory / output_model.stem
    assert report["buildDirectory"] == str(model_directory)
    assert Path(report["ifc"]).is_file()
    assert {path.name for path in model_directory.iterdir()} == {
        "build-metadata.json",
        "diagnostics.json",
        "model.glb",
        "model.ifc",
        "render-manifest.json",
        "resolved-model.json",
        "schedules.json",
        "envelope.json",
        "drawings.svg",
    }
    catalog = json.loads((web_assets / "index.json").read_text())
    browser_directory = web_assets / catalog["models"][0]["baseUrl"]
    assert {path.name for path in browser_directory.iterdir()} == {
        "model.glb",
        "render-manifest.json",
        "schedules.json",
        "envelope.json",
        "drawings.svg",
    }


@pytest.mark.integration
def test_transaction_conflict_preserves_model_and_skips_outputs(
    model_file: Path,
    tmp_path: Path,
) -> None:
    change = json.loads(CHANGE_EXAMPLE.read_text(encoding="utf-8"))
    change["baseRevision"] = 99
    stale_change = tmp_path / "stale-change.json"
    stale_change.write_text(json.dumps(change), encoding="utf-8")
    original = model_file.read_bytes()
    build_directory = tmp_path / "build"
    result = run_script(
        TRANSACTION_SCRIPT,
        str(model_file),
        str(stale_change),
        "--build-directory",
        str(build_directory),
    )

    assert result.returncode == 1
    assert "expects revision 99" in result.stderr
    assert model_file.read_bytes() == original
    assert not build_directory.exists()


@pytest.mark.integration
def test_conversion_script_emits_canonical_millimetres() -> None:
    result = run_script(CONVERSION_SCRIPT, "8 ft 6 1/2 in", "--to", "mm")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "input": "8 ft 6 1/2 in",
        "millimetres": "2603.5",
        "targetUnit": "mm",
        "value": "2603.5",
    }
