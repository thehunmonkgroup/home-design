"""Reference indexing and dependency analysis for authoring models."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from home_design.diagnostics import Diagnostic
from home_design.json_types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class Reference:
    """A typed reference from one canonical object to another."""

    owner_id: str
    target_id: str
    path: str
    registry: str
    expected_kinds: tuple[str, ...] = ()


class ModelIndex:
    """Index IDs, typed references, relations, and resolution dependencies."""

    def __init__(self, model: JsonObject) -> None:
        """Build an immutable logical index over a model.

        :param model: Canonical authoring model.
        """
        self.model: JsonObject = model
        self.registries: dict[str, dict[str, JsonObject]] = {
            name: self._object_registry(name)
            for name in (
                "levels",
                "anchors",
                "materials",
                "types",
                "elements",
                "relationships",
            )
        }
        self.references: tuple[Reference, ...] = tuple(self._collect_references())
        self.relationships_by_kind: dict[str, list[tuple[str, JsonObject]]] = (
            defaultdict(list)
        )
        for relationship_id, value in self.registries["relationships"].items():
            kind = value.get("kind")
            if isinstance(kind, str):
                self.relationships_by_kind[kind].append((relationship_id, value))

    def diagnostics(self) -> list[Diagnostic]:
        """Return reference, kind, and dependency-cycle diagnostics.

        :returns: Semantic diagnostics generated from the index.
        """
        diagnostics = self._identity_diagnostics()
        for reference in self.references:
            target_registry = self.registries[reference.registry]
            target = target_registry.get(reference.target_id)
            if target is None:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="reference.missing",
                        message=(
                            f"{reference.owner_id} references missing {reference.registry[:-1]} "
                            f"{reference.target_id}"
                        ),
                        path=reference.path,
                        subject_id=reference.owner_id,
                    )
                )
            elif reference.expected_kinds:
                actual_kind = target.get("kind")
                if actual_kind not in reference.expected_kinds:
                    expected = ", ".join(reference.expected_kinds)
                    diagnostics.append(
                        Diagnostic(
                            severity="error",
                            code="reference.kind-mismatch",
                            message=f"Expected {expected}, found {actual_kind}",
                            path=reference.path,
                            subject_id=reference.owner_id,
                        )
                    )
        for cycle in self.dependency_cycles():
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="dependency.cycle",
                    message=f"Geometry dependency cycle: {' -> '.join(cycle)}",
                    subject_id=cycle[0],
                )
            )
        return diagnostics

    def dependency_cycles(self) -> list[tuple[str, ...]]:
        """Find element/anchor geometry dependency cycles.

        :returns: Canonically ordered cycles without duplicates.
        """
        graph: dict[str, set[str]] = defaultdict(set)
        geometry_paths = (
            "/base",
            "/top",
            "/bottom",
            "/datum",
            "/path",
            "/footprint",
            "/geometry",
            "/axis",
            "/follow",
            "/target",
            "/location",
        )
        for reference in self.references:
            if reference.registry in {"elements", "anchors"} and any(
                marker in reference.path for marker in geometry_paths
            ):
                graph[reference.owner_id].add(reference.target_id)
        cycles: set[tuple[str, ...]] = set()
        active: list[str] = []
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in active:
                cycle = active[active.index(node) :] + [node]
                core = cycle[:-1]
                rotations = [
                    tuple(core[index:] + core[:index]) for index in range(len(core))
                ]
                normalized = min(rotations)
                cycles.add(normalized + (normalized[0],))
                return
            if node in visited:
                return
            active.append(node)
            for dependency in sorted(graph[node]):
                visit(dependency)
            active.pop()
            visited.add(node)

        for node in sorted(graph):
            visit(node)
        return sorted(cycles)

    def relationships(self, kind: str) -> tuple[tuple[str, JsonObject], ...]:
        """Return relationships of one kind.

        :param kind: Relationship discriminator.
        :returns: Relationship ID/object pairs.
        """
        return tuple(self.relationships_by_kind.get(kind, ()))

    def host_for_opening(self, opening_id: str) -> str | None:
        """Return an opening's declared host.

        :param opening_id: Opening element ID.
        :returns: Host element ID or ``None``.
        """
        matches = [
            rel.get("host")
            for _, rel in self.relationships("voids")
            if rel.get("opening") == opening_id
        ]
        return matches[0] if matches and isinstance(matches[0], str) else None

    def opening_for_fill(self, element_id: str) -> str | None:
        """Return the opening filled by a door or window.

        :param element_id: Door or window ID.
        :returns: Opening ID or ``None``.
        """
        matches = [
            rel.get("opening")
            for _, rel in self.relationships("fills")
            if rel.get("element") == element_id
        ]
        return matches[0] if matches and isinstance(matches[0], str) else None

    def _object_registry(self, name: str) -> dict[str, JsonObject]:
        registry = self.model.get(name, {})
        if not isinstance(registry, dict):
            return {}
        return {
            key: value for key, value in registry.items() if isinstance(value, dict)
        }

    def _identity_diagnostics(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        ownership: dict[str, str] = {}
        project = self.model.get("project")
        if isinstance(project, dict):
            for field in ("id",):
                value = project.get(field)
                if isinstance(value, str):
                    ownership[value] = f"project/{field}"
            for field in ("site", "building"):
                value = project.get(field)
                if isinstance(value, dict):
                    object_id = value.get("id")
                    if isinstance(object_id, str):
                        ownership[object_id] = f"project/{field}/id"
        for registry_name, registry in self.registries.items():
            for object_id in registry:
                if object_id in ownership:
                    diagnostics.append(
                        Diagnostic(
                            severity="error",
                            code="identity.duplicate",
                            message=f"ID {object_id} is also used by {ownership[object_id]}",
                            path=f"/{registry_name}/{object_id}",
                            subject_id=object_id,
                        )
                    )
                ownership[object_id] = f"{registry_name}/{object_id}"
        return diagnostics

    def _collect_references(self) -> Iterable[Reference]:
        yield from self._anchor_references()
        yield from self._type_references()
        yield from self._element_references()
        yield from self._relationship_references()
        requirements = self.model.get("requirements", [])
        if isinstance(requirements, list):
            for index, requirement in enumerate(requirements):
                if isinstance(requirement, dict):
                    owner_id = str(requirement.get("id", f"requirement[{index}]"))
                    applies_to = requirement.get("appliesTo", [])
                    if not isinstance(applies_to, list):
                        continue
                    for item_index, target in enumerate(applies_to):
                        if isinstance(target, str):
                            yield Reference(
                                owner_id,
                                target,
                                f"/requirements/{index}/appliesTo/{item_index}",
                                "elements",
                            )

    def _anchor_references(self) -> Iterable[Reference]:
        for anchor_id, anchor in self.registries["anchors"].items():
            kind = anchor.get("kind")
            if kind in {"point2", "axis2"}:
                yield from self._field_reference(
                    anchor_id, anchor, "level", "anchors", "levels"
                )
            if kind == "axis2":
                yield from self._locator_references(
                    anchor_id, anchor.get("start"), f"/anchors/{anchor_id}/start"
                )
                yield from self._locator_references(
                    anchor_id, anchor.get("end"), f"/anchors/{anchor_id}/end"
                )
            if kind == "elementStation":
                yield from self._field_reference(
                    anchor_id, anchor, "element", "anchors", "elements"
                )

    def _type_references(self) -> Iterable[Reference]:
        for type_id, component_type in self.registries["types"].items():
            layers = component_type.get("layers", [])
            if isinstance(layers, list):
                for index, layer in enumerate(layers):
                    if isinstance(layer, dict):
                        components = layer.get("components", [])
                        if isinstance(components, list):
                            for component_index, component in enumerate(components):
                                if isinstance(component, dict) and isinstance(
                                    component.get("material"), str
                                ):
                                    yield Reference(
                                        type_id,
                                        str(component["material"]),
                                        f"/types/{type_id}/layers/{index}/components/{component_index}/material",
                                        "materials",
                                    )
                        material_id = layer.get("material")
                        if not isinstance(material_id, str):
                            continue
                        yield Reference(
                            type_id,
                            material_id,
                            f"/types/{type_id}/layers/{index}/material",
                            "materials",
                        )
            yield from self._field_reference(
                type_id, component_type, "material", "types", "materials"
            )
            yield from self._field_reference(
                type_id, component_type, "infillMaterial", "types", "materials"
            )
            yield from self._field_reference(
                type_id,
                component_type,
                "stringerType",
                "types",
                "types",
                ("memberType",),
            )

    def _element_references(self) -> Iterable[Reference]:
        expected_type = {
            "wall": ("wallType",),
            "slab": ("slabType",),
            "roof": ("roofType",),
            "door": ("doorType",),
            "window": ("windowType",),
            "space": ("spaceType",),
            "member": ("memberType",),
            "framing": ("memberType",),
            "footing": ("footingType",),
            "stair": ("stairType",),
            "railing": ("railingType",),
            "panel": ("panelType",),
            "sweep": ("sweepType",),
            "detail": ("detailType",),
        }
        for element_id, element in self.registries["elements"].items():
            kind = element.get("kind")
            yield from self._field_reference(
                element_id, element, "storey", "elements", "levels", ("storey",)
            )
            yield from self._field_reference(
                element_id,
                element,
                "type",
                "elements",
                "types",
                expected_type.get(str(kind), ()),
            )
            yield from self._value_references(
                element_id,
                element,
                f"/elements/{element_id}",
                skip_fields={
                    "storey",
                    "type",
                    "properties",
                    "specifications",
                    "performance",
                },
            )
            yield from self._field_reference(
                element_id, element, "material", "elements", "materials"
            )
            yield from self._field_reference(
                element_id, element, "grade", "elements", "elements", ("terrain",)
            )
            yield from self._field_reference(
                element_id, element, "target", "elements", "elements"
            )
            participants = element.get("participants", [])
            if isinstance(participants, list):
                for index, target in enumerate(participants):
                    if isinstance(target, str):
                        yield Reference(
                            element_id,
                            target,
                            f"/elements/{element_id}/participants/{index}",
                            "elements",
                        )

    def _relationship_references(self) -> Iterable[Reference]:
        roles: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
            "voids": (
                ("host", ("wall", "panel", "slab", "roof")),
                ("opening", ("opening",)),
            ),
            "fills": (("opening", ("opening",)), ("element", ("door", "window"))),
            "supports": (("support", ()), ("supported", ())),
            "drainsTo": (("source", ("sweep",)), ("target", ("sweep",))),
            "attaches": (("primary", ()), ("attached", ())),
            "bounds": (("space", ("space",)), ("element", ())),
            "aggregates": (("assembly", ("assembly",)),),
        }
        for relationship_id, relationship in self.registries["relationships"].items():
            kind = str(relationship.get("kind", ""))
            base_path = f"/relationships/{relationship_id}"
            for field, expected in roles.get(kind, ()):
                target = relationship.get(field)
                if isinstance(target, str):
                    yield Reference(
                        relationship_id,
                        target,
                        f"{base_path}/{field}",
                        "elements",
                        expected,
                    )
            if kind == "joins":
                for field in ("a", "b"):
                    endpoint = relationship.get(field)
                    if isinstance(endpoint, dict):
                        element_id = endpoint.get("element")
                        if not isinstance(element_id, str):
                            continue
                        yield Reference(
                            relationship_id,
                            element_id,
                            f"{base_path}/{field}/element",
                            "elements",
                            ("wall",),
                        )
            if kind == "aggregates":
                parts = relationship.get("parts", [])
                if isinstance(parts, list):
                    for index, part in enumerate(parts):
                        if isinstance(part, str):
                            yield Reference(
                                relationship_id,
                                part,
                                f"{base_path}/parts/{index}",
                                "elements",
                            )

    def _value_references(
        self,
        owner_id: str,
        value: JsonValue,
        path: str,
        skip_fields: set[str] | None = None,
    ) -> Iterable[Reference]:
        if isinstance(value, list):
            for index, child in enumerate(value):
                yield from self._value_references(owner_id, child, f"{path}/{index}")
            return
        if not isinstance(value, dict):
            return
        skip_fields = skip_fields or set()
        for field, child in value.items():
            if field in skip_fields:
                continue
            child_path = f"{path}/{field}"
            if field == "anchor" and isinstance(child, str):
                yield Reference(owner_id, child, child_path, "anchors")
            elif field == "level" and isinstance(child, str):
                yield Reference(owner_id, child, child_path, "levels")
            elif field == "element" and isinstance(child, str):
                yield Reference(owner_id, child, child_path, "elements")
            else:
                yield from self._value_references(owner_id, child, child_path)

    def _locator_references(
        self, owner_id: str, locator: JsonValue, path: str
    ) -> Iterable[Reference]:
        if isinstance(locator, dict):
            anchor_id = locator.get("anchor")
            if isinstance(anchor_id, str):
                yield Reference(owner_id, anchor_id, f"{path}/anchor", "anchors")

    @staticmethod
    def _field_reference(
        owner_id: str,
        value: JsonObject,
        field: str,
        owner_registry: str,
        target_registry: str,
        expected_kinds: tuple[str, ...] = (),
    ) -> Iterable[Reference]:
        target = value.get(field)
        if isinstance(target, str):
            yield Reference(
                owner_id,
                target,
                f"/{owner_registry}/{owner_id}/{field}",
                target_registry,
                expected_kinds,
            )
