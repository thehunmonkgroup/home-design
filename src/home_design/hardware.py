"""Placed construction hardware, explicit fastener groups and scoped connection participants."""

from __future__ import annotations

from dataclasses import replace

from home_design.components import ConstructionResolver
from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.fabrication import FabricationGeometry
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.member_assemblies import MemberAssemblies
from home_design.resolved import MeshData, ResolvedElement
from home_design.solids import SolidOperations


class HardwareComponents:
    """Keep rendered hardware and scheduled fasteners on one authored type contract."""

    KINDS: frozenset[str] = frozenset({"hardware", "fastenerGroup"})

    @classmethod
    def resolve(
        cls, construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Place a fabricated item or resolve the declared fastener quantity and positions."""
        definition = construction.context.types[Authoring.text(source["type"])]
        template = FabricationGeometry.resolve(definition)
        frame = construction.placement(Authoring.object(source["placement"]))
        kind = Authoring.text(source["kind"])
        meshes: tuple[MeshData, ...] = (frame.mesh(template),)
        data: JsonObject = {
            "typeId": source["type"],
            "role": definition["role"],
            "placement": frame.to_dict(),
            "participants": source["participants"],
            "materialId": definition["material"],
        }
        if kind == "fastenerGroup":
            quantity = int(number(source["quantity"], "fastener quantity"))
            mode = Authoring.text(source["representation"])
            instances = Authoring.object(source.get("instances", {}))
            if mode == "detailed" and len(instances) != quantity:
                raise ResolutionError(
                    "Detailed fastener quantity must equal the number of named instances"
                )
            if mode == "scheduled" and "occupies" in source:
                raise ResolutionError(
                    "Scheduled fasteners cannot own a physical cavity without positions"
                )
            placed: list[MeshData] = []
            for key, value in sorted(instances.items()):
                local = FabricationGeometry.placement(Authoring.object(value))
                mesh = frame.mesh(local.mesh(template))
                mesh = replace(mesh, role=f"fastener:{key}")
                if any(
                    SolidOperations.intersection(mesh, previous) is not None
                    for previous in placed
                ):
                    raise ResolutionError("Detailed fastener instances overlap")
                placed.append(mesh)
            meshes = tuple(placed)
            data.update(
                {
                    "quantity": quantity,
                    "representation": mode,
                    "unitVolumeMm3": SolidOperations.volume(template),
                    "scheduledVolumeMm3": (
                        quantity * SolidOperations.volume(template)
                        if mode == "scheduled"
                        else 0
                    ),
                    "nominalDiameter": definition["nominalDiameter"],
                    "nominalLength": definition["nominalLength"],
                    "instances": {
                        key: FabricationGeometry.placement(
                            Authoring.object(value)
                        ).to_dict()
                        for key, value in sorted(instances.items())
                    },
                }
            )
        data["netVolumeMm3"] = sum(
            SolidOperations.volume(mesh) for mesh in meshes
        ) + number(data.get("scheduledVolumeMm3", 0), "scheduled volume")
        storey = source.get("storey")
        return ResolvedElement(
            element_id,
            kind,
            Authoring.text(source["name"]),
            storey if isinstance(storey, str) else None,
            meshes,
            data,
        )

    @classmethod
    def participants(cls, elements: dict[str, ResolvedElement]) -> None:
        """Resolve connection participants after cuts, including surviving scoped members."""
        for element in tuple(elements.values()):
            if element.kind not in cls.KINDS:
                continue
            participants: list[JsonValue] = []
            for value in Authoring.array(element.data["participants"]):
                reference = Authoring.object(value)
                target_id = Authoring.text(reference["element"])
                if target_id == element.element_id:
                    raise ResolutionError(
                        "Connection hardware cannot reference itself as a participant"
                    )
                target = elements[target_id]
                if "part" in reference:
                    if target.kind not in MemberAssemblies.KINDS:
                        raise ResolutionError(
                            "Scoped hardware participants require a member assembly"
                        )
                    target = MemberAssemblies.member(
                        target, Authoring.text(reference["part"])
                    )
                if (
                    target.kind
                    in {"opening", "penetration", "space", "load", "detail", "terrain"}
                    or not target.meshes
                ):
                    raise ResolutionError(
                        f"Hardware participant {target_id} has no physical construction geometry"
                    )
                if target.element_id in participants:
                    raise ResolutionError(
                        "Connection hardware has duplicate participants"
                    )
                participants.append(target.element_id)
            elements[element.element_id] = replace(
                element, data={**element.data, "participantIds": participants}
            )
