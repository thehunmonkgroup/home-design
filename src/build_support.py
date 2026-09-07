"""Package authoritative schemas and progressive guidance without maintained copies."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import override

from setuptools.command.build_py import build_py


class ResourceBuild(build_py):
    """Copy public authoring resources into wheels while preserving relative links."""

    @staticmethod
    def resources() -> list[Path]:
        """Enumerate distributable sources independently of command execution."""
        roots = ("schema", "examples", "recipes", "docs", "skills/home-design")
        files = [Path("README.md"), Path("TODO.md")]
        for root in roots:
            files.extend(
                path
                for path in Path(root).rglob("*")
                if path.is_file()
                and path.suffix in {".json", ".md", ".py", ".yaml", ".csv"}
            )
        return sorted(files)

    def resource_mapping(self) -> dict[str, str]:
        """Map packaged destinations to their single authoritative repository sources."""
        target = Path(self.build_lib) / "home_design" / "_resources"
        return {str(target / path): str(path) for path in self.resources()}

    @override
    def run(self) -> None:
        """Build Python normally and copy resources only for noneditable distributions."""
        super().run()
        if self.editable_mode:
            return
        for destination, source in self.resource_mapping().items():
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    @override
    def get_source_files(self) -> list[str]:
        """Include public resources in source distributions as well as wheels."""
        return super().get_source_files() + [str(path) for path in self.resources()]

    @override
    def get_outputs(self, include_bytecode: bool = True) -> list[str]:
        """Describe complete build outputs for packaging tools."""
        return super().get_outputs(include_bytecode) + list(self.resource_mapping())

    @override
    def get_output_mapping(self) -> dict[str, str]:
        """Expose copied-file provenance for editable-install tooling."""
        return {**super().get_output_mapping(), **self.resource_mapping()}
