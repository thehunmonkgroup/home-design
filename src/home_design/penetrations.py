"""Explicitly owned, layer-selective cuts through construction solids."""

from __future__ import annotations

from dataclasses import replace

from home_design.components import ConstructionResolver
from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import extrude_polygon, number, polygon_normal, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import MeshData, ResolvedElement, Vec3
from home_design.solids import SolidOperations
from home_design.cut_limits import CutLimits


class Penetrations:
    """Resolve cutter locations first, then cut fully resolved physical hosts."""

    def __init__(self, construction: ConstructionResolver) -> None:
        """Reuse construction locators and host coordinate frames."""
        self.construction: ConstructionResolver = construction

    def resolve(self, element_id: str, element: JsonObject) -> ResolvedElement:
        """Resolve a local extrusion or an owner's named construction volume."""
        if "geometrySource" in element:
            source = Authoring.object(element["geometrySource"])
            owner_id = Authoring.text(source["element"])
            if element.get("owner") != owner_id or element["host"] == owner_id:
                raise ResolutionError(
                    "A sourced penetration must name its geometry source as owner and cut a different host"
                )
            owner = self.construction.context.resolve_component(owner_id)
            key = Authoring.text(source["volume"])
            if key not in owner.construction_volumes:
                raise ResolutionError(
                    f"Penetration {element_id} references unavailable construction volume {owner_id}/{key}"
                )
            mesh = replace(
                owner.construction_volumes[key], role="void", material_id=None
            )
            geometry: JsonObject = {"geometrySource": source}
        else:
            mesh, geometry = self._extrusion(element)
        return ResolvedElement(
            element_id,
            "penetration",
            Authoring.text(element.get("name")),
            str(element["storey"]) if "storey" in element else None,
            (mesh,),
            {
                "host": element.get("host"),
                "owner": element.get("owner"),
                "purpose": element.get("purpose"),
                "layers": element.get("layers"),
                **(
                    {"limits": CutLimits.resolve(self.construction, element)}
                    if "limits" in element
                    else {}
                ),
                **geometry,
            },
        )

    def _extrusion(self, element: JsonObject) -> tuple[MeshData, JsonObject]:
        """Extrude a cutter along local positive Z from its authored origin."""
        frame = self.construction.placement(Authoring.object(element.get("placement")))
        depth = number(element.get("depth"), "penetration depth")
        mesh = frame.mesh(
            extrude_polygon(
                ConstructionGeometry.section(Authoring.object(element.get("section"))),
                0,
                depth,
                None,
                "void",
            )
        )
        return mesh, {
            "depth": depth,
            "section": element.get("section"),
            "placement": frame.to_dict(),
        }

    @classmethod
    def apply(cls, elements: dict[str, ResolvedElement]) -> None:
        """Apply cuts in stable ID order without hiding ambiguous overlapping ownership.

        :param elements: Resolved registry, replaced in place after each valid cut.
        :raises ResolutionError: For empty/overlapping cuts or a completely removed host.
        """
        previous: dict[str, list[MeshData]] = {}
        originals = dict(elements)
        cuts = sorted(
            (element for element in elements.values() if element.kind == "penetration"),
            key=lambda element: element.element_id,
        )
        for cut in cuts:
            host_id = Authoring.text(cut.data.get("host"))
            host = elements[host_id]
            cutter = cut.meshes[0]
            selected = cls._selected_layers(host, cut.data.get("layers"))
            for prior in previous.get(host_id, []):
                if selected is not None and not any(
                    prior.role.endswith(f"layer:{index}") for index in selected
                ):
                    continue
                overlap = SolidOperations.intersection(prior, cutter)
                if overlap is not None and SolidOperations.volume(overlap) > 1e-6:
                    raise ResolutionError(
                        f"Penetration {cut.element_id} overlaps another cut on {host_id}"
                    )
            remaining: list[MeshData] = []
            removed: list[MeshData] = []
            for mesh in host.meshes:
                if selected is not None and not any(
                    mesh.role.endswith(f"layer:{index}") for index in selected
                ):
                    remaining.append(mesh)
                    continue
                result, intersection = SolidOperations.partition(mesh, cutter)
                if intersection is None or SolidOperations.volume(intersection) <= 1e-6:
                    remaining.append(mesh)
                    continue
                removed.append(intersection)
                if result is not None:
                    remaining.append(result)
            void = SolidOperations.union(removed, None, "void")
            if void is None:
                raise ResolutionError(
                    f"Penetration {cut.element_id} removes no volume from its selected host layers"
                )
            if not remaining:
                raise ResolutionError(
                    f"Penetration {cut.element_id} removes its entire host"
                )
            previous.setdefault(host_id, []).extend(removed)
            cut_ids = Authoring.array(host.data.get("penetrations", []))
            elements[host_id] = replace(
                host,
                meshes=tuple(remaining),
                data={
                    **host.data,
                    "penetrations": [*cut_ids, cut.element_id],
                    "netVolumeMm3": sum(
                        SolidOperations.volume(mesh) for mesh in remaining
                    ),
                    "netExteriorAreaMm2": cls._exterior_area(host, remaining),
                },
            )
            if host.kind == "framing":
                updated = elements[host_id]
                elements[host_id] = replace(
                    updated,
                    data={
                        **updated.data,
                        "memberCount": len(remaining),
                        "memberIndices": [
                            int(mesh.role.split(":")[-1]) for mesh in remaining
                        ],
                    },
                )
            elements[cut.element_id] = replace(
                cut,
                meshes=(void,),
                data={
                    **cut.data,
                    "cutVolumeMm3": SolidOperations.volume(void),
                },
            )

        CutLimits.apply(elements, originals)

    @staticmethod
    def _exterior_area(host: ResolvedElement, meshes: list[MeshData]) -> float | None:
        """Measure remaining exterior/top faces of cut envelope components."""
        if host.kind == "slab":
            return SolidOperations.planar_area(
                [mesh for mesh in meshes if mesh.role.endswith("layer:0")],
                (0, 0, number(host.data.get("topElevation"), "slab top")),
                (0, 0, 1),
            )
        if host.kind == "roof":
            area = 0.0
            for value in Authoring.array(host.data.get("planes")):
                plane = Authoring.object(value)
                boundary = [
                    vector3(point, "roof plane")
                    for point in Authoring.array(plane.get("boundary"))
                ]
                normal = polygon_normal(boundary)
                if normal[2] < 0:
                    normal = (-normal[0], -normal[1], -normal[2])
                area += SolidOperations.planar_area(
                    [
                        mesh
                        for mesh in meshes
                        if mesh.role == f"roof-face:{plane['id']}:layer:0"
                    ],
                    boundary[0],
                    normal,
                )
            return area
        if host.kind != "wall":
            return None
        profile = [
            vector3(point, "wall top profile")
            for point in Authoring.array(host.data.get("topProfile"))
        ]
        thickness = number(host.data.get("thickness"), "wall thickness")
        exterior = {"exterior": 0.0, "interior": thickness}.get(
            str(host.data.get("locationLine")), thickness / 2
        )
        area = 0.0
        for index, (a, b) in enumerate(zip(profile, profile[1:])):
            normal = ConstructionGeometry.unit((a[1] - b[1], b[0] - a[0], 0))
            origin: Vec3 = (
                a[0] + normal[0] * exterior,
                a[1] + normal[1] * exterior,
                a[2],
            )
            area += SolidOperations.planar_area(
                [
                    mesh
                    for mesh in meshes
                    if mesh.role.startswith(f"body:{index + 1}:")
                    and mesh.role.endswith("layer:0")
                ],
                origin,
                normal,
            )
        return area

    @staticmethod
    def _selected_layers(host: ResolvedElement, value: JsonValue) -> list[int] | None:
        """Check layer selection before modifying any of the host's meshes."""
        if value is None:
            return None
        count = len(Authoring.array(host.data.get("layers", [])))
        indices = Authoring.array(value)
        if any(
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < count
            for index in indices
        ):
            raise ResolutionError(
                f"Penetration selects an unavailable layer on {host.element_id}"
            )
        return [int(number(index, "cut layer index")) for index in indices]
