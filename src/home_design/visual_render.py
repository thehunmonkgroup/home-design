"""Capture reproducible model images through the shared Three.js inspection client."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator

from home_design.build import BuildService, PreparedBuild
from home_design.constants import resource_root
from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject
from home_design.geometry import number
from home_design.construction import Authoring
from home_design.named_views import NamedViews
from home_design.source_state import SourceState

LOGGER = logging.getLogger(__name__)
RENDER_FORMAT = "home-design-render-0.1"


class RenderRuntime:
    """Prepare a content-addressed capture bundle from distributable viewer sources."""

    @classmethod
    def setup(cls, project: Path | None = None) -> JsonObject:
        """Install the optional Chromium runtime and prepare packaged capture sources."""
        cls._run(
            [sys.executable, "-m", "playwright", "install", "chromium"], Path.cwd()
        )
        site = cls.prepare(project or resource_root() / "web", install=True)
        return {"ready": True, "captureRuntime": str(site)}

    @staticmethod
    def files(project: Path) -> list[Path]:
        """Enumerate capture inputs, excluding generated files and dependencies."""
        files = [
            project / name
            for name in (
                "package.json",
                "package-lock.json",
                "capture.html",
                "capture.config.ts",
            )
        ]
        files.extend(sorted((project / "app").rglob("*.ts")))
        return [path for path in files if not path.name.endswith(".test.ts")]

    @classmethod
    def prepare(cls, project: Path, install: bool = False) -> Path:
        """Build once per exact source set, installing dependencies only on setup."""
        project = project.resolve()
        sources = cls.files(project)
        if any(not path.is_file() for path in sources[:4]):
            raise HomeDesignError(f"Capture sources not found at {project}")
        digest = hashlib.sha256()
        for path in sources:
            digest.update(str(path.relative_to(project)).encode())
            digest.update(path.read_bytes())
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        root = cache / "home-design" / "render" / digest.hexdigest()
        site = root / "site"
        if (site / "capture.html").is_file():
            return site
        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            raise HomeDesignError(
                "Visual inspection requires Node/npm; install Node 22 or newer"
            )
        if not (project / "node_modules/vite/bin/vite.js").is_file():
            target = root / "project"
            ready = target / ".capture-dependencies-ready"
            if (
                not (target / "node_modules/vite/bin/vite.js").is_file()
                or not ready.is_file()
            ):
                if not install:
                    raise HomeDesignError(
                        "Capture dependencies are missing. Run home-design render-setup "
                        + f"--web-project {project}"
                    )
                for path in sources:
                    destination = target / path.relative_to(project)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
                cls._run([npm, "ci", "--no-audit", "--no-fund"], target)
                ready.write_text("ready\n", encoding="utf-8")
            project = target
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="capture-", dir=root) as temporary:
            built = Path(temporary) / "site"
            cls._run(
                [
                    node,
                    str(project / "node_modules/vite/bin/vite.js"),
                    "build",
                    "--config",
                    "capture.config.ts",
                    "--outDir",
                    str(built),
                ],
                project,
            )
            if not site.exists():
                try:
                    built.rename(site)
                except FileExistsError:
                    if not (site / "capture.html").is_file():
                        raise
        return site

    @staticmethod
    def _run(command: list[str], project: Path) -> None:
        """Keep subprocess logs off the machine-readable stdout channel."""
        LOGGER.debug("Capture runtime command: %s", command)
        result = subprocess.run(
            command, cwd=project, stdout=sys.stderr, stderr=sys.stderr
        )
        if result.returncode:
            raise HomeDesignError(
                f"Capture runtime command failed (exit {result.returncode})"
            )


class VisualRenderer:
    """Render a validated snapshot without changing the source or published viewer."""

    def __init__(self, build_service: BuildService | None = None) -> None:
        """Use the normal validator and GLB adapter for every rendered model."""
        self.build_service: BuildService = build_service or BuildService()
        self._prepared: PreparedBuild | None = None
        self._prepared_source: bytes | None = None

    @staticmethod
    def view(path: Path | None) -> JsonObject:
        """Validate a small view request before launching a renderer."""
        value = json.loads(path.read_text()) if path else {}
        schema = json.loads(
            (resource_root() / "schema/render-view.schema.json").read_text()
        )
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            issue = errors[0]
            location = "/" + "/".join(str(item) for item in issue.absolute_path)
            raise HomeDesignError(f"Invalid render view at {location}: {issue.message}")
        return value

    @staticmethod
    def check_output(output: Path, inputs: list[Path]) -> None:
        """Replace only dedicated render directories separate from every input."""
        if output.is_symlink():
            raise ValueError("Render output cannot be a symlink")
        resolved = output.resolve()
        if any(path.resolve().is_relative_to(resolved) for path in inputs):
            raise ValueError(
                "Render output must be separate from source and view inputs"
            )
        if not output.exists() or output.is_dir() and not any(output.iterdir()):
            return
        try:
            marker = output / "render.json"
            recognized = (
                not marker.is_symlink()
                and json.loads(marker.read_text()).get("format") == RENDER_FORMAT
            )
        except (OSError, ValueError, AttributeError):
            recognized = False
        if not recognized:
            raise ValueError(
                "Render output must be empty or a previous render directory"
            )

    def render(
        self,
        model: Path,
        view_path: Path | None,
        output: Path,
        web_project: Path | None = None,
        named_view: str | None = None,
    ) -> JsonObject:
        """Publish an image, object map and provenance only after successful capture."""
        if view_path is not None and named_view is not None:
            raise HomeDesignError("Choose --view or --named-view, not both")
        library = NamedViews(model) if named_view is not None else None
        view = (
            library.get(named_view) if library and named_view else self.view(view_path)
        )
        project = web_project or resource_root() / "web"
        inputs = [model, project, *([view_path] if view_path else [])]
        if library:
            inputs.extend(source.path for source in library.sources)
        self.check_output(output, inputs)
        site = RenderRuntime.prepare(project)
        source = SourceState.capture(model)
        if self._prepared is None or self._prepared_source != source.content:
            LOGGER.info("Resolving the captured model revision for visual inspection")
            self._prepared = self.build_service.prepare(source.model, source.content)
            self._prepared_source = source.content
        else:
            LOGGER.info("Reusing the identical validated source snapshot")
        prepared = self._prepared
        resolved = prepared.evaluation.resolved
        if resolved is None:
            raise HomeDesignError("No resolved model was produced")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="home-design-render-", dir=output.parent
        ) as temporary:
            staging = Path(temporary)
            assets = staging / "assets"
            shutil.copytree(site, assets)
            self.build_service.gltf_exporter.export(
                resolved,
                assets / "model.glb",
                assets / "render-manifest.json",
                (
                    tuple(
                        (
                            {"x": 0, "y": 1, "z": 2}[str(section["axis"])],
                            number(section["position"], "section position"),
                            section.get("keep", "below") == "below",
                        )
                        for value in Authoring.array(view.get("sections", []))
                        for section in [Authoring.object(value)]
                    )
                    if view.get("sectionCaps", True)
                    else ()
                ),
            )
            images = staging / "result"
            images.mkdir()
            receipt = self._capture(assets, view, images)
            objects = receipt.pop("objects")
            receipt.update(
                {
                    "format": RENDER_FORMAT,
                    "sourceSha256": source.sha256,
                    "glbSha256": hashlib.sha256(
                        (assets / "model.glb").read_bytes()
                    ).hexdigest(),
                    "manifestSha256": hashlib.sha256(
                        (assets / "render-manifest.json").read_bytes()
                    ).hexdigest(),
                    "view": view,
                    "image": str(output.resolve() / "image.png"),
                    "objectMap": str(output.resolve() / "object-map.png"),
                    "objects": str(output.resolve() / "objects.json"),
                    "report": str(output.resolve() / "render.json"),
                }
            )
            (images / "objects.json").write_text(json.dumps(objects, indent=2) + "\n")
            (images / "view.json").write_text(json.dumps(view, indent=2) + "\n")
            (images / "render.json").write_text(json.dumps(receipt, indent=2) + "\n")
            source.assert_unchanged()
            if library:
                library.assert_unchanged()
            self.check_output(output, inputs)
            backup = staging / "previous"
            if output.exists():
                output.rename(backup)
            try:
                images.rename(output)
            except OSError:
                if backup.exists():
                    backup.rename(output)
                raise
        return {
            key: receipt[key]
            for key in (
                "format",
                "sourceRevision",
                "sourceSha256",
                "image",
                "objectMap",
                "objects",
                "report",
                "warnings",
            )
        }

    @staticmethod
    def _capture(assets: Path, view: JsonObject, images: Path) -> JsonObject:
        """Capture an offline browser page and reject load, GPU and empty-view failures."""
        try:
            from playwright.sync_api import Error, Route, sync_playwright
        except ImportError as error:
            raise HomeDesignError(
                'Install visual inspection with pip install "home-design[render]", '
                + "then run home-design render-setup"
            ) from error

        def serve(route: Route) -> None:
            """Fulfil only files in the temporary capture directory, without a server."""
            url = urlparse(route.request.url)
            path = (assets / unquote(url.path).lstrip("/")).resolve()
            if (
                url.netloc != "home-design.local"
                or not path.is_relative_to(assets)
                or not path.is_file()
            ):
                route.abort()
                return
            route.fulfill(path=path)

        errors: list[str] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
                )
                try:
                    page = browser.new_page(
                        viewport={
                            "width": int(number(view.get("width", 1280), "view width")),
                            "height": int(
                                number(view.get("height", 960), "view height")
                            ),
                        },
                        device_scale_factor=1,
                    )
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.route("**/*", serve)
                    page.goto("http://home-design.local/capture.html")
                    page.wait_for_function(
                        "typeof window.renderInspection === 'function'"
                    )
                    result: JsonObject = page.evaluate(
                        "view => Promise.race([window.renderInspection(view), "
                        + "new Promise((_, reject) => setTimeout(() => reject(new Error('Capture timed out')), 120000))])",
                        view,
                    )
                    if errors:
                        raise HomeDesignError(
                            "Capture page failed: " + "; ".join(errors)
                        )
                    png = result.pop("objectMapPng")
                    if not isinstance(png, str) or not png.startswith(
                        "data:image/png;base64,"
                    ):
                        raise HomeDesignError("Capture did not return an object map")
                    (images / "object-map.png").write_bytes(
                        base64.b64decode(png.split(",", 1)[1], validate=True)
                    )
                    page.locator("#inspection").screenshot(
                        path=str(images / "image.png"), animations="disabled"
                    )
                    result["renderer"] = {
                        "browser": browser.version,
                        "backend": "Chromium WebGL / SwiftShader",
                    }
                    return result
                finally:
                    browser.close()
        except Error as error:
            raise HomeDesignError(
                f"Visual capture failed: {error}. If Chromium is missing, run home-design render-setup."
            ) from error
