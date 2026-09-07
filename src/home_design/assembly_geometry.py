"""Authored member networks for trusses, ties and three-dimensional bracing systems."""

from __future__ import annotations

from home_design.components import ConstructionResolver
from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.member_geometry import MemberGeometry
from home_design.placement import LocalFrame
from home_design.resolved import MeshData, ResolvedElement, Vec3
from home_design.solids import SolidOperations


class AssemblyGeometry:
    """Resolve named nodes and typed members with explicit joint trimming intent."""

    def __init__(self, construction: ConstructionResolver, source: JsonObject) -> None:
        """Prepare scoped node/member registries and a local placement frame."""
        self.construction: ConstructionResolver = construction
        self.source: JsonObject = source
        self.frame: LocalFrame = construction.placement(
            Authoring.object(source["placement"])
        )
        self.nodes: dict[str, Vec3] = {}
        self.local_nodes: dict[str, Vec3] = {}
        for key, value in Authoring.object(source["nodes"]).items():
            node = Authoring.object(value, "assembly node")
            if "local" in node:
                self.local_nodes[key] = vector3(node["local"], "local node")
            self.nodes[key] = (
                self.frame.point(vector3(node["local"], "local node"))
                if "local" in node
                else construction.point(node)
            )
        self.members: dict[str, JsonObject] = {
            key: Authoring.object(value)
            for key, value in Authoring.object(source["members"]).items()
        }
        self.meshes: dict[str, MeshData] = {}
        self.records: dict[str, JsonObject] = {}
        self.active: list[str] = []

    def _network(self) -> None:
        """Validate scoped endpoints, referenced trimming members and truss connectivity."""
        used: set[str] = set()
        graph: dict[str, set[str]] = {key: set() for key in self.nodes}
        for key, member in self.members.items():
            start, end = Authoring.text(member["start"]), Authoring.text(member["end"])
            if start not in self.nodes or end not in self.nodes:
                raise ResolutionError(
                    f"Assembly member {key} references a missing node"
                )
            used.update((start, end))
            graph[start].add(end)
            graph[end].add(start)
            for target in Authoring.array(member.get("trimAgainst", [])):
                if target not in self.members:
                    raise ResolutionError(
                        f"Assembly member {key} trims against missing member {target}"
                    )
        if set(self.nodes) != used:
            raise ResolutionError("Assembly contains unused nodes")
        if self.source["assemblyType"] != "truss":
            return
        pending = [next(iter(self.nodes))]
        visited: set[str] = set()
        while pending:
            node = pending.pop()
            if node not in visited:
                visited.add(node)
                pending.extend(graph[node] - visited)
        if visited != set(self.nodes):
            raise ResolutionError("Truss member network is disconnected")

    def _member(self, key: str) -> MeshData:
        """Resolve trimming dependencies and retain the surviving stock under its original key."""
        if key in self.meshes:
            return self.meshes[key]
        if key in self.active:
            raise ResolutionError(
                f"Assembly trimming cycle: {' -> '.join([*self.active, key])}"
            )
        self.active.append(key)
        member = self.members[key]
        type_id = Authoring.text(member["memberType"])
        definition = self.construction.context.types[type_id]
        local = (
            member["start"] in self.local_nodes and member["end"] in self.local_nodes
        )
        points = self.local_nodes if local else self.nodes
        start, end = (
            points[Authoring.text(member["start"])],
            points[Authoring.text(member["end"])],
        )
        section = Authoring.object(definition["section"])
        roll = number(member.get("roll", 0), "member roll")
        mesh = ConstructionGeometry.member(
            start,
            end,
            section,
            Authoring.text(definition["material"]),
            f"part:{key}",
            roll,
        )
        record = MemberGeometry.record(
            key,
            type_id,
            Authoring.text(member["role"]),
            start,
            end,
            section,
            mesh,
            roll,
        )
        if local:
            mesh = self.frame.mesh(mesh)
            record["axis"] = [
                list(self.frame.point(start)),
                list(self.frame.point(end)),
            ]
            axes = Authoring.object(record["sectionFrame"])
            record["sectionFrame"] = {
                axis: list(self.frame.vector(vector3(axes[axis], "section axis")))
                for axis in ("x", "y", "z")
            }
        cuts = Authoring.object(member.get("endCuts", {}))
        if cuts:
            mesh = MemberGeometry.cut_record(mesh, record, cuts)
        for target in Authoring.array(member.get("trimAgainst", [])):
            other = self._member(Authoring.text(target))
            if SolidOperations.intersection(mesh, other) is None:
                raise ResolutionError(
                    f"Assembly member {key} does not intersect trimming member {target}"
                )
            trimmed = SolidOperations.difference(mesh, [other])
            if trimmed is None:
                raise ResolutionError(
                    f"Assembly trimming removes the entire member {key}"
                )
            mesh = trimmed
        record.update(
            {
                "startNode": member["start"],
                "endNode": member["end"],
                "trimAgainst": member.get("trimAgainst", []),
                "netVolumeMm3": SolidOperations.volume(mesh),
            }
        )
        self.records[key] = record
        self.meshes[key] = mesh
        self.active.pop()
        return mesh

    def _joints(self) -> list[JsonValue]:
        """Retain authored shared-node connections independently of board-end trimming."""
        return [
            {
                "key": key,
                "point": list(point),
                "parts": [
                    member_id
                    for member_id, member in sorted(self.members.items())
                    if key in (member["start"], member["end"])
                ],
            }
            for key, point in sorted(self.nodes.items())
        ]

    def resolve(self, element_id: str) -> ResolvedElement:
        """Return a physically disjoint, individually addressable member assembly."""
        self._network()
        for key in sorted(self.members):
            mesh = self._member(key)
            for other_key, other in self.meshes.items():
                if other_key == key:
                    continue
                overlap = SolidOperations.intersection(mesh, other)
                if overlap is not None and SolidOperations.volume(overlap) > 1e-5:
                    raise ResolutionError(
                        f"Assembly members {key} and {other_key} overlap; author joint cuts or trimming"
                    )
        storey = self.source.get("storey")
        return ResolvedElement(
            element_id,
            "memberAssembly",
            Authoring.text(self.source["name"]),
            storey if isinstance(storey, str) else None,
            tuple(self.meshes[key] for key in sorted(self.meshes)),
            {
                "assemblyType": self.source["assemblyType"],
                "placement": self.frame.to_dict(),
                "nodes": {
                    key: list(point) for key, point in sorted(self.nodes.items())
                },
                "members": [self.records[key] for key in sorted(self.records)],
                "memberCount": len(self.meshes),
                "joints": self._joints(),
            },
        )
