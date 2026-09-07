"""Authored cut dimensions and directional material margins in explicit host frames."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

import manifold3d
import numpy as np

from home_design.components import ConstructionResolver
from home_design.construction import Authoring
from home_design.diagnostics import Diagnostic
from home_design.errors import ResolutionError
from home_design.layers import LayerAssembly
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.member_assemblies import MemberAssemblies
from home_design.placement import HostPlacement, LocalFrame, tuple3
from home_design.resolved import MeshData, ResolvedElement, ResolvedModel, Vec3
from home_design.solids import SolidOperations


class CutLimits:
    """Check supplied geometric limits without supplying structural rules or nominal dimensions."""

    LENGTH_TOLERANCE_MM: float = 1e-6

    @staticmethod
    def resolve(construction: ConstructionResolver, source: JsonObject) -> JsonObject:
        """Resolve measurement frames against the same host as the owned cut."""
        limits: JsonObject = {}
        for key, value in Authoring.object(source.get("limits", {})).items():
            specification = Authoring.object(value)
            locator = Authoring.object(specification["host"])
            if locator["element"] != source["host"]:
                raise ResolutionError(
                    "A cut limit must measure its own penetration host"
                )
            frame = HostPlacement(construction.context).resolve(locator)
            host = construction.context.resolve_component(
                Authoring.text(source["host"])
            )
            if host.kind == "roof" and "face" not in locator:
                raise ResolutionError("A roof cut limit requires an explicit face")
            limits[key] = {**specification, "frame": frame.to_dict()}
        return limits

    @staticmethod
    def scope(host: ResolvedElement, locator: JsonObject) -> tuple[MeshData, ...]:
        """Select an individual member, roof face and/or layer without broadening the check."""
        meshes = host.meshes
        if "part" in locator:
            if host.kind not in MemberAssemblies.KINDS:
                raise ResolutionError(
                    "A scoped cut limit requires a generated member assembly"
                )
            meshes = tuple(
                mesh for mesh in meshes if mesh.role == f"part:{locator['part']}"
            )
        if "face" in locator:
            meshes = tuple(
                mesh
                for mesh in meshes
                if mesh.role.startswith(f"roof-face:{locator['face']}:")
            )
        if "layer" in locator:
            index = LayerAssembly.index(
                host.data.get("layers", []), locator["layer"], f"Host {host.element_id}"
            )
            meshes = tuple(
                mesh for mesh in meshes if mesh.role.endswith(f"layer:{index}")
            )
        return meshes

    @staticmethod
    def extents(mesh: MeshData, frame: LocalFrame) -> dict[str, float]:
        """Measure actual local projected dimensions, including oblique or notched boundaries."""
        result: dict[str, float] = {}
        for name, axis in zip(("x", "y", "z"), (frame.x, frame.y, frame.z)):
            coordinates = [
                sum((point[i] - frame.origin[i]) * axis[i] for i in range(3))
                for point in mesh.vertices
            ]
            result[name] = max(coordinates) - min(coordinates)
        return result

    @staticmethod
    def sweep(mesh: MeshData, displacement: Vec3) -> manifold3d.Manifold:
        """Sweep every boundary triangle along an interval, preserving concavity and internal holes.

        The union of the source solid and its swept boundary is the exact
        polyhedral translation sweep. Each boundary triangle produces a convex
        triangular prism; the whole source is never replaced by its convex hull.
        """
        original = SolidOperations.solid(mesh)
        triangles = original.to_mesh64()
        pieces = [original]
        for face in triangles.tri_verts:
            points = [
                tuple(float(value) for value in triangles.vert_properties[index][:3])
                for index in face
            ]
            shifted = [
                tuple(point[i] + displacement[i] for i in range(3)) for point in points
            ]
            prism = manifold3d.Manifold.hull_points(
                cast(
                    np.ndarray[tuple[int, Literal[3]], np.dtype[np.double]],
                    np.asarray([*points, *shifted], dtype=np.float64),
                )
            )
            if prism.status() != manifold3d.Error.NoError:
                raise ResolutionError("Cut margin boundary sweep failed")
            if not prism.is_empty():
                pieces.append(prism)
        result = manifold3d.Manifold.batch_boolean(pieces, manifold3d.OpType.Add)
        if result.status() != manifold3d.Error.NoError:
            raise ResolutionError("Cut margin sweep union failed")
        return result

    @classmethod
    def measurements(
        cls,
        specification: JsonObject,
        frame: LocalFrame,
        removed: MeshData,
        original: MeshData,
        restored: MeshData,
    ) -> JsonObject:
        """Compare cut extents and directional material reserves with only the supplied limits."""
        cut_size, host_size = cls.extents(removed, frame), cls.extents(original, frame)
        checks: list[JsonValue] = []
        for measure in ("maximumExtent", "maximumExtentFraction"):
            for axis, value in Authoring.object(specification.get(measure, {})).items():
                limit = number(value, measure)
                actual = (
                    cut_size[axis]
                    if measure == "maximumExtent"
                    else cut_size[axis] / host_size[axis]
                )
                tolerance = (
                    cls.LENGTH_TOLERANCE_MM if measure == "maximumExtent" else 1e-9
                )
                checks.append(
                    {
                        "measure": measure,
                        "axis": axis,
                        "actual": actual,
                        "limit": limit,
                        "status": (
                            "satisfied" if actual <= limit + tolerance else "violated"
                        ),
                    }
                )
        for direction, value in Authoring.object(
            specification.get("minimumEdgeDistance", {})
        ).items():
            distance = number(value, "minimum edge distance")
            local_axis = {"X": frame.x, "Y": frame.y, "Z": frame.z}[direction[-1]]
            sign = 1 if direction.startswith("positive") else -1
            swept = cls.sweep(
                removed, tuple3([sign * distance * value for value in local_axis])
            )
            outside = swept - SolidOperations.solid(restored)
            if outside.status() != manifold3d.Error.NoError:
                raise ResolutionError("Cut margin containment failed")
            outside_volume = max(0.0, outside.volume())
            checks.append(
                {
                    "measure": "minimumEdgeDistance",
                    "direction": direction,
                    "limit": distance,
                    "outsideVolumeMm3": outside_volume,
                    "status": (
                        "satisfied"
                        if outside_volume <= SolidOperations.OUTPUT_VOLUME_TOLERANCE_MM3
                        else "violated"
                    ),
                }
            )
        return {
            "cutExtentMm": dict(cut_size),
            "hostExtentMm": dict(host_size),
            "checks": checks,
            "status": (
                "violated"
                if any(
                    Authoring.object(check)["status"] == "violated" for check in checks
                )
                else "satisfied"
            ),
        }

    @classmethod
    def apply(
        cls, elements: dict[str, ResolvedElement], originals: dict[str, ResolvedElement]
    ) -> None:
        """Evaluate each removed volume after all cuts, retaining neighboring openings as boundaries."""
        for cut in tuple(elements.values()):
            if cut.kind != "penetration" or "limits" not in cut.data:
                continue
            host_id = Authoring.text(cut.data["host"])
            results: JsonObject = {}
            for key, value in Authoring.object(cut.data["limits"]).items():
                specification = Authoring.object(value)
                locator = Authoring.object(specification["host"])
                original = SolidOperations.union(
                    cls.scope(originals[host_id], locator), None, "limitHost"
                )
                if original is None:
                    raise ResolutionError(
                        "A cut limit requires nonempty selected host material"
                    )
                removed = SolidOperations.intersection(cut.meshes[0], original)
                if removed is None:
                    raise ResolutionError(
                        "A cut limit must select material affected by its penetration"
                    )
                retained = cls.scope(elements[host_id], locator)
                restored = SolidOperations.union(
                    [*retained, removed], None, "limitHost"
                )
                if restored is None:
                    raise ResolutionError("A cut limit has no reference host material")
                frame_data = Authoring.object(specification["frame"])
                frame = LocalFrame(
                    *(
                        vector3(frame_data[name], name)
                        for name in ("origin", "x", "y", "z")
                    )
                )
                results[key] = {
                    "host": (
                        f"{host_id}/member/{locator['part']}"
                        if "part" in locator
                        else host_id
                    ),
                    "frame": frame.to_dict(),
                    "severity": specification.get("severity", "error"),
                    **(
                        {"reference": specification["reference"]}
                        if "reference" in specification
                        else {}
                    ),
                    **cls.measurements(
                        specification, frame, removed, original, restored
                    ),
                }
            elements[cut.element_id] = replace(
                cut, data={**cut.data, "limitResults": results}
            )

    @staticmethod
    def diagnostics(model: ResolvedModel) -> list[Diagnostic]:
        """Report authored limit violations with precise source identity and measurement names."""
        diagnostics: list[Diagnostic] = []
        for cut in model.elements:
            for key, value in Authoring.object(
                cut.data.get("limitResults", {})
            ).items():
                result = Authoring.object(value)
                for item in Authoring.array(result["checks"]):
                    check = Authoring.object(item)
                    if check["status"] != "violated":
                        continue
                    dimension = check.get("axis", check.get("direction"))
                    evidence = (
                        f"outside material {check['outsideVolumeMm3']} mm3"
                        if "outsideVolumeMm3" in check
                        else f"measured {check['actual']}"
                    )
                    diagnostics.append(
                        Diagnostic(
                            "warning" if result["severity"] == "warning" else "error",
                            "penetration.limit-violated",
                            f"{cut.element_id} on {result['host']}: {check['measure']} {dimension} limit {check['limit']}, {evidence}",
                            path=f"/elements/{cut.element_id}/limits/{key}/{check['measure']}/{dimension}",
                            subject_id=cut.element_id,
                        )
                    )
        return diagnostics
