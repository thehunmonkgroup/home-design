"""Shared straight-member frames and explicitly authored end-cut geometry."""

from __future__ import annotations

import math

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject
from home_design.placement import LocalFrame, tuple3
from home_design.resolved import MeshData, Vec3
from home_design.solids import SolidOperations
from home_design.part_contracts import GeneratedMember


class MemberGeometry:
    """Keep stock coordinates and final cuts consistent across authored assemblies."""

    @staticmethod
    def frame(start: Vec3, end: Vec3, roll: float = 0) -> LocalFrame:
        """Return the same rolled stock frame used by straight member geometry."""
        direction = ConstructionGeometry.unit(
            tuple3([end[index] - start[index] for index in range(3)])
        )
        reference: Vec3 = (0, 1, 0) if abs(direction[2]) > 0.999 else (0, 0, 1)
        across = ConstructionGeometry.unit(
            ConstructionGeometry.cross(reference, direction)
        )
        up = ConstructionGeometry.cross(direction, across)
        return LocalFrame(start, across, up, direction).adjusted(
            (0, 0, 0), (0, 0, roll)
        )

    @staticmethod
    def end_cuts(
        mesh: MeshData, frame: LocalFrame, length: float, cuts: JsonObject
    ) -> MeshData:
        """Trim stock with inward-facing start/end planes in its local section frame.

        :param cuts: Start/end specifications with an inward normal and normal offset.
        :raises ResolutionError: When a cut removes the whole member or faces outward.
        """
        for end, value in sorted(cuts.items()):
            cut = Authoring.object(value, "end cut")
            normal = vector3(cut["normal"], "end cut normal")
            if not math.isclose(
                math.sqrt(sum(value * value for value in normal)), 1, abs_tol=1e-6
            ):
                raise ResolutionError("End-cut normal must be a unit vector")
            sign = 1 if end == "start" else -1
            if normal[2] * sign <= 1e-9:
                raise ResolutionError(f"The {end} cut normal must face into the member")
            offset = number(cut.get("offset", 0), "end cut offset")
            station = 0.0 if end == "start" else length
            origin = frame.point(
                (normal[0] * offset, normal[1] * offset, station + normal[2] * offset)
            )
            result = SolidOperations.clip_plane(mesh, origin, frame.vector(normal))
            if result is None:
                raise ResolutionError(f"The {end} cut removes the entire member")
            mesh = result
        return mesh

    @classmethod
    def cut_record(
        cls, mesh: MeshData, record: JsonObject, cuts: JsonObject
    ) -> MeshData:
        """Apply the same cut controls to a generated member's retained stock frame."""
        member = GeneratedMember.from_dict(record)
        result = cls.end_cuts(mesh, member.frame, math.dist(*member.axis), cuts)
        record["endCuts"] = cuts
        record["netVolumeMm3"] = SolidOperations.volume(result)
        return result

    @classmethod
    def record(
        cls,
        key: str,
        type_id: str,
        role: str,
        start: Vec3,
        end: Vec3,
        section: JsonObject,
        mesh: MeshData,
        roll: float = 0,
    ) -> JsonObject:
        """Serialize a stock axis, section frame and final physical volume."""
        frame = cls.frame(start, end, roll)
        return {
            "key": key,
            "typeId": type_id,
            "role": role,
            "axis": [list(start), list(end)],
            "section": section,
            "roll": roll,
            "sectionFrame": {
                "x": list(frame.x),
                "y": list(frame.y),
                "z": list(frame.z),
            },
            "lengthMm": math.dist(start, end),
            "stockLengthMm": math.dist(start, end),
            "netVolumeMm3": SolidOperations.volume(mesh),
        }
