"""Solid and hollow service routes with shared material, passage and clearance geometry."""

from __future__ import annotations

from home_design.capabilities import ComponentRegistry

import math
from dataclasses import replace

from shapely.geometry import Point, Polygon, box

from home_design.components import ConstructionResolver
from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.electrical import ElectricalStock
from home_design.plumbing import PlumbingRoutes
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject
from home_design.mechanical import MechanicalDucts
from home_design.placement import LocalFrame
from home_design.resolved import MeshData, ResolvedElement, Vec3
from home_design.round_paths import RoundPath
from home_design.service_ports import ServicePorts
from home_design.solids import SolidOperations


class RouteGeometry:
    """Use one transported frame sequence for the outside, bore and construction clearance."""

    def __init__(self, definition: JsonObject, source: JsonObject) -> None:
        """Read outside dimensions and reserve a shared tessellation error budget."""
        self.section: JsonObject = Authoring.object(definition["section"])
        self.thickness: float = number(
            definition.get("wallThickness", 0), "route wall thickness"
        )
        self.clearance: float = number(source.get("clearance", 0), "route clearance")
        self.tolerance: float = number(
            source["chordTolerance"], "route chord tolerance"
        )
        self.radius: float = number(source.get("bendRadius", 0), "route bend radius")
        self.quadrants: int = 1
        self.section_error: float = 0
        if self.section["kind"] == "circle":
            radius = (
                number(self.section["diameter"], "route diameter") / 2 + self.clearance
            )
            half_angle = math.acos(max(-1, 1 - self.tolerance / 2 / radius))
            if half_angle <= 0:
                raise ResolutionError("Route tolerance is below numeric resolution")
            self.quadrants = max(2, math.ceil(math.pi / 4 / half_angle))
            if self.quadrants * 4 > RoundPath.MAX_SECTIONS:
                raise ResolutionError("Route section requires more than 10000 sides")
            self.section_error = radius * (1 - math.cos(math.pi / (4 * self.quadrants)))

    def profile(self, offset: float) -> Polygon:
        """Offset a circular or rectangular outside section without changing its vertex pattern."""
        if self.section["kind"] == "circle":
            radius = number(self.section["diameter"], "route diameter") / 2 + offset
            if radius <= 0:
                raise ResolutionError("Route wall thickness leaves no bore")
            return Point(0, 0).buffer(radius, quad_segs=self.quadrants)
        width = number(self.section["width"], "route width") + 2 * offset
        height = number(self.section["height"], "route height") + 2 * offset
        if min(width, height) <= 0:
            raise ResolutionError("Route wall thickness leaves no bore")
        return box(-width / 2, -height / 2, width / 2, height / 2)

    def extent(self) -> float:
        """Return an analytic radius bounding every clearance-section vertex."""
        if self.section["kind"] == "circle":
            return (
                number(self.section["diameter"], "route diameter") / 2 + self.clearance
            )
        return math.hypot(
            number(self.section["width"], "route width") / 2 + self.clearance,
            number(self.section["height"], "route height") / 2 + self.clearance,
        )

    def resolve(
        self, points: list[Vec3], material: str, up: Vec3 | None
    ) -> tuple[MeshData, dict[str, MeshData], list[LocalFrame], JsonObject]:
        """Create disjoint route material and reusable masks from exactly matching loft stations."""
        outside = self.profile(0)
        inside = self.profile(-self.thickness) if self.thickness else None
        step = min(
            math.pi / 2,
            2
            * math.acos(
                max(
                    -1,
                    1
                    - (self.tolerance - self.section_error)
                    / (self.radius + self.extent()),
                )
            ),
        )
        if step <= 0:
            raise ResolutionError("Route bend tolerance is below numeric resolution")
        path = RoundPath(points, self.extent() * 2, self.radius, self.tolerance)
        frames = path.frames(step, up)
        envelope = path.loft(outside, frames, None, "construction:envelope")
        volumes = {"envelope": envelope}
        body = replace(envelope, material_id=material, role="body")
        if inside is not None:
            bore = path.loft(inside, frames, None, "construction:bore")
            volumes["bore"] = bore
            wall = outside.difference(inside)
            if not isinstance(wall, Polygon):
                raise ResolutionError(
                    "Hollow route section requires one connected wall profile"
                )
            body = path.continuous_loft(wall, frames, material, "body")
        volumes["clearance"] = (
            path.loft(
                self.profile(self.clearance), frames, None, "construction:clearance"
            )
            if self.clearance
            else replace(envelope, role="construction:clearance")
        )
        area = outside.area - (inside.area if inside is not None else 0)
        return (
            body,
            volumes,
            frames,
            {
                "centerlineLengthMm": path.length,
                "sectionAreaMm2": area,
                "maxDeviationMm": path.max_deviation + self.section_error,
                "sectionCount": len(frames),
                "sectionSides": len(outside.exterior.coords) - 1,
                "path": [list(frame.origin) for frame in frames],
                "pathControls": [list(point) for point in points],
                "sectionUp": list(frames[0].y),
                "wallThickness": self.thickness,
                "bendRadius": self.radius,
                "clearance": self.clearance,
                "constructionVolumeMm3": {
                    key: SolidOperations.volume(mesh) for key, mesh in volumes.items()
                },
            },
        )


