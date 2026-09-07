"""Domain exceptions raised by the home design engine."""

from __future__ import annotations

from home_design.diagnostics import ValidationReport
from home_design.json_types import JsonObject


class HomeDesignError(Exception):
    """Base exception for expected design workflow failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "workflow.failed",
        path: str = "",
        subject_id: str | None = None,
        details: JsonObject | None = None,
        report: ValidationReport | None = None,
    ) -> None:
        """Keep machine-readable context alongside the human-readable exception."""
        super().__init__(message)
        self.code: str = code
        self.path: str = path
        self.subject_id: str | None = subject_id
        self.details: JsonObject = details or {}
        self.report: ValidationReport | None = report

    def to_dict(self) -> JsonObject:
        """Serialize recovery context without requiring exception-text parsing."""
        result: JsonObject = {
            "code": self.code,
            "message": str(self),
            "path": self.path,
            "subject_id": self.subject_id,
            "details": self.details,
        }
        if self.report is not None:
            result["validation"] = self.report.to_dict()
        return result


class ModelLoadError(HomeDesignError):
    """Raised when an authoring model cannot be loaded."""


class ModelValidationError(HomeDesignError):
    """Raised when an authoring model fails validation."""

    def __init__(self, message: str, report: ValidationReport | None = None) -> None:
        """Retain structured validation evidence for command-line recovery."""
        super().__init__(message, code="model.validation-failed", report=report)


class ResolutionError(HomeDesignError):
    """Raised when validated design intent cannot be resolved."""


class ChangeConflictError(HomeDesignError):
    """Raised when transactional change preconditions are not satisfied."""


class ExportError(HomeDesignError):
    """Raised when a resolved model cannot be exported."""
