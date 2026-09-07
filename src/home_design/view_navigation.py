"""Explicit navigable building relationships for model review clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedModel
from home_design.member_assemblies import MemberAssemblies

LinkKind = Literal[
    "assembly",
    "room",
    "host",
    "ownership",
    "system",
    "connection",
    "support",
    "placement",
    "reference",
    "generated",
]


@dataclass(frozen=True)
class ViewLink:
    """A directed child-to-container or component-to-dependency review link."""

    source_id: str
    target_id: str
    kind: LinkKind
    source_label: str
    target_label: str
    path: str = ""

    def to_dict(self) -> JsonObject:
        """Publish labels for navigation in both directions and retained technical provenance."""
        return {
            "sourceId": self.source_id,
            "targetId": self.target_id,
            "kind": self.kind,
            "sourceLabel": self.source_label,
            "targetLabel": self.target_label,
            "path": self.path,
        }


class ViewNavigation:
    """Project explicit authored references into a compact review graph without inferring contact."""

    def __init__(self, model: ResolvedModel) -> None:
        """Keep valid canonical participants and deterministic deduplicated links."""
        self.model: ResolvedModel = model
        self.kinds: dict[str, str] = {
            element.element_id: element.kind for element in model.elements
        }
        self.kinds.update(
            {
                child.element_id: child.kind
                for element in model.elements
                if element.kind in MemberAssemblies.CHILD_KINDS
                for child in MemberAssemblies.children(element)
            }
        )
        self.links: dict[tuple[str, str, LinkKind], ViewLink] = {}

    def add(
        self,
        source: str,
        target: str,
        kind: LinkKind,
        source_label: str,
        target_label: str,
        path: str = "",
    ) -> None:
        """Keep one link per relationship meaning and pair of available participants."""
        if source != target and source in self.kinds and target in self.kinds:
            self.links.setdefault(
                (source, target, kind),
                ViewLink(source, target, kind, source_label, target_label, path),
            )

    def references(self) -> None:
        """Distinguish construction hosting, ownership, system membership and other placement."""
        for reference in self.model.component_references:
            source = Authoring.text(reference["ownerId"])
            target = Authoring.text(reference["targetId"])
            scope = Authoring.object(reference.get("scope", {}))
            if isinstance(scope.get("part"), str):
                target = f"{target}/member/{scope['part']}"
            path = Authoring.text(reference["path"])
            role = reference["role"]
            if self.kinds.get(source) in {
                "serviceSystem",
                "serviceCircuit",
            } and self.kinds.get(target) not in {"serviceSystem", "serviceCircuit"}:
                self.add(target, source, "system", "System", "System member", path)
            elif self.kinds.get(target) in {"serviceSystem", "serviceCircuit"}:
                self.add(source, target, "system", "System", "System member", path)
            elif role == "ownership":
                self.add(
                    source, target, "ownership", "Owned by", "Owned component", path
                )
            elif "host" in path.split("/") or "follow" in path.split("/"):
                self.add(source, target, "host", "Host", "Hosted component", path)
            elif role == "placement":
                self.add(
                    source,
                    target,
                    "placement",
                    "Position follows",
                    "Position drives",
                    path,
                )
            else:
                self.add(
                    source,
                    target,
                    "reference",
                    "Related component",
                    "Related component",
                    path,
                )

    def relationships(self) -> None:
        """Use semantic relationship fields to expose room, assembly and physical connection intent."""
        mappings: dict[str, tuple[str, str, LinkKind, str, str]] = {
            "voids": ("opening", "host", "host", "Host", "Opening"),
            "fills": ("element", "opening", "host", "Opening", "Door or window"),
            "bounds": ("element", "space", "room", "Room", "Room boundary"),
            "supports": ("supported", "support", "support", "Supported by", "Supports"),
            "attaches": (
                "attached",
                "primary",
                "connection",
                "Attached to",
                "Attachment",
            ),
            "drainsTo": (
                "source",
                "target",
                "connection",
                "Drains to",
                "Receives drainage",
            ),
        }
        for identity, raw in self.model.relationships.items():
            value = Authoring.object(raw)
            kind = Authoring.text(value["kind"])
            path = f"/relationships/{identity}"
            if kind == "aggregates":
                for part in Authoring.array(value["parts"]):
                    self.add(
                        Authoring.text(part),
                        Authoring.text(value["assembly"]),
                        "assembly",
                        "Assembly",
                        "Assembly part",
                        path,
                    )
            elif kind in {"joins", "connectsPorts"}:
                self.add(
                    Authoring.text(Authoring.object(value["a"])["element"]),
                    Authoring.text(Authoring.object(value["b"])["element"]),
                    "connection",
                    "Connected to",
                    "Connected to",
                    path,
                )
            elif kind in mappings:
                source, target, link_kind, label, inverse = mappings[kind]
                self.add(
                    Authoring.text(value[source]),
                    Authoring.text(value[target]),
                    link_kind,
                    label,
                    inverse,
                    path,
                )

    def build(self) -> tuple[ViewLink, ...]:
        """Return a stable review graph independent of JSON object order."""
        self.references()
        self.relationships()
        return tuple(self.links[key] for key in sorted(self.links))
