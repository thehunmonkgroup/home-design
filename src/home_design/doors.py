"""Operation-aware exterior doors and usable opening/swing envelopes."""

from __future__ import annotations

import math

from home_design.errors import ResolutionError
from home_design.geometry import number, oriented_box
from home_design.json_types import JsonObject
from home_design.resolved import MeshData, Vec2, Vec3


class DoorGeometry:
    """Model framed glazed panels and dimensioned operation clearances."""

    @classmethod
    def resolve(
        cls,
        definition: JsonObject,
        element: JsonObject,
        origin: Vec3,
        tangent: Vec2,
        width: float,
        height: float,
        depth: float,
        material: str | None,
    ) -> tuple[tuple[MeshData, ...], JsonObject]:
        """Generate a door using nominal product dimensions and authored operation."""
        frame = number(definition.get("frameWidth", 50), "door frame width")
        if width <= 2 * frame or height <= 2 * frame:
            raise ResolutionError("Door frame leaves no usable opening")
        inner_width, inner_height = width - 2 * frame, height - frame
        tx, ty = tangent
        meshes: list[MeshData] = []
        for side in (-1, 1):
            station = side * (width - frame) / 2
            meshes.append(
                oriented_box(
                    (origin[0] + tx * station, origin[1] + ty * station, origin[2]),
                    tangent,
                    frame,
                    depth,
                    height,
                    material,
                    "door-frame",
                )
            )
        meshes.append(
            oriented_box(
                (origin[0], origin[1], origin[2] + height - frame),
                tangent,
                inner_width,
                depth,
                frame,
                material,
                "door-frame",
            )
        )
        operation = str(definition.get("operation"))
        count = int(
            number(
                definition.get(
                    "panelCount",
                    2 if operation in {"sliding", "doubleDoor", "doubleSwing"} else 1,
                ),
                "door panel count",
            )
        )
        if operation == "sliding" and count < 2:
            raise ResolutionError("Sliding door requires at least two panels")
        glass = number(
            definition.get("glazingFraction", 0.85 if operation == "sliding" else 0),
            "door glazing fraction",
        )
        infill = definition.get("infillMaterial")
        infill_material = infill if isinstance(infill, str) else None
        fraction = number(
            definition.get("infillFraction", glass), "door infill fraction"
        )
        if infill_material is not None:
            glass = 0
        panel_width = inner_width / count
        clearance: list[list[float]] = []
        for index in range(count):
            station = -inner_width / 2 + panel_width * (index + 0.5)
            panel_origin: Vec3 = (
                origin[0] + tx * station,
                origin[1] + ty * station,
                origin[2],
            )
            panel_tangent = tangent
            if operation == "singleSwing":
                panel_origin, panel_tangent, clearance = cls._swing(
                    panel_origin, tangent, panel_width, element
                )
            if operation == "sliding":
                track = (index - (count - 1) / 2) * 30
                panel_origin = (
                    panel_origin[0] - ty * track,
                    panel_origin[1] + tx * track,
                    panel_origin[2],
                )
            meshes.extend(
                cls._panel(
                    panel_origin,
                    panel_tangent,
                    panel_width,
                    inner_height,
                    min(depth, 45),
                    frame / 2,
                    fraction,
                    material,
                    infill_material,
                )
            )
        clear_width = (
            inner_width * (count - 1) / count if operation == "sliding" else inner_width
        )
        clear_width = number(
            definition.get("clearOpeningWidth", clear_width), "clear opening width"
        )
        if clear_width > inner_width:
            raise ResolutionError(
                "Declared clear opening exceeds the door frame opening"
            )
        data: JsonObject = {
            "operation": operation,
            "handing": element.get("handing", "left"),
            "swingDirection": element.get("swingDirection", "outward"),
            "swingAngle": element.get("swingAngle", 0),
            "nominalWidth": width,
            "nominalHeight": height,
            "clearOpeningWidth": clear_width,
            "clearOpeningHeight": inner_height,
            "glazingFraction": glass,
            "glazedArea": inner_width * inner_height * glass,
            "swingEnvelope": [list(point) for point in clearance],
            "clearOpeningBasis": (
                "manufacturer"
                if "clearOpeningWidth" in definition
                else "geometricEstimate"
            ),
        }
        if infill_material is not None:
            data.update({"infillMaterial": infill_material, "infillFraction": fraction})
        return tuple(meshes), data

    @staticmethod
    def _swing(
        origin: Vec3, tangent: Vec2, width: float, element: JsonObject
    ) -> tuple[Vec3, Vec2, list[list[float]]]:
        side = -1 if element.get("handing", "left") == "left" else 1
        exterior = 1 if element.get("swingDirection", "outward") == "outward" else -1
        hinge = (
            origin[0] + tangent[0] * side * width / 2,
            origin[1] + tangent[1] * side * width / 2,
        )
        angle = (
            math.radians(number(element.get("swingAngle", 0), "door swing angle"))
            * -side
            * exterior
        )
        rotated = (
            tangent[0] * math.cos(angle) - tangent[1] * math.sin(angle),
            tangent[0] * math.sin(angle) + tangent[1] * math.cos(angle),
        )
        center: Vec3 = (
            hinge[0] - rotated[0] * side * width / 2,
            hinge[1] - rotated[1] * side * width / 2,
            origin[2],
        )
        envelope = [[hinge[0], hinge[1], origin[2]]]
        for index in range(19):
            sample = math.pi / 2 * index / 18 * -side * exterior
            direction = (
                tangent[0] * math.cos(sample) - tangent[1] * math.sin(sample),
                tangent[0] * math.sin(sample) + tangent[1] * math.cos(sample),
            )
            envelope.append(
                [
                    hinge[0] - direction[0] * side * width,
                    hinge[1] - direction[1] * side * width,
                    origin[2],
                ]
            )
        return center, rotated, envelope

    @staticmethod
    def _panel(
        origin: Vec3,
        tangent: Vec2,
        width: float,
        height: float,
        depth: float,
        frame: float,
        fraction: float,
        material: str | None,
        infill_material: str | None = None,
    ) -> list[MeshData]:
        if fraction == 0:
            return [
                oriented_box(
                    origin, tangent, width, depth, height, material, "door-panel"
                )
            ]
        if width <= 2 * frame:
            raise ResolutionError("Door panel frame leaves no glazing width")
        glass_height = min(height - 2 * frame, height * fraction)
        solid_height = (height - glass_height) / 2
        meshes = []
        for side in (-1, 1):
            shift = side * (width - frame) / 2
            meshes.append(
                oriented_box(
                    (
                        origin[0] + tangent[0] * shift,
                        origin[1] + tangent[1] * shift,
                        origin[2] + solid_height,
                    ),
                    tangent,
                    frame,
                    depth,
                    glass_height,
                    material,
                    "door-panel-frame",
                )
            )
        for z in (0, solid_height + glass_height):
            meshes.append(
                oriented_box(
                    (origin[0], origin[1], origin[2] + z),
                    tangent,
                    width,
                    depth,
                    solid_height,
                    material,
                    "door-panel-frame",
                )
            )
        meshes.append(
            oriented_box(
                (origin[0], origin[1], origin[2] + solid_height),
                tangent,
                width - 2 * frame,
                1 if infill_material is not None else 8,
                glass_height,
                infill_material,
                "door-infill" if infill_material is not None else "door-glass",
            )
        )
        return meshes
