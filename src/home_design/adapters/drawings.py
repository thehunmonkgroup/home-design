"""Dimensioned orthographic and material-section SVG sheets from resolved solids."""

from __future__ import annotations

import html
import math
from pathlib import Path

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union

from home_design.construction import Authoring
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject
from home_design.resolved import MeshData, ResolvedModel, Vec2, Vec3


class DrawingExporter:
    """Generate reproducible drawings without introducing a second design source."""

    WIDTH: int = 1000
    VIEW_HEIGHT: int = 650

    def export(self, model: ResolvedModel, destination: Path) -> None:
        """Write configured cuts/views, or storey plans and two exterior elevations."""
        views = [Authoring.object(view) for view in model.drawings] or self._defaults(
            model
        )
        height = 100 + self.VIEW_HEIGHT * len(views)
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.WIDTH}" height="{height}" viewBox="0 0 {self.WIDTH} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            "<style>text{font-family:Arial,sans-serif;fill:#26332e}.dimension{stroke:#52665c;stroke-width:1;fill:none}.body{stroke:#37433c;stroke-width:.65;stroke-linejoin:round}</style>",
            f'<text x="40" y="35" font-size="22">{html.escape(str(model.project.get("name")))}</text>',
            f'<text x="40" y="60" font-size="13">Revision {model.source_revision} · dimensions in mm · coordination drawings</text>',
        ]
        for index, view in enumerate(views):
            parts.append(
                f'<g transform="translate(0,{90 + index * self.VIEW_HEIGHT})">'
            )
            parts.extend(self._view(model, view))
            parts.append("</g>")
        parts.append("</svg>")
        destination.write_text("\n".join(parts) + "\n", encoding="utf-8")

    def _defaults(self, model: ResolvedModel) -> list[JsonObject]:
        views: list[JsonObject] = []
        for level_id, value in model.levels.items():
            if isinstance(value, dict) and value.get("kind") == "storey":
                views.append(
                    {
                        "id": f"{level_id}.plan",
                        "name": f"{value.get('name')} — plan cut",
                        "kind": "section",
                        "axis": "z",
                        "position": number(value.get("elevation"), "storey elevation")
                        + 1200,
                    }
                )
        vertices = [
            vertex
            for element in model.elements
            if element.kind != "terrain"
            for mesh in element.meshes
            for vertex in mesh.vertices
        ]
        if vertices:
            views.extend(
                [
                    {
                        "id": "view.south",
                        "name": "South elevation",
                        "kind": "projection",
                        "axis": "y",
                        "position": min(point[1] for point in vertices) - 1,
                    },
                    {
                        "id": "view.east",
                        "name": "East elevation",
                        "kind": "projection",
                        "axis": "x",
                        "position": max(point[0] for point in vertices) + 1,
                    },
                ]
            )
        return views

    def _view(self, model: ResolvedModel, view: JsonObject) -> list[str]:
        axis = {"x": 0, "y": 1, "z": 2}[Authoring.text(view.get("axis"))]
        position = number(view.get("position"), "drawing plane")
        include = view.get("includeKinds")
        items: list[tuple[float, list[Polygon], str, str]] = []
        for element in model.elements:
            if element.kind in {"space", "opening", "load", "detail"}:
                continue
            if isinstance(include, list) and element.kind not in include:
                continue
            if include is None and element.kind == "terrain":
                continue
            for mesh in element.meshes:
                polygons = (
                    self.section_polygons(mesh, axis, position)
                    if view.get("kind") == "section"
                    else self._project(mesh, axis)
                )
                if not polygons:
                    continue
                material = Authoring.object(
                    model.materials.get(mesh.material_id or "", {})
                )
                appearance = Authoring.object(material.get("appearance", {}))
                color = str(
                    appearance.get(
                        "color", "#c7dce3" if "glass" in mesh.role else "#deded7"
                    )
                )
                depth = sum(vertex[axis] for vertex in mesh.vertices) / len(
                    mesh.vertices
                )
                items.append(
                    (abs(position - depth), polygons, color, element.element_id)
                )
        title = html.escape(str(view.get("name")))
        parts = [
            f'<text x="40" y="25" font-size="18">{title}</text>',
            f'<text x="40" y="46" font-size="12">{html.escape(str(view.get("kind")))} · {"XYZ"[axis]} = {position:g} mm</text>',
        ]
        if not items:
            return [
                *parts,
                '<text x="40" y="90" font-size="14">No geometry intersects this view.</text>',
            ]
        bounds = unary_union(
            [polygon for _, polygons, _, _ in items for polygon in polygons]
        ).bounds
        min_x, min_y, max_x, max_y = bounds
        scale = min(820 / max(max_x - min_x, 1), 450 / max(max_y - min_y, 1))

        def project(point: Vec2) -> Vec2:
            return 90 + (point[0] - min_x) * scale, 520 - (point[1] - min_y) * scale

        for _, polygons, color, element_id in sorted(
            items, key=lambda item: item[0], reverse=True
        ):
            for polygon in polygons:
                commands: list[str] = []
                for ring in (polygon.exterior, *polygon.interiors):
                    coordinates = [
                        project((float(x), float(y))) for x, y in ring.coords
                    ]
                    commands.append(
                        "M "
                        + " L ".join(f"{x:.3f},{y:.3f}" for x, y in coordinates)
                        + " Z"
                    )
                parts.append(
                    f'<path class="body" fill="{html.escape(color, quote=True)}" fill-rule="evenodd" d="{" ".join(commands)}"><title>{html.escape(element_id)}</title></path>'
                )
        x0, y0 = project((min_x, min_y))
        x1, y1 = project((max_x, max_y))
        parts.extend(self._dimension((x0, 555), (x1, 555), f"{max_x - min_x:.1f} mm"))
        parts.extend(self._dimension((55, y0), (55, y1), f"{max_y - min_y:.1f} mm"))
        for dimension in Authoring.array(view.get("dimensions", [])):
            value = Authoring.object(dimension)
            start = vector3(value.get("start"), "dimension start")
            end = vector3(value.get("end"), "dimension end")
            parts.extend(
                self._dimension(
                    project(self._point(start, axis)),
                    project(self._point(end, axis)),
                    str(
                        value.get(
                            "label",
                            f"{math.dist(self._point(start, axis), self._point(end, axis)):.1f} mm",
                        )
                    ),
                )
            )
        parts.append(
            '<text x="40" y="610" font-size="11">Projected outlines and exact plane cuts; detail instructions and quantities are in schedules.json.</text>'
        )
        return parts

    @staticmethod
    def _dimension(start: Vec2, end: Vec2, label: str) -> list[str]:
        x0, y0 = start
        x1, y1 = end
        return [
            f'<path class="dimension" d="M{x0},{y0} L{x1},{y1} M{x0 - 4},{y0 - 4} L{x0 + 4},{y0 + 4} M{x1 - 4},{y1 - 4} L{x1 + 4},{y1 + 4}"/>',
            f'<text x="{(x0 + x1) / 2 + 5}" y="{(y0 + y1) / 2 - 6}" font-size="12" text-anchor="middle">{html.escape(label)}</text>',
        ]

    @staticmethod
    def _point(vertex: Vec3, axis: int) -> Vec2:
        if axis == 0:
            return vertex[1], vertex[2]
        if axis == 1:
            return vertex[0], vertex[2]
        return vertex[0], vertex[1]

    @classmethod
    def _project(cls, mesh: MeshData, axis: int) -> list[Polygon]:
        polygons = [
            Polygon([cls._point(mesh.vertices[index], axis) for index in face])
            for face in mesh.faces
        ]
        union = unary_union(
            [
                polygon
                for polygon in polygons
                if polygon.area > 0.001 and polygon.is_valid
            ]
        )
        return (
            list(union.geoms)
            if isinstance(union, MultiPolygon)
            else [union] if isinstance(union, Polygon) and not union.is_empty else []
        )

    @classmethod
    def section_polygons(
        cls, mesh: MeshData, axis: int, position: float
    ) -> list[Polygon]:
        segments: list[LineString] = []
        for face in mesh.faces:
            vertices = [mesh.vertices[index] for index in face]
            points: list[Vec2] = []
            for start, end in zip(vertices, (*vertices[1:], vertices[0])):
                a, b = start[axis] - position, end[axis] - position
                if abs(a) < 1e-7:
                    points.append(cls._point(start, axis))
                if a * b < 0:
                    ratio = a / (a - b)
                    coordinate: Vec3 = (
                        start[0] + ratio * (end[0] - start[0]),
                        start[1] + ratio * (end[1] - start[1]),
                        start[2] + ratio * (end[2] - start[2]),
                    )
                    points.append(cls._point(coordinate, axis))
            unique = list(dict.fromkeys((round(x, 6), round(y, 6)) for x, y in points))
            if len(unique) == 2 and math.dist(unique[0], unique[1]) > 1e-6:
                segments.append(LineString(unique))
        candidates = list(polygonize(unary_union(segments)))
        unique_segments = {
            tuple(sorted((tuple(segment.coords[0]), tuple(segment.coords[-1]))))
            for segment in segments
        }
        result = []
        for candidate in candidates:
            sample = candidate.representative_point()
            crossings = 0
            for start, end in unique_segments:
                if (start[1] > sample.y) != (end[1] > sample.y):
                    intersection_x = start[0] + (sample.y - start[1]) * (
                        end[0] - start[0]
                    ) / (end[1] - start[1])
                    crossings += intersection_x > sample.x
            if crossings % 2:
                result.append(candidate)
        return result
