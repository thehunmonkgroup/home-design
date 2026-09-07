"""Review authored edits and their actual resolved effects before committing."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.diagnostics import ValidationReport
from home_design.graph import ModelIndex
from home_design.geometry import number
from home_design.inspection import InspectionPage
from home_design.json_types import JsonObject, JsonValue
from home_design.member_assemblies import MemberAssemblies
from home_design.reports import ModelReports
from home_design.resolved import ResolvedElement, ResolvedModel
from home_design.validation.validator import ModelEvaluation


class JsonChanges:
    """Describe precise source paths without flooding a preview with large arrays."""

    @classmethod
    def compare(
        cls, before: JsonValue, after: JsonValue, path: str = ""
    ) -> list[JsonValue]:
        """Find changed leaves and retain explicit existence for additions/removals."""
        if before == after:
            return []
        if isinstance(before, dict) and isinstance(after, dict):
            changes: list[JsonValue] = []
            for key in sorted(before.keys() | after.keys()):
                child = f"{path}/{key.replace('~', '~0').replace('/', '~1')}"
                if key in before and key in after:
                    changes.extend(cls.compare(before[key], after[key], child))
                else:
                    changes.append(
                        cls.record(
                            child,
                            before.get(key),
                            after.get(key),
                            key in before,
                            key in after,
                        )
                    )
            return changes
        if (
            isinstance(before, list)
            and isinstance(after, list)
            and len(before) == len(after)
        ):
            return [
                item
                for index, (old, new) in enumerate(zip(before, after))
                for item in cls.compare(old, new, f"{path}/{index}")
            ]
        return [cls.record(path, before, after)]

    @classmethod
    def record(
        cls,
        path: str,
        before: JsonValue,
        after: JsonValue,
        before_exists: bool = True,
        after_exists: bool = True,
    ) -> JsonObject:
        """Distinguish a missing field from an explicitly authored null."""
        return {
            "path": path,
            "beforeExists": before_exists,
            "afterExists": after_exists,
            "before": cls.compact(before),
            "after": cls.compact(after),
        }

    @staticmethod
    def compact(value: JsonValue) -> JsonValue:
        """Summarize large source values while preserving a comparison fingerprint."""
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if len(encoded) <= 1500:
            return value
        return {
            "summarized": True,
            "kind": (
                "array"
                if isinstance(value, list)
                else "object" if isinstance(value, dict) else "scalar"
            ),
            "items": len(value) if isinstance(value, (list, dict, str)) else None,
            "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        }


@dataclass(frozen=True, slots=True)
class PreviewResult:
    """Retain the candidate and evaluation so a caller can stage exactly this revision."""

    candidate: JsonObject
    evaluation: ModelEvaluation
    report: JsonObject


class ChangePreview:
    """Compare one guarded candidate with its source and report coordinated effects."""

    def __init__(self, engine: ChangeEngine) -> None:
        """Use the same operation and validation contracts as committing a change."""
        self.engine: ChangeEngine = engine

    def evaluate(
        self, source: JsonObject, change: JsonObject, page: InspectionPage | None = None
    ) -> PreviewResult:
        """Evaluate authored and physical changes without writing source or artifacts."""
        selected = page or InspectionPage()
        candidate = self.engine.candidate(source, change)
        before = self.engine.validator.evaluate(source)
        after = self.engine.validator.evaluate(candidate)
        edits = [
            item
            for item in JsonChanges.compare(source, candidate)
            if Authoring.object(item)["path"] != "/revision"
        ]
        authored = self._authored_ids(edits)
        changed: list[JsonValue] = []
        unchanged: list[JsonValue] = []
        parts: list[JsonValue] = []
        related = self._related(source, candidate, authored)
        if before.resolved is not None and after.resolved is not None:
            old = {item.element_id: item for item in before.resolved.elements}
            new = {item.element_id: item for item in after.resolved.elements}
            quantities_before = self._volumes(before.resolved)
            quantities_after = self._volumes(after.resolved)
            for identity in sorted(old.keys() | new.keys()):
                entry = self._effect(
                    identity,
                    old.get(identity),
                    new.get(identity),
                    quantities_before.get(identity),
                    quantities_after.get(identity),
                )
                if entry["status"] != "unchanged":
                    entry["authoredDirectly"] = identity in authored
                    changed.append(entry)
                elif identity in related:
                    unchanged.append(
                        {
                            "id": identity,
                            "kind": new[identity].kind,
                            "name": new[identity].name,
                        }
                    )
            parts = self._parts(before.resolved, after.resolved)
        report: JsonObject = {
            "format": "home-design-change-preview-0.1",
            "changeId": change.get("id"),
            "description": change.get("description"),
            "baseRevision": source.get("revision"),
            "nextRevision": candidate.get("revision"),
            "written": False,
            "valid": after.report.is_valid,
            "sourceValidation": before.report.to_dict(),
            "validation": after.report.to_dict(),
            "geometryComparison": (
                "available"
                if before.resolved is not None and after.resolved is not None
                else "unavailable"
            ),
            "authoredChanges": selected.select(edits),
            "resolvedChanges": selected.select(changed),
            "unchangedRelated": selected.select(unchanged),
            "generatedPartChanges": selected.select(parts),
            "coordinationRequired": selected.select(self._coordination(after.report)),
            "exportsChecked": False,
        }
        return PreviewResult(candidate, after, report)

    @staticmethod
    def _authored_ids(edits: list[JsonValue]) -> set[str]:
        identities: set[str] = set()
        for value in edits:
            path = str(Authoring.object(value)["path"]).split("/")
            if len(path) > 2 and path[1] in {
                "elements",
                "anchors",
                "types",
                "materials",
                "levels",
                "relationships",
            }:
                identities.add(path[2].replace("~1", "/").replace("~0", "~"))
        return identities

    @staticmethod
    def _related(
        source: JsonObject, candidate: JsonObject, authored: set[str]
    ) -> set[str]:
        related = set(authored)
        for model in (source, candidate):
            index = ModelIndex(model)
            pending = list(authored)
            seen = set(authored)
            while pending:
                identity = pending.pop()
                for reference in index.incoming.get(identity, []):
                    if reference.owner_id not in seen:
                        seen.add(reference.owner_id)
                        pending.append(reference.owner_id)
                for reference in index.outgoing.get(identity, []):
                    related.add(reference.target_id)
                    if reference.role == "type":
                        related.update(
                            user.owner_id
                            for user in index.incoming.get(reference.target_id, [])
                            if user.role == "type"
                        )
            related.update(seen)
            for identity in seen:
                if identity in index.registries["relationships"]:
                    related.update(
                        reference.target_id for reference in index.outgoing[identity]
                    )
        return related

    @staticmethod
    def _volumes(model: ResolvedModel) -> dict[str, float]:
        rows = Authoring.array(ModelReports(model).schedules()["components"])
        return {
            str(Authoring.object(row)["id"]): number(
                Authoring.object(row)["volumeM3"], "scheduled volume"
            )
            for row in rows
        }

    @staticmethod
    def _effect(
        identity: str,
        before: ResolvedElement | None,
        after: ResolvedElement | None,
        old_volume: float | None,
        new_volume: float | None,
    ) -> JsonObject:
        old_data = before.data if before is not None else {}
        new_data = after.data if after is not None else {}
        geometry = before is None or after is None or before.meshes != after.meshes
        fields = JsonChanges.compare(old_data, new_data)
        status = (
            "added"
            if before is None
            else (
                "removed"
                if after is None
                else "changed" if geometry or before != after else "unchanged"
            )
        )
        return {
            "id": identity,
            "name": (
                after.name
                if after is not None
                else before.name if before is not None else identity
            ),
            "kind": (
                after.kind
                if after is not None
                else before.kind if before is not None else None
            ),
            "status": status,
            "geometryChanged": geometry,
            "quantity": {
                "unit": "m3",
                "before": old_volume,
                "after": new_volume,
                "changed": not math.isclose(
                    old_volume or 0, new_volume or 0, rel_tol=1e-9, abs_tol=1e-12
                ),
            },
            "changedProperties": [Authoring.object(item)["path"] for item in fields],
        }

    @classmethod
    def _parts(cls, before: ResolvedModel, after: ResolvedModel) -> list[JsonValue]:
        previous = {
            child.element_id: child
            for element in before.elements
            if element.kind in MemberAssemblies.CHILD_KINDS
            for child in MemberAssemblies.children(element)
        }
        current = {
            child.element_id: child
            for element in after.elements
            if element.kind in MemberAssemblies.CHILD_KINDS
            for child in MemberAssemblies.children(element)
        }
        changes: list[JsonValue] = []
        for identity in sorted(previous.keys() | current.keys()):
            old, new = previous.get(identity), current.get(identity)
            if old == new:
                continue
            changes.append(
                cls._effect(
                    identity,
                    old,
                    new,
                    (
                        sum(ModelReports.mesh_volume(mesh) for mesh in old.meshes) / 1e9
                        if old is not None
                        else None
                    ),
                    (
                        sum(ModelReports.mesh_volume(mesh) for mesh in new.meshes) / 1e9
                        if new is not None
                        else None
                    ),
                )
            )
        return changes

    @staticmethod
    def _coordination(report: ValidationReport) -> list[JsonValue]:
        return [
            {
                **diagnostic.to_dict(),
                "action": "Inspect the affected source object and revise its authored constraints or coordinated components; preserve supplied engineering limits.",
            }
            for diagnostic in report.diagnostics
            if diagnostic.severity in {"error", "warning"}
        ]
