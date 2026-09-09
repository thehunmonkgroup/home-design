"""Static website export isolation, replacement, and failure handling."""

from __future__ import annotations

import gzip
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil
import subprocess
from threading import Thread
from urllib.request import urlopen
from unittest.mock import Mock

import pytest

from home_design.cli import main
from home_design.errors import HomeDesignError
from home_design.website import DEFAULT_WEB_PROJECT, EXPORT_MARKER, WebsiteExporter


@pytest.fixture
def web_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a static build stand-in while exercising real model exports."""
    project = tmp_path / "web"
    vite = project / "node_modules/vite/bin/vite.js"
    vite.parent.mkdir(parents=True)
    vite.touch()
    (project / "index.html").write_text("viewer source")
    preview = project / "public/model"
    preview.mkdir(parents=True)
    (preview / "not-selected.json").write_text("local preview must stay untouched")
    (project / "public/private-note.txt").write_text("not for export")
    monkeypatch.setattr("home_design.website.shutil.which", Mock(return_value="/usr/bin/npm"))

    def build(_npm: str, _project: Path, public: Path, site: Path) -> None:
        shutil.copytree(public, site)
        (site / "index.html").write_text('<script src="./assets/viewer.js"></script>')
        (site / "assets").mkdir()
        (site / "assets/viewer.js").write_text("viewer bundle")

    monkeypatch.setattr(WebsiteExporter, "_build_viewer", staticmethod(build))
    return project


def test_export_selected_collection_and_replace(
    model_file: Path, web_project: Path, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    second = tmp_path / "second.json"
    second.write_bytes(model_file.read_bytes())
    before = model_file.read_bytes()
    output = tmp_path / "website"
    assert main([
        "website-export", str(tmp_path / "*.json"), "--output", str(output),
        "--web-project", str(web_project),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["output"] == str(output)
    assert {entry["key"] for entry in result["models"]} == {"home", "second"}
    catalog = json.loads((output / "model/index.json").read_text())
    for entry in catalog["models"]:
        files = output / "model" / entry["baseUrl"]
        assert {path.name for path in files.iterdir()} == {
            "model.glb", "render-manifest.json", "drawings.svg",
            "schedules.json", "envelope.json",
            "model.glb.gz", "render-manifest.json.gz",
        }
        for name, size in entry["compressedAssets"].items():
            compressed = (files / f"{name}.gz").read_bytes()
            assert len(compressed) == size
            assert gzip.decompress(compressed) == (files / name).read_bytes()
    assert not list(output.rglob("*.ifc"))
    assert not list(output.rglob("private-note.txt"))
    assert not list(output.rglob("not-selected.json"))
    assert not list(output.rglob("resolved-model.json"))
    (output / "stale.txt").write_text("disposable")
    WebsiteExporter().export([model_file], output, web_project)
    assert not (output / "model/second").exists()
    assert not (output / "stale.txt").exists()
    assert (output / EXPORT_MARKER).is_file()
    assert model_file.read_bytes() == before
    assert (web_project / "public/model/not-selected.json").read_text().startswith("local")
    assert (web_project / "public/private-note.txt").is_file()
    assert not list(tmp_path.glob("home-design-website-*"))


def test_build_failures_preserve_previous_export(
    model_file: Path, web_project: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = WebsiteExporter()
    output = tmp_path / "website"
    exporter.export([model_file], output, web_project)
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}

    def broken_build(*_args: object) -> None:
        raise HomeDesignError("Viewer build failed")

    monkeypatch.setattr(WebsiteExporter, "_build_viewer", staticmethod(broken_build))
    with pytest.raises(HomeDesignError, match="Viewer build failed"):
        exporter.export([model_file], output, web_project)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}")
    with pytest.raises(HomeDesignError):
        exporter.export([invalid], output, web_project)
    assert before == {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    assert not list(tmp_path.glob("home-design-website-*"))


def test_export_rejects_unsafe_destinations(
    model_file: Path, web_project: Path, tmp_path: Path,
) -> None:
    exporter = WebsiteExporter()
    occupied = tmp_path / "notes"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("keep")
    link = tmp_path / "link"
    link.symlink_to(occupied, target_is_directory=True)
    for output in [tmp_path, model_file, web_project, web_project / "dist", occupied, link]:
        with pytest.raises(ValueError):
            exporter.export([model_file], output, web_project)
    assert (occupied / "keep.txt").read_text() == "keep"


def test_missing_dependencies_and_cli_failure(
    model_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([
        "website-export", str(model_file), "--output", str(tmp_path / "website"),
        "--web-project", str(tmp_path / "missing-web"),
    ]) == 1
    result = capsys.readouterr()
    assert not result.out
    assert "npm ci" in result.err
    assert not (tmp_path / "website").exists()


def test_install_failure_restores_previous_export(
    model_file: Path, web_project: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "website"
    exporter = WebsiteExporter()
    exporter.export([model_file], output, web_project)
    before = (output / "model/index.json").read_bytes()
    rename = Path.rename

    def fail_install(path: Path, target: Path) -> Path:
        if path.name == "site" and target == output:
            raise OSError("install failed")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_install)
    with pytest.raises(OSError, match="install failed"):
        exporter.export([model_file], output, web_project)
    assert (output / "index.html").exists()
    assert (output / "model/index.json").read_bytes() == before


def test_viewer_subprocess_uses_isolated_public_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr("home_design.website.subprocess.run", runner)
    project, public, site = tmp_path / "web", tmp_path / "public", tmp_path / "site"
    build_viewer = getattr(WebsiteExporter, "_build_viewer")
    build_viewer("npm", project, public, site)
    assert runner.call_args.args[0] == ["npm", "run", "build", "--", "--outDir", str(site), "--emptyOutDir"]
    assert runner.call_args.kwargs["cwd"] == project
    assert runner.call_args.kwargs["env"]["HOME_DESIGN_PUBLIC_DIR"] == str(public)
    runner.return_value = subprocess.CompletedProcess([], 1)
    with pytest.raises(HomeDesignError, match="exit 1"):
        build_viewer("npm", project, public, site)


@pytest.mark.skipif(
    not shutil.which("npm")
    or not (DEFAULT_WEB_PROJECT / "node_modules/vite/bin/vite.js").is_file(),
    reason="Full website integration requires npm ci in web/",
)
def test_real_static_build_serves_from_subdirectory(model_file: Path, tmp_path: Path) -> None:
    """Serve an actual export using only a standard static HTTP server."""
    output = tmp_path / "published/homes"
    WebsiteExporter().export([model_file], output)
    catalog = json.loads((output / "model/index.json").read_text())
    assert [entry["key"] for entry in catalog["models"]] == ["home"]
    assert {path.name for path in output.iterdir()} == {
        "index.html", "assets", "model", EXPORT_MARKER,
    }
    handler = partial(SimpleHTTPRequestHandler, directory=str(output.parent))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}/homes/"
        with urlopen(origin, timeout=5) as response:
            html = response.read().decode()
        for asset in re.findall(r'(?:src|href)="([^"]+)"', html):
            assert asset.startswith("./assets/")
            with urlopen(origin + asset, timeout=5) as response:
                assert response.status == 200
                assert response.read()
        with urlopen(origin + "model/index.json", timeout=5) as response:
            assert json.load(response) == catalog
        entry = catalog["models"][0]
        for artifact in ["model.glb", "render-manifest.json", "drawings.svg", "schedules.json", "envelope.json", "model.glb.gz", "render-manifest.json.gz"]:
            with urlopen(origin + "model/" + entry["baseUrl"] + artifact, timeout=5) as response:
                assert response.status == 200
                assert response.read()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
