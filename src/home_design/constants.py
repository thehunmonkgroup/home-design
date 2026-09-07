"""Shared constants for model version 0.1."""

from __future__ import annotations

from pathlib import Path

MODEL_VERSION = "0.2"
SUPPORTED_MODEL_VERSIONS = ("0.1", "0.2")
DEFAULT_SCHEMA_NAME = "home-model-0.2.schema.json"
IFC_SCHEMA = "IFC4"
MILLIMETRES_PER_METRE = 1000.0
GEOMETRY_TOLERANCE_MM = 0.01
GUID_NAMESPACE = "urn:home-design:stable-guid:v1"


def repository_root() -> Path:
    """Return the source checkout root.

    :returns: Absolute repository path.
    :raises FileNotFoundError: If the package is not inside a source checkout.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "schema" / DEFAULT_SCHEMA_NAME).is_file():
            return parent
    raise FileNotFoundError(
        f"Cannot locate schema/{DEFAULT_SCHEMA_NAME}; pass an explicit schema path"
    )


def default_schema_path() -> Path:
    """Return the canonical authoring schema path.

    :returns: Absolute JSON Schema path.
    """
    return resource_root() / "schema" / DEFAULT_SCHEMA_NAME


def resource_root() -> Path:
    """Locate authoritative checkout resources or the matching installed bundle."""
    bundled = Path(__file__).resolve().parent / "_resources"
    if (bundled / "schema" / DEFAULT_SCHEMA_NAME).is_file():
        return bundled
    return repository_root()
