"""Material-filled inspection cuts derived from the shared drawing section geometry."""

from __future__ import annotations

from home_design.adapters.drawings import DrawingExporter
from home_design.geometry import triangulate_polygon
from home_design.resolved import Face, MeshData, Vec3


class RenderSections:
    """Generate temporary planar caps without changing physical model quantities."""

    @staticmethod
    def caps(
        mesh: MeshData, sections: tuple[tuple[int, float, bool], ...]
    ) -> tuple[MeshData, ...]:
        """Return outward-facing material sections with holes preserved.

        :param mesh: Final resolved stock after physical cuts and cavity composition.
        :param sections: Axis index, canonical position and whether to retain below.
        :returns: Planar display surfaces, independent of canonical material bodies.
        """
        result: list[MeshData] = []
        for axis, position, below in sections:
            coordinates = [point[axis] for point in mesh.vertices]
            if not coordinates or not min(coordinates) < position < max(coordinates):
                continue
            vertices: list[Vec3] = []
            faces: list[Face] = []
            for polygon in DrawingExporter.section_polygons(mesh, axis, position):
                for triangle in triangulate_polygon(polygon):
                    offset = len(vertices)
                    for u, v in list(triangle.exterior.coords)[:3]:
                        cut = position + (-0.005 if below else 0.005)
                        point: Vec3 = (
                            (cut, u, v)
                            if axis == 0
                            else (u, cut, v) if axis == 1 else (u, v, cut)
                        )
                        vertices.append(point)
                    a, b, c = vertices[-3:]
                    ab = [b[i] - a[i] for i in range(3)]
                    ac = [c[i] - a[i] for i in range(3)]
                    normal = (
                        ab[(axis + 1) % 3] * ac[(axis + 2) % 3]
                        - ab[(axis + 2) % 3] * ac[(axis + 1) % 3]
                    )
                    faces.append(
                        (offset, offset + 1, offset + 2)
                        if (normal > 0) == below
                        else (offset, offset + 2, offset + 1)
                    )
            if faces:
                result.append(
                    MeshData(tuple(vertices), tuple(faces), mesh.material_id, mesh.role)
                )
        return tuple(result)
