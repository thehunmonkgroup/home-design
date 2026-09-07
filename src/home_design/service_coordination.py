"""Authored service interference and clearance checks against final physical stock."""

from __future__ import annotations

from dataclasses import replace

import manifold3d

from home_design.construction import Authoring
from home_design.diagnostics import Diagnostic
from home_design.errors import ResolutionError
from home_design.json_types import JsonObject, JsonValue
from home_design.member_assemblies import MemberAssemblies
from home_design.mounted_parts import CoordinationVolumes, MountedParts
from home_design.resolved import MeshData, ResolvedElement, ResolvedModel
from home_design.solids import SolidOperations


class ServiceCoordination:
    """Keep material collisions independent of installation-clearance exceptions."""

    @staticmethod
    def physical_parts(
        elements: dict[str, ResolvedElement],
    ) -> tuple[ResolvedElement, ...]:
        """Expand each generated member exactly once and omit all nonphysical geometry."""
        return tuple(
            part
            for element in sorted(elements.values(), key=lambda item: item.element_id)
            if element.kind not in CoordinationVolumes.NON_OBSTACLES
            for part in (
                MemberAssemblies.children(element)
                if element.kind in MemberAssemblies.KINDS
                else (element,)
            )
            if part.meshes
        )

    @staticmethod
    def overlap(first: tuple[MeshData, ...], second: tuple[MeshData, ...]) -> float:
        """Measure unioned stock intersection without serializing diagnostic-only geometry."""
        pieces: list[manifold3d.Manifold] = []
        for a in first:
            for b in second:
                if any(
                    max(point[axis] for point in a.vertices)
                    <= min(point[axis] for point in b.vertices)
                    or max(point[axis] for point in b.vertices)
                    <= min(point[axis] for point in a.vertices)
                    for axis in range(3)
                ):
                    continue
                overlap = SolidOperations.solid(a) ^ SolidOperations.solid(b)
                if overlap.status() != manifold3d.Error.NoError:
                    raise ResolutionError("Service coordination intersection failed")
                if overlap.volume() > SolidOperations.OUTPUT_VOLUME_TOLERANCE_MM3:
                    pieces.append(overlap)
        if not pieces:
            return 0.0
        combined = pieces[0]
        for piece in pieces[1:]:
            combined = combined + piece
        if combined.status() != manifold3d.Error.NoError:
            raise ResolutionError("Service coordination intersection union failed")
        return combined.volume()

    @classmethod
    def exclusions(
        cls,
        service: ResolvedElement,
        elements: dict[str, ResolvedElement],
        specification: JsonObject,
    ) -> dict[str, str]:
        """Resolve explicit allowances and connected covers/interfaces/supports only for clearance."""
        excluded: dict[str, str] = {}
        for value in Authoring.array(specification.get("allow", [])):
            target = MountedParts.reference(elements, Authoring.object(value))
            if target.kind in CoordinationVolumes.NON_OBSTACLES or not target.meshes:
                raise ResolutionError(
                    "A service clearance allowance requires surviving physical stock"
                )
            parts = (
                MemberAssemblies.children(target)
                if target.kind in MemberAssemblies.KINDS
                else (target,)
            )
            excluded.update({part.element_id: "authored" for part in parts})
        attached = {service.element_id}
        for candidate in elements.values():
            if (
                candidate.kind == "serviceInsulation"
                and candidate.data.get("host") == service.element_id
            ):
                attached.add(candidate.element_id)
                excluded.setdefault(candidate.element_id, "hostedInsulation")
        for candidate in elements.values():
            if candidate.kind == "envelopePart" and any(
                identity in attached
                for identity in Authoring.array(
                    candidate.data.get("interfaceServiceIds", [])
                )
            ):
                excluded.setdefault(candidate.element_id, "serviceInterface")
            if candidate.kind in {"hardware", "fastenerGroup"} and any(
                identity in attached
                for identity in Authoring.array(
                    candidate.data.get("participantIds", [])
                )
            ):
                excluded.setdefault(candidate.element_id, "serviceSupport")
        return dict(sorted(excluded.items()))

    @classmethod
    def refresh(cls, elements: dict[str, ResolvedElement]) -> None:
        """Check only authored services, using cuts and cavity composition already applied."""
        checked = [
            element
            for element in elements.values()
            if "coordinationChecks" in element.data
        ]
        if not checked:
            return
        parts = cls.physical_parts(elements)
        for service in checked:
            specification = Authoring.object(service.data["coordinationChecks"])
            clearance = Authoring.object(specification.get("clearance", {}))
            if clearance and service.kind not in {"serviceRoute", "serviceFitting"}:
                raise ResolutionError(
                    "Service clearance checks require a route or fitting construction volume"
                )
            excluded = cls.exclusions(service, elements, clearance) if clearance else {}
            collisions: list[JsonValue] = []
            obstructions: list[JsonValue] = []
            for candidate in parts:
                if candidate.element_id == service.element_id:
                    continue
                volume = cls.overlap(service.meshes, candidate.meshes)
                if volume > SolidOperations.OUTPUT_VOLUME_TOLERANCE_MM3:
                    collisions.append(
                        {"element": candidate.element_id, "volumeMm3": volume}
                    )
                    continue
                if not clearance or candidate.element_id in excluded:
                    continue
                volume = cls.overlap(
                    (service.construction_volumes["clearance"],), candidate.meshes
                )
                if volume > SolidOperations.OUTPUT_VOLUME_TOLERANCE_MM3:
                    obstructions.append(
                        {"element": candidate.element_id, "volumeMm3": volume}
                    )
            results: JsonObject = {
                "interference": {
                    "status": "clashing" if collisions else "clear",
                    "collisions": collisions,
                }
            }
            if clearance:
                results["clearance"] = {
                    "status": "blocked" if obstructions else "clear",
                    "obstructions": obstructions,
                    "exclusions": [
                        {"element": identity, "reason": reason}
                        for identity, reason in excluded.items()
                    ],
                }
            elements[service.element_id] = replace(
                service, data={**service.data, "serviceCoordination": results}
            )

    @staticmethod
    def diagnostics(model: ResolvedModel) -> list[Diagnostic]:
        """Publish each obstruction with source check location and the exact affected member ID."""
        diagnostics: list[Diagnostic] = []
        for service in model.elements:
            if "serviceCoordination" not in service.data:
                continue
            specification = Authoring.object(service.data["coordinationChecks"])
            results = Authoring.object(service.data["serviceCoordination"])
            for check, field, code in (
                ("interference", "collisions", "service.interference"),
                ("clearance", "obstructions", "service.clearance-obstructed"),
            ):
                result = Authoring.object(results.get(check, {}))
                for value in Authoring.array(result.get(field, [])):
                    obstacle = Authoring.object(value)
                    severity = (
                        specification["interference"]
                        if check == "interference"
                        else Authoring.object(specification["clearance"])["severity"]
                    )
                    diagnostics.append(
                        Diagnostic(
                            "warning" if severity == "warning" else "error",
                            code,
                            f"{service.element_id} {check} intersects {obstacle['element']} ({obstacle['volumeMm3']} mm3)",
                            path=f"/elements/{service.element_id}/coordinationChecks/{check}",
                            subject_id=service.element_id,
                        )
                    )
        return diagnostics
