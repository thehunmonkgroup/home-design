"""Resolved, adapter-neutral geometry and metadata structures."""

from __future__ import annotations

from dataclasses import dataclass, field

from home_design.json_types import JsonObject, JsonValue

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Face = tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MeshData:
    """A closed or open polygon mesh in canonical millimetre coordinates."""

    vertices: tuple[Vec3, ...]
    faces: tuple[Face, ...]
    material_id: str | None = None
    role: str = "body"

    def to_dict(self) -> dict[str, JsonValue]:
        """Serialize mesh data.

        :returns: JSON-compatible mesh mapping.
        """
        return {
            "vertices": [list(vertex) for vertex in self.vertices],
            "faces": [list(face) for face in self.faces],
            "materialId": self.material_id,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class ResolvedElement:
    """One authoring element with all placements and geometry resolved."""

    element_id: str
    kind: str
    name: str
    storey_id: str | None
    meshes: tuple[MeshData, ...] = ()
    data: JsonObject = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        """Serialize a resolved element.

        :returns: JSON-compatible element mapping.
        """
        return {
            "id": self.element_id,
            "kind": self.kind,
            "name": self.name,
            "storeyId": self.storey_id,
            "meshes": [mesh.to_dict() for mesh in self.meshes],
            "data": self.data,
        }


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    """Complete deterministic build input shared by all adapters."""

    model_version: str
    source_revision: int
    project: JsonObject
    coordinate_system: JsonObject
    levels: JsonObject
    materials: JsonObject
    types: JsonObject
    elements: tuple[ResolvedElement, ...]
    relationships: JsonObject

    def element(self, element_id: str) -> ResolvedElement:
        """Return a resolved element by stable ID.

        :param element_id: Canonical element ID.
        :returns: Matching resolved element.
        :raises KeyError: If no matching element exists.
        """
        for element in self.elements:
            if element.element_id == element_id:
                return element
        raise KeyError(element_id)

    def to_dict(self) -> dict[str, JsonValue]:
        """Serialize the complete resolved model.

        :returns: JSON-compatible resolved model mapping.
        """
        return {
            "resolvedFormat": "home-design-resolved-0.1",
            "modelVersion": self.model_version,
            "sourceRevision": self.source_revision,
            "units": {"length": "mm", "angle": "deg"},
            "project": self.project,
            "coordinateSystem": self.coordinate_system,
            "levels": self.levels,
            "materials": self.materials,
            "types": self.types,
            "elements": [element.to_dict() for element in self.elements],
            "relationships": self.relationships,
        }
