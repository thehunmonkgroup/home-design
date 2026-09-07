"""Typed pipe stock, authored operating conditions and directional gravity coordination."""

from __future__ import annotations

from home_design.construction import Authoring
from home_design.drainage import DrainageFall
from home_design.errors import ResolutionError
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import Vec3


class PlumbingRoutes:
    """Retain pipe specifications and check explicit inputs without inferring hydraulic performance."""

    @staticmethod
    def ratings(specification: JsonObject, conditions: JsonObject) -> list[JsonValue]:
        """Compare known pressure/temperature limits and keep absent ratings explicitly unchecked."""
        checks: list[JsonValue] = []
        low, high = specification.get("minimumTemperatureC"), specification.get(
            "maximumTemperatureC"
        )
        if (
            low is not None
            and high is not None
            and number(low, "minimum temperature") > number(high, "maximum temperature")
        ):
            raise ResolutionError(
                "Pipe minimum temperature exceeds its maximum temperature"
            )
        for field, rating, lower in (
            ("pressurePa", "pressureRatingPa", False),
            ("temperatureC", "minimumTemperatureC", True),
            ("temperatureC", "maximumTemperatureC", False),
        ):
            if field not in conditions:
                continue
            actual, limit = conditions[field], specification.get(rating)
            if limit is not None and (
                number(actual, field) < number(limit, rating)
                if lower
                else number(actual, field) > number(limit, rating)
            ):
                raise ResolutionError(
                    f"Pipe condition {field} conflicts with authored {rating}"
                )
            checks.append(
                {
                    "field": field,
                    "rating": rating,
                    "actual": actual,
                    "limit": limit,
                    "comparison": "atLeast" if lower else "atMost",
                    "status": "satisfied" if limit is not None else "notChecked",
                }
            )
        if "flowRateM3s" in conditions:
            checks.append(
                {
                    "field": "flowRateM3s",
                    "actual": conditions["flowRateM3s"],
                    "status": "notChecked",
                    "basis": "Authored flow only; hydraulic performance is not calculated",
                }
            )
        return checks

    @classmethod
    def resolve(
        cls, definition: JsonObject, source: JsonObject, points: list[Vec3]
    ) -> JsonObject:
        """Resolve pipe-only specifications and gravity checks against actual located path controls."""
        present = (
            "pipe" in definition or "conditions" in source or "fallCheck" in source
        )
        if not present:
            return {}
        if definition["family"] != "pipe":
            raise ResolutionError(
                "Pipe specifications, conditions and fall checks require a pipe route"
            )
        specification = Authoring.object(definition.get("pipe", {}))
        conditions = Authoring.object(source.get("conditions", {}))
        checks = cls.ratings(specification, conditions)
        data: JsonObject = {
            **({"pipe": specification} if "pipe" in definition else {}),
            **({"conditions": conditions} if "conditions" in source else {}),
            "pipeRatingChecks": checks,
        }
        if "fallCheck" in source:
            check = Authoring.object(source["fallCheck"])
            ordered = (
                points if check["direction"] == "startToEnd" else list(reversed(points))
            )
            data["fallCheck"] = {
                **DrainageFall.check(
                    ordered, number(check["minimumFall"], "minimum fall")
                ),
                "direction": check["direction"],
            }
        return data


class PlumbingDevices:
    """Validate authored plumbing interfaces without inferring internal equipment operation."""

    MINIMUM_PORTS: dict[str, int] = {
        "valve": 2,
        "manifold": 3,
        "fixtureConnection": 1,
        "cleanout": 1,
        "waterHeater": 2,
        "plumbingPump": 2,
        "storageTank": 1,
        "waterMeter": 2,
    }
    MEDIA: frozenset[str] = frozenset({"water", "waste", "vent", "gas", "condensate"})

    @classmethod
    def validate(cls, definition: JsonObject) -> None:
        """Require fluid interfaces and explicit powered-device ratings; preserve isolated passages."""
        role = Authoring.text(definition["role"])
        if role not in cls.MINIMUM_PORTS:
            return
        specification = Authoring.object(definition["plumbing"])
        PlumbingRoutes.ratings(specification, {})
        ports = [
            Authoring.object(value)
            for value in Authoring.object(definition["ports"]).values()
        ]
        fluid = [port for port in ports if port["medium"] in cls.MEDIA]
        minimum = cls.MINIMUM_PORTS[role]
        if len(fluid) < minimum:
            raise ResolutionError(
                f"Plumbing device {role} requires at least {minimum} fluid interfaces"
            )
        for port in ports:
            if port["medium"] in cls.MEDIA:
                continue
            if (
                port["medium"] not in {"electrical", "communications"}
                or "function" not in port
            ):
                raise ResolutionError(
                    "Plumbing equipment requires fluid or purposeful electrical/communications interfaces"
                )
            if port["medium"] == "electrical" and "electrical" not in definition:
                raise ResolutionError(
                    "Powered plumbing equipment requires electrical ratings"
                )
        if (
            role in {"waterHeater", "waterMeter"}
            and sum(port["medium"] == "water" for port in fluid) < 2
        ):
            raise ResolutionError(
                f"Plumbing device {role} requires two water interfaces"
            )
        if "valveType" in specification and role != "valve":
            raise ResolutionError("Plumbing valveType requires the valve role")
        if specification.get("valveType") == "mixing" and len(fluid) < 3:
            raise ResolutionError(
                "A mixing valve requires at least three fluid interfaces"
            )
