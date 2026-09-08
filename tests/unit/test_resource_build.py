"""Repeated wheel resource builds exclude retired public examples."""

from __future__ import annotations

from pathlib import Path

from setuptools import Distribution
from setuptools.command.build_py import build_py
import pytest

from build_support import ResourceBuild


def test_resource_rebuild_prunes_retired_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A removed example cannot survive in a reused wheel build directory."""
    source = tmp_path / "current.json"
    source.write_text('{"revision": 2}')
    destination = tmp_path / "lib/home_design/_resources/examples"
    destination.mkdir(parents=True)
    retired = destination / "retired.json"
    retired.write_text('{"revision": 1}')
    current = destination / "current.json"
    current.write_text('{"revision": 1}')
    command = ResourceBuild(Distribution())
    command.build_lib = str(tmp_path / "lib")

    def skip_python_build(_self: build_py) -> None:
        """Leave the resource build isolated from unrelated package compilation."""

    def mapping(_self: ResourceBuild) -> dict[str, str]:
        """Expose the sole surviving resource."""
        return {str(current): str(source)}

    monkeypatch.setattr(build_py, "run", skip_python_build)
    monkeypatch.setattr(ResourceBuild, "resource_mapping", mapping)
    command.run()
    assert not retired.exists()
    assert current.read_bytes() == source.read_bytes()
    assert source.is_file()
