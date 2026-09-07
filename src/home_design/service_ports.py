"""Oriented, sized service interfaces independent of network and geometry dependencies."""

from __future__ import annotations

import math

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.placement import LocalFrame, PlacementContext
from home_design.resolved import Vec3
from home_design.port_contracts import ResolvedPort


class ServicePorts:
    """Resolve connection faces and check actual mating geometry in canonical millimetres."""

    POSITION_TOLERANCE_MM: float = 0.01
    ANGULAR_DOT_TOLERANCE: float = 1e-8
    FUNCTION_MEDIA: dict[str, frozenset[str]] = {
        "power": frozenset({"electrical"}),
        "neutral": frozenset({"electrical"}),
        "protectiveEarth": frozenset({"electrical"}),
        "bonding": frozenset({"electrical"}),
        "signal": frozenset({"communications"}),
        "containment": frozenset({"electrical", "communications"}),
    }

    @classmethod
    def resolve(
        cls, definitions: JsonObject, placement: LocalFrame, states: JsonObject
    ) -> JsonObject:
        """Transform reusable local ports, retaining their full rectangular orientation."""
        unknown = set(states) - set(definitions)
        if unknown:
            raise ResolutionError(
                f"Unknown service port state keys: {', '.join(sorted(unknown))}"
            )
        ports: JsonObject = {}
        for key, value in definitions.items():
            definition = Authoring.object(value)
            function = definition.get("function")
            if (
                function is not None
                and definition["medium"]
                not in cls.FUNCTION_MEDIA[Authoring.text(function)]
            ):
                raise ResolutionError(
                    f"Service port {key} has incompatible medium and function"
                )
            normal = ConstructionGeometry.unit(
                vector3(definition["direction"], "port direction")
            )
            default_up: Vec3 = (0, 1, 0) if abs(normal[2]) > 0.999 else (0, 0, 1)
            up = vector3(definition.get("up", list(default_up)), "port up")
            across = ConstructionGeometry.unit(ConstructionGeometry.cross(up, normal))
            up = ConstructionGeometry.cross(normal, across)
            frame = LocalFrame(
                placement.point(vector3(definition["position"], "port position")),
                placement.vector(across),
                placement.vector(up),
                placement.vector(normal),
            )
            ports[key] = {
                **definition,
                "frame": frame.to_dict(),
                "state": states.get(key, "connected"),
            }
        return ports

    @staticmethod
    def frame(port: JsonObject) -> LocalFrame:
        """Read an already resolved port frame."""
        return LocalFrame.from_dict(port["frame"])

    @classmethod
    def _corners(cls, port: JsonObject) -> list[Vec3]:
        """Express the four interface corners in model coordinates."""
        frame = cls.frame(port)
        section = Authoring.object(port["section"])
        width, height = number(section["width"], "port width"), number(
            section["height"], "port height"
        )
        return [
            frame.point((x * width / 2, y * height / 2, 0))
            for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ]

    @classmethod
    def compatible(cls, a: JsonObject, b: JsonObject, identity: str) -> None:
        """Require matching connection technology, medium, opposed flow faces and physical size.

        :raises ResolutionError: For a connection that cannot mate as authored.
        """
        port_a, port_b = ResolvedPort.from_dict(a), ResolvedPort.from_dict(b)
        for field, first_value, second_value in (
            ("medium", port_a.medium, port_b.medium),
            ("connectionType", port_a.connection_type, port_b.connection_type),
        ):
            if first_value != second_value:
                raise ResolutionError(
                    f"Service connection {identity} has incompatible {field}"
                )
        if port_a.function != port_b.function:
            raise ResolutionError(
                f"Service connection {identity} has incompatible port function"
            )
        if port_a.flow == port_b.flow and port_a.flow != "bidirectional":
            raise ResolutionError(
                f"Service connection {identity} has incompatible flow directions"
            )
        first, second = port_a.frame, port_b.frame
        if math.dist(first.origin, second.origin) > cls.POSITION_TOLERANCE_MM:
            raise ResolutionError(
                f"Service connection {identity} has misaligned endpoints"
            )
        if (
            sum(x * y for x, y in zip(first.z, second.z))
            > -1 + cls.ANGULAR_DOT_TOLERANCE
        ):
            raise ResolutionError(
                f"Service connection {identity} requires opposing port directions"
            )
        section_a, section_b = port_a.section, port_b.section
        if section_a.kind != section_b.kind:
            raise ResolutionError(
                f"Service connection {identity} requires a transition between section shapes"
            )
        if section_a.kind == "circle":
            matches = (
                abs(section_a.width.value - section_b.width.value)
                <= cls.POSITION_TOLERANCE_MM
            )
        else:
            corners = cls._corners(b)
            matches = all(
                min(math.dist(point, other) for other in corners)
                <= cls.POSITION_TOLERANCE_MM
                for point in cls._corners(a)
            )
        if not matches:
            raise ResolutionError(
                f"Service connection {identity} has incompatible size or section orientation"
            )

    @staticmethod
    def reference(value: JsonValue) -> tuple[str, str]:
        """Read a canonical element ID and scoped port key."""
        reference = Authoring.object(value)
        return Authoring.text(reference["element"]), Authoring.text(reference["port"])

    @classmethod
    def lookup(cls, context: PlacementContext, value: JsonObject) -> JsonObject:
        """Resolve a port locator through the ordinary geometry dependency cache."""
        element_id, key = cls.reference(value)
        element = context.resolve_component(element_id)
        ports = Authoring.object(element.data.get("ports", {}))
        if key not in ports:
            raise ResolutionError(f"Unknown service port {element_id}/{key}")
        return Authoring.object(ports[key])

    @classmethod
    def references(cls, value: JsonValue) -> list[JsonValue]:
        """Retain authored port locators separately from resolved placement coordinates."""
        if isinstance(value, list):
            return [reference for child in value for reference in cls.references(child)]
        if not isinstance(value, dict):
            return []
        if isinstance(value.get("port"), dict):
            return [value["port"]]
        return [
            reference for child in value.values() for reference in cls.references(child)
        ]
