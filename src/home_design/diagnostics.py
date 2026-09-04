"""Structured validation diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single machine-readable model diagnostic."""

    severity: Severity
    code: str
    message: str
    path: str = ""
    subject_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Serialize the diagnostic.

        :returns: JSON-compatible diagnostic mapping.
        """
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Collection of diagnostics produced by a validation run."""

    diagnostics: tuple[Diagnostic, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether no error diagnostics were produced.

        :returns: ``True`` when the report has no errors.
        """
        return not any(item.severity == "error" for item in self.diagnostics)

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        """Return error diagnostics only.

        :returns: Error diagnostic tuple.
        """
        return tuple(item for item in self.diagnostics if item.severity == "error")

    def to_dict(self) -> dict[str, object]:
        """Serialize the validation report.

        :returns: JSON-compatible report mapping.
        """
        return {
            "valid": self.is_valid,
            "counts": {
                severity: sum(item.severity == severity for item in self.diagnostics)
                for severity in ("error", "warning", "info")
            },
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }
