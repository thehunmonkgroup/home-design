"""Layer-aware geometry and concurrent framed-cavity material composition."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Polygon

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.geometry import (
    extrude_planar_face,
    extrude_polygon,
    extrude_wall_profile,
    number,
)
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import MeshData, Vec2, Vec3


@dataclass(frozen=True)
class AssemblyLayer:
    """One thickness-bearing layer, optionally containing concurrent materials."""

    index: int
    thickness: float
    material: str | None
    source: JsonObject


class LayerAssembly:
    """Generate contiguous material layers without counting cavity infill twice."""

    @staticmethod
    def layers(component_type: JsonObject) -> tuple[AssemblyLayer, ...]:
        """Validate composition fractions and retain one physical layer thickness."""
        result: list[AssemblyLayer] = []
        for index, value in enumerate(Authoring.array(component_type.get("layers"))):
            source = Authoring.object(value)
            material = source.get("material")
            components = source.get("components")
            if isinstance(components, list):
                fractions = [
                    number(
                        Authoring.object(component).get("fraction"),
                        "cavity material fraction",
                    )
                    for component in components
                ]
                if not math.isclose(sum(fractions), 1, abs_tol=1e-6):
                    raise ResolutionError(
                        "Concurrent layer component fractions must sum to one"
                    )
                if not isinstance(material, str):
                    representative = Authoring.object(
                        components[fractions.index(max(fractions))]
                    )
                    material = representative.get("material")
            result.append(
                AssemblyLayer(
                    index,
                    number(source.get("thickness"), "layer thickness"),
                    material if isinstance(material, str) else None,
                    source,
                )
            )
        return tuple(result)

    @classmethod
    def slab(
        cls, polygon: Polygon, top: float, component_type: JsonObject
    ) -> tuple[MeshData, ...]:
        """Stack closed layers from the finished top surface downward."""
        meshes: list[MeshData] = []
        for layer in cls.layers(component_type):
            meshes.append(
                extrude_polygon(
                    polygon,
                    top - layer.thickness,
                    top,
                    layer.material,
                    f"layer:{layer.index}",
                )
            )
            top -= layer.thickness
        return tuple(meshes)

    @classmethod
    def wall(
        cls,
        profile: Polygon,
        origin: Vec2,
        tangent: Vec2,
        exterior_offset: float,
        base: float,
        component_type: JsonObject,
        prefix: str,
    ) -> tuple[MeshData, ...]:
        """Stack exterior-to-interior layers with the same hosted opening cuts."""
        meshes: list[MeshData] = []
        for layer in cls.layers(component_type):
            offset = exterior_offset - layer.thickness / 2
            mesh = extrude_wall_profile(
                profile, origin, tangent, offset, layer.thickness, base, layer.material
            )
            meshes.append(
                MeshData(
                    mesh.vertices,
                    mesh.faces,
                    layer.material,
                    f"{prefix}:layer:{layer.index}",
                )
            )
            exterior_offset -= layer.thickness
        return tuple(meshes)

    @classmethod
    def roof(
        cls, boundary: tuple[Vec3, ...], component_type: JsonObject, face_id: str
    ) -> tuple[MeshData, ...]:
        """Stack layers along the face normal and expose both finish surfaces."""
        meshes: list[MeshData] = []
        for layer in cls.layers(component_type):
            mesh = extrude_planar_face(
                boundary,
                layer.thickness,
                layer.material,
                f"roof-face:{face_id}:layer:{layer.index}",
            )
            meshes.append(mesh)
            boundary = mesh.vertices[len(mesh.vertices) // 2 :]
        return tuple(meshes)

    @classmethod
    def metadata(cls, component_type: JsonObject) -> list[JsonValue]:
        """Preserve assembly specifications for sections, schedules and inspection."""
        return [layer.source for layer in cls.layers(component_type)]