class ServiceRoutes:
    """Resolve two-port pipe, duct, cable and conduit routes on authored 3D paths."""

    KINDS: frozenset[str] = ComponentRegistry.resolver_kinds("route")
    FAMILY_MEDIA: dict[str, frozenset[str]] = {
        "pipe": frozenset(
            {"water", "waste", "vent", "gas", "refrigerant", "condensate", "other"}
        ),
        "duct": frozenset({"air", "other"}),
        "cable": frozenset({"electrical", "communications"}),
        "conduit": frozenset({"electrical", "communications", "other"}),
    }

    @classmethod
    def validate_family(cls, definition: JsonObject) -> None:
        """Keep electrical containment interfaces distinct from conductive service stock."""
        family = Authoring.text(definition["family"])
        if definition["medium"] not in cls.FAMILY_MEDIA[family]:
            raise ResolutionError(
                f"Service route/fitting family {family} has incompatible medium"
            )
        function = definition.get("function")
        if function is not None and (
            (family == "conduit" and function != "containment")
            or (family != "conduit" and function == "containment")
        ):
            raise ResolutionError(
                f"Service route/fitting family {family} has incompatible port function"
            )

    @staticmethod
    def _up(construction: ConstructionResolver, source: JsonObject) -> Vec3 | None:
        """Use authored world up, or inherit the starting port's oriented section Y axis."""
        if "up" in source:
            return vector3(source["up"], "route up")
        start = Authoring.object(Authoring.array(source["path"])[0])
        if "port" in start:
            return ServicePorts.frame(
                ServicePorts.lookup(
                    construction.context, Authoring.object(start["port"])
                )
            ).y
        return None

    @staticmethod
    def _ports(
        definition: JsonObject, frames: list[LocalFrame], states: JsonObject
    ) -> JsonObject:
        """Create opposed outward endpoint frames with the loft's actual rectangular orientation."""
        forward = definition.get("flow", "bidirectional") == "forward"
        ports: JsonObject = {}
        for key, frame, sign, flow in (
            ("start", frames[0], -1, "sink" if forward else "bidirectional"),
            ("end", frames[-1], 1, "source" if forward else "bidirectional"),
        ):
            ports[key] = {
                "position": list(frame.origin),
                "direction": [value * sign for value in frame.z],
                "up": list(frame.y),
                "section": definition["section"],
                "medium": definition["medium"],
                "connectionType": definition["connectionType"],
                "flow": flow,
                **(
                    {"function": definition["function"]}
                    if "function" in definition
                    else {}
                ),
            }
        return ServicePorts.resolve(
            ports, LocalFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), states
        )

    @classmethod
    def resolve(
        cls, construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Build a physical route with ports and separately retained construction-only masks."""
        definition = construction.component_type(source)
        family = Authoring.text(definition["family"])
        cls.validate_family(definition)
        points = construction.path(source)
        geometry = RouteGeometry(definition, source)
        material = Authoring.text(definition["material"])
        body, volumes, frames, data = geometry.resolve(
            points, material, cls._up(construction, source)
        )
        return ResolvedElement(
            element_id,
            "serviceRoute",
            Authoring.text(source["name"]),
            Authoring.text(source["storey"]) if "storey" in source else None,
            (body,),
            {
                **data,
                **ElectricalStock.resolve(
                    definition, number(data["centerlineLengthMm"], "route length")
                ),
                **PlumbingRoutes.resolve(definition, source, points),
                **MechanicalDucts.resolve(definition, source),
                "typeId": source["type"],
                "family": family,
                "materialId": material,
                "section": definition["section"],
                "placement": frames[0].to_dict(),
                "ports": cls._ports(
                    definition, frames, Authoring.object(source.get("portStates", {}))
                ),
                "portGroups": [["start", "end"]],
                "netVolumeMm3": SolidOperations.volume(body),
            },
            volumes,
        )

    @classmethod
    def refresh(cls, elements: dict[str, ResolvedElement]) -> None:
        """Require an owned bore cut to remove no further host material.

        Reuse the cut partition for this post-cut check; an independent
        intersection can retain spurious coincident boundary sheets.
        """
        for route in elements.values():
            if (
                route.kind not in cls.KINDS | {"serviceFitting"}
                or "bore" not in route.construction_volumes
            ):
                continue
            regions = Authoring.array(
                Authoring.object(route.data.get("occupies", {})).get("regions", [])
            )
            hosts = {
                Authoring.text(Authoring.object(region)["host"]) for region in regions
            }
            bore = route.construction_volumes["bore"]
            for host_id in sorted(hosts):
                if any(
                    SolidOperations.partition(mesh, bore)[1] is not None
                    for mesh in elements[host_id].meshes
                ):
                    raise ResolutionError(
                        f"Service component {route.element_id} has host material inside its bore at {host_id}; add an owned construction-volume penetration"
                    )
