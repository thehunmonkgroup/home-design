"""Physical service insulation generated around resolved route and fitting envelopes."""

from __future__ import annotations

from home_design.capabilities import ComponentRegistry

import math
from copy import deepcopy
from dataclasses import replace
from itertools import combinations

from home_design.components import ConstructionResolver
from home_design.construction import Authoring
from home_design.constants import GEOMETRY_TOLERANCE_MM
from home_design.errors import ResolutionError
from home_design.fitting_geometry import FittingGeometry
from home_design.frames import LocalFrame
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject
from home_design.resolved import MeshData, ResolvedElement, Vec3
from home_design.service_ports import ServicePorts
from home_design.service_routes import RouteGeometry
from home_design.solids import SolidOperations


class ServiceInsulation:
    """Generate separate material stock without duplicating the service body or its passage."""

    KINDS: frozenset[str] = ComponentRegistry.resolver_kinds("insulation")

    @staticmethod
    def _outer(
        construction: ConstructionResolver,
        host: ResolvedElement,
        thickness: float,
        tolerance: float,
    ) -> MeshData:
        """Regenerate the outside mask with radial growth, also covering a cap's closed end."""
        definition = deepcopy(
            construction.context.types[Authoring.text(host.data["typeId"])]
        )
        if host.data.get("family") not in {"pipe", "duct"}:
            raise ResolutionError(
                "Service insulation requires a pipe or duct route/fitting"
            )
        if host.kind == "serviceRoute":
            geometry = RouteGeometry(
                definition,
                {
                    "chordTolerance": tolerance,
                    "clearance": thickness,
                    "bendRadius": host.data["bendRadius"],
                },
            )
            _, volumes, _, _ = geometry.resolve(
                [
                    vector3(value, "insulation path")
                    for value in Authoring.array(host.data["pathControls"])
                ],
                Authoring.text(definition["material"]),
                vector3(host.data["sectionUp"], "section up"),
            )
            return volumes["clearance"]
        definition["chordTolerance"] = tolerance
        recipe = Authoring.object(definition["geometry"])
        if recipe["kind"] == "cap":
            recipe["depth"] = number(recipe["depth"], "cap depth") + thickness
        outer = FittingGeometry(definition, thickness).resolve().volumes["clearance"]
        placement = Authoring.object(host.data["placement"])
        frame = LocalFrame.from_dict(placement)
        return frame.mesh(outer)

    @staticmethod
    def _on_port(point: Vec3, frame: LocalFrame, section: JsonObject) -> bool:
        """Identify cap vertices within an outside service interface."""
        delta = tuple(point[i] - frame.origin[i] for i in range(3))
        x, y, z = (
            sum(delta[i] * axis[i] for i in range(3))
            for axis in (frame.x, frame.y, frame.z)
        )
        tolerance = GEOMETRY_TOLERANCE_MM
        if abs(z) > tolerance:
            return False
        if section["kind"] == "circle":
            return (
                math.hypot(x, y)
                <= number(section["diameter"], "diameter") / 2 + tolerance
            )
        return (
            abs(x) <= number(section["width"], "width") / 2 + tolerance
            and abs(y) <= number(section["height"], "height") / 2 + tolerance
        )

    @classmethod
    def _extended_passage(cls, inner: MeshData, ports: JsonObject) -> MeshData:
        """Extend cap faces by one millimetre without changing the original passage boundary.

        A temporary cutter extends beyond mating faces to avoid coincident-cap
        Boolean triangulation. Its added volume must remove no extra cover stock.
        """
        vertices, faces = list(inner.vertices), list(inner.faces)
        for key in sorted(ports):
            port = Authoring.object(ports[key])
            frame = ServicePorts.frame(port)
            section = Authoring.object(port["section"])
            cap = {
                face
                for face in faces
                if all(cls._on_port(vertices[index], frame, section) for index in face)
            }
            edges: set[tuple[int, int]] = set()
            for face in sorted(cap):
                for first, second in zip(face, face[1:] + face[:1]):
                    if (second, first) in edges:
                        edges.remove((second, first))
                    else:
                        edges.add((first, second))
            shifted: dict[int, int] = {}
            for index in sorted({index for face in cap for index in face}):
                shifted[index] = len(vertices)
                vertices.append(
                    (
                        vertices[index][0] + frame.z[0],
                        vertices[index][1] + frame.z[1],
                        vertices[index][2] + frame.z[2],
                    )
                )
            faces = [face for face in faces if face not in cap]
            faces.extend(
                tuple(shifted[index] for index in face) for face in sorted(cap)
            )
            faces.extend(
                (first, second, shifted[second], shifted[first])
                for first, second in sorted(edges)
            )
        return replace(inner, vertices=tuple(vertices), faces=tuple(faces))

    @classmethod
    def _shell(
        cls, outer: MeshData, inner: MeshData, material: str, ports: JsonObject
    ) -> MeshData:
        """Preserve the exact envelope difference while avoiding coincident open end caps."""
        outside = SolidOperations.solid(outer)
        expected = outside - SolidOperations.solid(inner)
        extended = outside - SolidOperations.solid(cls._extended_passage(inner, ports))
        candidate = (
            extended
            if math.isclose(
                extended.volume(),
                expected.volume(),
                rel_tol=1e-9,
                abs_tol=SolidOperations.OUTPUT_VOLUME_TOLERANCE_MM3,
            )
            else expected
        )
        try:
            body = SolidOperations.mesh(candidate, material, "body")
        except ResolutionError:
            body = SolidOperations.mesh(expected, material, "body")
        if body is None:
            raise ResolutionError("Service insulation has no physical material")
        return body

    @classmethod
    def resolve(
        cls, construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Build a physical covering from an expanded envelope minus the exact original envelope."""
        host = construction.context.resolve_component(Authoring.text(source["host"]))
        if host.kind not in {"serviceRoute", "serviceFitting"}:
            raise ResolutionError("Service insulation requires a route or fitting host")
        definition = construction.component_type(source)
        thickness = number(definition["thickness"], "insulation thickness")
        tolerance = min(
            number(source["chordTolerance"], "insulation tolerance"), thickness / 4
        )
        outer = cls._outer(construction, host, thickness, tolerance)
        inner = host.construction_volumes["envelope"]
        if SolidOperations.difference(inner, [outer]) is not None:
            raise ResolutionError(
                "Insulation envelope does not enclose its host; refine the host or insulation chord tolerance"
            )
        material = Authoring.text(definition["material"])
        body = cls._shell(outer, inner, material, Authoring.object(host.data["ports"]))
        storey = source.get("storey", host.storey_id)
        return ResolvedElement(
            element_id,
            "serviceInsulation",
            Authoring.text(source["name"]),
            storey if isinstance(storey, str) else None,
            (body,),
            {
                "typeId": source["type"],
                "role": "insulation",
                "materialId": material,
                "host": source["host"],
                "mountHostId": source["host"],
                "placement": host.data["placement"],
                "thickness": thickness,
                "chordTolerance": tolerance,
                "netVolumeMm3": SolidOperations.volume(body),
            },
            {"envelope": outer, "bore": inner, "clearance": outer},
        )

    @classmethod
    def refresh(cls, elements: dict[str, ResolvedElement]) -> None:
        """Reject duplicate physical coverings on one service after ownership and local cuts."""
        parts = [element for element in elements.values() if element.kind in cls.KINDS]
        for first, second in combinations(parts, 2):
            if first.data["host"] == second.data["host"] and any(
                SolidOperations.intersection(a, b) is not None
                for a in first.meshes
                for b in second.meshes
            ):
                raise ResolutionError(
                    f"Service insulation parts {first.element_id} and {second.element_id} overlap on their host"
                )
