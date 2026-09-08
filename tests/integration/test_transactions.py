"""Transaction failure boundaries, exact snapshots and recovery without reapplication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from home_design.build import BuildService
from home_design.cli import main
from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.publication import ModelPublisher
from home_design.resolved import ResolvedModel
from home_design.source_state import SourceState
from home_design.transactions import DesignTransaction
from home_design.validation.validator import ModelEvaluation

CHANGE = Path(__file__).resolve().parents[2] / "tests/fixtures/move-window.json"


def test_export_failure_preserves_source_and_existing_artifacts(
    model_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = BuildService()
    output = tmp_path / "build"
    prior = service.build(model_file, output)
    source = model_file.read_bytes()
    metadata = prior.metadata.read_bytes()

    def fail(_model: ResolvedModel, _path: Path) -> None:
        raise OSError("Adapter failed before commit")

    monkeypatch.setattr(service.ifc_exporter, "export", fail)
    with pytest.raises(HomeDesignError, match="before commit") as caught:
        DesignTransaction(service).apply(model_file, CHANGE, build_directory=output)
    assert caught.value.details["committed"] is False
    assert caught.value.details["published"] is False
    assert model_file.read_bytes() == source
    assert prior.metadata.read_bytes() == metadata
    assert not (output / ".transactions").exists()


def test_publication_failure_is_recoverable_without_incrementing_revision(
    model_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = BuildService()
    output, web = tmp_path / "build", tmp_path / "web"
    prior = service.build(model_file, output, web)
    metadata = prior.metadata.read_bytes()
    catalog = (web / "index.json").read_bytes()
    revision = ModelLoader().load(model_file)["revision"]

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("Publication unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(ModelPublisher, "publish", fail)
        with pytest.raises(HomeDesignError) as caught:
            DesignTransaction(service).apply(
                model_file, CHANGE, build_directory=output, web_assets=web
            )
    detail = caught.value.details
    assert detail["committed"] is True
    assert detail["published"] is False
    assert prior.metadata.read_bytes() == metadata
    assert (web / "index.json").read_bytes() == catalog
    saved = model_file.read_bytes()
    assert json.loads(saved)["revision"] == int(str(revision)) + 1
    journal = Path(str(detail["journal"]))
    recovered = DesignTransaction(service).recover(journal)
    assert recovered["recovered"] is True
    assert recovered["written"] is False
    assert recovered["committed"] is True
    assert recovered["published"] is True
    assert model_file.read_bytes() == saved
    assert (
        json.loads(prior.metadata.read_bytes())["sourceSha256"]
        == hashlib.sha256(saved).hexdigest()
    )
    assert json.loads(journal.read_bytes())["state"] == "published"
    assert (
        DesignTransaction(service).recover(journal)["revision"] == recovered["revision"]
    )


def test_recovery_rejects_changed_bytes_even_at_same_revision(
    model_file: Path, tmp_path: Path
) -> None:
    result = DesignTransaction().apply(
        model_file, CHANGE, build_directory=tmp_path / "build"
    )
    journal = Path(str(result["journal"]))
    model_file.write_bytes(model_file.read_bytes() + b"\n")
    with pytest.raises(HomeDesignError) as caught:
        DesignTransaction().recover(journal)
    assert caught.value.code == "transaction.recovery-source-changed"


def test_source_change_during_export_prevents_commit_and_publication(
    model_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = BuildService()
    export = service.ifc_exporter.export
    altered = model_file.read_bytes() + b"\n"

    def concurrent_write(model: ResolvedModel, path: Path) -> None:
        model_file.write_bytes(altered)
        export(model, path)

    monkeypatch.setattr(service.ifc_exporter, "export", concurrent_write)
    output = tmp_path / "build"
    with pytest.raises(HomeDesignError) as caught:
        DesignTransaction(service).apply(model_file, CHANGE, build_directory=output)
    assert caught.value.code == "source.changed"
    assert model_file.read_bytes() == altered
    assert not (output / model_file.stem).exists()
    assert not (output / ".transactions").exists()


def test_guarded_writers_reject_competing_destination_lock(
    model_file: Path, tmp_path: Path
) -> None:
    original = model_file.read_bytes()
    with SourceState.lock(model_file):
        with pytest.raises(HomeDesignError) as caught:
            DesignTransaction().apply(
                model_file, CHANGE, build_directory=tmp_path / "build"
            )
    assert caught.value.code == "source.locked"
    assert model_file.read_bytes() == original


def test_transaction_and_build_each_evaluate_their_snapshot_once(
    model_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = BuildService()
    evaluate = service.validator.evaluate
    calls: list[JsonObject] = []

    def count(model: JsonObject, resolve_geometry: bool = True) -> ModelEvaluation:
        calls.append(model)
        return evaluate(model, resolve_geometry)

    monkeypatch.setattr(service.validator, "evaluate", count)
    DesignTransaction(service).apply(
        model_file, CHANGE, build_directory=tmp_path / "build"
    )
    assert len(calls) == 1
    calls.clear()
    built = service.build(model_file, tmp_path / "build")
    assert len(calls) == 1
    assert (
        json.loads(built.metadata.read_bytes())["sourceSha256"]
        == hashlib.sha256(model_file.read_bytes()).hexdigest()
    )


def test_prepared_build_rejects_mutation_after_validation(model_file: Path) -> None:
    service = BuildService()
    prepared = service.prepare(ModelLoader().load(model_file))
    prepared.model["revision"] = 900
    with pytest.raises(HomeDesignError) as caught:
        prepared.check()
    assert caught.value.code == "build.snapshot-mismatch"


def test_package_cli_dry_run_has_no_filesystem_side_effects(
    model_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = model_file.read_bytes()
    output = tmp_path / "absent" / "build"
    assert (
        main(
            [
                "transact",
                str(model_file),
                str(CHANGE),
                "--build-directory",
                str(output),
                "--dry-run",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["written"] is False
    assert report["committed"] is False
    assert report["exportsChecked"] is False
    assert model_file.read_bytes() == original
    assert not output.parent.exists()


def test_interrupted_committing_journal_recovers_saved_revision(
    model_file: Path, tmp_path: Path
) -> None:
    result = DesignTransaction().apply(
        model_file, CHANGE, build_directory=tmp_path / "build"
    )
    path = Path(str(result["journal"]))
    journal = ModelLoader().load(path)
    journal["state"] = "committing"
    ModelLoader.write(journal, path)
    saved = model_file.read_bytes()
    assert DesignTransaction().recover(path)["published"] is True
    assert model_file.read_bytes() == saved


def test_build_rejects_source_changed_during_export(
    model_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = BuildService()
    export = service.ifc_exporter.export

    def concurrent_write(model: ResolvedModel, path: Path) -> None:
        model_file.write_bytes(model_file.read_bytes() + b"\n")
        export(model, path)

    monkeypatch.setattr(service.ifc_exporter, "export", concurrent_write)
    with pytest.raises(HomeDesignError) as caught:
        service.build(model_file, tmp_path / "build")
    assert caught.value.code == "source.changed"
    assert not (tmp_path / "build" / model_file.stem).exists()
