"""Batch CLI, replacement, and failure isolation using public reference models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import unquote

import pytest

from home_design.batch import ModelBatch
from home_design.build import BuildService
from home_design.cli import main
from home_design.errors import ModelValidationError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.publication import ModelPublisher
from home_design.resolved import ResolvedModel


def test_globs_literals_deduplication_and_input_errors(tmp_path: Path) -> None:
    for name in ("z.json", "a.json", "literal[1].json"):
        (tmp_path / name).write_text("{}")
    paths = ModelBatch.expand([str(tmp_path / "*.json"), str(tmp_path / "a.json")])
    assert [path.name for path in paths] == ["a.json", "literal[1].json", "z.json"]
    assert ModelBatch.expand([str(tmp_path / "literal[1].json")])[0].is_file()
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.json").write_text("{}")
    assert len(ModelBatch.expand([str(tmp_path / "**/*.json")])) == 4
    with pytest.raises(ValueError, match="No model files match"):
        ModelBatch.expand([str(tmp_path / "absent*.json")])
    with pytest.raises(ValueError, match="not a file"):
        ModelBatch.expand([str(nested)])


def test_validation_reports_every_input(
    model_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("not JSON")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}")
    assert main(["validate", str(model_file), str(broken), str(invalid), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is False
    assert [entry["valid"] for entry in report["models"]] == [True, False, False]
    assert report["models"][1]["diagnostics"][0]["code"] == "model.load"
    assert main(["validate", str(model_file), "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["models"]) == 1


def test_build_cli_glob_and_stem_replacement(
    model_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path / "other.json"
    other.write_bytes(model_file.read_bytes())
    output, web = tmp_path / "out", tmp_path / "web"
    assert (
        main(
            [
                "build",
                str(tmp_path / "*.json"),
                "--output",
                str(output),
                "--web-assets",
                str(web),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert [entry["key"] for entry in report["models"]] == ["home", "other"]
    assert report["publication"]["added"] == ["home", "other"]
    stale = output / "home" / "stale-artifact.txt"
    stale.write_text("disposable")
    unrelated = output / "notes.txt"
    unrelated.write_text("keep")
    BuildService().build(model_file, output, web)
    assert not stale.exists()
    assert unrelated.read_text() == "keep"
    assert (output / "other" / "model.ifc").exists()
    catalog = json.loads((web / "index.json").read_text())
    assert len(catalog["models"]) == 2
    assert not (web / ".home-design-publish.lock").exists()


def test_same_stem_last_input_wins(
    model_file: Path, tmp_path: Path, reference_model: JsonObject
) -> None:
    other = tmp_path / "other" / "home.json"
    reference_model["revision"] = 8
    ModelLoader.write(reference_model, other)
    result = BuildService().build_many([model_file, other], tmp_path / "out")
    assert len(result.models) == 1
    assert (
        json.loads(result.models[0].render_manifest.read_text())["sourceRevision"] == 8
    )


def test_invalid_batch_and_export_failure_preserve_published_outputs(
    model_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = BuildService()
    output, web = tmp_path / "out", tmp_path / "web"
    original = service.build(model_file, output, web)
    metadata = original.metadata.read_bytes()
    catalog = (web / "index.json").read_bytes()
    broken = tmp_path / "broken.json"
    broken.write_text("{}")
    with pytest.raises(ModelValidationError):
        service.build_many([model_file, broken], output, web, "replace")
    assert original.metadata.read_bytes() == metadata
    assert (web / "index.json").read_bytes() == catalog

    broken.write_bytes(model_file.read_bytes())
    export = service.ifc_exporter.export
    calls = 0

    def fail_export(model: ResolvedModel, path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Synthetic export failure")
        export(model, path)

    monkeypatch.setattr(service.ifc_exporter, "export", fail_export)
    with pytest.raises(OSError, match="Synthetic export"):
        service.build_many([model_file, broken], output, web)
    assert calls == 2
    assert original.metadata.read_bytes() == metadata
    assert (web / "index.json").read_bytes() == catalog


def test_merge_versioning_replace_and_unrelated_file_preservation(
    model_file: Path, tmp_path: Path, reference_model: JsonObject
) -> None:
    output, web = tmp_path / "out", tmp_path / "web"
    service = BuildService()
    service.build(model_file, output, web)
    first_catalog = json.loads((web / "index.json").read_text())
    old_assets = web / first_catalog["models"][0]["baseUrl"]
    old_manifest = (old_assets / "render-manifest.json").read_bytes()
    reference_model["revision"] = 3
    ModelLoader.write(reference_model, model_file)
    service.build(model_file, output, web)
    second_catalog = json.loads((web / "index.json").read_text())
    assert first_catalog != second_catalog
    assert (old_assets / "render-manifest.json").read_bytes() == old_manifest
    other = tmp_path / "Home ! café.json"
    ModelLoader.write(reference_model, other)
    service.build(other, output, web)
    (web / "notes.txt").write_text("keep")
    (web / "home" / "notes.txt").write_text("keep too")
    result = service.build_many([other], output, web, "replace")
    assert result.publication is not None
    assert result.publication["removed"] == ["home"]
    final_catalog = json.loads((web / "index.json").read_text())
    assert len(final_catalog["models"]) == 1
    assets = web / unquote(final_catalog["models"][0]["baseUrl"])
    assert (assets / "model.glb").is_file()
    assert not (old_assets / "model.glb").exists()
    assert (web / "notes.txt").read_text() == "keep"
    assert (web / "home" / "notes.txt").read_text() == "keep too"


def test_catalog_publication_failure_keeps_previous_index(
    model_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = BuildService().build(model_file, tmp_path / "out", tmp_path / "web")
    web = tmp_path / "web"
    previous = (web / "index.json").read_bytes()
    original_replace = os.replace

    def fail_catalog(source: Path, destination: Path) -> None:
        if destination == web / "index.json":
            raise OSError("Synthetic publication failure")
        original_replace(source, destination)

    monkeypatch.setattr("home_design.publication.os.replace", fail_catalog)
    with pytest.raises(OSError, match="Synthetic publication"):
        ModelPublisher.publish({"home": result.output_directory}, web, "replace")
    assert (web / "index.json").read_bytes() == previous
    assert not (web / ".home-design-publish.lock").exists()


def test_destination_safety_and_competing_publisher(
    model_file: Path, tmp_path: Path
) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "home").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe"):
        BuildService().build(model_file, output)
    with ModelPublisher.lock(tmp_path / "web"):
        with pytest.raises(ValueError, match="locked"):
            ModelPublisher.publish({}, tmp_path / "web")
    assert model_file.is_file()


def test_build_rolls_back_directories_on_publication_failure(
    model_file: Path,
    tmp_path: Path,
    reference_model: JsonObject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = BuildService()
    output, web = tmp_path / "out", tmp_path / "web"
    result = service.build(model_file, output, web)
    metadata = result.metadata.read_bytes()
    index = (web / "index.json").read_bytes()
    reference_model["revision"] = 9
    ModelLoader.write(reference_model, model_file)
    added = tmp_path / "added.json"
    ModelLoader.write(reference_model, added)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("Synthetic publication failure")

    monkeypatch.setattr(ModelPublisher, "publish", fail)
    with pytest.raises(OSError, match="Synthetic publication"):
        service.build_many([model_file, added], output, web)
    assert result.metadata.read_bytes() == metadata
    assert (web / "index.json").read_bytes() == index
    assert not (output / "added").exists()
    assert not (output / ".home-design-publish.lock").exists()


def test_replace_prunes_old_versions_of_retained_models(
    model_file: Path, tmp_path: Path, reference_model: JsonObject
) -> None:
    output, web = tmp_path / "out", tmp_path / "web"
    service = BuildService()
    service.build(model_file, output, web)
    original = json.loads((web / "index.json").read_text())["models"][0]
    reference_model["revision"] = 6
    ModelLoader.write(reference_model, model_file)
    service.build_many([model_file], output, web, "replace")
    current = json.loads((web / "index.json").read_text())["models"][0]
    assert current["sourceRevision"] == 6
    assert not (web / original["baseUrl"]).exists()
    assert (web / current["baseUrl"] / "model.glb").is_file()


def test_rebuild_repairs_incomplete_browser_artifacts(
    model_file: Path, tmp_path: Path
) -> None:
    output, web = tmp_path / "out", tmp_path / "web"
    service = BuildService()
    result = service.build(model_file, output, web)
    entry = json.loads((web / "index.json").read_text())["models"][0]
    assets = web / entry["baseUrl"]
    (assets / "model.glb").write_bytes(b"incomplete")
    (assets / "schedules.json").unlink()
    (assets / "notes.txt").write_text("keep")
    service.build(model_file, output, web)
    assert (assets / "model.glb").read_bytes() == result.glb_model.read_bytes()
    assert (assets / "schedules.json").read_bytes() == result.schedules.read_bytes()
    assert (assets / "notes.txt").read_text() == "keep"


def test_replace_removes_managed_root_assets(model_file: Path, tmp_path: Path) -> None:
    output, web = tmp_path / "out", tmp_path / "web"
    result = BuildService().build(model_file, output, web)
    for name in ModelPublisher.ARTIFACTS:
        (web / name).write_bytes((result.output_directory / name).read_bytes())
    (web / "notes.txt").write_text("keep")
    ModelPublisher.publish({"home": result.output_directory}, web, "replace")
    assert not (web / "model.glb").exists()
    assert not (web / "render-manifest.json").exists()
    assert (web / "index.json").is_file()
    assert (web / "notes.txt").read_text() == "keep"
