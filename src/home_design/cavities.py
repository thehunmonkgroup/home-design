"""Physical cavity composition with explicit part ownership and net infill solids."""

from __future__ import annotations

from dataclasses import dataclass, replace

from home_design.construction import Authoring
from home_design.capabilities import ComponentRegistry
from home_design.layers import LayerAssembly
from home_design.errors import ResolutionError
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import MeshData, ResolvedElement
from home_design.solids import SolidOperations


@dataclass(frozen=True)
class CavityRegion:
    """One explicitly represented layer used to reconcile parts, infill and cuts."""

    host: str
    index: int
    material: str | None
    meshes: tuple[MeshData, ...]
    mask: MeshData | None
    layer_id: str | None = None


class CavityComposition:
    """Replace aggregate cavity geometry with disjoint infill and owned parts."""

    VOLUME_TOLERANCE: float = 1e-5
    PART_KINDS: frozenset[str] = ComponentRegistry.kinds("cavity_part")

    @classmethod
    def apply(
        cls, elements: dict[str, ResolvedElement]
    ) -> dict[tuple[str, int], CavityRegion]:
        """Fit occupants and remove their actual volume from explicit cavity layers.

        :param elements: Resolved registry before penetration processing.
        :returns: Authoritative cavity regions for final quantity reconciliation.
        :raises ResolutionError: For incompatible layers, invalid fits or shared volume.
        """
        regions = cls._regions(elements)
        occupied: dict[tuple[str, int], list[tuple[str, MeshData]]] = {
            key: [] for key in regions
        }
        for part in sorted(elements.values(), key=lambda element: element.element_id):
            if "occupies" not in part.data:
                continue
            if part.kind not in cls.PART_KINDS or not part.meshes:
                raise ResolutionError(
                    f"{part.element_id} is not a physical cavity part"
                )
            specification = Authoring.object(part.data["occupies"])
            keys = [
                cls._key(Authoring.object(region), elements)
                for region in Authoring.array(specification.get("regions"))
            ]
            mask = cls._combined_mask(part.element_id, keys, regions)
            fitted = cls._fit(part, mask, str(specification.get("fit", "contained")))
            contributions: list[JsonValue] = []
            for key in keys:
                region_mask = regions[key].mask
                if region_mask is None:
                    continue
                volume = cls._allocate(
                    part.element_id, fitted, region_mask, occupied[key], key
                )
                contribution: JsonObject = {"host": key[0], "layer": key[1], "volumeMm3": volume}
                if regions[key].layer_id is not None:
                    contribution["layerId"] = regions[key].layer_id
                contributions.append(contribution)
            data: JsonObject = {
                **part.data,
                "cavityContributions": contributions,
                "netVolumeMm3": sum(SolidOperations.volume(mesh) for mesh in fitted),
            }
            if part.kind == "framing":
                data["memberCount"] = len(fitted)
                data["memberIndices"] = [
                    int(mesh.role.split(":")[-1]) for mesh in fitted
                ]
            elements[part.element_id] = replace(part, meshes=fitted, data=data)
        for key, region in sorted(regions.items()):
            try:
                cls._infill(elements, region, occupied[key])
            except ResolutionError as error:
                error.subject_id = error.subject_id or region.host
                host_key = region.host.replace("~", "~0").replace("/", "~1")
                error.path = error.path or f"/elements/{host_key}"
                error.details.setdefault("layer", region.index)
                if region.layer_id is not None:
                    error.details.setdefault("layerId", region.layer_id)
                raise
        return regions

    @classmethod
    def refresh(
        cls,
        elements: dict[str, ResolvedElement],
        regions: dict[tuple[str, int], CavityRegion],
    ) -> None:
        """Reconcile final infill/part/void volumes after cuts to disjoint physical hosts."""
        if not regions or not any(
            element.kind == "penetration" for element in elements.values()
        ):
            return
        for region in regions.values():
            host = elements[region.host]
            compositions = [
                Authoring.object(value)
                for value in Authoring.array(host.data["cavities"])
            ]
            composition = next(
                value for value in compositions if value["layer"] == region.index
            )
            occupied_volume = 0.0
            final_parts: list[JsonValue] = []
            for value in Authoring.array(composition["parts"]):
                part_id = Authoring.text(Authoring.object(value)["element"])
                part = elements[part_id]
                volume = cls._volume_in(part.meshes, region.mask)
                contributions: list[JsonValue] = []
                for item in Authoring.array(part.data["cavityContributions"]):
                    entry = Authoring.object(item)
                    contributions.append(
                        {**entry, "volumeMm3": volume}
                        if cls._key(entry, elements) == (region.host, region.index)
                        else entry
                    )
                elements[part_id] = replace(
                    part, data={**part.data, "cavityContributions": contributions}
                )
                final_parts.append({"element": part_id, "volumeMm3": volume})
                occupied_volume += volume
            infill_volume = sum(
                SolidOperations.volume(mesh)
                for mesh in host.meshes
                if mesh.role.endswith(f"layer:{region.index}")
            )
            updated: JsonObject = {
                **composition,
                "parts": final_parts,
                "occupiedVolumeMm3": occupied_volume,
                "infillVolumeMm3": infill_volume,
                "voidVolumeMm3": max(
                    0.0,
                    number(composition["grossVolumeMm3"], "gross volume")
                    - occupied_volume
                    - infill_volume,
                ),
            }
            elements[region.host] = replace(
                host,
                data={
                    **host.data,
                    "cavities": [
                        updated if entry["layer"] == region.index else entry
                        for entry in compositions
                    ],
                },
            )

    @staticmethod
    def _volume_in(meshes: tuple[MeshData, ...], mask: MeshData | None) -> float:
        """Measure the final contribution of a physical part within an original cavity."""
        if mask is None:
            return 0.0
        volume = 0.0
        for mesh in meshes:
            shared = SolidOperations.intersection(mesh, mask)
            if shared is not None:
                volume += SolidOperations.volume(shared)
        return volume

    @classmethod
    def _combined_mask(
        cls,
        part_id: str,
        keys: list[tuple[str, int]],
        regions: dict[tuple[str, int], CavityRegion],
    ) -> MeshData:
        """Combine disjoint, explicitly selected regions into one fitting volume."""
        masks: list[MeshData] = []
        for key in keys:
            if key not in regions or regions[key].mask is None:
                raise ResolutionError(
                    f"{part_id} requires an explicit, nonempty cavity at {key}"
                )
            region_mask = regions[key].mask
            if region_mask is not None:
                masks.append(region_mask)
        for index, first in enumerate(masks):
            for second in masks[index + 1 :]:
                overlap = SolidOperations.intersection(first, second)
                if (
                    overlap is not None
                    and SolidOperations.volume(overlap) > cls.VOLUME_TOLERANCE
                ):
                    raise ResolutionError(
                        f"{part_id} declares overlapping cavity regions"
                    )
        mask = SolidOperations.union(masks, None, "cavity-fit")
        if mask is None:
            raise ResolutionError(f"{part_id} has no cavity volume")
        return mask

    @classmethod
    def _allocate(
        cls,
        part_id: str,
        meshes: tuple[MeshData, ...],
        mask: MeshData,
        previous_parts: list[tuple[str, MeshData]],
        key: tuple[str, int],
    ) -> float:
        """Assign physical intersections to one owner, rejecting shared volume."""
        volume = 0.0
        for mesh in meshes:
            intersection = SolidOperations.intersection(mesh, mask)
            if intersection is None:
                continue
            for previous_id, previous in previous_parts:
                overlap = SolidOperations.intersection(previous, intersection)
                if (
                    overlap is not None
                    and SolidOperations.volume(overlap) > cls.VOLUME_TOLERANCE
                ):
                    raise ResolutionError(
                        f"Cavity volume is owned by both {previous_id} and {part_id} at {key}"
                    )
            previous_parts.append((part_id, intersection))
            volume += SolidOperations.volume(intersection)
        if volume <= cls.VOLUME_TOLERANCE:
            raise ResolutionError(f"{part_id} does not occupy cavity {key}")
        return volume

    @staticmethod
    def _key(
        value: JsonObject, elements: dict[str, ResolvedElement]
    ) -> tuple[str, int]:
        """Read an explicit host/layer ownership identity."""
        identity = Authoring.text(value.get("host"))
        host = elements[identity]
        return identity, LayerAssembly.index(
            host.data.get("layers", []), value.get("layer"), f"Host {identity}"
        )

    @classmethod
    def _regions(
        cls, elements: dict[str, ResolvedElement]
    ) -> dict[tuple[str, int], CavityRegion]:
        """Collect layer masks without counting disconnected or overlapping pieces twice."""
        regions: dict[tuple[str, int], CavityRegion] = {}
        for host in elements.values():
            if host.kind not in ComponentRegistry.kinds("cavity_host"):
                continue
            for index, value in enumerate(Authoring.array(host.data.get("layers", []))):
                layer = Authoring.object(value)
                if layer.get("representation") != "explicit":
                    continue
                if "components" in layer:
                    raise ResolutionError(
                        "Explicit cavities cannot also use aggregate material fractions"
                    )
                meshes = tuple(
                    mesh for mesh in host.meshes if mesh.role.endswith(f"layer:{index}")
                )
                material = layer.get("material")
                regions[(host.element_id, index)] = CavityRegion(
                    host.element_id,
                    index,
                    material if isinstance(material, str) else None,
                    meshes,
                    SolidOperations.union(meshes, None, "cavity-mask"),
                    str(layer["id"]) if "id" in layer else None,
                )
        return regions

    @classmethod
    def _fit(
        cls, part: ResolvedElement, mask: MeshData, mode: str
    ) -> tuple[MeshData, ...]:
        """Keep, clip or require containment of the physical part, without moving it."""
        fitted: list[MeshData] = []
        for mesh in part.meshes:
            if mode == "contained":
                outside = SolidOperations.difference(mesh, [mask])
                if (
                    outside is not None
                    and SolidOperations.volume(outside) > cls.VOLUME_TOLERANCE
                ):
                    raise ResolutionError(
                        f"{part.element_id} extends outside its declared cavity regions"
                    )
            if mode == "clip":
                intersection = SolidOperations.intersection(mesh, mask)
                if intersection is not None:
                    fitted.append(intersection)
            else:
                fitted.append(mesh)
        if not fitted:
            raise ResolutionError(
                f"{part.element_id} is entirely outside its declared cavities"
            )
        return tuple(fitted)

    @classmethod
    def _infill(
        cls,
        elements: dict[str, ResolvedElement],
        region: CavityRegion,
        parts: list[tuple[str, MeshData]],
    ) -> None:
        """Subtract original fitted solids and publish an auditable volume balance.

        Host subtraction already limits each cutter to this region. Reusing the
        physical part avoids re-tessellating coincident surfaces through an
        unnecessary intersection before later owned penetration operations.
        """
        host = elements[region.host]
        cutters = [
            mesh
            for part_id in sorted({identity for identity, _ in parts})
            for mesh in elements[part_id].meshes
        ]
        infill: list[MeshData] = []
        if region.material is not None:
            previous: list[MeshData] = []
            for mesh in region.meshes:
                result = SolidOperations.difference(mesh, [*cutters, *previous])
                if result is not None:
                    infill.append(result)
                previous.append(mesh)
        replacement = tuple(
            mesh
            for mesh in host.meshes
            if not mesh.role.endswith(f"layer:{region.index}")
        ) + tuple(infill)
        by_part: dict[str, float] = {}
        for part_id, mesh in parts:
            by_part[part_id] = by_part.get(part_id, 0) + SolidOperations.volume(mesh)
        gross = SolidOperations.volume(region.mask) if region.mask is not None else 0
        infill_volume = sum(SolidOperations.volume(mesh) for mesh in infill)
        occupied_volume = sum(by_part.values())
        composition: JsonObject = {
            "layer": region.index,
            "infillMaterial": region.material,
            "grossVolumeMm3": gross,
            "infillVolumeMm3": infill_volume,
            "occupiedVolumeMm3": occupied_volume,
            "voidVolumeMm3": max(0.0, gross - infill_volume - occupied_volume),
            "parts": [
                {"element": part_id, "volumeMm3": volume}
                for part_id, volume in sorted(by_part.items())
            ],
        }
        if region.layer_id is not None:
            composition["layerId"] = region.layer_id
        elements[region.host] = replace(
            host,
            meshes=replacement,
            data={
                **host.data,
                "cavities": [
                    *Authoring.array(host.data.get("cavities", [])),
                    composition,
                ],
                "netVolumeMm3": sum(
                    SolidOperations.volume(mesh) for mesh in replacement
                ),
            },
        )
