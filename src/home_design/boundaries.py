"""Durable scoped identities for profile edges and wall path segments."""

from __future__ import annotations

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.json_types import JsonObject, JsonValue


class BoundaryIdentity:
    """Resolve authored topology names while retaining explicit legacy compatibility."""

    @staticmethod
    def _names(value: JsonValue, count: int, prefix: str) -> tuple[str, ...]:
        """Require one unique name per geometric span; derive names only for legacy input."""
        names = (
            tuple(
                Authoring.text(item, "boundary ID") for item in Authoring.array(value)
            )
            if value is not None
            else tuple(f"{prefix}.{index}" for index in range(count))
        )
        if len(names) != count or len(set(names)) != count:
            raise ResolutionError(
                "Boundary IDs must be unique and match the number of geometric edges",
                code="boundary.invalid-identities",
            )
        return names

    @classmethod
    def profile(cls, profile: JsonObject) -> tuple[tuple[str, ...], ...]:
        """Read outer and hole edge IDs, each associated with its outgoing vertex edge."""
        rings = [profile["outer"], *Authoring.array(profile.get("holes", []))]
        supplied = profile.get("boundaryIds")
        ids = Authoring.object(supplied) if supplied is not None else {}
        holes = Authoring.array(ids.get("holes", []))
        if supplied is not None and len(holes) != len(rings) - 1:
            raise ResolutionError(
                "Boundary hole identities must match the profile holes",
                code="boundary.invalid-identities",
            )
        result = tuple(
            cls._names(
                ids.get("outer") if index == 0 else holes[index - 1] if holes else None,
                len(Authoring.array(ring)),
                f"boundary.legacy.{index}",
            )
            for index, ring in enumerate(rings)
        )
        flattened = [name for ring in result for name in ring]
        if len(flattened) != len(set(flattened)):
            raise ResolutionError(
                "Boundary IDs must be unique across a profile's outer ring and holes",
                code="boundary.duplicate-id",
            )
        return result

    @classmethod
    def metadata(cls, profile: JsonObject) -> JsonObject:
        """Serialize a validated identity set alongside resolved coordinates."""
        names = cls.profile(profile)
        return {"outer": list(names[0]), "holes": [list(ring) for ring in names[1:]]}

    @classmethod
    def path(cls, path: JsonObject, count: int) -> tuple[str, ...]:
        """Read the names of consecutive path spans independently of their array positions."""
        return cls._names(path.get("segmentIds"), count, "segment.legacy")

    @staticmethod
    def select(names: tuple[str, ...], value: JsonValue) -> int:
        """Resolve a named span or a legacy integer without a positional fallback."""
        if isinstance(value, str) and value in names:
            return names.index(value)
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < len(names)
        ):
            return value
        raise ResolutionError(
            f"Boundary or segment {value} is unavailable",
            code="boundary.identity-unavailable",
            details={"selection": value, "available": list(names)},
        )
