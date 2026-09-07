"""Remap generated-part locators without changing authored topology names."""

from __future__ import annotations

from home_design.construction import Authoring
from home_design.json_types import JsonObject, JsonValue


class ScopedRemapping:
    """Keep opening-derived members and default roof planes attached to copied owners."""

    def __init__(self, objects: JsonObject, identities: dict[str, str]) -> None:
        """Identify scoped names that the engine derives from canonical object IDs."""
        self.elements: JsonObject = Authoring.object(objects.get("elements", {}))
        self.openings: dict[str, str] = {}
        self.roofs: dict[str, str] = {}
        self.aliases: set[str] = set()
        for identity, value in self.elements.items():
            element = Authoring.object(value)
            if element.get("kind") == "opening":
                self.openings[identity] = identities.get(identity, identity)
            if element.get("kind") == "roof":
                geometry = Authoring.object(element.get("geometry", {}))
                if geometry.get("kind") == "parametric":
                    self.roofs[identity] = identities.get(identity, identity)
                    self.aliases.update(
                        Authoring.text(value)
                        for value in Authoring.object(
                            geometry.get("faceIds", {})
                        ).values()
                    )

    def face(self, value: str) -> str:
        """Preserve explicit aliases while renaming default plane IDs."""
        if value in self.aliases:
            return value
        for identity, replacement in sorted(
            self.roofs.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if value.startswith(identity + ".face"):
                return replacement + value[len(identity) :]
        return value

    def key(self, value: str) -> str:
        """Remap owner tokens while preserving local boundary and layer names."""
        return "/".join(
            self.face(self.openings.get(token, token)) for token in value.split("/")
        )

    def hosted(self, value: JsonValue) -> None:
        """Visit declared locator structures without inspecting freeform metadata."""
        if isinstance(value, list):
            for child in value:
                self.hosted(child)
        elif isinstance(value, dict):
            self.locator(value)
            for field, child in value.items():
                if field not in {
                    "properties",
                    "specifications",
                    "performance",
                    "externalIds",
                    "recipeInstance",
                }:
                    self.hosted(child)

    def locator(self, value: JsonObject) -> None:
        """Remap roof face selectors and generated wall-member hosts in place."""
        roof_host = value.get("host", value.get("element"))
        if isinstance(roof_host, str) and roof_host in self.roofs:
            for field in ("face", "selector"):
                if isinstance(value.get(field), str):
                    value[field] = self.face(Authoring.text(value[field]))
        host_id = value.get("element")
        host = self.elements.get(host_id) if isinstance(host_id, str) else None
        if (
            value.get("kind") == "member"
            and isinstance(host, dict)
            and host.get("kind") == "wallFraming"
            and isinstance(value.get("part"), str)
        ):
            value["part"] = self.key(Authoring.text(value["part"]))

    def apply(self) -> None:
        """Update scoped overrides, retained member aliases and nested host locators."""
        for raw in self.elements.values():
            element = Authoring.object(raw)
            if element.get("kind") == "wallFraming":
                for field in ("memberOverrides", "memberIds"):
                    if field in element:
                        element[field] = {
                            self.key(name): (
                                self.key(Authoring.text(value))
                                if field == "memberIds"
                                else value
                            )
                            for name, value in Authoring.object(element[field]).items()
                        }
            self.hosted(element)
