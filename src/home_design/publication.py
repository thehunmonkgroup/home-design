"""Catalog-based publication of immutable browser model assets."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote
from typing import ClassVar

from home_design.json_types import JsonObject, JsonValue

LOGGER = logging.getLogger(__name__)


class ModelPublisher:
    """Publish a complete catalog only after all referenced assets are ready."""

    FORMAT: ClassVar[str] = "home-design-model-catalog-0.1"
    ARTIFACTS: ClassVar[tuple[str, ...]] = (
        "model.glb",
        "render-manifest.json",
        "schedules.json",
        "envelope.json",
        "drawings.svg",
    )

    @staticmethod
    def check_key(key: str) -> None:
        """Require a single, non-special directory name for managed writes."""
        if (
            not key
            or key
            in (".", "..", ".git", ".agents", ".codex", ".home-design-publish.lock")
            or any(c in key for c in "/\\")
        ):
            raise ValueError(f"Invalid model directory name: {key!r}")

    @staticmethod
    @contextmanager
    def lock(root: Path) -> Generator[None]:
        """Exclude competing writers without retaining a stale open file lock."""
        root.mkdir(parents=True, exist_ok=True)
        lock = root / ".home-design-publish.lock"
        try:
            lock.mkdir()
        except FileExistsError as error:
            raise ValueError(
                f"Publication is locked: {lock}. Retry after the other build finishes; "
                + "remove this lock only if its build was interrupted."
            ) from error
        try:
            yield
        finally:
            lock.rmdir()

    @classmethod
    def publish(
        cls, models: Mapping[str, Path], root: Path, mode: str = "merge"
    ) -> JsonObject:
        """Merge or replace managed models, preserving unrelated files.

        :param models: Model keys mapped to complete staged build directories.
        :param root: Viewer asset root.
        :param mode: ``merge`` preserves other models; ``replace`` removes them.
        :returns: Added, updated, retained and removed model keys.
        """
        if mode not in ("merge", "replace"):
            raise ValueError(f"Unsupported web assets mode: {mode}")
        with cls.lock(root):
            return cls._publish_locked(models, root, mode)

    @classmethod
    def _read_catalog(cls, root: Path) -> dict[str, JsonObject]:
        path = root / "index.json"
        if not path.exists():
            return {}
        value: JsonValue = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("format") != cls.FORMAT:
            raise ValueError(f"Unsupported model catalog: {path}")
        entries = value.get("models")
        if not isinstance(entries, list):
            raise ValueError(f"Invalid model catalog: {path}")
        result: dict[str, JsonObject] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid catalog entry: {path}")
            key, version = entry.get("key"), entry.get("version")
            if not isinstance(key, str) or not isinstance(version, str):
                raise ValueError(f"Invalid catalog identity: {path}")
            cls.check_key(key)
            if not re.fullmatch(r"[0-9a-f]{64}", version):
                raise ValueError(f"Invalid catalog asset version: {path}")
            if entry.get("baseUrl") != f"{quote(key, safe='')}/{version}/":
                raise ValueError(f"Invalid catalog asset location: {path}")
            result[key] = entry
        return result

    @classmethod
    def _publish_locked(
        cls, models: Mapping[str, Path], root: Path, mode: str
    ) -> JsonObject:
        previous = cls._read_catalog(root)
        entries = dict(previous) if mode == "merge" else {}
        for key, source in models.items():
            cls.check_key(key)
            model_root = root / key
            if model_root.is_symlink():
                raise ValueError(f"Model destination cannot be a symlink: {model_root}")
            digest = hashlib.sha256()
            for artifact in cls.ARTIFACTS:
                digest.update(artifact.encode())
                digest.update((source / artifact).read_bytes())
            version = digest.hexdigest()
            destination = model_root / version
            model_root.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink():
                raise ValueError(
                    f"Asset destination cannot be a symlink: {destination}"
                )
            cls._install_assets(source, destination)
            manifest: JsonObject = json.loads(
                (source / "render-manifest.json").read_text(encoding="utf-8")
            )
            project = manifest["project"]
            if not isinstance(project, dict):
                raise ValueError("Render manifest must include a project")
            entries[key] = {
                "key": key,
                "name": project["name"],
                "sourceRevision": manifest["sourceRevision"],
                "version": version,
                "baseUrl": f"{quote(key, safe='')}/{version}/",
            }
        ordered = sorted(
            entries.values(),
            key=lambda entry: (str(entry["name"]).casefold(), str(entry["key"])),
        )
        catalog: JsonObject = {
            "format": cls.FORMAT,
            "models": [entry for entry in ordered],
        }
        with tempfile.TemporaryDirectory(dir=root, prefix=".catalog-") as temp:
            staged_index = Path(temp) / "index.json"
            staged_index.write_text(
                json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(staged_index, root / "index.json")
        removed = set(previous) - set(entries)
        for key in removed:
            cls._cleanup(root, previous[key])
        if mode == "replace":
            for entry in entries.values():
                cls._cleanup(root, entry, keep=str(entry["version"]))
            cls._cleanup_root_assets(root)
        return {
            "mode": mode,
            "added": [key for key in sorted(set(models) - set(previous))],
            "updated": [key for key in sorted(set(models) & set(previous))],
            "retained": [key for key in sorted(set(entries) - set(models))],
            "removed": [key for key in sorted(removed)],
        }

    @classmethod
    def _cleanup_root_assets(cls, root: Path) -> None:
        """Remove generated root-level browser artifacts identified by their manifest."""
        manifest = root / "render-manifest.json"
        if not manifest.is_file() or manifest.is_symlink():
            return
        try:
            value: JsonValue = json.loads(manifest.read_text(encoding="utf-8"))
            if (
                not isinstance(value, dict)
                or value.get("format") != "home-design-render-manifest-0.1"
            ):
                return
            for artifact in cls.ARTIFACTS:
                (root / artifact).unlink(missing_ok=True)
        except (OSError, ValueError):
            LOGGER.warning(
                "Could not clean generated root assets in %s", root, exc_info=True
            )

    @classmethod
    def _install_assets(cls, source: Path, destination: Path) -> None:
        """Install a complete version or repair missing/corrupted generated files."""
        if destination.exists() and not destination.is_dir():
            raise ValueError(f"Asset destination is not a directory: {destination}")
        if destination.is_dir() and all(
            (destination / artifact).is_file()
            and not (destination / artifact).is_symlink()
            and (destination / artifact).read_bytes()
            == (source / artifact).read_bytes()
            for artifact in cls.ARTIFACTS
        ):
            return
        with tempfile.TemporaryDirectory(
            dir=destination.parent, prefix=".staging-"
        ) as temp:
            staging = Path(temp) / "assets"
            staging.mkdir()
            for artifact in cls.ARTIFACTS:
                shutil.copyfile(source / artifact, staging / artifact)
            if destination.exists():
                for artifact in cls.ARTIFACTS:
                    os.replace(staging / artifact, destination / artifact)
            else:
                os.replace(staging, destination)

    @classmethod
    def _cleanup(cls, root: Path, entry: JsonObject, keep: str | None = None) -> None:
        """Treat post-commit cleanup failures as warnings, not publication failures."""
        try:
            cls._remove_managed_version(root, entry, keep)
        except OSError:
            LOGGER.warning("Could not clean assets for %s", entry["key"], exc_info=True)

    @classmethod
    def _remove_managed_version(
        cls, root: Path, entry: JsonObject, keep: str | None = None
    ) -> None:
        """Remove only generated asset files; unrelated directory content survives."""
        model_root = root / str(entry["key"])
        if model_root.is_symlink():
            return
        for version in model_root.glob("*"):
            if version.name == keep:
                continue
            if version.is_symlink() or not re.fullmatch(r"[0-9a-f]{64}", version.name):
                continue
            if not version.is_dir():
                continue
            try:
                for artifact in cls.ARTIFACTS:
                    (version / artifact).unlink(missing_ok=True)
                if not any(version.iterdir()):
                    version.rmdir()
            except OSError:
                LOGGER.warning(
                    "Could not clean generated assets in %s", version, exc_info=True
                )
        try:
            if model_root.is_dir() and not any(model_root.iterdir()):
                model_root.rmdir()
        except OSError:
            LOGGER.warning(
                "Could not clean model directory %s", model_root, exc_info=True
            )
