"""Circular-section paths with tangent bends and bounded geometric approximation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Point, Polygon

from home_design.construction import ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import extrude_polygon
from home_design.json_types import JsonObject
from home_design.frames import LocalFrame, tuple3
from home_design.resolved import MeshData, Vec3
from home_design.solids import SolidOperations


@dataclass(frozen=True)
class PathBend:
    """A tangent circular bend replacing one authored path corner."""

    start: Vec3
    end: Vec3
    center: Vec3
    normal: Vec3
    incoming: Vec3
    angle: float
    setback: float


class RoundPath:
    """Loft shared circular sections through straight spans and tangent arcs."""

    MAX_SECTIONS: int = 10000
    MAX_VERTICES: int = 2000000

    def __init__(
        self,
        points: list[Vec3],
        diameter: float,
        radius: float,
        tolerance: float,
        closed: bool = False,
    ) -> None:
        """Prepare authored centerline intent independently of its rendering resolution."""
        self.points: list[Vec3] = points
        self.diameter: float = diameter
        self.radius: float = radius
        self.tolerance: float = tolerance
        self.closed: bool = closed
        self.samples: list[tuple[Vec3, Vec3]] = []
        self.length: float = 0
        self.max_deviation: float = 0

    @staticmethod
    def _difference(a: Vec3, b: Vec3) -> Vec3:
        """Subtract vectors while retaining their fixed-dimensional type."""
        return tuple3([a[index] - b[index] for index in range(3)])

    @staticmethod
    def _shift(point: Vec3, vector: Vec3, distance: float) -> Vec3:
        """Translate along a direction by a signed distance."""
        return tuple3([point[index] + vector[index] * distance for index in range(3)])

    def _bend(self, index: int, directions: list[Vec3]) -> PathBend:
        """Construct tangent points and a center from an authored corner."""
        point = self.points[index]
        incoming, outgoing = directions[index - 1], directions[index % len(directions)]
        angle = math.acos(
            max(-1, min(1, sum(a * b for a, b in zip(incoming, outgoing))))
        )
        if angle >= math.pi - 1e-8:
            raise ResolutionError("Rounded path reverses at a corner")
        if angle < 1e-8:
            return PathBend(point, point, point, (0, 0, 1), incoming, 0, 0)
        if self.radius <= self.diameter / 2:
            raise ResolutionError("Bend radius must exceed the circular section radius")
        normal = ConstructionGeometry.unit(
            ConstructionGeometry.cross(incoming, outgoing)
        )
        setback = self.radius * math.tan(angle / 2)
        start = self._shift(point, incoming, -setback)
        end = self._shift(point, outgoing, setback)
        center = self._shift(
            start, ConstructionGeometry.cross(normal, incoming), self.radius
        )
        return PathBend(start, end, center, normal, incoming, angle, setback)

    def _append(self, point: Vec3, tangent: Vec3) -> None:
        """Share identical tangent stations without producing a zero-length loft."""
        if self.samples and math.dist(self.samples[-1][0], point) < 1e-7:
            return
        self.samples.append((point, tangent))
        if len(self.samples) > self.MAX_SECTIONS:
            raise ResolutionError("Rounded path requires more than 10000 sections")

    def _arc(self, bend: PathBend, step: float) -> None:
        """Sample a true circular bend while retaining its analytic end tangents."""
        self._append(bend.start, bend.incoming)
        if not bend.angle:
            return
        count = math.ceil(bend.angle / step)
        radial = self._difference(bend.start, bend.center)
        self.max_deviation = max(
            self.max_deviation,
            (self.radius + self.diameter / 2) * (1 - math.cos(bend.angle / count / 2)),
        )
        for index in range(1, count + 1):
            angle = bend.angle * index / count
            point = self._shift(
                bend.center, LocalFrame.rotate_vector(radial, bend.normal, angle), 1
            )
            self._append(
                bend.end if index == count else point,
                LocalFrame.rotate_vector(bend.incoming, bend.normal, angle),
            )

    def _sample(self, step: float) -> None:
        """Reject conflicting setbacks and build one continuous sequence of tangent sections."""
        if self.closed and len(self.points) < 3:
            raise ResolutionError(
                "Closed rounded paths require at least three distinct vertices"
            )
        edges = list(
            zip(self.points, self.points[1:] + (self.points[:1] if self.closed else []))
        )
        directions = [
            ConstructionGeometry.unit(self._difference(b, a)) for a, b in edges
        ]
        indices = (
            range(len(self.points)) if self.closed else range(1, len(self.points) - 1)
        )
        bends = {index: self._bend(index, directions) for index in indices}
        if self.closed:
            normal = next(
                (bend.normal for bend in bends.values() if bend.angle), (0, 0, 1)
            )
            if any(
                abs(
                    sum(
                        a * b
                        for a, b in zip(self._difference(point, self.points[0]), normal)
                    )
                )
                > 1e-6
                for point in self.points
            ):
                raise ResolutionError("Closed rounded paths must be planar")
        for index, (start, end) in enumerate(edges):
            before = bends.get(index)
            after = bends.get((index + 1) % len(self.points))
            consumed = (before.setback if before else 0) + (
                after.setback if after else 0
            )
            if consumed > math.dist(start, end) + 1e-7:
                raise ResolutionError(
                    "Adjacent bend setbacks consume a rounded path span"
                )
        self.length = sum(math.dist(a, b) for a, b in edges) + sum(
            self.radius * bend.angle - 2 * bend.setback for bend in bends.values()
        )
        if self.closed:
            self._append(bends[0].end, directions[0])
            for index in [*range(1, len(self.points)), 0]:
                self._arc(bends[index], step)
            self.samples[-1] = self.samples[0]
        else:
            self._append(self.points[0], directions[0])
            for bend in bends.values():
                self._arc(bend, step)
            self._append(self.points[-1], directions[-1])

    def resolve(self, material: str) -> tuple[MeshData, JsonObject]:
        """Create a closed tube solid and reject unintended self-intersection.

        :returns: Net mesh and analytic length/tessellation inspection records.
        :raises ResolutionError: For invalid bends, oversized meshes or intersecting spans.
        """
        section_radius = self.diameter / 2
        half_angle = math.acos(max(-1, 1 - self.tolerance / 2 / section_radius))
        if half_angle <= 0:
            raise ResolutionError("Rounded path tolerance is below numeric resolution")
        quadrants = max(2, math.ceil(math.pi / 4 / half_angle))
        if quadrants * 4 > self.MAX_SECTIONS:
            raise ResolutionError("Round section requires more than 10000 sides")
        section_error = section_radius * (1 - math.cos(math.pi / (4 * quadrants)))
        step = min(
            math.pi / 2,
            2
            * math.acos(
                max(
                    -1,
                    1
                    - (self.tolerance - section_error) / (self.radius + section_radius),
                )
            ),
        )
        if step <= 0:
            raise ResolutionError("Bend tolerance is below numeric resolution")
        profile = Point(0, 0).buffer(section_radius, quad_segs=quadrants)
        frames = self.frames(step)
        mesh = self.loft(profile, frames, material, "body")
        return mesh, {
            "centerlineLengthMm": self.length,
            "sectionAreaMm2": profile.area,
            "nominalSectionAreaMm2": math.pi * section_radius**2,
            "maxDeviationMm": self.max_deviation + section_error,
            "sectionCount": len(self.samples),
            "sectionSides": quadrants * 4,
            "path": [list(point) for point, _ in self.samples],
            "netVolumeMm3": SolidOperations.volume(mesh),
        }

    def frames(self, step: float, up: Vec3 | None = None) -> list[LocalFrame]:
        """Sample tangent bends and parallel-transport one oriented cross-section frame.

        :param step: Maximum angular step in radians, with the section error budget reserved.
        :param up: Initial section Y direction projected perpendicular to the first tangent.
        :raises ResolutionError: For degenerate directions, bends or excessive sampling.
        """
        if len(self.points) < 2 or not 0 < step <= math.pi / 2:
            raise ResolutionError(
                "Rounded path needs two points and a positive bounded angular step"
            )
        self.samples = []
        self.max_deviation = 0
        self._sample(step)
        tangent = self.samples[0][1]
        reference: Vec3 = up or ((0, 1, 0) if abs(tangent[2]) > 0.999 else (0, 0, 1))
        across = ConstructionGeometry.unit(
            ConstructionGeometry.cross(reference, tangent)
        )
        frames: list[LocalFrame] = []
        for point, following in self.samples:
            cross = ConstructionGeometry.cross(tangent, following)
            if math.sqrt(sum(value**2 for value in cross)) > 1e-10:
                axis = ConstructionGeometry.unit(cross)
                angle = math.acos(
                    max(-1, min(1, sum(a * b for a, b in zip(tangent, following))))
                )
                across = LocalFrame.rotate_vector(across, axis, angle)
            tangent = following
            frames.append(
                LocalFrame(
                    point, across, ConstructionGeometry.cross(tangent, across), tangent
                )
            )
        if self.closed:
            frames[-1] = frames[0]
        return frames

    @classmethod
    def _bend_frame(cls, frame: LocalFrame, bend: PathBend, angle: float) -> LocalFrame:
        """Rotate an entry frame through an analytic portion of one circular bend."""
        radial = cls._difference(bend.start, bend.center)
        origin = cls._shift(
            bend.center, LocalFrame.rotate_vector(radial, bend.normal, angle), 1
        )
        return LocalFrame(
            origin,
            *(
                LocalFrame.rotate_vector(axis, bend.normal, angle)
                for axis in (frame.x, frame.y, frame.z)
            ),
        )

    def station_frame(self, station: float, up: Vec3 | None = None) -> LocalFrame:
        """Locate an exact arc-length station with the same parallel transport as the loft.

        :param station: Distance from the start of an open path, in millimetres.
        :param up: Initial section Y reference, as used by :meth:`frames`.
        :raises ResolutionError: For closed paths or stations outside the analytic length.
        """
        if self.closed:
            raise ResolutionError("Station frames require an open rounded path")
        frames = self.frames(math.pi / 2, up)
        if not math.isfinite(station) or not 0 <= station <= self.length:
            raise ResolutionError(
                "Route station lies outside its analytic centerline length"
            )
        directions = [
            ConstructionGeometry.unit(self._difference(b, a))
            for a, b in zip(self.points, self.points[1:])
        ]
        bends = {
            index: self._bend(index, directions)
            for index in range(1, len(self.points) - 1)
        }
        frame = frames[0]
        remaining = station
        for index, direction in enumerate(directions):
            before, after = bends.get(index), bends.get(index + 1)
            start = before.end if before else self.points[index]
            end = after.start if after else self.points[index + 1]
            length = math.dist(start, end)
            if remaining <= length:
                return LocalFrame(
                    self._shift(start, direction, remaining),
                    frame.x,
                    frame.y,
                    direction,
                )
            remaining -= length
            if after is not None and after.angle:
                arc = self.radius * after.angle
                if remaining <= arc:
                    return self._bend_frame(frame, after, remaining / self.radius)
                remaining -= arc
                frame = self._bend_frame(frame, after, after.angle)
        return frames[-1]

    @classmethod
    def continuous_loft(
        cls, profile: Polygon, frames: list[LocalFrame], material: str | None, role: str
    ) -> MeshData:
        """Join matching section vertices directly after validating the enclosing path.

        Hollow stock shares one continuous skin without Boolean unions of
        coincident annular caps. The caller validates its filled envelope first.
        """
        template = extrude_polygon(profile, 0, 1, material, role)
        if len(frames) * len(template.vertices) > cls.MAX_VERTICES:
            raise ResolutionError(
                "Rounded path requires more than 2000000 loft vertices"
            )
        coordinates = sorted({(x, y) for x, y, _ in template.vertices})
        lookup = {point: index for index, point in enumerate(coordinates)}
        closed = frames[0] == frames[-1]
        stations = len(frames) - int(closed)
        count = len(coordinates)
        vertices = tuple(
            frame.point((x, y, 0))
            for frame in frames[:stations]
            for x, y in coordinates
        )
        faces: list[tuple[int, ...]] = []
        for span in range(len(frames) - 1):
            for face in template.faces:
                ends = {int(template.vertices[index][2]) for index in face}
                if ends == {0} and (closed or span != 0):
                    continue
                if ends == {1} and (closed or span != len(frames) - 2):
                    continue
                faces.append(
                    tuple(
                        ((span + int(template.vertices[index][2])) % stations) * count
                        + lookup[template.vertices[index][:2]]
                        for index in face
                    )
                )
        result = SolidOperations.mesh(
            SolidOperations.solid(MeshData(vertices, tuple(faces), material, role)),
            material,
            role,
        )
        if result is None:
            raise ResolutionError("Continuous loft has no physical material")
        return result

    @classmethod
    def loft(
        cls, profile: Polygon, frames: list[LocalFrame], material: str | None, role: str
    ) -> MeshData:
        """Loft shared section caps, rejecting positive-volume overlap between spans."""
        template = extrude_polygon(profile, 0, 1, material, role)
        if len(frames) * len(template.vertices) > cls.MAX_VERTICES:
            raise ResolutionError(
                "Rounded path requires more than 2000000 loft vertices"
            )
        pieces = [
            MeshData(
                tuple(
                    frames[index + int(z)].point((x, y, 0))
                    for x, y, z in template.vertices
                ),
                template.faces,
                material,
                role,
            )
            for index in range(len(frames) - 1)
        ]
        mesh = SolidOperations.union(pieces, material, role)
        if mesh is None:
            raise ResolutionError("Rounded path has no physical geometry")
        summed = sum(SolidOperations.volume(piece) for piece in pieces)
        volume = SolidOperations.volume(mesh)
        if summed - volume > max(1e-5, summed * 1e-9):
            raise ResolutionError("Rounded path intersects itself")
        return mesh
