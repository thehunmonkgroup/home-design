"""Resolution of construction members, stairs, enclosures and site components."""

from __future__ import annotations

from home_design.capabilities import ComponentRegistry
from home_design.boundaries import BoundaryIdentity

import math
from typing import Protocol

from shapely.geometry import Point

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.drainage import DrainageFall
from home_design.geometry import (
    extrude_polygon,
    normalize2,
    number,
    oriented_box,
    polygon_from_loops,
    vector2,
    vector3,
)
from home_design.json_types import JsonObject, JsonValue
from home_design.locators import LocatorResolver
from home_design.placement import HostPlacement, LocalFrame
from home_design.service_ports import ServicePorts
from home_design.resolved import MeshData, ResolvedElement, Vec3
from home_design.terrain import TerrainSurface
from home_design.member_geometry import MemberGeometry


class ResolutionContext(Protocol):
    """Dependency-aware services supplied by the canonical resolver."""

    elements: dict[str, JsonObject]
    types: dict[str, JsonObject]
    locators: LocatorResolver

    def elevation(self, datum: JsonObject) -> float:
        """Resolve a sampled surface or level elevation."""
        ...

    def resolve_component(self, element_id: str) -> ResolvedElement:
        """Resolve one canonical dependency by ID."""
        ...


class ConstructionResolver:
    """Generate construction geometry from reusable types and dependencies."""

    KINDS: frozenset[str] = ComponentRegistry.resolver_kinds("construction", "panel")

    def __init__(self, context: ResolutionContext) -> None:
        """Share canonical references and surface-query services."""
        self.context: ResolutionContext = context

    def point(self, value: JsonValue) -> Vec3:
        """Resolve a literal, shared anchor or grade/element-connected 3D point."""
        locator = Authoring.object(value, "3D locator")
        if "port" in locator:
            return ServicePorts.frame(
                ServicePorts.lookup(self.context, Authoring.object(locator["port"]))
            ).origin
        if "host" in locator:
            return (
                HostPlacement(self.context)
                .resolve(Authoring.object(locator["host"], "host placement"))
                .origin
            )
        if "anchor" in locator:
            point = self.context.locators.point3_anchor(
                Authoring.text(locator["anchor"])
            )
            offset = vector3(locator.get("offset", [0, 0, 0]), "anchor point offset")
            return point[0] + offset[0], point[1] + offset[1], point[2] + offset[2]
        if "elevation" in locator:
            x, y = vector2(locator.get("point"), "plan point")
            return x, y, self.context.elevation(Authoring.object(locator["elevation"]))
        return vector3(locator.get("point"), "3D point")

    def resolve(self, element_id: str, element: JsonObject) -> ResolvedElement:
        """Dispatch a schema-validated construction element."""
        kind = Authoring.text(element.get("kind"))
        handlers = {
            "member": self.members,
            "framing": self.members,
            "footing": self.footing,
            "stair": self.stair,
            "railing": self.enclosure,
            "panel": self.enclosure,
            "terrain": self.terrain,
            "sweep": self.sweep,
            "load": self.load,
            "detail": self.detail,
        }
        meshes, data = handlers[kind](element)
        data.update({"typeId": element.get("type"), "role": element.get("role")})
        storey = element.get("storey")
        return ResolvedElement(
            element_id,
            kind,
            str(element.get("name")),
            storey if isinstance(storey, str) else None,
            meshes,
            data,
        )

    def placement(self, value: JsonObject) -> LocalFrame:
        """Resolve a solid's origin and intrinsic orientation from shared locators."""
        origin = Authoring.object(value.get("origin"), "placement origin")
        if "port" in origin:
            frame = ServicePorts.frame(
                ServicePorts.lookup(self.context, Authoring.object(origin["port"]))
            )
        elif "host" in origin:
            frame = HostPlacement(self.context).resolve(
                Authoring.object(origin["host"])
            )
        else:
            frame = LocalFrame(self.point(origin), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        return frame.adjusted(
            (0, 0, 0),
            vector3(value.get("rotation", [0, 0, 0]), "placement rotation"),
        )

    def component_type(self, element: JsonObject) -> JsonObject:
        """Return a validated reusable construction type."""
        return self.context.types[Authoring.text(element.get("type"), "component type")]

    def members(self, element: JsonObject) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Resolve one member or an explicitly spaced framing group."""
        component_type = self.component_type(element)
        start, end = [
            self.point(value) for value in Authoring.array(element.get("axis"))
        ]
        section = Authoring.object(component_type.get("section"))
        material = Authoring.text(component_type.get("material"))
        count = int(number(element.get("count", 1), "member count"))
        distribution = vector3(
            element.get("distribution", [0, 0, 0]), "framing distribution"
        )
        if element.get("kind") == "framing" and not math.isclose(
            sum(value * value for value in distribution), 1, abs_tol=1e-6
        ):
            raise ResolutionError("Framing distribution must be a unit vector")
        spacing = number(element.get("spacing", 0), "framing spacing")
        omit = Authoring.array(element.get("omit", []))
        if any(not isinstance(index, int) or index >= count for index in omit):
            raise ResolutionError(
                "Omitted framing index is outside its repetition count"
            )
        template = ConstructionGeometry.member(
            start,
            end,
            section,
            material,
            "member",
            number(element.get("roll", 0), "member roll"),
        )
        cuts = Authoring.object(element.get("endCuts", {}))
        if cuts:
            frame = MemberGeometry.frame(
                start, end, number(element.get("roll", 0), "member roll")
            )
            template = MemberGeometry.end_cuts(
                template, frame, math.dist(start, end), cuts
            )
        meshes = tuple(
            ConstructionGeometry.translated(
                template,
                (
                    distribution[0] * spacing * index,
                    distribution[1] * spacing * index,
                    distribution[2] * spacing * index,
                ),
                f"member:{index}",
            )
            for index in range(count)
            if index not in omit
        )
        return meshes, {
            "axis": [list(start), list(end)],
            **({"endCuts": cuts} if cuts else {}),
            "memberCount": len(meshes),
            "memberLength": math.dist(start, end),
            "section": section,
            "spacing": spacing,
            "memberIndices": [index for index in range(count) if index not in omit],
            "distribution": list(distribution),
        }

    def footing(self, element: JsonObject) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Resolve a pad, strip, or pier against its individual top datum."""
        component_type = self.component_type(element)
        if "footprint" in element:
            outer, holes = self.context.locators.profile2(element["footprint"])
            polygon = polygon_from_loops(outer, holes)
        else:
            polygon = Point(vector2(element.get("center"), "pier center")).buffer(
                number(element.get("diameter"), "pier diameter") / 2, quad_segs=16
            )
        top = self.context.elevation(Authoring.object(element.get("datum")))
        depth = number(component_type.get("depth"), "footing depth")
        material = Authoring.text(component_type.get("material"))
        explicit = component_type.get("representation") == "explicit"
        mesh = extrude_polygon(
            polygon,
            top - depth,
            top,
            material,
            "footing:layer:0" if explicit else "footing",
        )
        return (mesh,), {
            "shape": element.get("shape"),
            "topElevation": top,
            "bottomElevation": top - depth,
            "area": polygon.area,
            "volume": polygon.area * depth,
            **(
                {
                    "layers": [
                        {
                            "id": "layer.legacy.0",
                            "name": "Foundation body",
                            "thickness": depth,
                            "material": material,
                            "function": "structure",
                            "representation": "explicit",
                        }
                    ]
                }
                if explicit
                else {}
            ),
            "footprint": {
                "outer": [list(point) for point in list(polygon.exterior.coords)[:-1]],
                **(
                    {
                        "boundaryIds": BoundaryIdentity.metadata(
                            Authoring.object(element["footprint"])
                        )
                    }
                    if "footprint" in element
                    else {}
                ),
            },
        }

    def stair(self, element: JsonObject) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Derive uniform risers, treads and side stringers between connected datums."""
        component_type = self.component_type(element)
        bottom = self.context.elevation(Authoring.object(element.get("bottom")))
        top = self.context.elevation(Authoring.object(element.get("top")))
        rise = top - bottom
        if rise <= 0:
            raise ResolutionError("Stair top must be above its bottom")
        maximum = number(component_type.get("maxRiser"), "maximum riser")
        count = int(
            number(
                element.get("riserCount", max(2, math.ceil(rise / maximum))),
                "riser count",
            )
        )
        riser = rise / count
        minimum = number(component_type.get("minRiser", 0), "minimum riser")
        if riser > maximum + 0.01 or riser < minimum - 0.01:
            raise ResolutionError(
                f"Stair riser {riser:g} mm is outside its specified [{minimum:g}, {maximum:g}] range"
            )
        tread = number(component_type.get("treadDepth"), "tread depth")
        thickness = number(component_type.get("treadThickness"), "tread thickness")
        if thickness > riser:
            raise ResolutionError("Tread thickness exceeds the stair riser")
        width = number(element.get("clearWidth"), "stair clear width")
        origin = vector2(element.get("origin"), "stair origin")
        dx, dy = normalize2(
            vector2(element.get("direction"), "stair direction"), "stair direction"
        )
        material = Authoring.text(component_type.get("material"))
        nosing = number(component_type.get("nosing", 0), "stair nosing")
        meshes: list[MeshData] = []
        for index in range(count - 1):
            station = (index + 0.5) * tread - nosing / 2
            center: Vec3 = (
                origin[0] + dx * station,
                origin[1] + dy * station,
                bottom + (index + 1) * riser - thickness,
            )
            meshes.append(
                oriented_box(
                    center,
                    (-dy, dx),
                    width,
                    tread + nosing,
                    thickness,
                    material,
                    f"tread:{index}",
                )
            )
        run = (count - 1) * tread
        stringer_type = self.context.types[
            Authoring.text(component_type.get("stringerType"))
        ]
        section = Authoring.object(stringer_type.get("section"))
        bounds = ConstructionGeometry.section(section).bounds
        half_stringer = max(abs(bounds[0]), abs(bounds[2]))
        for side in (-1, 1):
            offset = side * (width / 2 + half_stringer)
            start: Vec3 = (
                origin[0] - dy * offset,
                origin[1] + dx * offset,
                bottom + riser - thickness + bounds[1],
            )
            end: Vec3 = (
                start[0] + dx * run,
                start[1] + dy * run,
                top - thickness + bounds[1],
            )
            meshes.append(
                ConstructionGeometry.member(
                    start,
                    end,
                    section,
                    Authoring.text(stringer_type.get("material")),
                    f"stringer:{side}",
                )
            )
        return tuple(meshes), {
            "bottomElevation": bottom,
            "topElevation": top,
            "riserCount": count,
            "riserHeight": riser,
            "treadDepth": tread,
            "treadCount": count - 1,
            "clearWidth": width,
            "run": run,
            "path": [
                [origin[0], origin[1], bottom + riser],
                [origin[0] + dx * run, origin[1] + dy * run, top],
            ],
            "landingRequiredAtEnds": True,
        }

    def path(self, element: JsonObject) -> list[Vec3]:
        """Resolve an authored path or follow a stair side or slab perimeter edge."""
        if "path" in element:
            return [self.point(value) for value in Authoring.array(element["path"])]
        follow = Authoring.object(element.get("follow"))
        dependency = self.context.resolve_component(
            Authoring.text(follow.get("element"))
        )
        offset = number(follow.get("offset", 0), "path offset")
        if dependency.kind == "stair":
            path = [
                vector3(point, "stair path")
                for point in Authoring.array(dependency.data.get("path"))
            ]
            dx, dy = normalize2(
                (path[-1][0] - path[0][0], path[-1][1] - path[0][1]), "stair path"
            )
            side = -1 if follow.get("side", "left") == "right" else 1
            width = number(dependency.data.get("clearWidth"), "stair width")
            component_type = self.component_type(element)
            if element.get("kind") == "railing":
                section = Authoring.object(
                    component_type.get(
                        "railSection"
                        if element.get("role") == "handrail"
                        else "postSection"
                    )
                )
                bounds = ConstructionGeometry.section(section).bounds
                allowance = max(abs(value) for value in bounds)
            else:
                allowance = (
                    number(component_type.get("frameWidth"), "screen frame width") / 2
                )
            distance = side * (width / 2 + allowance + offset)
            return [(x - dy * distance, y + dx * distance, z) for x, y, z in path]
        if dependency.kind in {"slab", "footing"}:
            footprint = Authoring.object(dependency.data.get("footprint"))
            loop = [
                vector2(point, "deck edge")
                for point in Authoring.array(footprint.get("outer"))
            ]
            index = BoundaryIdentity.select(
                BoundaryIdentity.profile(footprint)[0],
                follow.get("edge", follow.get("edgeIndex", 0)),
            )
            start, end = loop[index], loop[(index + 1) % len(loop)]
            dx, dy = normalize2((end[0] - start[0], end[1] - start[1]), "deck edge")
            z = number(dependency.data.get("topElevation"), "deck top")
            return [
                (point[0] - dy * offset, point[1] + dx * offset, z)
                for point in (start, end)
            ]
        raise ResolutionError(
            "Enclosure follow must reference a stair, slab or footing"
        )

    def enclosure(self, element: JsonObject) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Generate guards/handrails or framed screens while retaining access gaps."""
        component_type = self.component_type(element)
        points = self.path(element)
        lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
        total = sum(lengths)
        openings = [
            (
                number(Authoring.object(value).get("start"), "opening start"),
                number(Authoring.object(value).get("end"), "opening end"),
            )
            for value in Authoring.array(element.get("openings", []))
        ]
        intervals = ConstructionGeometry.interval_segments(total, openings)
        meshes: list[MeshData] = []
        station = 0.0
        for start, end, length in zip(points, points[1:], lengths):
            direction = ConstructionGeometry.unit(
                (end[0] - start[0], end[1] - start[1], end[2] - start[2])
            )
            for interval_start, interval_end in intervals:
                low, high = max(station, interval_start), min(
                    station + length, interval_end
                )
                if high <= low:
                    continue
                a = self._along(start, direction, low - station)
                b = self._along(start, direction, high - station)
                meshes.extend(self._enclosure_segment(a, b, element, component_type))
            station += length
        return tuple(meshes), {
            "path": [list(point) for point in points],
            "height": component_type.get("height"),
            "length": total,
            "openings": element.get("openings", []),
            "isStructuralGuard": element.get("kind") == "railing"
            and element.get("role") == "guard",
        }

    def _enclosure_segment(
        self, start: Vec3, end: Vec3, element: JsonObject, component_type: JsonObject
    ) -> list[MeshData]:
        height = number(component_type.get("height"), "enclosure height")
        material = Authoring.text(component_type.get("material"))
        if element.get("kind") == "panel":
            return self._screen_segment(start, end, component_type)
        rail_section = Authoring.object(component_type.get("railSection"))
        top_start, top_end = (start[0], start[1], start[2] + height), (
            end[0],
            end[1],
            end[2] + height,
        )
        meshes = [
            ConstructionGeometry.member(
                top_start,
                top_end,
                rail_section,
                material,
                "handrail" if element.get("role") == "handrail" else "guard-rail",
            )
        ]
        if element.get("role") == "handrail":
            return meshes
        spacing = number(component_type.get("postSpacing"), "post spacing")
        length = math.dist(start, end)
        count = max(1, math.ceil(length / spacing))
        post_section = Authoring.object(component_type.get("postSection"))
        for index in range(count + 1):
            point = self._interpolate(start, end, index / count)
            meshes.append(
                ConstructionGeometry.member(
                    point,
                    (point[0], point[1], point[2] + height),
                    post_section,
                    material,
                    "guard-post",
                )
            )
        if component_type.get("infill") == "balusters":
            section = Authoring.object(
                component_type.get("balusterSection"), "baluster section"
            )
            bounds = ConstructionGeometry.section(section).bounds
            thickness = bounds[2] - bounds[0]
            gap = number(component_type.get("maxInfillGap"), "maximum infill gap")
            count = max(1, math.ceil(length / (gap + thickness)))
            for index in range(1, count):
                point = self._interpolate(start, end, index / count)
                meshes.append(
                    ConstructionGeometry.member(
                        point,
                        (point[0], point[1], point[2] + height),
                        section,
                        material,
                        "baluster",
                    )
                )
        return meshes

    def _screen_segment(
        self, start: Vec3, end: Vec3, component_type: JsonObject
    ) -> list[MeshData]:
        height = number(component_type.get("height"), "screen height")
        width = number(component_type.get("frameWidth"), "screen frame width")
        depth = number(component_type.get("frameDepth"), "screen frame depth")
        material = Authoring.text(component_type.get("material"))
        length = math.dist(start, end)
        if length <= 2 * width or height <= 2 * width:
            raise ResolutionError("Screen frame leaves no usable infill")
        section: JsonObject = {"kind": "rectangle", "width": depth, "depth": width}
        meshes = []
        for z in (width / 2, height - width / 2):
            meshes.append(
                ConstructionGeometry.member(
                    (start[0], start[1], start[2] + z),
                    (end[0], end[1], end[2] + z),
                    section,
                    material,
                    "screen-frame",
                )
            )
        for point in (start, end):
            meshes.append(
                ConstructionGeometry.member(
                    point,
                    (point[0], point[1], point[2] + height),
                    {"kind": "rectangle", "width": width, "depth": depth},
                    material,
                    "screen-frame",
                )
            )
        a = self._interpolate(start, end, width / length)
        b = self._interpolate(start, end, 1 - width / length)
        meshes.append(
            ConstructionGeometry.member(
                (a[0], a[1], a[2] + height / 2),
                (b[0], b[1], b[2] + height / 2),
                {"kind": "rectangle", "width": 1, "depth": height - 2 * width},
                Authoring.text(component_type.get("infillMaterial")),
                "screen-infill",
            )
        )
        return meshes

    def terrain(self, element: JsonObject) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Resolve terrain without turning the site into a building solid."""
        surface = TerrainSurface.from_element(element)
        material = element.get("material")
        return (surface.mesh(material if isinstance(material, str) else None),), {
            "state": element.get("state"),
            "pointCount": len(surface.vertices),
            "triangleCount": len(surface.faces),
        }

    def sweep(self, element: JsonObject) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Resolve linear drainage/trim segments and measure their actual falls."""
        component_type = self.component_type(element)
        points = self.path(element)
        section = Authoring.object(component_type.get("section"))
        material = Authoring.text(component_type.get("material"))
        meshes = ConstructionGeometry.sweep(points, section, material)
        falls = DrainageFall.ratios(points)
        minimum = element.get("minFall")
        if isinstance(minimum, (int, float)):
            DrainageFall.check(points, minimum)
        return meshes, {
            "path": [list(point) for point in points],
            "length": sum(math.dist(a, b) for a, b in zip(points, points[1:])),
            "segmentFalls": falls,
            "outlet": element.get("outlet"),
        }

    def load(self, element: JsonObject) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Retain an explicit total load and its plan footprint on the target."""
        target = self.context.resolve_component(Authoring.text(element.get("target")))
        outer, holes = self.context.locators.profile2(element.get("footprint"))
        polygon = polygon_from_loops(outer, holes)
        return (), {
            "target": target.element_id,
            "footprint": {
                "outer": [list(point) for point in outer],
                "holes": [[list(point) for point in loop] for loop in holes],
            },
            "area": polygon.area,
            "forceN": element.get("forceN"),
            "category": element.get("category"),
            "foundationRequired": element.get("foundationRequired", True),
        }

    def detail(self, element: JsonObject) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Preserve reusable interface instructions and a coordinated location."""
        return (), {
            "participants": element.get("participants"),
            "location": list(self.point(element.get("location"))),
            "specification": self.component_type(element),
        }

    @staticmethod
    def _along(start: Vec3, direction: Vec3, distance: float) -> Vec3:
        return (
            start[0] + direction[0] * distance,
            start[1] + direction[1] * distance,
            start[2] + direction[2] * distance,
        )

    @staticmethod
    def _interpolate(start: Vec3, end: Vec3, ratio: float) -> Vec3:
        return (
            start[0] + (end[0] - start[0]) * ratio,
            start[1] + (end[1] - start[1]) * ratio,
            start[2] + (end[2] - start[2]) * ratio,
        )
