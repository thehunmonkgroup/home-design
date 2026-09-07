"""Hosted interior accessories and envelope-interface parts with physical fit checks."""

from __future__ import annotations

import math
from dataclasses import replace

from home_design.components import ConstructionResolver
from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.diagnostics import Diagnostic
from home_design.fabrication import FabricationGeometry
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.member_assemblies import MemberAssemblies
from home_design.placement import HostPlacement, LocalFrame, tuple3
from home_design.resolved import MeshData, ResolvedElement, ResolvedModel
from home_design.solids import SolidOperations


class MountedParts:
    """Place authored material geometry and reject unresolved material overlap at its host."""

    KINDS: frozenset[str] = frozenset({"accessory", "envelopePart"})

    @classmethod
    def resolve(
        cls, construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Offset the mounting origin along its host frame before applying part orientation."""
        definition = construction.context.types[Authoring.text(source["type"])]
        if (
            definition["role"] in {"sleeve", "protectivePlate"}
            and "interface" not in source
        ):
            raise ResolutionError(
                "Sleeves and protective plates require an explicit service interface"
            )
        placement = Authoring.object(source["placement"])
        mounting = Authoring.object(Authoring.object(placement["origin"])["host"])
        mount_frame = HostPlacement(construction.context).resolve(mounting)
        frame = construction.placement(placement)
        projection = number(source.get("projection", 0), "mounting projection")
        frame = LocalFrame(
            tuple3(
                [
                    frame.origin[index] + mount_frame.z[index] * projection
                    for index in range(3)
                ]
            ),
            frame.x,
            frame.y,
            frame.z,
        )
        mesh = frame.mesh(FabricationGeometry.resolve(definition))
        host = construction.context.resolve_component(
            Authoring.text(mounting["element"])
        )
        storey = source.get("storey", host.storey_id)
        return ResolvedElement(
            element_id,
            Authoring.text(source["kind"]),
            Authoring.text(source["name"]),
            storey if isinstance(storey, str) else None,
            (mesh,),
            {
                "typeId": source["type"],
                "role": definition["role"],
                "materialId": definition["material"],
                "mounting": mounting,
                "mountingFrame": mount_frame.to_dict(),
                "placement": frame.to_dict(),
                "projection": projection,
                "netVolumeMm3": SolidOperations.volume(mesh),
                **({"interface": source["interface"]} if "interface" in source else {}),
            },
        )

    @staticmethod
    def reference(
        elements: dict[str, ResolvedElement], value: JsonObject
    ) -> ResolvedElement:
        """Read a surviving component or scoped generated member."""
        target = elements[Authoring.text(value["element"])]
        if "part" in value:
            if target.kind not in MemberAssemblies.KINDS:
                raise ResolutionError(
                    "A scoped component reference requires a member assembly"
                )
            return MemberAssemblies.member(target, Authoring.text(value["part"]))
        return target

    @classmethod
    def refresh(cls, elements: dict[str, ResolvedElement]) -> None:
        """Verify final host fit after ownership/cuts and retain actual mounting extents."""
        for element in tuple(elements.values()):
            if (
                element.kind not in cls.KINDS | {"serviceDevice"}
                or "mounting" not in element.data
            ):
                continue
            mounting = Authoring.object(element.data["mounting"])
            host = cls.reference(elements, mounting)
            if host.kind in CoordinationVolumes.NON_OBSTACLES or not host.meshes:
                raise ResolutionError("Mounted parts require a physical host")
            if any(
                SolidOperations.intersection(part, host_mesh) is not None
                for part in element.meshes
                for host_mesh in host.meshes
            ):
                raise ResolutionError(
                    f"Mounted part {element.element_id} overlaps host {host.element_id}; resolve its cavity ownership or owned cut"
                )
            frame = Authoring.object(element.data["mountingFrame"])
            origin, normal = vector3(frame["origin"], "mounting origin"), vector3(
                frame["z"], "mounting normal"
            )
            extents = [
                sum(
                    (vertex[index] - origin[index]) * normal[index]
                    for index in range(3)
                )
                for mesh in element.meshes
                for vertex in mesh.vertices
            ]
            elements[element.element_id] = replace(
                element,
                data={
                    **element.data,
                    "mountHostId": host.element_id,
                    "mountingRangeMm": [min(extents), max(extents)],
                    "netVolumeMm3": sum(
                        SolidOperations.volume(mesh) for mesh in element.meshes
                    ),
                },
            )


class CoordinationVolumes:
    """Resolve nonmaterial coordination volumes independently of physical parts."""

    KINDS: frozenset[str] = frozenset({"clearanceZone", "barrierCheck"})
    NON_OBSTACLES: frozenset[str] = frozenset(
        {
            "space",
            "opening",
            "penetration",
            "clearanceZone",
            "barrierCheck",
            "terrain",
            "load",
            "detail",
        }
    )

    @staticmethod
    def resolve(
        construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Place a probe/access volume while excluding it from physical material accounting."""
        frame = construction.placement(Authoring.object(source["placement"]))
        mesh = frame.mesh(
            FabricationGeometry.extrusion(
                Authoring.object(source["geometry"]), None, "coordination"
            )
        )
        storey = source.get("storey")
        return ResolvedElement(
            element_id,
            Authoring.text(source["kind"]),
            Authoring.text(source["name"]),
            storey if isinstance(storey, str) else None,
            (mesh,),
            {
                "placement": frame.to_dict(),
                "purpose": source["purpose"],
                "severity": source.get("severity", "error"),
                "volumeMm3": SolidOperations.volume(mesh),
                **{
                    key: source[key]
                    for key in ("owner", "allow", "participants", "maximumGapVolumeMm3")
                    if key in source
                },
            },
        )

    @classmethod
    def access(cls, elements: dict[str, ResolvedElement]) -> None:
        """Check every access volume against final physical geometry with explicit exceptions."""
        for zone in tuple(elements.values()):
            if zone.kind != "clearanceZone":
                continue
            owner = elements[Authoring.text(zone.data["owner"])]
            if owner.kind in cls.NON_OBSTACLES or not owner.meshes:
                raise ResolutionError("A clearance zone requires a physical owner")
            excluded = {owner.element_id}
            for value in Authoring.array(zone.data.get("allow", [])):
                excluded.add(
                    MountedParts.reference(elements, Authoring.object(value)).element_id
                )
            obstructions: list[JsonValue] = []
            for candidate in elements.values():
                if (
                    candidate.kind in cls.NON_OBSTACLES
                    or candidate.element_id in excluded
                ):
                    continue
                parts = (
                    MemberAssemblies.children(candidate)
                    if candidate.kind in MemberAssemblies.KINDS
                    else (candidate,)
                )
                for part in parts:
                    if part.element_id in excluded:
                        continue
                    intersections: list[MeshData] = []
                    for mesh in part.meshes:
                        overlap = SolidOperations.intersection(zone.meshes[0], mesh)
                        if overlap is not None:
                            intersections.append(overlap)
                    overlap = SolidOperations.union(intersections, None, "coordination")
                    if overlap is not None:
                        obstructions.append(
                            {
                                "element": part.element_id,
                                "volumeMm3": SolidOperations.volume(overlap),
                            }
                        )
            elements[zone.element_id] = replace(
                zone,
                data={
                    **zone.data,
                    "status": "blocked" if obstructions else "clear",
                    "obstructions": sorted(
                        obstructions,
                        key=lambda value: str(Authoring.object(value)["element"]),
                    ),
                },
            )

    @staticmethod
    def barriers(elements: dict[str, ResolvedElement]) -> None:
        """Measure coverage and connected material inside explicitly authored barrier probes."""
        for check in tuple(elements.values()):
            if check.kind != "barrierCheck":
                continue
            probe = check.meshes[0]
            allowance = number(
                check.data.get("maximumGapVolumeMm3", 1e-5), "barrier gap allowance"
            )
            probe_volume = SolidOperations.volume(probe)
            if allowance >= probe_volume or math.isclose(
                allowance,
                probe_volume,
                rel_tol=1e-12,
                abs_tol=SolidOperations.OUTPUT_VOLUME_TOLERANCE_MM3,
            ):
                raise ResolutionError(
                    "Barrier gap allowance must be smaller than its probe volume"
                )
            pieces: list[MeshData] = []
            missing: list[JsonValue] = []
            for value in Authoring.array(check.data["participants"]):
                reference = Authoring.object(value)
                target = elements[Authoring.text(reference["element"])]
                if "layer" in reference:
                    index = int(number(reference["layer"], "barrier layer"))
                    if (
                        not 0
                        <= index
                        < len(Authoring.array(target.data.get("layers", [])))
                    ):
                        raise ResolutionError(
                            f"Barrier participant {target.element_id} has no layer {index}"
                        )
                    meshes = tuple(
                        mesh
                        for mesh in target.meshes
                        if mesh.role.endswith(f"layer:{index}")
                    )
                elif target.kind == "envelopePart":
                    meshes = target.meshes
                else:
                    raise ResolutionError(
                        "Barrier participants require an envelope part or an explicit host layer"
                    )
                intersections = [
                    overlap
                    for mesh in meshes
                    if (overlap := SolidOperations.intersection(probe, mesh))
                    is not None
                ]
                part = SolidOperations.union(intersections, None, "coordination")
                if part is None:
                    missing.append(reference)
                    continue
                if any(
                    SolidOperations.intersection(part, previous) is not None
                    for previous in pieces
                ):
                    raise ResolutionError(
                        "Barrier participants duplicate physical material inside the probe"
                    )
                pieces.append(part)
            covered = SolidOperations.union(pieces, None, "coordination")
            gap = (
                SolidOperations.difference(probe, [covered])
                if covered is not None
                else probe
            )
            gap_volume = SolidOperations.volume(gap) if gap is not None else 0.0
            connected = (
                len(SolidOperations.solid(covered).decompose())
                if covered is not None
                else 0
            )
            passed = not missing and gap_volume <= allowance and connected == 1
            elements[check.element_id] = replace(
                check,
                data={
                    **check.data,
                    "status": "continuous" if passed else "discontinuous",
                    "gapVolumeMm3": gap_volume,
                    "coverageFraction": 1 - gap_volume / SolidOperations.volume(probe),
                    "connectedRegions": connected,
                    "missingParticipants": missing,
                },
            )

    @staticmethod
    def diagnostics(model: ResolvedModel) -> list[Diagnostic]:
        """Report declared access/barrier failures without inferring whole-building compliance."""
        return [
            Diagnostic(
                "warning" if element.data["severity"] == "warning" else "error",
                (
                    "access.obstructed"
                    if element.kind == "clearanceZone"
                    else "barrier.discontinuous"
                ),
                f"{element.name}: {element.data['status']}",
                subject_id=element.element_id,
            )
            for element in model.elements
            if element.kind in CoordinationVolumes.KINDS
            and element.data.get("status") in {"blocked", "discontinuous"}
        ]
