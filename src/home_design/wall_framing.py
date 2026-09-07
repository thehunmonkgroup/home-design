"""Host-driven wall framing with physical boards and stable semantic part keys."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from shapely.affinity import translate
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import extrude_wall_profile, number, vector2, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import MeshData, ResolvedElement, Vec2, Vec3
from home_design.solids import SolidOperations
from home_design.member_geometry import MemberGeometry


@dataclass(frozen=True)
class FramedOpening:
    """A rectangular rough framing envelope around a hosted opening."""

    key: str
    start: float
    end: float
    bottom: float
    top: float

    @property
    def polygon(self) -> Polygon:
        """Return the rough opening's elevation envelope."""
        return box(self.start, self.bottom, self.end, self.top)


@dataclass(frozen=True)
class FramingBoard:
    """One physical board in the wall's station/height plane."""

    key: str
    role: str
    type_id: str
    profile: Polygon
    vertical: bool
    depth_offset: float = 0.0


class WallFraming:
    """Resolve authored framing recipes without inferring structural capacities."""

    TOLERANCE: float = 1e-6

    def __init__(
        self,
        source: JsonObject,
        host: ResolvedElement,
        types: dict[str, JsonObject],
        openings: list[FramedOpening],
    ) -> None:
        """Prepare a straight wall's elevation profile and explicitly selected layer."""
        self.source: JsonObject = source
        self.host: ResolvedElement = host
        self.types: dict[str, JsonObject] = types
        self.definition: JsonObject = types[Authoring.text(source["type"])]
        self.boards: list[FramingBoard] = []
        path = [
            vector2(value, "wall axis") for value in Authoring.array(host.data["axis"])
        ]
        segment = int(number(source.get("segment", 0), "wall segment"))
        if not 0 <= segment < len(path) - 1:
            raise ResolutionError("Wall framing segment is outside its host path")
        if len(path) > 2 and "segment" not in source:
            raise ResolutionError(
                "Framing a bent wall requires an explicit segment index"
            )
        axis = path[segment : segment + 2]
        self.segment: int = segment
        offset = sum(
            math.dist(a, b) for a, b in zip(path[:segment], path[1 : segment + 1])
        )
        self.origin: Vec2 = axis[0]
        length = math.dist(*axis)
        self.openings: list[FramedOpening] = self._segment_openings(
            openings, offset, length
        )
        self.tangent: Vec2 = (
            (axis[1][0] - axis[0][0]) / length,
            (axis[1][1] - axis[0][1]) / length,
        )
        self.start: float = number(source.get("startInset", 0), "start inset")
        self.end: float = length - number(source.get("endInset", 0), "end inset")
        if self.start >= self.end:
            raise ResolutionError("Wall framing insets consume its entire length")
        self.base: float = number(host.data["baseElevation"], "wall base")
        self.tops: list[Vec2] = self._segment_tops(offset, length)
        self.profile: BaseGeometry = Polygon(
            [(0, 0), (length, 0), *reversed(self.tops)]
        ).intersection(box(self.start, 0, self.end, max(z for _, z in self.tops)))
        self.cutouts: BaseGeometry = unary_union(
            [item.polygon for item in self.openings]
        )
        self.available: BaseGeometry = self.profile.difference(self.cutouts)
        self.center: float
        self.depth: float
        self.center, self.depth = self._layer()

    def _segment_tops(self, offset: float, length: float) -> list[Vec2]:
        """Select roof-profile knots along the authored plan segment."""
        points = [
            vector3(value, "wall top")
            for value in Authoring.array(self.host.data["topProfile"])
        ]
        result: list[Vec2] = []
        station = 0.0
        previous = points[0]
        for point in points:
            station += math.dist((previous[0], previous[1]), (point[0], point[1]))
            if offset - self.TOLERANCE <= station <= offset + length + self.TOLERANCE:
                result.append(
                    (max(0.0, min(length, station - offset)), point[2] - self.base)
                )
            previous = point
        return result

    @classmethod
    def _segment_openings(
        cls, openings: list[FramedOpening], offset: float, length: float
    ) -> list[FramedOpening]:
        """Require each rough opening package to belong to one planar framing run."""
        result: list[FramedOpening] = []
        for opening in sorted(openings, key=lambda item: item.key):
            if opening.end <= offset or opening.start >= offset + length:
                continue
            if (
                opening.start < offset - cls.TOLERANCE
                or opening.end > offset + length + cls.TOLERANCE
            ):
                raise ResolutionError("A framed opening cannot cross a wall path bend")
            result.append(
                replace(opening, start=opening.start - offset, end=opening.end - offset)
            )
        return result

    def _layer(self) -> tuple[float, float]:
        """Require explicit cavity ownership and compute its normal center offset."""
        layers = [
            Authoring.object(value)
            for value in Authoring.array(self.host.data["layers"])
        ]
        index = int(number(self.source["layer"], "framing layer"))
        if (
            not 0 <= index < len(layers)
            or layers[index].get("representation") != "explicit"
        ):
            raise ResolutionError("Wall framing requires an explicit host layer")
        depths = [number(layer["thickness"], "layer thickness") for layer in layers]
        thickness = sum(depths)
        center = {"exterior": -thickness / 2, "interior": thickness / 2}.get(
            str(self.host.data.get("locationLine")), 0.0
        )
        return (
            center + thickness / 2 - sum(depths[:index]) - depths[index] / 2,
            depths[index],
        )

    def _dimensions(self, type_id: str, vertical: bool) -> tuple[float, float]:
        """Read rectangular board size in elevation and across the wall."""
        section = Authoring.object(self.types[type_id]["section"])
        if section.get("kind") != "rectangle":
            raise ResolutionError(
                "Wall framing member types require rectangular sections"
            )
        width = number(section["width"], "member width")
        depth = number(section["depth"], "member depth")
        face, across = (width, depth) if vertical else (depth, width)
        if across > self.depth + self.TOLERANCE:
            raise ResolutionError(f"Framing type {type_id} exceeds its cavity depth")
        return face, across

    def _type(self, field: str, default: str | None = None) -> str:
        """Resolve an explicit recipe member type or its documented fallback."""
        return Authoring.text(self.definition.get(field, default), field)

    @classmethod
    def _polygons(cls, region: BaseGeometry) -> list[Polygon]:
        """Discard zero-area contact edges and numerical slivers after planar operations."""
        if isinstance(region, Polygon):
            return [region] if region.area > cls.TOLERANCE else []
        if isinstance(region, (MultiPolygon, GeometryCollection)):
            return [
                polygon
                for part in region.geoms
                if isinstance(part, BaseGeometry)
                for polygon in cls._polygons(part)
            ]
        return []

    def _add(
        self,
        key: str,
        role: str,
        type_id: str,
        region: BaseGeometry,
        vertical: bool,
        depth_offset: float = 0.0,
    ) -> None:
        """Add one contiguous member and reject unintended cuts or overlaps."""
        if region.is_empty or region.area <= self.TOLERANCE:
            return
        polygons = self._polygons(region)
        if len(polygons) != 1 or polygons[0].interiors:
            raise ResolutionError(f"Framing member {key} is not one solid board")
        region = polygons[0].simplify(1e-8, preserve_topology=True)
        if not isinstance(region, Polygon):
            raise ResolutionError(f"Framing member {key} has no polygonal body")
        if region.difference(self.available).area > self.TOLERANCE:
            raise ResolutionError(
                f"Framing member {key} does not fit its host or opening"
            )
        if any(
            region.intersection(board.profile).area > self.TOLERANCE
            for board in self.boards
        ):
            raise ResolutionError(f"Framing member {key} overlaps another board")
        _, across = self._dimensions(type_id, vertical)
        if abs(depth_offset) + across / 2 > self.depth / 2 + self.TOLERANCE:
            raise ResolutionError(f"Framing member {key} projects outside its cavity")
        self.boards.append(
            FramingBoard(key, role, type_id, region, vertical, depth_offset)
        )

    def _plate_regions(self) -> None:
        """Build bottom courses and slope-following top courses with plumb end joints."""
        type_id = self._type("plateType")
        depth, _ = self._dimensions(type_id, False)
        bottom_count = int(
            number(self.definition.get("bottomPlates", 1), "bottom plates")
        )
        top_count = int(number(self.definition.get("topPlates", 2), "top plates"))
        extension = depth * top_count + 1
        first, second = self.tops[:2]
        before_last, last = self.tops[-2:]
        first_slope = (second[1] - first[1]) / (second[0] - first[0])
        last_slope = (last[1] - before_last[1]) / (last[0] - before_last[0])
        top_line = LineString(
            [
                (first[0] - extension, first[1] - extension * first_slope),
                *self.tops,
                (last[0] + extension, last[1] + extension * last_slope),
            ]
        )
        for course in range(bottom_count):
            region = box(self.start, course * depth, self.end, (course + 1) * depth)
            for part in self._polygons(region.intersection(self.available)):
                key = self._bay_key(part.bounds[0], part.bounds[2])
                self._add(f"bottom/{course}/{key}", "bottomPlate", type_id, part, False)
        previous: BaseGeometry = Polygon()
        for course in range(top_count):
            band = top_line.buffer(
                -(course + 1) * depth, single_sided=True, join_style="mitre"
            )
            region = band.difference(previous).intersection(self.profile)
            if region.intersection(self.cutouts).area > self.TOLERANCE:
                raise ResolutionError(
                    "Opening leaves insufficient space for top plates"
                )
            for index, (a, b) in enumerate(zip(self.tops, self.tops[1:])):
                part = region.intersection(box(a[0], 0, b[0], self.profile.bounds[3]))
                self._add(f"top/{course}/{index}", "topPlate", type_id, part, False)
            previous = band

    def _bay_key(self, start: float, end: float) -> str:
        """Identify a horizontal interval by adjacent openings, independent of dimensions."""
        before = [item for item in self.openings if item.end <= start + self.TOLERANCE]
        after = [item for item in self.openings if item.start >= end - self.TOLERANCE]
        left = max(before, key=lambda item: item.end).key if before else "start"
        right = min(after, key=lambda item: item.start).key if after else "end"
        return f"{left}/{right}"

    def _inside_plates(self) -> BaseGeometry:
        """Return the clear framing region after horizontal plate courses."""
        plates = [
            board.profile for board in self.boards if board.role.endswith("Plate")
        ]
        return self.available.difference(unary_union(plates))

    def _opening_package(self, opening: FramedOpening, clear: BaseGeometry) -> None:
        """Add full kings, bearing jacks, a header and a window rough sill."""
        overrides = Authoring.object(self.source.get("openingOverrides", {}))
        settings = {
            **self.definition,
            **Authoring.object(overrides.get(opening.key, {})),
        }
        stud_type = self._type("studType")
        width, _ = self._dimensions(stud_type, True)
        king_count = int(number(settings.get("kingStuds", 1), "king count"))
        jack_count = int(number(settings.get("jackStuds", 1), "jack count"))
        plate_depth, _ = self._dimensions(self._type("plateType"), False)
        floor = plate_depth * number(
            self.definition.get("bottomPlates", 1), "bottom courses"
        )
        header_type = Authoring.text(settings["headerType"])
        header_depth, _ = self._dimensions(header_type, False)
        for side, edge, direction in (
            ("left", opening.start, -1),
            ("right", opening.end, 1),
        ):
            for index in range(jack_count + king_count):
                x = edge + direction * width * (index + 0.5)
                is_jack = index < jack_count
                role = "jackStud" if is_jack else "kingStud"
                ordinal = index if is_jack else index - jack_count
                top = opening.top if is_jack else self.profile.bounds[3]
                rectangle = box(x - width / 2, floor, x + width / 2, top)
                region = rectangle if is_jack else rectangle.intersection(clear)
                self._add(
                    f"opening/{opening.key}/{side}/{role}/{ordinal}",
                    role,
                    stud_type,
                    region,
                    True,
                )
        self._add(
            f"opening/{opening.key}/header",
            "header",
            header_type,
            box(
                opening.start - jack_count * width,
                opening.top,
                opening.end + jack_count * width,
                opening.top + header_depth,
            ),
            False,
        )
        if opening.bottom > self.TOLERANCE:
            sill_type = Authoring.text(
                settings.get("sillType", self._type("plateType"))
            )
            sill_depth, _ = self._dimensions(sill_type, False)
            self._add(
                f"opening/{opening.key}/sill",
                "sill",
                sill_type,
                box(
                    opening.start,
                    opening.bottom - sill_depth,
                    opening.end,
                    opening.bottom,
                ),
                False,
            )

    def _ends(self, clear: BaseGeometry) -> None:
        """Build authored end/corner stud packs inside coordinated wall insets."""
        type_id = self._type("studType")
        width, _ = self._dimensions(type_id, True)
        count = int(number(self.definition.get("endStuds", 1), "end studs"))
        for side, edge, direction in (("start", self.start, 1), ("end", self.end, -1)):
            for index in range(count):
                x = edge + direction * width * (index + 0.5)
                region = box(
                    x - width / 2, 0, x + width / 2, self.profile.bounds[3]
                ).intersection(clear)
                self._add(
                    f"end/{side}/{index}",
                    "cornerStud" if count > 1 else "endStud",
                    type_id,
                    region,
                    True,
                )

    def _field(self, clear: BaseGeometry) -> None:
        """Fit field and cripple studs to the remaining framing bays on a fixed grid."""
        type_id = self._type("studType")
        width, _ = self._dimensions(type_id, True)
        spacing = number(self.definition["spacing"], "stud spacing")
        origin = number(self.source.get("gridOffset", spacing), "grid offset")
        obstacles = unary_union([board.profile for board in self.boards])
        remaining = clear.difference(obstacles)
        index = 0
        while origin + index * spacing < self.end - width / 2:
            x = origin + index * spacing
            if x >= self.start + width / 2:
                strip = box(x - width / 2, 0, x + width / 2, self.profile.bounds[3])
                for polygon in self._polygons(strip.intersection(remaining)):
                    if polygon.bounds[2] - polygon.bounds[0] < width - self.TOLERANCE:
                        continue
                    key, role = self._vertical_key(x, polygon)
                    self._add(f"grid/{index}/{key}", role, type_id, polygon, True)
            index += 1

    def _vertical_key(self, station: float, polygon: Polygon) -> tuple[str, str]:
        """Distinguish upper/lower cripple parts by opening identity."""
        for opening in self.openings:
            if opening.start <= station <= opening.end:
                position = "below" if polygon.centroid.y < opening.bottom else "above"
                return f"{opening.key}/{position}", "crippleStud"
        return "full", "stud"

    def _blocking(self) -> None:
        """Fit individually identified blocking boards between existing vertical boards."""
        rows = Authoring.object(self.source.get("blocking", {}))
        for key, value in sorted(rows.items()):
            settings: JsonObject = (
                value if isinstance(value, dict) else {"height": value}
            )
            type_id = Authoring.text(
                settings.get(
                    "memberType", self._type("blockingType", self._type("plateType"))
                )
            )
            depth, _ = self._dimensions(type_id, False)
            height = number(settings["height"], "blocking height")
            band = box(self.start, height - depth / 2, self.end, height + depth / 2)
            occupied = unary_union([board.profile for board in self.boards])
            region = band.intersection(self.available).difference(occupied)
            for polygon in self._polygons(region):
                if (
                    abs(polygon.area - (polygon.bounds[2] - polygon.bounds[0]) * depth)
                    > self.TOLERANCE
                ):
                    raise ResolutionError(
                        f"Blocking row {key} intersects a sloped or partial-height board"
                    )
                left = self._adjacent_key(polygon.bounds[0], height, True)
                right = self._adjacent_key(polygon.bounds[2], height, False)
                self._add(
                    f"blocking/{key}/{left}/{right}",
                    str(settings.get("role", "blocking")),
                    type_id,
                    polygon,
                    False,
                    number(settings.get("depthOffset", 0), "backing depth offset"),
                )

    def _adjacent_key(self, station: float, height: float, left: bool) -> str:
        """Use neighboring board identities to stabilize blocking keys."""
        for board in self.boards:
            low, bottom, high, top = board.profile.bounds
            if (
                bottom <= height <= top
                and abs((high if left else low) - station) < self.TOLERANCE
            ):
                return board.key
        return "boundary"

    def _overrides(self) -> None:
        """Apply explicit member omissions, offsets and same-section substitutions."""
        values = Authoring.object(self.source.get("memberOverrides", {}))
        unknown = set(values) - {board.key for board in self.boards}
        if unknown:
            raise ResolutionError(
                f"Unknown wall framing member overrides: {sorted(unknown)}"
            )
        original = self.boards
        self.boards = []
        for board in original:
            override = Authoring.object(values.get(board.key, {}))
            if override.get("omit") is True:
                continue
            type_id = Authoring.text(override.get("memberType", board.type_id))
            if self._dimensions(type_id, board.vertical) != self._dimensions(
                board.type_id, board.vertical
            ):
                raise ResolutionError(
                    "Member type overrides must retain section dimensions"
                )
            x, z = vector2(override.get("offset", [0, 0]), "member offset")
            self._add(
                board.key,
                board.role,
                type_id,
                translate(board.profile, xoff=x, yoff=z),
                board.vertical,
                board.depth_offset,
            )

    def resolve(self, element_id: str) -> ResolvedElement:
        """Generate all boards, physical geometry and inspectable construction records."""
        overrides = Authoring.object(self.source.get("openingOverrides", {}))
        if set(overrides) - {opening.key for opening in self.openings}:
            raise ResolutionError(
                "Opening override does not belong to the framing host"
            )
        self._plate_regions()
        clear = self._inside_plates()
        for opening in self.openings:
            self._opening_package(opening, clear)
        self._ends(clear)
        self._field(clear)
        self._blocking()
        self._overrides()
        meshes: list[MeshData] = []
        members: list[JsonValue] = []
        for board in sorted(self.boards, key=lambda item: item.key):
            _, across = self._dimensions(board.type_id, board.vertical)
            mesh = extrude_wall_profile(
                board.profile,
                self.origin,
                self.tangent,
                self.center + board.depth_offset,
                across,
                self.base,
                Authoring.text(self.types[board.type_id]["material"]),
            )
            mesh = replace(mesh, role=f"part:{board.key}")
            record = self._record(board, mesh)
            override = Authoring.object(
                Authoring.object(self.source.get("memberOverrides", {})).get(
                    board.key, {}
                )
            )
            if "endCuts" in override:
                mesh = MemberGeometry.cut_record(
                    mesh, record, Authoring.object(override["endCuts"])
                )
            meshes.append(mesh)
            members.append(record)
        return ResolvedElement(
            element_id,
            "wallFraming",
            Authoring.text(self.source["name"]),
            self.host.storey_id,
            tuple(meshes),
            {
                "typeId": self.source["type"],
                "hostId": self.host.element_id,
                "segment": self.segment,
                "assemblyType": "wallSystem",
                "memberCount": len(meshes),
                "members": members,
                "occupies": {
                    "regions": [
                        {"host": self.host.element_id, "layer": self.source["layer"]}
                    ]
                },
            },
        )

    def _record(self, board: FramingBoard, mesh: MeshData) -> JsonObject:
        """Retain actual cut geometry and nominal board dimensions for downstream use."""
        low, bottom, high, top = board.profile.bounds
        if board.vertical:
            station = (low + high) / 2
            cut = board.profile.intersection(
                LineString([(station, bottom - 1), (station, top + 1)])
            )
            local_start, local_end = (station, cut.bounds[1]), (station, cut.bounds[3])
        else:
            local_start, local_end = [
                (station, (cut.bounds[1] + cut.bounds[3]) / 2)
                for station in (low, high)
                for cut in [
                    board.profile.intersection(
                        LineString([(station, bottom - 1), (station, top + 1)])
                    )
                ]
            ]
        start, end = self._world(local_start, board.depth_offset), self._world(
            local_end, board.depth_offset
        )
        direction = ConstructionGeometry.unit(
            (end[0] - start[0], end[1] - start[1], end[2] - start[2])
        )
        across: Vec3 = (
            (self.tangent[0], self.tangent[1], 0)
            if board.vertical
            else (-self.tangent[1], self.tangent[0], 0)
        )
        up = ConstructionGeometry.cross(direction, across)
        along = (
            (local_end[0] - local_start[0]) / math.dist(local_start, local_end),
            (local_end[1] - local_start[1]) / math.dist(local_start, local_end),
        )
        projections = [
            x * along[0] + z * along[1] for x, z in board.profile.exterior.coords
        ]
        return {
            "key": board.key,
            "typeId": board.type_id,
            "role": board.role,
            "section": self.types[board.type_id]["section"],
            "vertical": board.vertical,
            "depthOffset": board.depth_offset,
            "lengthMm": math.dist(start, end),
            "stockLengthMm": max(projections) - min(projections),
            "axis": [list(start), list(end)],
            "sectionFrame": {"x": list(across), "y": list(up), "z": list(direction)},
            "elevationProfile": [[x, z] for x, z in board.profile.exterior.coords],
            "netVolumeMm3": SolidOperations.volume(mesh),
        }

    def _world(self, point: Vec2, depth_offset: float = 0.0) -> Vec3:
        """Transform a station/height point to the cavity center plane."""
        return (
            self.origin[0]
            + self.tangent[0] * point[0]
            - self.tangent[1] * (self.center + depth_offset),
            self.origin[1]
            + self.tangent[1] * point[0]
            + self.tangent[0] * (self.center + depth_offset),
            self.base + point[1],
        )
