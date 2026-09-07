"""Bounded source and dependency inspection independent of geometry validity."""

from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from home_design.errors import HomeDesignError
from home_design.construction import Authoring
from home_design.graph import ModelIndex, Reference, ReferenceRole
from home_design.json_types import JsonObject, JsonPointer, JsonValue
from home_design.member_assemblies import MemberAssemblies
from home_design.resolved import ResolvedElement, ResolvedModel


@dataclass(frozen=True, slots=True)
class InspectionPage:
    """Bound response size without hiding omitted records from an author."""

    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        """Reject invalid pagination before slicing records."""
        if not 1 <= self.limit <= 1000 or self.offset < 0:
            raise HomeDesignError(
                "Inspection limit must be 1–1000 and offset nonnegative"
            )

    def select(self, values: list[JsonValue]) -> JsonObject:
        """Return a deterministic page and a continuation offset."""
        end = self.offset + self.limit
        return {
            "items": values[self.offset : end],
            "total": len(values),
            "offset": self.offset,
            "limit": self.limit,
            "nextOffset": end if end < len(values) else None,
        }


class ModelInspection:
    """Inspect authored objects, typed edges and optional resolved measurements."""

    def __init__(self, model: JsonObject) -> None:
        """Index source objects without requiring schema or geometry success."""
        self.model: JsonObject = model
        self.index: ModelIndex = ModelIndex(model)

    def locate(
        self, identity: str, registry: str | None = None
    ) -> tuple[str, JsonObject]:
        """Locate an object and reject ambiguous identities in invalid models."""
        matches = [
            (name, objects[identity])
            for name, objects in self.index.registries.items()
            if (registry is None or name == registry) and identity in objects
        ]
        if len(matches) != 1:
            reason = "is ambiguous; select --registry" if matches else "does not exist"
            raise HomeDesignError(f"Object {identity} {reason}")
        return matches[0]

    def summary(
        self,
        page: InspectionPage,
        registry: str = "elements",
        kind: str | None = None,
        query: str = "",
    ) -> JsonObject:
        """Discover IDs by registry, kind and human-readable name."""
        objects = self.index.registries[registry]
        term = query.casefold()
        values: list[JsonValue] = [
            {"id": identity, "kind": value.get("kind"), "name": value.get("name")}
            for identity, value in sorted(objects.items())
            if (kind is None or value.get("kind") == kind)
            and (
                term in identity.casefold()
                or term in str(value.get("name", "")).casefold()
            )
        ]
        counts = Counter(str(value.get("kind")) for value in objects.values())
        project = self.model.get("project")
        return {
            "project": project.get("name") if isinstance(project, dict) else None,
            "modelVersion": self.model.get("modelVersion"),
            "revision": self.model.get("revision"),
            "registry": registry,
            "elementCounts" if registry == "elements" else "kindCounts": dict(
                sorted(counts.items())
            ),
            "elements" if registry == "elements" else "objects": page.select(values)[
                "items"
            ],
            "page": {
                key: value
                for key, value in page.select(values).items()
                if key != "items"
            },
        }

    def source(
        self, identity: str, registry: str | None = None, fields: tuple[str, ...] = ()
    ) -> JsonObject:
        """Return editable fields, preserving their authored reference coordinates."""
        name, value = self.locate(identity, registry)
        result: JsonObject = {
            "id": identity,
            "registry": name,
            "kind": value.get("kind"),
            "name": value.get("name"),
            "revision": self.model.get("revision"),
            "modelVersion": self.model.get("modelVersion"),
        }
        if fields:
            try:
                result["fields"] = {
                    field: JsonPointer.get(value, field) for field in fields
                }
            except (KeyError, IndexError, ValueError, TypeError) as error:
                raise HomeDesignError(
                    f"Cannot inspect selected field: {error}"
                ) from error
        else:
            result["authored"] = deepcopy(value)
        return result

    def assembly(self, identity: str, page: InspectionPage) -> JsonObject:
        """Inspect recipe parameters, bound interfaces and paged canonical membership without templates."""
        _, element = self.locate(identity, "elements")
        record = element.get("recipeInstance")
        if element.get("kind") != "assembly" or not isinstance(record, dict):
            raise HomeDesignError(
                "Select an assembly with recipe provenance",
                code="recipe.instance-unavailable",
                subject_id=identity,
            )
        result = {
            key: deepcopy(value) for key, value in record.items() if key != "objectIds"
        }
        objects: list[JsonValue] = [
            {
                "registry": registry,
                "localId": local,
                "id": target,
                "available": target in self.index.registries[registry],
            }
            for registry, values in Authoring.object(record["objectIds"]).items()
            for local, target in sorted(Authoring.object(values).items())
        ]
        result["objects"] = page.select(objects)
        return result

    def references(
        self,
        identity: str,
        page: InspectionPage,
        direction: Literal["incoming", "outgoing"],
        role: ReferenceRole | None = None,
    ) -> JsonObject:
        """List direct typed references with exact source paths and target scope."""
        references = (
            self.index.incoming if direction == "incoming" else self.index.outgoing
        )
        return page.select(
            [
                self._edge(reference)
                for reference in sorted(
                    references.get(identity, []), key=lambda item: item.path
                )
                if role is None or reference.role == role
            ]
        )

    def _edge(self, reference: Reference) -> JsonObject:
        value = reference.to_dict(self.model)
        value["targetExists"] = (
            reference.target_id in self.index.registries[reference.registry]
        )
        return value

    def closure(
        self,
        identity: str,
        page: InspectionPage,
        direction: Literal["incoming", "outgoing"],
        depth: int = 2,
        role: ReferenceRole | None = None,
    ) -> JsonObject:
        """Traverse dependencies or dependents with explicit roles and depth bounds."""
        if not 1 <= depth <= 64:
            raise HomeDesignError("Inspection depth must be 1–64")
        adjacency = (
            self.index.incoming if direction == "incoming" else self.index.outgoing
        )
        queue: deque[tuple[str, int]] = deque([(identity, 0)])
        seen = {identity}
        values: list[JsonValue] = []
        boundary: set[str] = set()
        while queue:
            current, distance = queue.popleft()
            edges = sorted(adjacency.get(current, []), key=lambda item: item.path)
            for reference in edges:
                if role is not None and role != reference.role:
                    continue
                target = (
                    reference.owner_id
                    if direction == "incoming"
                    else reference.target_id
                )
                if target in seen:
                    continue
                if distance == depth:
                    boundary.add(target)
                    continue
                seen.add(target)
                values.append(
                    {
                        "id": target,
                        "registry": (
                            reference.owner_registry
                            if direction == "incoming"
                            else reference.registry
                        ),
                        "depth": distance + 1,
                        "via": current,
                        "reference": self._edge(reference),
                    }
                )
                queue.append((target, distance + 1))
        return {
            **page.select(values),
            "maxDepth": depth,
            "depthLimited": bool(boundary - seen),
        }

    def relationships(self, identity: str, page: InspectionPage) -> JsonObject:
        """Return semantic records through typed edges rather than string matching."""
        identities = sorted(
            {
                reference.owner_id
                for reference in self.index.incoming.get(identity, [])
                if reference.owner_registry == "relationships"
            }
        )
        return page.select(
            [
                {"id": key, **self.index.registries["relationships"][key]}
                for key in identities
            ]
        )

    def type_users(self, identity: str, page: InspectionPage) -> JsonObject:
        """Find direct and indirect users of an occurrence's reusable type."""
        registry, source = self.locate(identity)
        target = identity if registry == "types" else source.get("type")
        if not isinstance(target, str):
            raise HomeDesignError(f"Object {identity} has no reusable type")
        return {
            "typeId": target,
            **self.closure(target, page, "incoming", 64, "type"),
        }

    @staticmethod
    def resolved(element: ResolvedElement, meshes: bool = False) -> JsonObject:
        """Expose dimensions without exporting vertices unless explicitly requested."""
        if meshes:
            return element.to_dict()
        geometry: JsonObject = {
            "meshCount": len(element.meshes),
            "constructionVolumes": [
                name for name in sorted(element.construction_volumes)
            ],
        }
        result: JsonObject = {
            "id": element.element_id,
            "kind": element.kind,
            "name": element.name,
            "storeyId": element.storey_id,
            "data": {
                key: value for key, value in element.data.items() if key != "members"
            },
            "geometry": geometry,
        }
        members = element.data.get("members")
        if isinstance(members, list):
            result["generatedParts"] = {
                "total": len(members),
                "inspection": "Use --parts --limit N --offset N, or --part KEY",
            }
        return result

    @classmethod
    def parts(
        cls,
        model: ResolvedModel,
        identity: str,
        page: InspectionPage,
        key: str | None = None,
        meshes: bool = False,
    ) -> JsonObject:
        """Inspect independently addressable generated structural members."""
        element = model.element(identity)
        if element.kind not in MemberAssemblies.CHILD_KINDS:
            raise HomeDesignError(f"Element {identity} has no scoped generated members")
        children = MemberAssemblies.children(element)
        if key is not None:
            child = MemberAssemblies.member(element, key)
            return cls.resolved(child, meshes)
        return page.select([cls.resolved(child, meshes) for child in children])
