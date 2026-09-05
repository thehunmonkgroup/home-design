"""Export a portable static viewer with an isolated, explicitly selected collection."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence

from home_design.build import BuildService
from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject

LOGGER = logging.getLogger(__name__)
DEFAULT_WEB_PROJECT = Path(__file__).resolve().parents[2] / "web"
EXPORT_MARKER = "website-export.json"
EXPORT_FORMAT = "home-design-website-0.1"


class WebsiteExporter:
    """Build selected models and the viewer without modifying local preview assets."""

    def __init__(self, build_service: BuildService | None = None) -> None:
        """Initialize the exporter with an optional model build service."""
        self.build_service: BuildService = build_service or BuildService()

    def export(
        self,
        model_paths: Sequence[Path],
        output: Path,
        web_project: Path = DEFAULT_WEB_PROJECT,
    ) -> JsonObject:
        """Publish a complete static directory after both builds succeed.

        :param model_paths: Selected canonical sources, in batch precedence order.
        :param output: Empty directory or a previous website-export destination.
        :param web_project: Viewer source directory with installed npm dependencies.
        :returns: Output directory and selected catalog entries.
        :raises HomeDesignError: If the viewer is unavailable or its build fails.
        :raises ValueError: If replacing the destination could overwrite source files.
        """
        if not model_paths:
            raise ValueError("At least one model is required")
        if output.is_symlink():
            raise ValueError("Website output cannot be a symlink")
        output, web_project = output.resolve(), web_project.resolve()
        self._check_output(output, model_paths, web_project)
        npm = shutil.which("npm")
        if not npm or not (web_project / "node_modules/vite/bin/vite.js").is_file():
            raise HomeDesignError(
                "Website export requires Node/npm and viewer dependencies. "
                + f"Run npm ci in {web_project}; use --web-project for another checkout."
            )
        if not (web_project / "index.html").is_file():
            raise HomeDesignError(f"Viewer source not found at {web_project}")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="home-design-website-", dir=output.parent
        ) as temporary:
            staging = Path(temporary)
            public = staging / "public"
            LOGGER.info("Building %d selected model(s) for website export", len(model_paths))
            self.build_service.build_many(
                model_paths, staging / "models", public / "model", "replace"
            )
            site = staging / "site"
            self._build_viewer(npm, web_project, public, site)
            if not (site / "index.html").is_file():
                raise HomeDesignError("Viewer build did not produce index.html")
            catalog = json.loads((site / "model/index.json").read_text())
            (site / EXPORT_MARKER).write_text(
                json.dumps({"format": EXPORT_FORMAT}) + "\n", encoding="utf-8"
            )
            self._check_output(output, model_paths, web_project)
            backup = staging / "previous"
            if output.exists():
                output.rename(backup)
            try:
                site.rename(output)
            except OSError:
                if backup.exists():
                    backup.rename(output)
                raise
        LOGGER.info("Website ready at %s", output)
        return {"output": str(output), "models": catalog["models"]}

    @staticmethod
    def _check_output(output: Path, sources: Sequence[Path], web_project: Path) -> None:
        """Restrict replacement to dedicated generated directories outside sources."""
        if (
            output.is_symlink()
            or output.is_relative_to(web_project)
            or web_project.is_relative_to(output)
            or any(source.resolve().is_relative_to(output) for source in sources)
        ):
            raise ValueError("Website output must be separate from model and viewer sources")
        if not output.exists():
            return
        if output.is_dir() and not any(output.iterdir()):
            return
        marker = output / EXPORT_MARKER
        try:
            recognized = (
                not marker.is_symlink()
                and json.loads(marker.read_text()).get("format") == EXPORT_FORMAT
            )
        except (OSError, ValueError, AttributeError):
            recognized = False
        if not recognized:
            raise ValueError(
                "Website output must be empty or a previous website-export directory"
            )

    @staticmethod
    def _build_viewer(npm: str, project: Path, public: Path, site: Path) -> None:
        """Run the local static build, sending build logs to stderr."""
        LOGGER.info("Building the static viewer")
        environment = {**os.environ, "HOME_DESIGN_PUBLIC_DIR": str(public)}
        command = [npm, "run", "build", "--", "--outDir", str(site), "--emptyOutDir"]
        LOGGER.debug("Viewer build: %s (cwd=%s)", command, project)
        result = subprocess.run(
            command, cwd=project, env=environment, stdout=sys.stderr, stderr=sys.stderr
        )
        if result.returncode:
            raise HomeDesignError(f"Viewer build failed (exit {result.returncode})")
