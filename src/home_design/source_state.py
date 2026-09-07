"""Source snapshots, cooperative writer locks and atomic revision replacement."""

from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Generator

from home_design.errors import ChangeConflictError
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader


@dataclass(frozen=True, slots=True)
class SourceState:
    """Capture exact bytes once and guard against changes before publishing a result."""

    path: Path
    content: bytes | None

    @classmethod
    def capture(cls, path: Path, required: bool = True) -> SourceState:
        """Capture the current contents, including an intentionally absent destination."""
        destination = path.resolve()
        try:
            content = destination.read_bytes()
        except FileNotFoundError:
            if required:
                raise
            content = None
        return cls(destination, content)

    @property
    def model(self) -> JsonObject:
        """Parse the captured bytes without rereading a potentially changed source."""
        if self.content is None:
            raise ChangeConflictError(
                f"Source does not exist: {self.path}", code="source.missing"
            )
        return ModelLoader.parse(self.content, str(self.path))

    @property
    def sha256(self) -> str | None:
        """Fingerprint exact on-disk bytes for build provenance and recovery."""
        return (
            hashlib.sha256(self.content).hexdigest()
            if self.content is not None
            else None
        )

    def assert_unchanged(self) -> None:
        """Reject changed or replaced sources even when their revision was not advanced."""
        current = SourceState.capture(self.path, required=False)
        if current.content != self.content:
            raise ChangeConflictError(
                f"Source changed while preparing the operation: {self.path}",
                code="source.changed",
                details={
                    "path": str(self.path),
                    "expectedSha256": self.sha256,
                    "actualSha256": current.sha256,
                },
            )

    @staticmethod
    @contextmanager
    def lock(path: Path) -> Generator[None]:
        """Coordinate participating writers without treating elapsed time as lock expiry."""
        destination = path.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock = destination.parent / f".{destination.name}.home-design.lock"
        try:
            lock.mkdir()
        except FileExistsError as error:
            raise ChangeConflictError(
                f"Source is locked by another writer: {destination}",
                code="source.locked",
                details={
                    "lock": str(lock),
                    "recovery": "Retry after the writer finishes. Remove a stale lock only after confirming no writer is active.",
                },
            ) from error
        try:
            (lock / "owner").write_text(f"{os.getpid()}\n", encoding="utf-8")
            yield
        finally:
            (lock / "owner").unlink(missing_ok=True)
            lock.rmdir()

    @staticmethod
    def write(path: Path, content: bytes) -> None:
        """Replace one file atomically after a caller has acquired the appropriate guard."""
        destination = path.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
