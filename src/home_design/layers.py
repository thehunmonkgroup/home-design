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
class MaterialShare:
    """One concurrent material fraction within a single physical layer thickness."""

    material_id: str
    fraction: float
    source: JsonObject

    @classmethod
    def from_dict(cls, value: JsonValue) -> MaterialShare:
        """Read the shared material ownership contract used by geometry and reports."""
        source = Authoring.object(value, "layer material share")
        fraction = number(source["fraction"], "cavity material fraction")
        if not math.isfinite(fraction) or fraction <= 0 or fraction > 1:
            raise ResolutionError(
                "Layer material fraction must be greater than zero and at most one"
            )
        return cls(
            Authoring.text(source["material"], "layer material"), fraction, source
        )


@dataclass(frozen=True)
class AssemblyLayer:
    """One thickness-bearing layer, optionally containing concurrent materials."""

    index: int
    thickness: float
    material: str | None
    source: JsonObject
    components: tuple[MaterialShare, ...] = ()

    @property
    def identity(self) -> str | None:
        """Return a durable authored layer ID when the model supplies one."""
        value = self.source.get("id")
        return value if isinstance(value, str) else None


class LayerAssembly:
    """Generate contiguous material layers without counting cavity infill twice."""

    @staticmethod
    def export_key(identity: JsonValue) -> str:
        """Preserve legacy IFC relationship seeds through explicit identity migration."""
        text = str(identity)
        prefix = "layer.legacy."
        suffix = text.removeprefix(prefix)
        return suffix if text.startswith(prefix) and suffix.isdigit() else text

    @staticmethod
    def index(layers: JsonValue, selection: JsonValue, label: str = "host") -> int:
        """Resolve a durable layer ID or a legacy integer without silently retargeting."""
        values = Authoring.array(layers, "host layers")
        if isinstance(selection, str):
            matches = [
                index
                for index, value in enumerate(values)
                if Authoring.object(value).get("id") == selection
            ]
            if len(matches) == 1:
                return matches[0]
            reason = "ambiguous" if matches else "missing"
            raise ResolutionError(
                f"{label} has {reason} layer ID {selection}",
                code="layer.identity-unavailable",
            )
        if (
            isinstance(selection, int)
            and not isinstance(selection, bool)
            and 0 <= selection < len(values)
        ):
            return selection
        raise ResolutionError(
            f"{label} has no layer {selection}", code="layer.selection-unavailable"
        )

    @staticmethod
    def layers(component_type: JsonObject) -> tuple[AssemblyLayer, ...]:
        """Validate composition fractions and retain one physical layer thickness."""
        result: list[AssemblyLayer] = []
        for index, value in enumerate(Authoring.array(component_type.get("layers"))):
            source = Authoring.object(value)
            material = source.get("material")
            values = source.get("components")
            components = (
                tuple(MaterialShare.from_dict(value) for value in values)
                if isinstance(values, list)
                else ()
            )
            if isinstance(values, list):
                fractions = [component.fraction for component in components]
                if not math.isclose(sum(fractions), 1, abs_tol=1e-6):
                    raise ResolutionError(
                        "Concurrent layer component fractions must sum to one"
                    )
                if not isinstance(material, str):
                    material = components[fractions.index(max(fractions))].material_id
            result.append(
                AssemblyLayer(
                    index,
                    number(source.get("thickness"), "layer thickness"),
                    material if isinstance(material, str) else None,
                    source,
                    components,
                )
            )
        identities = [layer.identity for layer in result if layer.identity is not None]
        if len(identities) != len(set(identities)):
            raise ResolutionError(
                "Layer IDs must be unique within their reusable type",
                code="layer.duplicate-id",
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
