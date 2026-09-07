"""Placed service devices and explicit port-level systems, circuits and connections."""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations

from home_design.components import ConstructionResolver
from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.electrical import ElectricalDevices
from home_design.fabrication import FabricationGeometry
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject
from home_design.mechanical import MechanicalDevices
from home_design.mounted_parts import MountedParts
from home_design.placement import LocalFrame
from home_design.plumbing import PlumbingDevices
from home_design.resolved import ResolvedElement
from home_design.service_ports import ServicePorts
from home_design.solids import SolidOperations


class ServiceComponents:
    """Resolve reusable device geometry before checking its external network."""

    KINDS: frozenset[str] = frozenset(
        {"serviceDevice", "serviceSystem", "serviceCircuit"}
    )
    SYSTEM_MEDIA: dict[str, str] = {
        "electrical": "electrical",
        "communications": "communications",
        "water": "water",
        "coldWater": "water",
        "hotWater": "water",
        "waste": "waste",
        "vent": "vent",
        "gas": "gas",
        "supplyAir": "air",
        "exhaustAir": "air",
        "refrigerant": "refrigerant",
        "condensate": "condensate",
        "other": "other",
    }

    @classmethod
    def resolve(
        cls, construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Place fabricated equipment or retain a nonphysical service group."""
        kind = Authoring.text(source["kind"])
        if kind != "serviceDevice":
            data: JsonObject = {
                key: source[key]
                for key in ("members", "system", "systemType", "schedule")
                if key in source
            }
            return ResolvedElement(
                element_id, kind, Authoring.text(source["name"]), None, data=data
            )
        definition = construction.component_type(source)
        ElectricalDevices.validate(definition)
        PlumbingDevices.validate(definition)
        MechanicalDevices.validate(definition)
        placement = Authoring.object(source["placement"])
        if "host" in Authoring.object(placement["origin"]):
            device = MountedParts.resolve(construction, element_id, source)
            resolved_placement = Authoring.object(device.data["placement"])
            frame = LocalFrame(
                *(
                    vector3(resolved_placement[key], key)
                    for key in ("origin", "x", "y", "z")
                )
            )
        else:
            if number(source.get("projection", 0), "service projection") != 0:
                raise ResolutionError("Service device projection requires a host frame")
            frame = construction.placement(placement)
            mesh = frame.mesh(FabricationGeometry.resolve(definition))
            storey = source.get("storey")
            device = ResolvedElement(
                element_id,
                kind,
                Authoring.text(source["name"]),
                storey if isinstance(storey, str) else None,
                (mesh,),
                {
                    "typeId": source["type"],
                    "role": definition["role"],
                    "placement": frame.to_dict(),
                    "materialId": definition["material"],
                    "netVolumeMm3": SolidOperations.volume(mesh),
                },
            )
        return replace(
            device,
            data={
                **device.data,
                "ports": ServicePorts.resolve(
                    Authoring.object(definition["ports"]),
                    frame,
                    Authoring.object(source.get("portStates", {})),
                ),
                "portGroups": definition.get("portGroups", []),
                **(
                    {"mechanical": definition["mechanical"]}
                    if "mechanical" in definition
                    else {}
                ),
                **(
                    {"plumbing": definition["plumbing"]}
                    if "plumbing" in definition
                    else {}
                ),
                **(
                    {"electrical": definition["electrical"]}
                    if "electrical" in definition
                    else {}
                ),
            },
        )


class ServiceNetworks:
    """Check declared physical connections separately from internal device connectivity."""

    def __init__(
        self, elements: dict[str, ResolvedElement], relationships: JsonObject
    ) -> None:
        """Copy port records so network annotation does not modify the placement cache."""
        self.elements: dict[str, ResolvedElement] = elements
        self.relationships: JsonObject = relationships
        self.ports: dict[tuple[str, str], JsonObject] = {
            (element.element_id, key): dict(Authoring.object(value))
            for element in elements.values()
            for key, value in Authoring.object(element.data.get("ports", {})).items()
        }
        self.adjacency: dict[tuple[str, str], set[tuple[str, str]]] = {
            key: set() for key in self.ports
        }
        self.connections: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {}

    def _port(self, key: tuple[str, str]) -> JsonObject:
        """Reject unresolved scoped port keys before network evaluation."""
        if key not in self.ports:
            raise ResolutionError(f"Unknown service port {key[0]}/{key[1]}")
        return self.ports[key]

    def _link(self, first: tuple[str, str], second: tuple[str, str]) -> None:
        """Add a semantic edge without adding a geometry dependency."""
        self.adjacency[first].add(second)
        self.adjacency[second].add(first)

    def _connections(self) -> None:
        """Require exactly one explicit mating connection per connected external port."""
        for identity, value in self.relationships.items():
            relation = Authoring.object(value)
            if relation["kind"] != "connectsPorts":
                continue
            first, second = ServicePorts.reference(
                relation["a"]
            ), ServicePorts.reference(relation["b"])
            if first[0] == second[0]:
                raise ResolutionError(
                    f"Service connection {identity} must join different components; use internal portGroups within a device"
                )
            a, b = self._port(first), self._port(second)
            ServicePorts.compatible(a, b, identity)
            for key, port in ((first, a), (second, b)):
                if "connectionId" in port:
                    raise ResolutionError(
                        f"Service port {key} has multiple external connections; branches require distinct fitting ports"
                    )
                if port["state"] != "connected":
                    raise ResolutionError(
                        f"Service port {key} is declared {port['state']} but has a connection"
                    )
                port["connectionId"] = identity
            self.connections[identity] = first, second
            self._link(first, second)

    def _internal_links(self) -> None:
        """Use authored groups for internal buses/passages without consuming external ports."""
        for element in self.elements.values():
            for group in Authoring.array(element.data.get("portGroups", [])):
                keys = [
                    (element.element_id, Authoring.text(key))
                    for key in Authoring.array(group)
                ]
                media = {Authoring.text(self._port(key)["medium"]) for key in keys}
                if len(media) != 1:
                    raise ResolutionError(
                        f"Service device {element.element_id} internally connects incompatible media"
                    )
                for a, b in combinations(keys, 2):
                    self._link(a, b)

    def _members(self, element: ResolvedElement) -> set[tuple[str, str]]:
        """Read explicit port membership, including ports of shared equipment."""
        members = {
            ServicePorts.reference(value)
            for value in Authoring.array(element.data["members"])
        }
        for key in members:
            self._port(key)
        return members

    def _connected(self, identity: str, members: set[tuple[str, str]]) -> None:
        """Reject disconnected induced networks while permitting genuine connected loops."""
        pending = [min(members)]
        visited: set[tuple[str, str]] = set()
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            visited.add(key)
            pending.extend((self.adjacency[key] & members) - visited)
        if visited != members:
            absent = ", ".join(
                f"{owner}/{port}" for owner, port in sorted(members - visited)
            )
            raise ResolutionError(
                f"Service network {identity} is disconnected: {absent}"
            )

    def _annotate(
        self, element: ResolvedElement, members: set[tuple[str, str]], system_type: str
    ) -> None:
        """Retain an inspectable network summary alongside the authored membership."""
        self.elements[element.element_id] = replace(
            element,
            data={
                **element.data,
                "systemType": system_type,
                "medium": ServiceComponents.SYSTEM_MEDIA[system_type],
                "portCount": len(members),
                "componentIds": sorted({key[0] for key in members}),
                "connections": sorted(
                    identity
                    for identity, pair in self.connections.items()
                    if set(pair) <= members
                ),
                "status": "connected",
            },
        )

    def _systems(self) -> dict[str, set[tuple[str, str]]]:
        """Assign every port to one compatible physical distribution system."""
        memberships: dict[str, set[tuple[str, str]]] = {}
        for element in tuple(self.elements.values()):
            if element.kind != "serviceSystem":
                continue
            members = self._members(element)
            system_type = Authoring.text(element.data["systemType"])
            medium = ServiceComponents.SYSTEM_MEDIA[system_type]
            for key in members:
                port = self._port(key)
                if port["medium"] != medium:
                    raise ResolutionError(
                        f"Service system {element.element_id} has incompatible medium at {key}"
                    )
                if "systemId" in port:
                    raise ResolutionError(
                        f"Service port {key} belongs to multiple systems"
                    )
                port["systemId"] = element.element_id
            self._connected(element.element_id, members)
            memberships[element.element_id] = members
            self._annotate(element, members, system_type)
        return memberships

    def _circuits(self, systems: dict[str, set[tuple[str, str]]]) -> None:
        """Circuits are connected subsets of a declared parent system with unique port ownership."""
        for element in tuple(self.elements.values()):
            if element.kind != "serviceCircuit":
                continue
            parent_id = Authoring.text(element.data["system"])
            members = self._members(element)
            if parent_id not in systems or not members <= systems[parent_id]:
                raise ResolutionError(
                    f"Service circuit {element.element_id} members must belong to its parent system"
                )
            for key in members:
                port = self._port(key)
                if "circuitId" in port:
                    raise ResolutionError(
                        f"Service port {key} belongs to multiple circuits"
                    )
                port["circuitId"] = element.element_id
            self._connected(element.element_id, members)
            self._annotate(
                element,
                members,
                Authoring.text(self.elements[parent_id].data["systemType"]),
            )

    def resolve(self) -> None:
        """Validate and annotate complete networks after physical geometry resolution."""
        self._connections()
        self._internal_links()
        systems = self._systems()
        self._circuits(systems)
        for key, port in self.ports.items():
            if "systemId" not in port:
                raise ResolutionError(f"Service port {key} has no system membership")
            if port["state"] == "connected" and "connectionId" not in port:
                raise ResolutionError(
                    f"Service port {key} is disconnected; author a connection or declare an open/capped termination"
                )
        for identity, (a, b) in self.connections.items():
            if self.ports[a]["systemId"] != self.ports[b]["systemId"]:
                raise ResolutionError(
                    f"Service connection {identity} joins different systems"
                )
        for element in tuple(self.elements.values()):
            if "ports" not in element.data:
                continue
            if (
                element.kind in {"serviceRoute", "serviceFitting"}
                and len(
                    {
                        Authoring.text(port["systemId"])
                        for key, port in self.ports.items()
                        if key[0] == element.element_id
                    }
                )
                != 1
            ):
                raise ResolutionError(
                    f"Service route/fitting {element.element_id} cannot span different systems; use explicit equipment interfaces"
                )
            self.elements[element.element_id] = replace(
                element,
                data={
                    **element.data,
                    "ports": {
                        key[1]: value
                        for key, value in self.ports.items()
                        if key[0] == element.element_id
                    },
                    "netVolumeMm3": sum(
                        SolidOperations.volume(mesh) for mesh in element.meshes
                    ),
                },
            )
