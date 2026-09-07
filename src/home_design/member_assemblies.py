"""Shared identity and final quantity contracts for generated member assemblies."""

from __future__ import annotations

from dataclasses import replace

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.json_types import JsonValue
from home_design.resolved import ResolvedElement
from home_design.solids import SolidOperations


class MemberAssemblies:
    """Keep individually addressable generated members consistent after solid operations."""

    KINDS: frozenset[str] = frozenset(
        {"wallFraming", "planarFraming", "memberAssembly"}
    )

    @staticmethod
    def children(element: ResolvedElement) -> tuple[ResolvedElement, ...]:
        """Expand surviving parts with source-derived IDs and their own member type."""
        records = {
            str(Authoring.object(value)["key"]): Authoring.object(value)
            for value in Authoring.array(element.data["members"])
        }
        children: list[ResolvedElement] = []
        for mesh in element.meshes:
            key = mesh.role.removeprefix("part:")
            record = records[key]
            role = (
                "beam"
                if record["role"] in {"header", "beam"}
                else "column" if record["role"] == "column" else "other"
            )
            children.append(
                ResolvedElement(
                    f"{element.element_id}/member/{key}",
                    "member",
                    f"{element.name} {key}",
                    None,
                    (mesh,),
                    {
                        **record,
                        "generatedFrom": element.element_id,
                        "discipline": "framing",
                        "constructionRole": record["role"],
                        "role": role,
                    },
                )
            )
        return tuple(children)

    @classmethod
    def member(cls, element: ResolvedElement, key: str) -> ResolvedElement:
        """Resolve a scoped generated member for a host placement."""
        for child in cls.children(element):
            if child.data["key"] == key:
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
            for value in Authoring.array(element.data["members"]):
                record = Authoring.object(value)
                key = str(record["key"])
                if key in volumes:
                    records.append({**record, "netVolumeMm3": volumes[key]})
            elements[element.element_id] = replace(
                element,
                data={
                    **element.data,
                    "members": records,
                    "memberCount": len(records),
                    "netVolumeMm3": sum(volumes.values()),
                },
            )
