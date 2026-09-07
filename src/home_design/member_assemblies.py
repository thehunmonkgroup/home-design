"""Shared identity and final quantity contracts for generated member assemblies."""

from __future__ import annotations

from dataclasses import replace

from home_design.construction import Authoring
from home_design.capabilities import ComponentRegistry
from home_design.errors import ResolutionError
from home_design.json_types import JsonValue
from home_design.resolved import MeshData, ResolvedElement
from home_design.geometry import number, vector3
from home_design.solids import SolidOperations
from home_design.part_contracts import GeneratedMember


class MemberAssemblies:
    """Keep individually addressable generated members consistent after solid operations."""

    KINDS: frozenset[str] = ComponentRegistry.kinds("scoped_member_host")
    CHILD_KINDS: frozenset[str] = ComponentRegistry.kinds("generated_members")

    @staticmethod
    def records(element: ResolvedElement) -> tuple[GeneratedMember, ...]:
        """Read the common generated-member contract while retaining family-specific details."""
        return tuple(
            GeneratedMember.from_dict(value)
            for value in Authoring.array(element.data["members"])
        )

    @staticmethod
    def children(element: ResolvedElement) -> tuple[ResolvedElement, ...]:
        """Expand surviving parts with source-derived IDs and their own member type."""
        if element.kind == "framing":
            return tuple(
                MemberAssemblies._repeated_child(element, mesh)
                for mesh in element.meshes
            )
        records = {member.key: member for member in MemberAssemblies.records(element)}
        children: list[ResolvedElement] = []
        for mesh in element.meshes:
            key = mesh.role.removeprefix("part:")
            record = records[key]
            role = (
                "beam"
                if record.role in {"header", "beam"}
                else "column" if record.role == "column" else "other"
            )
            children.append(
                ResolvedElement(
                    f"{element.element_id}/member/{key}",
                    "member",
                    f"{element.name} {key}",
                    None,
                    (mesh,),
                    {
                        **record.to_dict(),
                        "generatedFrom": element.element_id,
                        "discipline": "framing",
                        "constructionRole": record.role,
                        "role": role,
                    },
                )
            )
        return tuple(children)

    @staticmethod
    def _repeated_child(element: ResolvedElement, mesh: MeshData) -> ResolvedElement:
        """Publish one repeated member's actual axis and quantity, retaining omitted index gaps."""
        index = int(mesh.role.split(":")[-1])
        distribution = vector3(
            element.data.get("distribution", [0, 0, 0]), "framing distribution"
        )
        spacing = number(element.data.get("spacing", 0), "framing spacing")
        axis: list[JsonValue] = [
            [
                coordinate + distribution[dimension] * spacing * index
                for dimension, coordinate in enumerate(vector3(point, "framing axis"))
            ]
            for point in Authoring.array(element.data["axis"])
        ]
        return ResolvedElement(
            f"{element.element_id}/member/{index}",
            "member",
            f"{element.name} {index}",
            None,
            (mesh,),
            {
                **element.data,
                "axis": axis,
                "generatedFrom": element.element_id,
                "memberIndex": index,
                "memberIndices": [index],
                "memberCount": 1,
                "spacing": 0,
                "netVolumeMm3": SolidOperations.volume(mesh),
            },
        )

    @classmethod
    def member(cls, element: ResolvedElement, key: str) -> ResolvedElement:
        """Resolve a scoped generated member for a host placement."""
        for child in cls.children(element):
            if str(child.data.get("key", child.data.get("memberIndex"))) == key:
                return child
        raise ResolutionError(
            f"Assembly {element.element_id} has no surviving member {key}"
        )

    @classmethod
    def refresh(cls, elements: dict[str, ResolvedElement]) -> None:
        """Recompute surviving member counts and net quantities after cavity fitting/cuts."""
        for element in tuple(elements.values()):
            if element.kind not in cls.KINDS:
                continue
            volumes = {
                mesh.role.removeprefix("part:"): SolidOperations.volume(mesh)
                for mesh in element.meshes
            }
            records: list[JsonValue] = []
            for record in cls.records(element):
                if record.key in volumes:
                    records.append(record.with_volume(volumes[record.key]).to_dict())
            elements[element.element_id] = replace(
                element,
                data={
                    **element.data,
                    "members": records,
                    "memberCount": len(records),
                    "netVolumeMm3": sum(volumes.values()),
                },
            )
