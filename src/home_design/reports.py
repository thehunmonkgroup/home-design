"""Deterministic construction schedules and envelope coordination exports."""

from __future__ import annotations

import json
import math
from pathlib import Path
from shapely.geometry import Polygon

from home_design.construction import Authoring, ConstructionGeometry
from home_design.geometry import number, vector2
from home_design.json_types import JsonObject, JsonValue
from home_design.layers import LayerAssembly
from home_design.member_assemblies import MemberAssemblies
from home_design.resolved import MeshData, ResolvedElement, ResolvedModel


class ModelReports:
    """Derive usable quantities while retaining specifications and stable IDs."""

    def __init__(self, model: ResolvedModel) -> None:
        """Use the resolved model shared with geometry adapters."""
        self.model: ResolvedModel = model

    @staticmethod
    def mesh_volume(mesh: MeshData) -> float:
        """Integrate a closed triangle mesh in cubic millimetres."""
        total = 0.0
        for face in mesh.faces:
            a = mesh.vertices[face[0]]
            for index in range(1, len(face) - 1):
                b, c = mesh.vertices[face[index]], mesh.vertices[face[index + 1]]
                cross = ConstructionGeometry.cross(b, c)
                total += sum(a[axis] * cross[axis] for axis in range(3)) / 6
        return abs(total)

    @staticmethod
    def roof_area(element: ResolvedElement) -> float:
        """Measure exposed top faces once, excluding layer sides and undersides."""
        area = 0.0
        for mesh in element.meshes:
            if not mesh.role.endswith(":layer:0"):
                continue
            for face in mesh.faces:
                a, b, c = (mesh.vertices[index] for index in face[:3])
                cross = ConstructionGeometry.cross(
                    (b[0] - a[0], b[1] - a[1], b[2] - a[2]),
                    (c[0] - a[0], c[1] - a[1], c[2] - a[2]),
                )
                if cross[2] > 0.001:
                    area += math.sqrt(sum(value * value for value in cross)) / 2
        return area

    def schedules(self) -> JsonObject:
        """Return component, opening, framing, material, load and detail schedules."""
        rows: list[JsonValue] = []
        material_volumes: dict[str, float] = {}
        for element in self.model.elements:
            data = element.data
            volume = (
                0.0
                if element.kind
                in {
                    "terrain",
                    "space",
                    "opening",
                    "penetration",
                    "clearanceZone",
                    "barrierCheck",
                }
                else sum(self.mesh_volume(mesh) for mesh in element.meshes)
            )
            if element.kind == "fastenerGroup":
                scheduled_volume = number(
                    data.get("scheduledVolumeMm3", 0), "scheduled fastener volume"
                )
                volume += scheduled_volume
                if scheduled_volume:
                    material_id = Authoring.text(data["materialId"])
                    material_volumes[material_id] = (
                        material_volumes.get(material_id, 0) + scheduled_volume
                    )
            row: JsonObject = {
                "id": element.element_id,
                "name": element.name,
                "kind": element.kind,
                "storeyId": element.storey_id,
                "typeId": data.get("typeId"),
                "role": data.get("role"),
                "volumeM3": volume / 1e9,
                "dimensionsAndSpecifications": data,
            }
            rows.append(row)
            component_type = self.model.types.get(str(data.get("typeId")), {})
            if isinstance(component_type, dict) and "layers" in component_type:
                layers = LayerAssembly.layers(component_type)
                for layer in layers:
                    layer_volume = sum(
                        self.mesh_volume(mesh)
                        for mesh in element.meshes
                        if mesh.role.endswith(f"layer:{layer.index}")
                    )
                    if layer.components:
                        for component in layer.components:
                            material_id = component.material_id
                            material_volumes[material_id] = (
                                material_volumes.get(material_id, 0)
                                + layer_volume * component.fraction
                            )
                    elif layer.material is not None:
                        material_volumes[layer.material] = (
                            material_volumes.get(layer.material, 0) + layer_volume
                        )
            elif element.kind not in {
                "terrain",
                "space",
                "opening",
                "penetration",
                "clearanceZone",
                "barrierCheck",
            }:
                for mesh in element.meshes:
                    if mesh.material_id is not None:
                        material_volumes[mesh.material_id] = material_volumes.get(
                            mesh.material_id, 0
                        ) + self.mesh_volume(mesh)
        materials: list[JsonValue] = [
            {
                "materialId": material_id,
                "volumeM3": volume / 1e9,
                "specification": self.model.materials.get(material_id),
            }
            for material_id, volume in sorted(material_volumes.items())
        ]
        categories: JsonObject = {}
        for name, kinds in {
            "openings": {"door", "window"},
            "penetrations": {"penetration"},
            "framing": {
                "member",
                "framing",
                "wallFraming",
                "planarFraming",
                "memberAssembly",
                "curvedMember",
            },
            "foundations": {"footing"},
            "hardware": {"hardware"},
            "masonry": {"masonryPart"},
            "accessories": {"accessory"},
            "envelopeParts": {"envelopePart"},
            "coordinationVolumes": {"clearanceZone", "barrierCheck"},
            "serviceDevices": {"serviceDevice"},
            "serviceRoutes": {"serviceRoute"},
            "serviceFittings": {"serviceFitting"},
            "serviceInsulation": {"serviceInsulation"},
            "serviceSystems": {"serviceSystem"},
            "serviceCircuits": {"serviceCircuit"},
            "reinforcement": {"reinforcingBar", "reinforcingMesh"},
            "fasteners": {"fastenerGroup"},
            "stairsAndGuards": {"stair", "railing", "panel"},
            "drainage": {"sweep"},
            "loads": {"load"},
            "details": {"detail"},
        }.items():
            categories[name] = [
                row
                for row in rows
                if isinstance(row, dict) and row.get("kind") in kinds
            ]
        return {
            "format": "home-design-schedules-0.1",
            "sourceRevision": self.model.source_revision,
            "units": {"length": "mm", "area": "m2", "volume": "m3", "force": "N"},
            "components": rows,
            "materials": materials,
            "cavities": [
                {"elementId": element.element_id, **Authoring.object(cavity)}
                for element in self.model.elements
                for cavity in Authoring.array(element.data.get("cavities", []))
            ],
            "generatedMembers": [
                {"assemblyId": element.element_id, **member.to_dict()}
                for element in self.model.elements
                if element.kind in MemberAssemblies.KINDS
                for member in MemberAssemblies.records(element)
            ],
            **categories,
            "circuitSchedules": [
                element.data["circuitSchedule"]
                for element in self.model.elements
                if "circuitSchedule" in element.data
            ],
            "requirements": list(self.model.requirements),
            "quantityBasis": "Modeled net geometry plus explicitly scheduled fastener type volumes; no waste factors, fasteners or engineering capacity inferred",
        }

    def envelope(self) -> JsonObject:
        """Export boundary quantities and full shading geometry for external raters."""
        surfaces: list[JsonValue] = []
        for element in self.model.elements:
            if element.kind not in {"wall", "roof", "slab", "door", "window"}:
                continue
            data = element.data
            area = 0.0
            orientation: JsonValue = None
            if element.kind == "wall":
                area = number(data.get("netArea"), "net wall area")
                axis = [
                    vector2(point, "wall axis")
                    for point in Authoring.array(data.get("axis"))
                ]
                orientations: list[JsonValue] = []
                for a, b in zip(axis, axis[1:]):
                    orientations.append(self._azimuth(-(b[1] - a[1]), b[0] - a[0]))
                orientation = orientations
            elif element.kind == "roof":
                area = self.roof_area(element)
            elif element.kind in {"door", "window"}:
                area = number(data.get("nominalWidth"), "opening width") * number(
                    data.get("nominalHeight"), "opening height"
                )
                tx, ty = vector2(data.get("tangent"), "opening tangent")
                orientation = self._azimuth(-ty, tx)
            else:
                footprint = Authoring.object(data.get("footprint"))
                polygon = Polygon(
                    [
                        vector2(point, "slab point")
                        for point in Authoring.array(footprint.get("outer"))
                    ],
                    [
                        [vector2(point, "slab hole") for point in Authoring.array(loop)]
                        for loop in Authoring.array(footprint.get("holes", []))
                    ],
                )
                area = polygon.area
            if isinstance(data.get("netExteriorAreaMm2"), (int, float)):
                area = number(data["netExteriorAreaMm2"], "net exterior area")
            specification = Authoring.object(data.get("specifications", {}))
            surfaces.append(
                {
                    "elementId": element.element_id,
                    "kind": element.kind,
                    "role": data.get("role"),
                    "areaM2": area / 1e6,
                    "azimuthDegrees": orientation,
                    "thermalBoundary": specification.get("thermalBoundary"),
                    "performance": data.get("performance", {}),
                    "layers": data.get("layers", []),
                    "openingId": data.get("openingId"),
                }
            )
        shading: list[JsonValue] = [
            {
                "elementId": element.element_id,
                "kind": element.kind,
                "meshes": [mesh.to_dict() for mesh in element.meshes],
            }
            for element in self.model.elements
            if element.kind
            not in {
                "space",
                "opening",
                "penetration",
                "load",
                "detail",
                "clearanceZone",
                "barrierCheck",
            }
        ]
        return {
            "format": "home-design-envelope-0.1",
            "sourceRevision": self.model.source_revision,
            "coordinateSystem": self.model.coordinate_system,
            "units": {
                "geometry": "mm",
                "area": "m2",
                "uFactor": "W/(m2.K)",
                "rValue": "m2.K/W",
            },
            "surfaces": surfaces,
            "shadingGeometry": shading,
            "solarStudies": list(self.model.solar_studies),
            "boundaryPolicy": "thermalBoundary null means unassigned; review boundary assignments before energy modeling",
        }

    def _azimuth(self, x: float, y: float) -> float:
        north = number(
            self.model.coordinate_system.get("trueNorthDegrees", 0), "true north"
        )
        return (math.degrees(math.atan2(x, y)) - north) % 360

    @staticmethod
    def write(path: Path, report: JsonObject) -> None:
        """Write a deterministic report as UTF-8 JSON."""
        path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
