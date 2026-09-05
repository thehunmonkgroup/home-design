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
from home_design.errors import ModelValidationError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator
from home_design.reports import ModelReports
from home_design.adapters.drawings import DrawingExporter
from home_design.batch import ModelBatch
from home_design.publication import ModelPublisher


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
        report = ModelBatch.validate(model_paths, self.loader, self.validator)
        if report["valid"] is not True:
            raise ModelValidationError(json.dumps(report, indent=2))
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
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="home-design-batch-", dir=output_directory.parent
        ) as temporary:
            staging = Path(temporary)
            winners: dict[str, Path] = {}
            for position, path in enumerate(model_paths):
                result = self._export_one(path, staging / str(position))
                winners[path.stem] = result.output_directory
            publication = None
            with ModelPublisher.lock(output_directory):
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

    def _export_one(self, model_path: Path, output_directory: Path) -> BuildResult:
        """Validate and atomically publish all derived artifacts.

        :param model_path: Canonical model JSON path.
        :param output_directory: Derived artifact destination.
        :returns: Build artifact paths.
        :raises ModelValidationError: If the source model fails any validation layer.
        """
        source_bytes = model_path.read_bytes()
        model = self.loader.load(model_path)
        report = self.validator.validate(model)
        if not report.is_valid:
            summary = "; ".join(
                f"{item.code}: {item.message}" for item in report.errors
            )
            raise ModelValidationError(summary)
        resolved = ModelResolver(model).resolve()
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
