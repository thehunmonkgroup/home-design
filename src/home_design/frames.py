"""Orthonormal coordinate transforms independent of host and path resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass

from home_design.construction import ConstructionGeometry
from home_design.json_types import JsonObject
from home_design.resolved import MeshData, Vec3


@dataclass(frozen=True, slots=True)
class LocalFrame:
    """An orthonormal right-handed coordinate frame in canonical millimetres."""

    origin: Vec3
    x: Vec3
    y: Vec3
    z: Vec3

    def vector(self, value: Vec3) -> Vec3:
        """Transform a local vector without translation."""
        return tuple3(
            [
                self.x[i] * value[0] + self.y[i] * value[1] + self.z[i] * value[2]
                for i in range(3)
            ]
        )

    def point(self, value: Vec3) -> Vec3:
        """Transform a local point into model coordinates."""
        direction = self.vector(value)
        return tuple3([self.origin[i] + direction[i] for i in range(3)])

    def mesh(self, mesh: MeshData) -> MeshData:
        """Transform a mesh while preserving material and role."""
        return MeshData(
            tuple(self.point(point) for point in mesh.vertices),
            mesh.faces,
            mesh.material_id,
            mesh.role,
        )

    def adjusted(self, offset: Vec3, rotation: Vec3) -> LocalFrame:
        """Offset in the host frame, then rotate about intrinsic X, Y and Z axes."""
        axes = [self.x, self.y, self.z]
        for index, degrees in enumerate(rotation):
            angle = math.radians(degrees)
            axis = axes[index]
            axes = [self.rotate_vector(value, axis, angle) for value in axes]
        return LocalFrame(self.point(offset), axes[0], axes[1], axes[2])

    @staticmethod
    def rotate_vector(value: Vec3, axis: Vec3, angle: float) -> Vec3:
        """Apply Rodrigues rotation around a unit axis."""
        cross = ConstructionGeometry.cross(axis, value)
        dot = sum(a * b for a, b in zip(axis, value))
        cosine, sine = math.cos(angle), math.sin(angle)
        if abs(cosine) < 1e-15:
            cosine = 0.0
        if abs(sine) < 1e-15:
            sine = 0.0
        return tuple3(
            [
                value[i] * cosine + cross[i] * sine + axis[i] * dot * (1 - cosine)
                for i in range(3)
            ]
        )

    def to_dict(self) -> JsonObject:
        """Serialize the origin and local axes for inspection and exporters."""
        return {
            "origin": list(self.origin),
            "x": list(self.x),
            "y": list(self.y),
            "z": list(self.z),
        }


def tuple3(values: list[float]) -> Vec3:
    """Convert a computed three-vector to its fixed-length typed representation."""
    return values[0], values[1], values[2]
