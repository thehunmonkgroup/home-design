"""Boundary-fitted floor, deck and roof-face framing with explicit physical parts."""

from __future__ import annotations

import math
from dataclasses import replace

from shapely import get_coordinates
from shapely.affinity import affine_transform
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.layers import LayerAssembly
from home_design.geometry import (
    extrude_polygon,
    number,
    polygon_normal,
    vector2,
    vector3,
)
from home_design.json_types import JsonObject
from home_design.placement import LocalFrame, tuple3
from home_design.resolved import MeshData, ResolvedElement, Vec2, Vec3
from home_design.solids import SolidOperations
from home_design.member_geometry import MemberGeometry
from home_design.boundaries import BoundaryIdentity
from home_design.topology import NamedSpan, PartIdentity


class PlanarFraming:
    """Generate authored framing members within one slab layer or roof-face layer."""

    AREA_TOLERANCE: float = 1e-6

    def __init__(
        self, source: JsonObject, host: ResolvedElement, types: dict[str, JsonObject]
    ) -> None:
        """Set up the layer-center plane and its canonical planar boundary."""
        self.source: JsonObject = source
        self.host: ResolvedElement = host
        self.types: dict[str, JsonObject] = types
        self.definition: JsonObject = types[Authoring.text(source["type"])]
        self.layer: int = LayerAssembly.index(
            host.data["layers"], source["layer"], f"Host {host.element_id}"
        )
        self.depth: float
        offset: float
        offset, self.depth = self._layer_depth()
        self.frame: LocalFrame
        self.profile: Polygon
        self.boundaries: tuple[NamedSpan, ...] = ()
        self.identities: dict[str, str] = {}
        self.frame, self.profile = self._plane(offset)
        selected = [
            mesh for mesh in host.meshes if mesh.role.endswith(f"layer:{self.layer}")
        ]
        if host.kind == "roof":
            face_id = Authoring.text(source["face"], "roof face")
            selected = [
                mesh
                for mesh in selected
                if mesh.role.startswith(f"roof-face:{face_id}:")
            ]
        mask = SolidOperations.union(selected, None, "framing-domain")
        if mask is None:
            raise ResolutionError("Framing host layer has no physical domain")
        self.mask: MeshData = self._roof_miters(mask) if host.kind == "roof" else mask
        self.meshes: dict[str, MeshData] = {}
        self.records: dict[str, JsonObject] = {}
        self.regions: dict[str, Polygon] = {}

    def _layer_depth(self) -> tuple[float, float]:
        """Require an explicit layer and measure its center from the finished surface."""
        layers = [
            Authoring.object(value)
            for value in Authoring.array(self.host.data["layers"])
        ]
        if (
            not 0 <= self.layer < len(layers)
            or layers[self.layer].get("representation") != "explicit"
        ):
            raise ResolutionError("Planar framing requires an explicit host layer")
        depths = [number(layer["thickness"], "layer thickness") for layer in layers]
        return sum(depths[: self.layer]) + depths[self.layer] / 2, depths[self.layer]

    def _roof_miters(self, mask: MeshData) -> MeshData:
        """Partition adjacent roof-face framing at the bisector of their surface normals."""
        planes = [
            Authoring.object(value)
            for value in Authoring.array(self.host.data["planes"])
        ]
        selected = next(plane for plane in planes if plane["id"] == self.source["face"])
        boundary = [
            vector3(value, "roof boundary")
            for value in Authoring.array(selected["boundary"])
        ]
        perimeter = Polygon([(point[0], point[1]) for point in boundary]).boundary
        for plane in planes:
            if plane["id"] == selected["id"]:
                continue
            other = [
                vector3(value, "roof boundary")
                for value in Authoring.array(plane["boundary"])
            ]
            shared = perimeter.intersection(
                Polygon([(point[0], point[1]) for point in other]).boundary
            )
            if shared.length <= 0.01:
                continue
            normal = polygon_normal(other)
            if normal[2] < 0:
                normal = (-normal[0], -normal[1], -normal[2])
            if not self._same_edge_elevation(
                shared, boundary[0], self.frame.z, other[0], normal
            ):
                continue
            difference: Vec3 = tuple3(
                [self.frame.z[index] - normal[index] for index in range(3)]
            )
            if math.sqrt(sum(value * value for value in difference)) <= 1e-8:
                continue
            midpoint = shared.representative_point()
            z = (
                boundary[0][2]
                - (
                    self.frame.z[0] * (midpoint.x - boundary[0][0])
                    + self.frame.z[1] * (midpoint.y - boundary[0][1])
                )
                / self.frame.z[2]
            )
            origin = (midpoint.x, midpoint.y, z)
            inside = self.frame.point(
                (self.profile.centroid.x, self.profile.centroid.y, 0)
            )
            if (
                sum(
                    difference[index] * (inside[index] - origin[index])
                    for index in range(3)
                )
                < 0
            ):
                difference = tuple3([-value for value in difference])
            clipped = SolidOperations.clip_plane(mask, origin, difference)
            if clipped is None:
                raise ResolutionError(
                    "Roof miter consumes the entire selected framing face"
                )
            mask = clipped
            self._clip_profile(origin, difference)
        return mask

    @staticmethod
    def _same_edge_elevation(
        shared: BaseGeometry,
        first: Vec3,
        first_normal: Vec3,
        second: Vec3,
        second_normal: Vec3,
    ) -> bool:
        """Require a real shared spatial edge rather than coincident plan projections."""
        if second_normal[2] <= 1e-9:
            return False
        for x, y in get_coordinates(shared):
            a = (
                first[2]
                - (first_normal[0] * (x - first[0]) + first_normal[1] * (y - first[1]))
                / first_normal[2]
            )
            b = (
                second[2]
                - (
                    second_normal[0] * (x - second[0])
                    + second_normal[1] * (y - second[1])
                )
                / second_normal[2]
            )
            if abs(a - b) > 0.01:
                return False
        return True

    def _clip_profile(self, origin: Vec3, normal: Vec3) -> None:
        """Apply a spatial miter plane to the two-dimensional layer-center layout."""
        u = sum(normal[index] * self.frame.x[index] for index in range(3))
        v = sum(normal[index] * self.frame.y[index] for index in range(3))
        magnitude = math.hypot(u, v)
        if magnitude <= 1e-9:
            raise ResolutionError("Roof miter is parallel to the framing plane")
        offset = (
            sum(
                normal[index] * (origin[index] - self.frame.origin[index])
                for index in range(3)
            )
            / magnitude
        )
        u, v = u / magnitude, v / magnitude
        span = 4 * (max(abs(value) for value in self.profile.bounds) + abs(offset) + 1)
        center = (u * offset, v * offset)
        half = Polygon(
            [
                (center[0] - v * span, center[1] + u * span),
                (center[0] + v * span, center[1] - u * span),
                (center[0] + v * span + u * span, center[1] - u * span + v * span),
                (center[0] - v * span + u * span, center[1] + u * span + v * span),
            ]
        )
        result = self.profile.intersection(half)
        if not isinstance(result, Polygon) or result.is_empty:
            raise ResolutionError(
                "Roof miter divides the framing face into disconnected regions"
            )
        self.profile = result

    def _plane(self, offset: float) -> tuple[LocalFrame, Polygon]:
        """Offset a finished boundary along its normal onto the layer center plane."""
        normal: Vec3 = (0, 0, 1)
        holes: list[list[Vec3]] = []
        if self.host.kind == "roof":
            planes = [
                Authoring.object(value)
                for value in Authoring.array(self.host.data["planes"])
            ]
            selected = [
                plane for plane in planes if plane["id"] == self.source.get("face")
            ]
            if len(selected) != 1:
                raise ResolutionError("Roof framing requires an existing face ID")
            boundary = [
                vector3(value, "roof boundary")
                for value in Authoring.array(selected[0]["boundary"])
            ]
            names = BoundaryIdentity.profile(
                {
                    "outer": selected[0]["boundary"],
                    **(
                        {"boundaryIds": selected[0]["boundaryIds"]}
                        if "boundaryIds" in selected[0]
                        else {}
                    ),
                }
            )
            normal = polygon_normal(boundary)
            if normal[2] < 0:
                normal = (-normal[0], -normal[1], -normal[2])
        else:
            if "face" in self.source:
                raise ResolutionError("Only roof framing accepts a face ID")
            footprint = Authoring.object(self.host.data["footprint"])
            names = BoundaryIdentity.profile(footprint)
            elevation = number(self.host.data["topElevation"], "slab top")
            boundary = [
                (point[0], point[1], elevation)
                for point in (
                    vector2(value, "slab boundary")
                    for value in Authoring.array(footprint["outer"])
                )
            ]
            holes = [
                [
                    (point[0], point[1], elevation)
                    for point in (
                        vector2(value, "slab hole") for value in Authoring.array(loop)
                    )
                ]
                for loop in Authoring.array(footprint.get("holes", []))
            ]
        direction = vector2(self.source["direction"], "framing direction")
        if normal[2] <= 1e-9:
            raise ResolutionError("Planar roof framing requires a nonvertical face")
        if not math.isclose(math.hypot(*direction), 1, abs_tol=1e-6):
            raise ResolutionError("Framing direction must be a unit plan vector")
        along = ConstructionGeometry.unit(
            (
                direction[0],
                direction[1],
                -(normal[0] * direction[0] + normal[1] * direction[1]) / normal[2],
            )
        )
        across = ConstructionGeometry.cross(normal, along)
        origin_index = BoundaryIdentity.select(
            names[0], self.source.get("originBoundary", 0)
        )
        origin = (
            boundary[origin_index][0] - normal[0] * offset,
            boundary[origin_index][1] - normal[1] * offset,
            boundary[origin_index][2] - normal[2] * offset,
        )
        frame = LocalFrame(origin, along, across, normal)

        def local(point: Vec3) -> Vec2:
            """Offset a finished-surface point normally to the layer center."""
            delta = (
                point[0] - normal[0] * offset - origin[0],
                point[1] - normal[1] * offset - origin[1],
                point[2] - normal[2] * offset - origin[2],
            )
            return sum(delta[i] * along[i] for i in range(3)), sum(
                delta[i] * across[i] for i in range(3)
            )

        loops = [[local(point) for point in loop] for loop in [boundary, *holes]]
        self.boundaries = tuple(
            NamedSpan(identity, loop[index], loop[(index + 1) % len(loop)])
            for loop, identities in zip(loops, names)
            for index, identity in enumerate(identities)
        )
        outer = loops[0][origin_index:] + loops[0][:origin_index]
        return frame, Polygon(outer, loops[1:])

    def _section(self, type_id: str) -> tuple[float, float]:
        """Read a rectangular section in transverse-width and surface-normal depth."""
        section = Authoring.object(self.types[type_id]["section"])
        if section.get("kind") != "rectangle":
            raise ResolutionError("Planar framing requires rectangular member types")
        width, depth = number(section["width"], "member width"), number(
            section["depth"], "member depth"
        )
        if depth > self.depth + 1e-6:
            raise ResolutionError(f"Member type {type_id} exceeds the host layer depth")
        return width, depth

    @classmethod
    def _polygons(cls, value: BaseGeometry) -> list[Polygon]:
        """Extract significant polygonal regions, retaining disconnected physical boards."""
        if isinstance(value, Polygon):
            return [value] if value.area > cls.AREA_TOLERANCE else []
        if isinstance(value, (GeometryCollection, MultiPolygon)):
            return [
                polygon
                for child in value.geoms
                if isinstance(child, BaseGeometry)
                for polygon in cls._polygons(child)
            ]
        return []

    def _add(
        self,
        key: str,
        role: str,
        type_id: str,
        region: Polygon,
        direction: Vec2,
        identity: str,
    ) -> None:
        """Fit one member's actual profile to the host and retain its stock reference."""
        semantic_key = identity
        if "originBoundary" in self.source:
            aliases = Authoring.object(self.source.get("memberIds", {}))
            key = Authoring.text(aliases.get(identity, identity))
        if semantic_key in self.identities.values():
            raise ResolutionError(
                f"Ambiguous generated member identity {semantic_key}",
                code="member.ambiguous-identity",
            )
        if key in self.records:
            raise ResolutionError(f"Duplicate generated member key {key}")
        width, depth = self._section(type_id)
        profile = region.simplify(1e-8, preserve_topology=True)
        if not isinstance(profile, Polygon) or profile.interiors:
            raise ResolutionError(f"Framing member {key} is not one solid board")
        u, v = direction
        section_bounds = affine_transform(profile, [u, v, -v, u, 0, 0]).bounds
        if section_bounds[3] - section_bounds[1] > width + 1e-6:
            raise ResolutionError(
                f"Framing member {key} exceeds its nominal stock width"
            )
        material = Authoring.text(self.types[type_id]["material"])
        stock = self.frame.mesh(
            extrude_polygon(profile, -depth / 2, depth / 2, material, f"part:{key}")
        )
        mesh = SolidOperations.intersection(stock, self.mask)
        if mesh is None:
            raise ResolutionError(f"Framing member {key} has no volume inside its host")
        for other in self.meshes.values():
            overlap = SolidOperations.intersection(mesh, other)
            if overlap is not None and SolidOperations.volume(overlap) > 1e-5:
                raise ResolutionError(
                    f"Framing member {key} overlaps another generated member"
                )
        self.meshes[key] = mesh
        self.regions[key] = profile
        self.records[key] = self._record(key, role, type_id, profile, direction, mesh)
        self.records[key]["identityKey"] = semantic_key
        self.identities[key] = semantic_key

    def _record(
        self,
        key: str,
        role: str,
        type_id: str,
        profile: Polygon,
        direction: Vec2,
        mesh: MeshData,
    ) -> JsonObject:
        """Serialize member identity, oriented nominal stock and final physical volume."""
        u, v = direction
        aligned = affine_transform(profile, [u, v, -v, u, 0, 0])
        low, left, high, right = aligned.bounds
        center = (left + right) / 2
        start = self.frame.point((u * low - v * center, v * low + u * center, 0))
        end = self.frame.point((u * high - v * center, v * high + u * center, 0))
        longitudinal = self.frame.vector((u, v, 0))
        transverse = self.frame.vector((-v, u, 0))
        return {
            "key": key,
            "typeId": type_id,
            "role": role,
            "axis": [list(start), list(end)],
            "section": self.types[type_id]["section"],
            "sectionFrame": {
                "x": list(transverse),
                "y": list(self.frame.z),
                "z": list(longitudinal),
            },
            "lengthMm": high - low,
            "stockLengthMm": high - low,
            "planeProfile": [[x, y] for x, y in profile.exterior.coords],
            "netVolumeMm3": SolidOperations.volume(mesh),
        }

    def _rim(self) -> None:
        """Fit perimeter stock in boundary order, with joints cut against earlier boards."""
        type_id = self.definition.get("rimType")
        if not isinstance(type_id, str):
            return
        width, _ = self._section(type_id)
        band = self.profile.difference(self.profile.buffer(-width, join_style="mitre"))
        oriented = orient(self.profile, sign=1.0)
        for ring_index, ring in enumerate((oriented.exterior, *oriented.interiors)):
            points = list(ring.coords)
            for index, (a, b) in enumerate(zip(points, points[1:])):
                edge = PartIdentity.edge((a[0], a[1]), (b[0], b[1]), self.boundaries)
                length = math.dist(a, b)
                direction = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
                extended = LineString(
                    [
                        (a[0] - direction[0] * width, a[1] - direction[1] * width),
                        (b[0] + direction[0] * width, b[1] + direction[1] * width),
                    ]
                )
                candidate = extended.buffer(
                    width, single_sided=True, cap_style="flat"
                ).intersection(band)
                candidate = candidate.difference(
                    unary_union(list(self.regions.values()))
                )
                for part_index, polygon in enumerate(
                    sorted(self._polygons(candidate), key=lambda part: part.bounds)
                ):
                    self._add(
                        f"rim/{ring_index}/{index}/{part_index}",
                        "rim",
                        type_id,
                        polygon,
                        direction,
                        f"rim/{edge}/{PartIdentity.fragment(polygon, direction, tuple(span for span in self.boundaries if span.identity != edge))}",
                    )

    def _grid(self) -> None:
        """Fit regular grid boards to the remaining boundary, splitting at holes and rims."""
        type_id = Authoring.text(self.definition["memberType"])
        width, _ = self._section(type_id)
        spacing = number(self.definition["spacing"], "framing spacing")
        if spacing < width:
            raise ResolutionError("Framing spacing must be at least the member width")
        offset = number(self.source.get("gridOffset", 0), "grid offset")
        low, bottom, high, top = self.profile.bounds
        clear = self.profile.difference(unary_union(list(self.regions.values())))
        first = math.ceil((bottom + width / 2 - offset) / spacing)
        last = math.floor((top - width / 2 - offset) / spacing)
        for index in range(first, last + 1):
            station = offset + index * spacing
            strip = box(low, station - width / 2, high, station + width / 2)
            parts = sorted(
                self._polygons(strip.intersection(clear)), key=lambda part: part.bounds
            )
            for part_index, polygon in enumerate(parts):
                if polygon.bounds[3] - polygon.bounds[1] < width - 1e-6:
                    continue
                self._add(
                    f"grid/{index}/{part_index}",
                    str(
                        self.source.get(
                            "role", "rafter" if self.host.kind == "roof" else "joist"
                        )
                    ),
                    type_id,
                    polygon,
                    (1, 0),
                    f"grid/{index}/{PartIdentity.fragment(polygon, (1, 0), self.boundaries)}",
                )

    def _blocking(self) -> None:
        """Create individual transverse bay boards at authored stable row stations."""
        rows = Authoring.object(self.source.get("blocking", {}))
        type_id = self.definition.get("blockingType", self.definition["memberType"])
        type_id = Authoring.text(type_id)
        width, _ = self._section(type_id)
        _, bottom, _, top = self.profile.bounds
        for key, value in sorted(rows.items()):
            station = number(value, "blocking station")
            strip = box(station - width / 2, bottom, station + width / 2, top)
            clear = self.profile.difference(unary_union(list(self.regions.values())))
            for index, polygon in enumerate(
                sorted(
                    self._polygons(strip.intersection(clear)),
                    key=lambda part: part.bounds,
                )
            ):
                if polygon.bounds[2] - polygon.bounds[0] < width - 1e-6:
                    raise ResolutionError(
                        f"Blocking row {key} intersects a perimeter joint"
                    )
                boundaries = list(self.boundaries)
                for member_key, member in self.regions.items():
                    if member_key.startswith("blocking/"):
                        continue
                    points = list(member.exterior.coords)
                    boundaries.extend(
                        NamedSpan(
                            self.identities[member_key], (a[0], a[1]), (b[0], b[1])
                        )
                        for a, b in zip(points, points[1:])
                    )
                self._add(
                    f"blocking/{key}/{index}",
                    "blocking",
                    type_id,
                    polygon,
                    (0, 1),
                    f"blocking/{key}/{PartIdentity.fragment(polygon, (0, 1), tuple(boundaries))}",
                )

    def _overrides(self) -> None:
        """Apply explicit omissions and same-section material/type substitutions."""
        values = Authoring.object(self.source.get("memberOverrides", {}))
        unknown = set(values) - set(self.records)
        if unknown:
            raise ResolutionError(
                f"Unknown planar framing member overrides: {sorted(unknown)}"
            )
        for key, value in values.items():
            override = Authoring.object(value)
            if override.get("omit") is True:
                del self.meshes[key]
                del self.records[key]
                continue
            if "memberType" in override:
                type_id = Authoring.text(override["memberType"])
                previous = Authoring.text(self.records[key]["typeId"])
                if self._section(type_id) != self._section(previous):
                    raise ResolutionError(
                        "Planar framing type overrides must retain section dimensions"
                    )
                self.meshes[key] = replace(
                    self.meshes[key],
                    material_id=Authoring.text(self.types[type_id]["material"]),
                )
                self.records[key]["typeId"] = type_id
            if "endCuts" in override:
                self.meshes[key] = MemberGeometry.cut_record(
                    self.meshes[key],
                    self.records[key],
                    Authoring.object(override["endCuts"]),
                )

    def resolve(self, element_id: str) -> ResolvedElement:
        """Return a physically disjoint assembly of fitted framing members."""
        self._rim()
        self._grid()
        self._blocking()
        self._overrides()
        if not self.meshes:
            raise ResolutionError("Planar framing contains no surviving members")
        return ResolvedElement(
            element_id,
            "planarFraming",
            Authoring.text(self.source["name"]),
            self.host.storey_id,
            tuple(self.meshes[key] for key in sorted(self.meshes)),
            {
                "typeId": self.source["type"],
                "hostId": self.host.element_id,
                "face": self.source.get("face"),
                "plane": self.frame.to_dict(),
                "assemblyType": (
                    "roofSystem" if self.host.kind == "roof" else "floorSystem"
                ),
                "memberCount": len(self.meshes),
                "memberIdentities": {
                    identity: key for key, identity in self.identities.items()
                },
                "members": [self.records[key] for key in sorted(self.records)],
                "occupies": {
                    "regions": [{"host": self.host.element_id, "layer": self.layer}]
                },
            },
        )
