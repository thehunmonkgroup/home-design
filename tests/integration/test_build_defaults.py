"""Exercise CLI output defaults and workspace-local viewer publication."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from home_design.cli import HomeDesignCli, main


class ViewerWorkspace:
    """Create minimal viewer markers without generated assets or dependencies."""

    @staticmethod
    def create(path: Path) -> Path:
        """Return a source viewer directory recognized by workspace discovery."""
        path.mkdir(parents=True)
        (path / "package.json").write_text('{"name": "home-design-viewer"}')
        (path / "index.html").write_text("<!doctype html>")
        return path


@pytest.mark.parametrize("location", [".", "design/nested", "web", "web/app"])
def test_discovery_from_workspace_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    """Nested design and viewer directories find the same local asset root."""
    viewer = ViewerWorkspace.create(tmp_path / "web")
    working = tmp_path / location
    working.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(working)
    assert HomeDesignCli.discover_web_assets() == viewer / "public/model"


def test_discovery_uses_nearest_viewer_and_ignores_unrelated_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid package markers cannot divert publication from a real ancestor viewer."""
    outer = ViewerWorkspace.create(tmp_path / "web")
    inner = ViewerWorkspace.create(tmp_path / "nested/web")
    monkeypatch.chdir(inner.parent)
    assert HomeDesignCli.discover_web_assets() == inner / "public/model"
    for metadata in ('{"name": "another-app"}', "invalid json", "[]"):
        (inner / "package.json").write_text(metadata)
        assert HomeDesignCli.discover_web_assets() == outer / "public/model"


@pytest.mark.parametrize("publication", ["discover", "explicit", "disabled", "absent"])
def test_build_defaults_publish_only_to_the_selected_workspace(
    model_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    publication: str,
) -> None:
    """Real builds use the source stem, honor overrides, and work without a viewer."""
    if publication != "absent":
        ViewerWorkspace.create(tmp_path / "web")
    monkeypatch.chdir(tmp_path)
    arguments = ["build", str(model_file)]
    expected_assets = tmp_path / "web/public/model"
    expected_output = tmp_path / "build/home"
    if publication == "explicit":
        arguments.extend(["--web-assets", "custom-assets", "--output", "custom-build"])
        expected_assets = tmp_path / "custom-assets"
        expected_output = tmp_path / "custom-build/home"
    elif publication == "disabled":
        arguments.append("--no-web-assets")
    assert main(arguments) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["models"][0]["output"] == str(expected_output)
    assert (expected_output / "model.ifc").is_file()
    assert (expected_output / "model.glb").is_file()
    if publication in ("discover", "explicit"):
        catalog = json.loads((expected_assets / "index.json").read_text())
        assert catalog["models"][0]["key"] == "home"
        assert receipt["publication"]["added"] == ["home"]
    else:
        assert receipt["publication"] is None
        assert not expected_assets.exists()
    if publication == "explicit":
        assert not (tmp_path / "web/public/model").exists()


def test_build_rejects_conflicting_publication_options() -> None:
    """An opt-out cannot silently override an explicit publication request."""
    with pytest.raises(SystemExit) as error:
        main(["build", "home.json", "--web-assets", "web", "--no-web-assets"])
    assert error.value.code == 2
