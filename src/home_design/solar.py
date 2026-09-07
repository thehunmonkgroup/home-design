"""NOAA solar positions and direct-sun geometric shading studies.

Equations: https://gml.noaa.gov/grad/solcalc/solareqns.PDF
These geometric studies do not calculate annual energy use or certification.
"""

from __future__ import annotations

import calendar
import math
from datetime import datetime, timezone

import numpy as np
from numpy.typing import NDArray

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.geometry import number, vector2, vector3
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import ResolvedModel, Vec3


class SolarPosition:
    """Evaluate NOAA's fractional-year position equations at an explicit instant."""

    @staticmethod
    def calculate(
        at: str, latitude: float, longitude: float, true_north: float = 0
    ) -> JsonObject:
        """Return altitude, true azimuth and a canonical direction toward the sun."""
        try:
            instant = datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ResolutionError(f"Invalid solar study timestamp: {at}") from error
        if instant.tzinfo is None:
            raise ResolutionError("Solar study timestamp requires a UTC offset")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ResolutionError("Solar study latitude/longitude is out of range")
        instant = instant.astimezone(timezone.utc)
        hour = instant.hour + instant.minute / 60 + instant.second / 3600
        days = 366 if calendar.isleap(instant.year) else 365
        gamma = (
            2 * math.pi / days * (instant.timetuple().tm_yday - 1 + (hour - 12) / 24)
        )
        equation = 229.18 * (
            0.000075
            + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2 * gamma)
            - 0.040849 * math.sin(2 * gamma)
        )
        declination = (
            0.006918
            - 0.399912 * math.cos(gamma)
            + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma)
            + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma)
            + 0.00148 * math.sin(3 * gamma)
        )
        solar_minutes = (hour * 60 + equation + 4 * longitude) % 1440
        hour_angle = math.radians(solar_minutes / 4 - 180)
        lat = math.radians(latitude)
        sine_altitude = math.sin(lat) * math.sin(declination) + math.cos(
            lat
        ) * math.cos(declination) * math.cos(hour_angle)
        altitude = math.asin(max(-1.0, min(1.0, sine_altitude)))
        azimuth = (
            math.atan2(
                math.sin(hour_angle),
                math.cos(hour_angle) * math.sin(lat)
                - math.tan(declination) * math.cos(lat),
            )
            + math.pi
        ) % (2 * math.pi)
        model_azimuth = azimuth + math.radians(true_north)
        return {
            "at": instant.isoformat(),
            "altitudeDegrees": math.degrees(altitude),
            "azimuthDegrees": math.degrees(azimuth),
            "sunDirection": [
                math.sin(model_azimuth) * math.cos(altitude),
                math.cos(model_azimuth) * math.cos(altitude),
                math.sin(altitude),
            ],
            "method": "NOAA fractional-year approximation; no atmospheric refraction",
        }


class RayOccluder:
    """Intersect deterministic rays with opaque triangles without optional indexes."""

    def __init__(self, triangles: list[tuple[Vec3, Vec3, Vec3]]) -> None:
        """Cache triangle edge vectors for vectorized ray tests."""
        points = np.asarray(triangles, dtype=np.float64).reshape((-1, 3, 3))
        self.origins: NDArray[np.float64] = points[:, 0]
        self.edge1: NDArray[np.float64] = points[:, 1] - points[:, 0]
        self.edge2: NDArray[np.float64] = points[:, 2] - points[:, 0]

    def blocked(self, origin: Vec3, direction: Vec3) -> bool:
        """Test the positive half-ray with a millimetre self-hit tolerance."""
        ray = np.asarray(direction, dtype=np.float64)
        cross = np.cross(ray, self.edge2)
        determinant = np.einsum("ij,ij->i", self.edge1, cross)
        valid = np.abs(determinant) > 1e-9
        inverse = np.divide(
            1.0, determinant, out=np.zeros_like(determinant), where=valid
        )
        delta = np.asarray(origin, dtype=np.float64) - self.origins
        first = inverse * np.einsum("ij,ij->i", delta, cross)
        other = np.cross(delta, self.edge1)
        second = inverse * np.einsum("j,ij->i", ray, other)
        distance = inverse * np.einsum("ij,ij->i", self.edge2, other)
        return bool(
            np.any(
                valid
                & (first >= 0)
                & (second >= 0)
                & (first + second <= 1)
                & (distance > 0.5)
            )
        )


