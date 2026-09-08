"""Guarded source commits with prepared adapters and recoverable publication."""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, NoReturn
from uuid import uuid4

from home_design.build import BuildService, BuildResult
from home_design.changes import ChangeEngine
from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.source_state import SourceState
from home_design.named_views import NamedViews


@dataclass(slots=True)
class TransactionState:
    """Track completed side effects even when a later phase raises an exception."""

    committed: bool = False
    published: bool = False


class DesignTransaction:
    """Prepare everything before committing, then journal independent publication."""

    FORMAT: ClassVar[str] = "home-design-transaction-0.1"

    def __init__(self, build_service: BuildService | None = None) -> None:
        """Share the build service's loader and validator across all phases."""
        self.build_service: BuildService = build_service or BuildService()
        self.engine: ChangeEngine = ChangeEngine(
            self.build_service.loader, self.build_service.validator
        )

    def apply(
        self,
        model_path: Path,
        change_path: Path,
        output: Path | None = None,
        build_directory: Path | None = None,
        web_assets: Path | None = None,
        dry_run: bool = False,
    ) -> JsonObject:
        """Validate and export a candidate before atomically saving its revision.

        Dry runs evaluate without exporting or creating directories. A failure after
        the source commit retains a journal for rebuilding that same saved revision.
        """
        state = TransactionState()
        try:
            return self._execute(
                model_path,
                change_path,
                output,
                build_directory,
                web_assets,
                dry_run,
                state,
            )
        except Exception as error:
            failure = (
                error
                if isinstance(error, HomeDesignError)
                else HomeDesignError(str(error), code="transaction.failed")
            )
            failure.details.setdefault("committed", state.committed)
            failure.details.setdefault("published", state.published)
            if failure is error:
                raise
            raise failure from error

    def _execute(
        self,
        model_path: Path,
        change_path: Path,
        output: Path | None,
        build_directory: Path | None,
        web_assets: Path | None,
        dry_run: bool,
        state: TransactionState,
    ) -> JsonObject:
        """Run preparation, source replacement and publication with explicit phase state."""
        source = SourceState.capture(model_path)
        destination = (output or model_path).resolve()
        previous = (
            source
            if destination == source.path
            else SourceState.capture(destination, required=False)
        )
        change = self.engine.load_change(change_path)
        candidate = self.engine.candidate(source.model, change)
        prepared = self.build_service.prepare(candidate)
        named_views = NamedViews(destination)
        if dry_run:
            return self._result(candidate, None, False, None)
        if destination == change_path.resolve():
            raise HomeDesignError("Model output must be separate from the changeset")
        build_directory = (build_directory or Path("build")).resolve()
        web_assets = web_assets.resolve() if web_assets is not None else None
        self.build_service.check_destinations(
            [source.path, destination, change_path], build_directory, web_assets
        )
        journal_directory = build_directory / ".transactions"
        if any(
            path.resolve().is_relative_to(journal_directory)
            for path in (source.path, destination, change_path)
        ):
            raise HomeDesignError(
                "Canonical inputs must be outside transaction journals"
            )
        build_directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="home-design-transaction-", dir=build_directory.parent
        ) as temporary:
            staged = self.build_service.export_prepared(
                prepared, Path(temporary) / "model", named_views
            )
            with SourceState.lock(destination):
                source.assert_unchanged()
                previous.assert_unchanged()
                named_views.assert_unchanged()
                journal_path = journal_directory / f"{uuid4().hex}.json"
                journal: JsonObject = {
                    "format": self.FORMAT,
                    "state": "committing",
                    "changeId": change.get("id"),
                    "source": str(source.path),
                    "destination": str(destination),
                    "previousSha256": previous.sha256,
                    "candidateSha256": hashlib.sha256(
                        prepared.source_bytes
                    ).hexdigest(),
                    "revision": candidate["revision"],
                    "buildDirectory": str(build_directory),
                    "webAssets": str(web_assets) if web_assets is not None else None,
                }
                self._write_journal(journal_path, journal)
                try:
                    SourceState.write(destination, prepared.source_bytes)
                    state.committed = True
                    journal["state"] = "committed"
                    self._write_journal(journal_path, journal)
                    self.build_service.install(
                        {destination.stem: staged.output_directory},
                        build_directory,
                        web_assets,
                        sources=(SourceState(destination, prepared.source_bytes),),
                    )
                    state.published = True
                    journal["state"] = "published"
                    self._write_journal(journal_path, journal)
                except Exception as error:
                    self._raise_failure(error, journal_path, journal)
                result = BuildResult.at(build_directory / destination.stem)
                return self._result(candidate, result, True, journal_path)

    def recover(self, journal_path: Path) -> JsonObject:
        """Rebuild only the exact committed source recorded by a transaction journal."""
        journal_path = journal_path.resolve()
        journal = self.build_service.loader.load(journal_path)
        if journal.get("format") != self.FORMAT:
            raise HomeDesignError(
                "Unsupported transaction journal", code="transaction.journal"
            )
        destination = self._path(journal, "destination")
        build_directory = self._path(journal, "buildDirectory")
        web_assets = (
            self._path(journal, "webAssets")
            if journal.get("webAssets") is not None
            else None
        )
        self.build_service.check_destinations(
            [destination, journal_path], build_directory, web_assets
        )
        with SourceState.lock(destination):
            source = SourceState.capture(destination)
            if source.sha256 != journal.get("candidateSha256"):
                raise HomeDesignError(
                    "Recovery requires the exact committed source; inspect the current revision and prepare a fresh build",
                    code="transaction.recovery-source-changed",
                    details={
                        "destination": str(destination),
                        "expectedSha256": journal.get("candidateSha256"),
                        "actualSha256": source.sha256,
                    },
                )
            try:
                build = self.build_service.build(
                    destination, build_directory, web_assets
                )
                journal["state"] = "published"
                journal.pop("error", None)
                self._write_journal(journal_path, journal)
            except Exception as error:
                self._raise_failure(error, journal_path, journal)
            result = self._result(source.model, build, False, journal_path)
            result["recovered"] = True
            result["committed"] = True
            return result

    @staticmethod
    def _path(journal: JsonObject, key: str) -> Path:
        """Require absolute journal paths so recovery is independent of working directory."""
        value = journal.get(key)
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise HomeDesignError(f"Invalid transaction journal path: {key}")
        return Path(value).resolve()

    @staticmethod
    def _write_journal(path: Path, journal: JsonObject) -> None:
        """Atomically persist the latest completed transaction phase."""
        SourceState.write(path, ModelLoader.serialize(journal))

    @classmethod
    def _raise_failure(
        cls, error: Exception, journal_path: Path, journal: JsonObject
    ) -> NoReturn:
        """Report actual source state even if the final journal update itself fails."""
        destination = cls._path(journal, "destination")
        current = SourceState.capture(destination, required=False)
        committed = current.sha256 == journal.get("candidateSha256")
        details: JsonObject = {
            "committed": committed,
            "published": journal.get("state") == "published",
            "journal": str(journal_path),
            "destination": str(destination),
            "revision": journal.get("revision"),
            "cause": (
                error.to_dict() if isinstance(error, HomeDesignError) else str(error)
            ),
            "recovery": (
                ["home-design", "recover", str(journal_path)] if committed else None
            ),
        }
        journal["error"] = details["cause"]
        try:
            cls._write_journal(journal_path, journal)
        except OSError as journal_error:
            details["journalError"] = str(journal_error)
        raise HomeDesignError(
            (
                "Transaction saved its revision but did not finish publication; recover the journal"
                if committed
                else "Transaction did not save its candidate; inspect the source before retrying"
            ),
            code="transaction.incomplete",
            details=details,
        ) from error

    @staticmethod
    def _result(
        model: JsonObject,
        build: BuildResult | None,
        written: bool,
        journal: Path | None,
    ) -> JsonObject:
        """Expose saving and publication separately while retaining familiar artifact fields."""
        return {
            "valid": True,
            "revision": model.get("revision"),
            "written": written,
            "committed": written,
            "published": build is not None,
            "exportsChecked": build is not None,
            "journal": str(journal) if journal is not None else None,
            "buildDirectory": (
                str(build.output_directory) if build is not None else None
            ),
            "ifc": str(build.ifc_model) if build is not None else None,
            "viewerModel": str(build.glb_model) if build is not None else None,
        }
