"""Domain exceptions raised by the home design engine."""

from __future__ import annotations


class HomeDesignError(Exception):
    """Base exception for expected design workflow failures."""


class ModelLoadError(HomeDesignError):
    """Raised when an authoring model cannot be loaded."""


class ModelValidationError(HomeDesignError):
    """Raised when an authoring model fails validation."""


class ResolutionError(HomeDesignError):
    """Raised when validated design intent cannot be resolved."""


class ChangeConflictError(HomeDesignError):
    """Raised when transactional change preconditions are not satisfied."""


class ExportError(HomeDesignError):
    """Raised when a resolved model cannot be exported."""
