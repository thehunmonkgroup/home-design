"""Discover and snapshot portable named camera and construction views."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject
from home_design.constants import resource_root
from home_design.source_state import SourceState


class NamedViews:
    """Read a model's ordered companion views without modifying design intent."""

    def __init__(self, model: Path) -> None:
        """Capture the index and every referenced view beneath views/MODEL-STEM."""
        root = model.parent / "views" / model.stem
        index = SourceState.capture(root / "index.json", required=False)
        self.sources: list[SourceState] = [index]
        self.entries: list[JsonObject] = []
        if index.content is None:
            return
        value = json.loads(index.content)
        schema = json.loads(
            (resource_root() / "schema/named-views.schema.json").read_text()
        )
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            raise HomeDesignError(f"Invalid named-view index: {errors[0].message}")
        seen: set[str] = set()
        for item in value["views"]:
            identity = item["id"]
            if identity in seen:
                raise HomeDesignError(f"Duplicate named view: {identity}")
            seen.add(identity)
            path = root / item["file"]
            if not path.resolve().is_relative_to(root.resolve()):
                raise HomeDesignError(
                    "Named view must remain inside its view directory"
                )
            source = SourceState.capture(path)
            self.sources.append(source)
            view = self.validate(json.loads(source.content or b"{}"))
            self.entries.append({**item, "view": view})

    @staticmethod
    def validate(value: JsonObject) -> JsonObject:
        """Validate an authored view against the shared capture schema."""
        schema = json.loads(
            (resource_root() / "schema/render-view.schema.json").read_text()
        )
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            raise HomeDesignError(f"Invalid render view: {errors[0].message}")
        return value

    def get(self, identity: str) -> JsonObject:
        """Select a stable view identity, failing explicitly when it is absent."""
        for entry in self.entries:
            if entry["id"] == identity:
                return Authoring.object(entry["view"])
        raise HomeDesignError(f"Unknown named view: {identity}")

    def assert_unchanged(self) -> None:
        """Guard index and definitions before publishing their captured contents."""
        for source in self.sources:
            source.assert_unchanged()

    @staticmethod
    def check_references(entries: list[JsonObject], manifest: JsonObject) -> None:
        """Reject stale component and layer references before publishing a tour."""
        elements = Authoring.object(manifest["elements"])
        meshes = Authoring.object(manifest["meshes"])
        for entry in entries:
            view = Authoring.object(entry["view"])
            selectors = [view[key] for key in ("isolate", "highlight") if key in view]
            for key in ("hide", "show"):
                selectors.extend(Authoring.array(view.get(key, [])))
            identities = []
            if "reveal" in view:
                identities.append(Authoring.object(view["reveal"])["id"])
            for value in selectors:
                selector = Authoring.object(value)
                identities.extend(Authoring.array(selector.get("ids", [])))
                for layer_value in Authoring.array(selector.get("layers", [])):
                    layer = Authoring.object(layer_value)
                    if not any(
                        Authoring.object(mesh).get("elementId") == layer["elementId"]
                        and Authoring.object(mesh).get("layerId") == layer["layerId"]
                        for mesh in meshes.values()
                    ):
                        raise HomeDesignError(
                            f"Named view {entry['id']} references an unknown layer: {layer}"
                        )
            for identity in identities:
                if str(identity) not in elements:
                    raise HomeDesignError(
                        f"Named view {entry['id']} references an unknown component: {identity}"
                    )

    def sections(self) -> tuple[tuple[int, float, bool], ...]:
        """Collect unique cap planes needed by published named views."""
        result: set[tuple[int, float, bool]] = set()
        for entry in self.entries:
            view = Authoring.object(entry["view"])
            if view.get("sectionCaps", True) is False:
                continue
            for value in Authoring.array(view.get("sections", [])):
                section = Authoring.object(value)
                result.add(
                    (
                        {"x": 0, "y": 1, "z": 2}[str(section["axis"])],
                        float(str(section["position"])),
                        section.get("keep", "below") == "below",
                    )
                )
        return tuple(sorted(result))
