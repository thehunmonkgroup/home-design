"""Atomic orchestration of validation, resolution, and export adapters."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from home_design.adapters import GltfExporter, IfcExporter
from home_design.errors import HomeDesignError, ModelValidationError
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.validation import ModelValidator
from home_design.validation.validator import ModelEvaluation
from home_design.reports import ModelReports
from home_design.adapters.drawings import DrawingExporter
from home_design.publication import ModelPublisher
from home_design.source_state import SourceState


@dataclass(frozen=True, slots=True)
class PreparedBuild:
    """One captured source and its retained validation and resolved geometry."""

    model: JsonObject
    source_bytes: bytes
    evaluation: ModelEvaluation

    def check(self) -> None:
        """Reject stale evaluation evidence or bytes belonging to another source."""
        if (
            ModelLoader.fingerprint(self.model) != self.evaluation.source_fingerprint
            or ModelLoader.parse(self.source_bytes) != self.model
        ):
            raise HomeDesignError(
                "Prepared build no longer matches its evaluated source",
                code="build.snapshot-mismatch",
            )
        if not self.evaluation.report.is_valid or self.evaluation.resolved is None:
            raise ModelValidationError(
                "Model must validate before export", self.evaluation.report
            )


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Paths and metadata from one successful deterministic build."""

    output_directory: Path
    resolved_model: Path
    ifc_model: Path
    glb_model: Path
    render_manifest: Path
    diagnostics: Path
    metadata: Path
    schedules: Path
    envelope: Path
    drawings: Path

    @classmethod
    def at(cls, directory: Path) -> BuildResult:
        """Describe the fixed artifact set at a completed model directory."""
        return cls(
            directory,
            directory / "resolved-model.json",
            directory / "model.ifc",
            directory / "model.glb",
            directory / "render-manifest.json",
            directory / "diagnostics.json",
            directory / "build-metadata.json",
            directory / "schedules.json",
            directory / "envelope.json",
            directory / "drawings.svg",
        )


@dataclass(frozen=True, slots=True)
class BatchBuildResult:
    """Final model directories and optional browser publication summary."""

    models: tuple[BuildResult, ...]
    publication: JsonObject | None


