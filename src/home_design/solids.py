"""Deterministic double-precision solid operations with material provenance."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

import manifold3d
import numpy as np
from shapely.errors import GEOSException

from home_design.errors import ResolutionError
from home_design.constants import GEOMETRY_TOLERANCE_MM
from home_design.construction import ConstructionGeometry
from home_design.geometry import triangulate_planar
from home_design.resolved import Face, MeshData, Vec3
from home_design.solid_surfaces import SolidSurfaces

LOGGER = logging.getLogger(__name__)


class SolidOperations:
    """Perform real solid cuts and intersections on closed component meshes."""

    OUTPUT_VOLUME_TOLERANCE_MM3: float = 1e-6

    @classmethod
    def _volume_tolerance(cls, expected: float) -> float:
        """Use the same absolute and relative material tolerance for every serialization path."""
        return max(cls.OUTPUT_VOLUME_TOLERANCE_MM3, abs(expected) * 1e-9)

    @classmethod
    def _matches_volume(cls, mesh: MeshData, expected: float) -> bool:
        """Require both triangle integration and native reimport to preserve the reference volume."""
        tolerance = cls._volume_tolerance(expected)
        return (
            abs(cls._triangle_volume(mesh) - expected) <= tolerance
            and abs(cls.volume(mesh) - expected) <= tolerance
        )

    @staticmethod
    def solid(mesh: MeshData) -> manifold3d.Manifold:
        """Convert outward-wound polygon faces to a validated solid.

        :param mesh: Closed mesh in canonical millimetres.
        :returns: Double-precision solid, retaining submillimetre coordinates.
        :raises ResolutionError: For nonfinite, open or invalid input geometry.
        """
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        if not len(vertices) or not np.isfinite(vertices).all():
            raise ResolutionError("Solid input requires finite vertices")
        triangles: list[Face] = []
        for face in mesh.faces:
            if len(face) < 3 or any(
                index < 0 or index >= len(vertices) for index in face
            ):
                raise ResolutionError("Solid input has an invalid face index")
            if len(face) == 3:
                triangles.append(face)
            else:
                triangles.extend(
                    tuple(face[index] for index in triangle)
                    for triangle in triangulate_planar(
                        [mesh.vertices[index] for index in face]
                    )
                )
        solid = manifold3d.Manifold(
            manifold3d.Mesh64(
                vert_properties=vertices,
                tri_verts=np.asarray(triangles, dtype=np.uint64).reshape((-1, 3)),
            )
        )
        if solid.status() != manifold3d.Error.NoError or solid.volume() <= 0:
            raise ResolutionError(
                f"Solid input is not a closed positive volume: {solid.status()}"
            )
        return solid

    @classmethod
    def mesh(
        cls, solid: manifold3d.Manifold, material: str | None, role: str
    ) -> MeshData | None:
        """Serialize a canonical mesh only when its volume survives reimport."""
        if solid.status() != manifold3d.Error.NoError:
            raise ResolutionError(f"Solid operation failed: {solid.status()}")
        if (
            solid.is_empty()
            or solid.volume() <= SolidOperations.OUTPUT_VOLUME_TOLERANCE_MM3
        ):
            return None
        expected = solid.volume()
        for normalize in (True, False):
            candidate = solid.as_original().simplify(0) if normalize else solid
            mesh = cls._canonical_mesh(candidate, material, role)
            try:
                if cls._matches_volume(mesh, expected):
                    return mesh
            except ResolutionError:
                continue
        try:
            mesh = cls._surface_mesh(solid, material, role)
            if cls._matches_volume(mesh, expected):
                return mesh
        except (ResolutionError, GEOSException, ValueError) as error:
            LOGGER.debug("Planar boundary normalization failed for %s: %s", role, error)
        raise ResolutionError(
            "Solid output cannot preserve its volume through mesh serialization"
        )

    @classmethod
    def _surface_mesh(
        cls, solid: manifold3d.Manifold, material: str | None, role: str
    ) -> MeshData:
        """Cancel coincident surface folds without welding independent connected shells."""
        vertices: list[Vec3] = []
        faces: list[Face] = []
        for component in solid.decompose():
            if component.volume() <= cls.OUTPUT_VOLUME_TOLERANCE_MM3:
                continue
            mesh = SolidSurfaces.regularize(
                cls._canonical_mesh(component, material, role)
            )
            if not mesh.faces:
                continue
            if not cls._matches_volume(mesh, component.volume()):
                raise ResolutionError(
                    "Planar boundary normalization changed material volume"
                )
            offset = len(vertices)
            vertices.extend(mesh.vertices)
            faces.extend(tuple(index + offset for index in face) for face in mesh.faces)
        if not vertices:
            raise ResolutionError("Planar boundary normalization produced no material")
        return MeshData(tuple(vertices), tuple(faces), material, role)

    @staticmethod
    def _triangle_volume(mesh: MeshData) -> float:
        """Measure signed triangle volume relative to a nearby reference vertex."""
        origin = mesh.vertices[0]
        volumes: list[float] = []
        for face in mesh.faces:
            a, b, c = (
                tuple(point[i] - origin[i] for i in range(3))
                for point in (mesh.vertices[index] for index in face)
            )
            volumes.append(
                (
                    a[0] * (b[1] * c[2] - b[2] * c[1])
                    + a[1] * (b[2] * c[0] - b[0] * c[2])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])
                )
                / 6
            )
        return math.fsum(volumes)

    @staticmethod
    def _canonical_mesh(
        solid: manifold3d.Manifold, material: str | None, role: str
    ) -> MeshData:
        """Order vertices and oriented triangles without modifying the solid."""
        output = solid.to_mesh64()
        original: list[Vec3] = [
            (float(point[0]), float(point[1]), float(point[2]))
            for point in output.vert_properties
        ]
        ordered = sorted(enumerate(original), key=lambda item: (item[1], item[0]))
        vertices = tuple(point for _, point in ordered)
        lookup = {
            original_index: index for index, (original_index, _) in enumerate(ordered)
        }
        faces: list[Face] = []
        for triangle in output.tri_verts:
            indices = tuple(lookup[int(index)] for index in triangle)
            faces.append(min(indices[index:] + indices[:index] for index in range(3)))
        return MeshData(vertices, tuple(sorted(faces)), material, role)

    @classmethod
    def difference(
        cls, source: MeshData, cutters: Sequence[MeshData]
    ) -> MeshData | None:
        """Subtract cutters while keeping the source material and mesh role."""
        LOGGER.debug("Subtracting %d cutters from %s", len(cutters), source.role)
        result = cls.solid(source)
        for cutter in cutters:
            result = result - cls.solid(cutter)
        return cls.mesh(result, source.material_id, source.role)

    @classmethod
    def intersection(
        cls, a: MeshData, b: MeshData, role: str | None = None
    ) -> MeshData | None:
        """Return only shared volume, inheriting material from the first operand."""
        if any(
            max(point[axis] for point in a.vertices)
            <= min(point[axis] for point in b.vertices)
            or max(point[axis] for point in b.vertices)
            <= min(point[axis] for point in a.vertices)
            for axis in range(3)
        ):
            return None
        return cls.mesh(cls.solid(a) ^ cls.solid(b), a.material_id, role or a.role)

    @classmethod
    def partition(
        cls, source: MeshData, cutter: MeshData
    ) -> tuple[MeshData | None, MeshData | None]:
        """Return remaining and removed material from one shared Boolean partition.

        Prefer a native split; retry the equivalent removed difference when
        the split intersection cannot survive volume-checked serialization.
        """
        if any(
            max(point[axis] for point in source.vertices)
            <= min(point[axis] for point in cutter.vertices)
            or max(point[axis] for point in cutter.vertices)
            <= min(point[axis] for point in source.vertices)
            for axis in range(3)
        ):
            return source, None
        original = cls.solid(source)
        removed, remaining = original.split(cls.solid(cutter))
        retained_mesh = cls.mesh(remaining, source.material_id, source.role)
        try:
            removed_mesh = cls.mesh(removed, source.material_id, source.role)
        except ResolutionError:
            alternative = original - remaining
            tolerance = max(
                cls.OUTPUT_VOLUME_TOLERANCE_MM3,
                original.volume() * 1e-12,
                removed.volume() * 1e-9,
            )
            if abs(alternative.volume() - removed.volume()) > tolerance:
                raise ResolutionError(
                    "Solid partition cannot preserve removed material volume"
                ) from None
            removed_mesh = cls.mesh(alternative, source.material_id, source.role)
        return retained_mesh, removed_mesh

    @classmethod
    def clip_plane(
        cls, source: MeshData, origin: Vec3, normal: Vec3
    ) -> MeshData | None:
        """Keep the half of a solid in the normal direction from an authored plane."""
        direction = ConstructionGeometry.unit(normal)
        offset = sum(origin[index] * direction[index] for index in range(3))
        return cls.mesh(
            cls.solid(source).trim_by_plane(direction, offset),
            source.material_id,
            source.role,
        )

    @classmethod
    def union(
        cls, meshes: Sequence[MeshData], material: str | None, role: str
    ) -> MeshData | None:
        """Combine volumes for a single explicit material or nonphysical cutter."""
        result = manifold3d.Manifold()
        for mesh in meshes:
            result = result + cls.solid(mesh)
        return cls.mesh(result, material, role)

    @classmethod
    def volume(cls, mesh: MeshData) -> float:
        """Measure validated positive volume in cubic millimetres."""
        return cls.solid(mesh).volume()

    @staticmethod
    def planar_area(meshes: Sequence[MeshData], origin: Vec3, normal: Vec3) -> float:
        """Measure outward faces on a specified plane, excluding recess bottoms."""
        area = 0.0
        for mesh in meshes:
            for face in mesh.faces:
                points = [mesh.vertices[index] for index in face]
                if any(
                    abs(sum((point[i] - origin[i]) * normal[i] for i in range(3)))
                    > GEOMETRY_TOLERANCE_MM
                    for point in points
                ):
                    continue
                for index in range(1, len(points) - 1):
                    a, b, c = points[0], points[index], points[index + 1]
                    edge_a: Vec3 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                    edge_b: Vec3 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                    cross = ConstructionGeometry.cross(edge_a, edge_b)
                    area += max(0, sum(cross[i] * normal[i] for i in range(3))) / 2
        return area
