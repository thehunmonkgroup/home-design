"""Build and exercise a wheel outside the checkout using only its bundled resources."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


class InstalledPackage:
    """Run the package from an isolated extraction with existing runtime dependencies."""

    def __init__(self, root: Path, workspace: Path) -> None:
        """Keep package imports and user outputs outside the source checkout."""
        self.root: Path = root
        self.workspace: Path = workspace

    def run(self, *arguments: str) -> dict[str, object]:
        """Execute a real CLI subprocess and require successful structured output."""
        environment = {**os.environ, "PYTHONPATH": str(self.root)}
        completed = subprocess.run(
            [sys.executable, "-m", "home_design.cli", *arguments],
            cwd=self.workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout)


def test_sdist_wheel_resources_and_guarded_cli_outside_checkout(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    source = tmp_path / "source"
    source.mkdir()
    for name in ("src", "schema", "examples", "docs", "skills", "recipes"):
        shutil.copytree(
            repository / name,
            source / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", "_resources"),
        )
    for name in ("pyproject.toml", "MANIFEST.in", "README.md", "TODO.md"):
        shutil.copyfile(repository / name, source / name)
    distribution = tmp_path / "dist"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(distribution),
        ],
        cwd=source,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheel = next(distribution.glob("*.whl"))
    installed = tmp_path / "installed"
    with zipfile.ZipFile(wheel) as archive:
        assert "home_design-0.1.0.dist-info/entry_points.txt" in archive.namelist()
        archive.extractall(installed)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cli = InstalledPackage(installed, workspace)
    locations = cli.run("resources")
    assert Path(str(locations["root"])).is_relative_to(installed)
    skill = Path(str(locations["skill"]))
    assert (
        skill.read_bytes() == (repository / "skills/home-design/SKILL.md").read_bytes()
    )
    assert (skill.parent / "references/editing.md").is_file()
    examples = Path(str(locations["examples"]))
    assert (examples / "integrated-authoring-house.json").is_file()
    assert (examples / "assemblies.json").is_file()
    assert (skill.parent / "references/catalog.md").is_file()
    assert (Path(str(locations["recipes"])) / "exterior-wall.json").is_file()
    assert (examples / "change-sets/adapt-copied-deck.json").is_file()
    model = workspace / "home.json"
    shutil.copyfile(examples / "single-story-gable-house.json", model)
    assert cli.run("validate", str(model), "--json")["valid"] is True
    assert cli.run("convert-length", "8 ft 6 1/2 in")["millimetres"] == "2603.5"
    change = examples / "change-sets/move-window.json"
    dry = cli.run("transact", str(model), str(change), "--dry-run")
    assert dry["written"] is False
    committed = cli.run("transact", str(model), str(change))
    assert committed["published"] is True
    assert Path(str(committed["ifc"])).is_file()
    recovered = cli.run("recover", str(committed["journal"]))
    assert recovered["revision"] == committed["revision"]
    assert recovered["written"] is False
    assert Path(str(locations["recipes"])).is_dir()
    catalog = cli.run("recipes")["recipes"]
    assert isinstance(catalog, list)
    assert {recipe["id"] for recipe in catalog} == {
        f"recipe.{name}" for name in (
            "serviced-partition", "coordinated-deck", "exterior-wall",
            "insulated-roof", "complete-deck", "insulated-floor",
            "interior-wet-wall", "ventilation-branch", "reinforced-foundation",
            "screened-entrance", "king-post-truss",
        )
    }
    migration = workspace / "migration.json"
    cli.run("migrate", str(model), "--output", str(migration))
    cli.run("transact", str(model), str(migration))
    assembly_change = workspace / "assembly.json"
    cli.run(
        "prepare",
        str(model),
        "instantiate",
        "--object",
        "assembly.packaged",
        "--recipe",
        "serviced-partition",
        "--bind",
        "binding.storey=level.ground",
        "--output",
        str(assembly_change),
    )
    assert cli.run("transact", str(model), str(assembly_change))["published"] is True
    instance = cli.run(
        "inspect", str(model), "--object", "assembly.packaged", "--view", "assembly"
    )
    assert "assembly" in instance