class BuildService:
    """Build every derived artifact from one validated source revision."""

    _ARTIFACTS: ClassVar[tuple[str, ...]] = (
        "resolved-model.json",
        "model.ifc",
        "model.glb",
        "render-manifest.json",
        "diagnostics.json",
        "schedules.json",
        "envelope.json",
        "drawings.svg",
        "build-metadata.json",
    )

    def __init__(
        self,
        loader: ModelLoader | None = None,
        validator: ModelValidator | None = None,
        gltf_exporter: GltfExporter | None = None,
        ifc_exporter: IfcExporter | None = None,
    ) -> None:
        """Initialize the build service and injectable adapters.

        :param loader: Optional schema-aware loader.
        :param validator: Optional coordinated validator.
        :param gltf_exporter: Optional GLB adapter.
        :param ifc_exporter: Optional IFC adapter.
        """
        self.loader: ModelLoader = loader or ModelLoader()
        self.validator: ModelValidator = validator or ModelValidator(self.loader)
        self.gltf_exporter: GltfExporter = gltf_exporter or GltfExporter()
        self.ifc_exporter: IfcExporter = ifc_exporter or IfcExporter()

    def build(
        self, model_path: Path, output_directory: Path, web_assets: Path | None = None
    ) -> BuildResult:
        """Build one model beneath its filename stem using the batch workflow."""
        return self.build_many([model_path], output_directory, web_assets).models[0]

    def build_many(
        self,
        model_paths: Sequence[Path],
        output_directory: Path,
        web_assets: Path | None = None,
        web_assets_mode: str = "merge",
    ) -> BatchBuildResult:
        """Stage every model before replacing generated model directories.

        :param model_paths: Ordered sources; the last input with a given stem wins.
        :param output_directory: Root containing one directory per source stem.
        :param web_assets: Optional catalog-based browser asset root.
        :param web_assets_mode: Browser collection publication mode.
        :returns: Final artifact paths and browser collection changes.
        """
        if not model_paths:
            raise ValueError("At least one model is required")
        if web_assets_mode not in ("merge", "replace"):
            raise ValueError(f"Unsupported web assets mode: {web_assets_mode}")
        self.check_destinations(model_paths, output_directory, web_assets)
        prepared, sources = self._prepare_sources(model_paths)
        output_directory = output_directory.resolve()
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="home-design-batch-", dir=output_directory.parent
        ) as temporary:
            staging = Path(temporary)
            winners: dict[str, Path] = {}
            for position, (path, item) in enumerate(zip(model_paths, prepared)):
                result = self.export_prepared(item, staging / str(position))
                winners[path.stem] = result.output_directory
            return self.install(
                winners, output_directory, web_assets, web_assets_mode, tuple(sources)
            )

    @staticmethod
    def check_destinations(
        model_paths: Sequence[Path],
        output_directory: Path,
        web_assets: Path | None = None,
    ) -> None:
        """Keep canonical sources outside replaceable generated directories."""
        output_directory = output_directory.resolve()
        for path in model_paths:
            ModelPublisher.check_key(path.stem)
            target = output_directory / path.stem
            if target.is_symlink() or any(
                source.resolve().is_relative_to(target) for source in model_paths
            ):
                raise ValueError(f"Unsafe generated model destination: {target}")
        if web_assets is not None:
            web_assets = web_assets.resolve()
            if any(
                source.resolve().is_relative_to(web_assets) for source in model_paths
            ):
                raise ValueError("Canonical model sources must be outside web assets")
            if web_assets == output_directory or any(
                web_assets.is_relative_to(output_directory / path.stem)
                or (output_directory / path.stem).is_relative_to(web_assets)
                for path in model_paths
            ):
                raise ValueError(
                    "Build model directories and web assets must not overlap"
                )

    def prepare(
        self,
        model: JsonObject,
        source_bytes: bytes | None = None,
        evaluation: ModelEvaluation | None = None,
    ) -> PreparedBuild:
        """Evaluate once or reuse evidence bound to exactly this source snapshot."""
        prepared = PreparedBuild(
            model,
            source_bytes if source_bytes is not None else self.loader.serialize(model),
            evaluation if evaluation is not None else self.validator.evaluate(model),
        )
        prepared.check()
        return prepared

    def _prepare_sources(
        self, paths: Sequence[Path]
    ) -> tuple[list[PreparedBuild], list[SourceState]]:
        """Capture and evaluate every input before allowing any adapter to export."""
        prepared: list[PreparedBuild] = []
        sources: list[SourceState] = []
        reports: list[JsonValue] = []
        valid = True
        for path in paths:
            try:
                source = SourceState.capture(path)
                model = source.model
                evaluation = self.validator.evaluate(model)
                reports.append({"source": str(path), **evaluation.report.to_dict()})
                valid = valid and evaluation.report.is_valid
                prepared.append(PreparedBuild(model, source.content or b"", evaluation))
                sources.append(source)
            except (HomeDesignError, OSError, ValueError, KeyError) as error:
                valid = False
                reports.append(
                    {
                        "source": str(path),
                        "valid": False,
                        "diagnostics": [
                            {
                                "severity": "error",
                                "code": "model.load",
                                "message": str(error),
                            }
                        ],
                    }
                )
        if not valid:
            raise ModelValidationError(
                json.dumps({"valid": False, "models": reports}, indent=2)
            )
        return prepared, sources

    @staticmethod
    def install(
        winners: dict[str, Path],
        output_directory: Path,
        web_assets: Path | None = None,
        web_assets_mode: str = "merge",
        sources: tuple[SourceState, ...] = (),
    ) -> BatchBuildResult:
        """Install complete staged builds and roll back artifacts on publication failure."""
        output_directory = output_directory.resolve()
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="home-design-backup-", dir=output_directory.parent
        ) as temporary:
            staging = Path(temporary)
            publication = None
            with ModelPublisher.lock(output_directory):
                for snapshot in sources:
                    snapshot.assert_unchanged()
                installed: list[str] = []
                backups: dict[str, Path] = {}
                try:
                    for key, source in winners.items():
                        destination = output_directory / key
                        if destination.is_symlink():
                            raise ValueError(
                                f"Model destination cannot be a symlink: {destination}"
                            )
                        if destination.exists():
                            backup = staging / f"previous-{key}"
                            os.replace(destination, backup)
                            backups[key] = backup
                        os.replace(source, destination)
                        installed.append(key)
                    if web_assets is not None:
                        publication = ModelPublisher.publish(
                            {key: output_directory / key for key in winners},
                            web_assets,
                            web_assets_mode,
                        )
                except Exception:
                    for key in reversed(installed):
                        os.replace(output_directory / key, winners[key])
                    for key, backup in backups.items():
                        os.replace(backup, output_directory / key)
                    raise
            return BatchBuildResult(
                tuple(BuildResult.at(output_directory / key) for key in winners),
                publication,
            )

    def export_prepared(
        self, prepared: PreparedBuild, output_directory: Path
    ) -> BuildResult:
        """Export every adapter from one retained, validated source snapshot.

        :param prepared: Captured source and matching validation evidence.
        :param output_directory: Derived artifact destination.
        :returns: Build artifact paths.
        :raises ModelValidationError: If the source model fails any validation layer.
        """
        prepared.check()
        source_bytes = prepared.source_bytes
        report = prepared.evaluation.report
        resolved = prepared.evaluation.resolved
        if resolved is None:
            raise ModelValidationError(
                "Prepared build has no resolved geometry", report
            )
        output_directory = output_directory.resolve()
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="home-design-build-", dir=output_directory.parent
        ) as temporary:
            staging = Path(temporary)
            (staging / "resolved-model.json").write_text(
                json.dumps(resolved.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
            self.ifc_exporter.export(resolved, staging / "model.ifc")
            self.gltf_exporter.export(
                resolved, staging / "model.glb", staging / "render-manifest.json"
            )
            reports = ModelReports(resolved)
            reports.write(staging / "schedules.json", reports.schedules())
            reports.write(staging / "envelope.json", reports.envelope())
            DrawingExporter().export(resolved, staging / "drawings.svg")
            (staging / "diagnostics.json").write_text(
                json.dumps(report.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
            metadata: JsonObject = {
                "format": "home-design-build-0.1",
                "modelVersion": resolved.model_version,
                "sourceRevision": resolved.source_revision,
                "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
                "artifacts": list(self._ARTIFACTS[:-1]),
            }
            (staging / "build-metadata.json").write_text(
                json.dumps(metadata, indent=2) + "\n",
                encoding="utf-8",
            )
            output_directory.mkdir(parents=True, exist_ok=True)
            for artifact in self._ARTIFACTS:
                os.replace(staging / artifact, output_directory / artifact)
        return BuildResult.at(output_directory)