class SolarAnalysis:
    """Sample direct sunlight on opening rectangles including modeled obstructions."""

    def __init__(self, model: ResolvedModel) -> None:
        """Use the same canonical-coordinate geometry as both model adapters."""
        self.model: ResolvedModel = model
        triangles: list[tuple[Vec3, Vec3, Vec3]] = []
        for element in model.elements:
            if element.kind in {
                "space",
                "opening",
                "penetration",
                "clearanceZone",
                "barrierCheck",
                "window",
                "door",
                "load",
                "detail",
            }:
                continue
            for mesh in element.meshes:
                material = model.materials.get(mesh.material_id or "", {})
                appearance = Authoring.object(
                    Authoring.object(material).get("appearance", {})
                )
                if number(appearance.get("opacity", 1), "material opacity") < 0.5:
                    continue
                for face in mesh.faces:
                    for index in range(1, len(face) - 1):
                        triangles.append(
                            (
                                mesh.vertices[face[0]],
                                mesh.vertices[face[index]],
                                mesh.vertices[face[index + 1]],
                            )
                        )
        self.occluder: RayOccluder = RayOccluder(triangles)

    def study(self, specification: JsonObject) -> JsonObject:
        """Resolve a dated study with reproducible sample density and orientation."""
        georeference = Authoring.object(
            self.model.coordinate_system.get("georeference"), "solar study georeference"
        )
        latitude = number(georeference.get("latitude"), "latitude")
        longitude = number(georeference.get("longitude"), "longitude")
        north = number(
            self.model.coordinate_system.get("trueNorthDegrees", 0), "true north"
        )
        position = SolarPosition.calculate(
            Authoring.text(specification.get("at")), latitude, longitude, north
        )
        direction = vector3(position.get("sunDirection"), "sun direction")
        count = int(
            number(specification.get("samplesPerSide", 5), "solar samples per side")
        )
        if not 1 <= count <= 20:
            raise ResolutionError("Solar samples per side must be in 1..20")
        openings: list[JsonValue] = []
        for element in self.model.elements:
            if element.kind not in {"window", "door"}:
                continue
            opening = self.model.element(Authoring.text(element.data.get("openingId")))
            tangent = vector2(opening.data.get("tangent"), "opening tangent")
            outward = (-tangent[1], tangent[0])
            faces_sun = (
                outward[0] * direction[0] + outward[1] * direction[1] > 0
                and direction[2] > 0
            )
            origin = vector3(opening.data.get("origin"), "opening origin")
            width = number(element.data.get("nominalWidth"), "opening width")
            height = number(element.data.get("nominalHeight"), "opening height")
            unshaded = 0
            if faces_sun:
                for row in range(count):
                    for column in range(count):
                        station = width * ((column + 0.5) / count - 0.5)
                        point = (
                            origin[0] + tangent[0] * station,
                            origin[1] + tangent[1] * station,
                            origin[2] + height * (row + 0.5) / count,
                        )
                        unshaded += not self.occluder.blocked(point, direction)
            openings.append(
                {
                    "elementId": element.element_id,
                    "facesSun": faces_sun,
                    "unshadedFraction": unshaded / (count * count),
                    "sampleCount": count * count,
                }
            )
        return {
            **specification,
            **position,
            "latitude": latitude,
            "longitude": longitude,
            "samplesPerSide": count,
            "openings": openings,
            "scope": "Direct-sun opaque-geometry sampling; translucent screens and glazing excluded; no energy/certification prediction",
        }
