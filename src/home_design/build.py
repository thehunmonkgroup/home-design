"""Atomic orchestration of validation, resolution, and export adapters."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from home_design.adapters import GltfExporter, IfcExporter
from home_design.errors import ModelValidationError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator


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


class BuildService:
    """Build every derived artifact from one validated source revision."""

    _ARTIFACTS: ClassVar[tuple[str, ...]] = (
        "resolved-model.json",
        "model.ifc",
        "model.glb",
        "render-manifest.json",
        "diagnostics.json",
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
        """Validate and atomically publish all derived artifacts.

        :param model_path: Canonical model JSON path.
        :param output_directory: Derived artifact destination.
        :param web_assets: Optional viewer asset directory receiving GLB and manifest copies.
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
        if web_assets is not None:
            self._publish_web_assets(output_directory, web_assets.resolve())
        return BuildResult(
            output_directory,
            output_directory / "resolved-model.json",
            output_directory / "model.ifc",
            output_directory / "model.glb",
            output_directory / "render-manifest.json",
            output_directory / "diagnostics.json",
            output_directory / "build-metadata.json",
        )

    @staticmethod
    def _publish_web_assets(output_directory: Path, web_assets: Path) -> None:
        web_assets.mkdir(parents=True, exist_ok=True)
        for artifact in ("model.glb", "render-manifest.json"):
            source = output_directory / artifact
            destination = web_assets / artifact
            descriptor, temporary_name = tempfile.mkstemp(
                dir=web_assets,
                prefix=f".{artifact}.",
                suffix=".tmp",
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            try:
                temporary_path.write_bytes(source.read_bytes())
                os.replace(temporary_path, destination)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
