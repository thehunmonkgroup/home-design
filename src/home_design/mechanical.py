"""Authored duct stock and operating limits independent of airflow sizing or balancing."""

from __future__ import annotations

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue


class MechanicalDucts:
    """Compare explicit operating inputs with the corresponding authored stock limits."""

    @staticmethod
    def ratings(specification: JsonObject, conditions: JsonObject) -> list[JsonValue]:
        """Keep signed pressure limits separate and leave airflow performance unchecked."""
        low, high = specification.get("minimumTemperatureC"), specification.get(
            "maximumTemperatureC"
        )
        if (
            low is not None
            and high is not None
            and number(low, "minimum temperature") > number(high, "maximum temperature")
        ):
            raise ResolutionError(
                "Duct minimum temperature exceeds its maximum temperature"
            )
        comparisons = [
            ("temperatureC", "minimumTemperatureC", True, 1),
            ("temperatureC", "maximumTemperatureC", False, 1),
        ]
        if "pressurePa" in conditions:
            negative = number(conditions["pressurePa"], "duct pressure") < 0
            comparisons.insert(
                0,
                (
                    "pressurePa",
                    (
                        "negativePressureRatingPa"
                        if negative
                        else "positivePressureRatingPa"
                    ),
                    negative,
                    -1 if negative else 1,
                ),
            )
        checks: list[JsonValue] = []
        for field, rating, lower, sign in comparisons:
            if field not in conditions:
                continue
            actual = number(conditions[field], field)
            limit = (
                number(specification[rating], rating) * sign
                if rating in specification
                else None
            )
            if limit is not None and (actual < limit if lower else actual > limit):
                raise ResolutionError(
                    f"Duct condition {field} conflicts with authored {rating}"
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
                    "basis": "Authored airflow only; sizing, pressure loss and balancing are not calculated",
                }
            )
        return checks

    @classmethod
    def resolve(cls, definition: JsonObject, source: JsonObject) -> JsonObject:
        """Retain duct-only specifications and conditions on either a route or fitting."""
        if "duct" not in definition and "ductConditions" not in source:
            return {}
        if definition["family"] != "duct":
            raise ResolutionError(
                "Duct specifications and conditions require a duct route or fitting"
            )
        specification = Authoring.object(definition.get("duct", {}))
        conditions = Authoring.object(source.get("ductConditions", {}))
        return {
            **({"duct": specification} if "duct" in definition else {}),
            **({"ductConditions": conditions} if "ductConditions" in source else {}),
            "ductRatingChecks": cls.ratings(specification, conditions),
        }


class MechanicalDevices:
    """Validate explicit equipment interfaces without inferring internal performance."""

    MINIMUM_AIR_PORTS: dict[str, int] = {
        "damper": 2,
        "airTerminal": 1,
        "fan": 2,
        "airHandler": 2,
        "heatRecoveryVentilator": 4,
        "airFilter": 2,
        "coil": 2,
        "airConditioner": 2,
        "dehumidifier": 2,
        "refrigerantUnit": 0,
    }
    SUBTYPES: dict[str, str] = {
        "damperType": "damper",
        "terminalType": "airTerminal",
        "fanType": "fan",
        "coilType": "coil",
        "heatRecoveryType": "heatRecoveryVentilator",
    }

    @classmethod
    def validate(cls, definition: JsonObject) -> None:
        """Require role-specific passages and purposeful powered/control interfaces."""
        role = Authoring.text(definition["role"])
        if role not in cls.MINIMUM_AIR_PORTS:
            return
        specification = Authoring.object(definition["mechanical"])
        for field, owner in cls.SUBTYPES.items():
            if field in specification and role != owner:
                raise ResolutionError(f"Mechanical {field} requires the {owner} role")
        ports = {
            key: Authoring.object(value)
            for key, value in Authoring.object(definition["ports"]).items()
        }
        air = {key for key, port in ports.items() if port["medium"] == "air"}
        if len(air) < cls.MINIMUM_AIR_PORTS[role]:
            raise ResolutionError(
                f"Mechanical device {role} requires at least {cls.MINIMUM_AIR_PORTS[role]} air interfaces"
            )
        allowed = {"air", "electrical", "communications"}
        if role in {
            "airHandler",
            "coil",
            "airConditioner",
            "dehumidifier",
            "refrigerantUnit",
        }:
            allowed.update({"water", "refrigerant", "condensate", "gas"})
        for port in ports.values():
            medium = Authoring.text(port["medium"])
            if medium not in allowed:
                raise ResolutionError(
                    f"Mechanical device {role} has incompatible {medium} interface"
                )
            if medium in {"electrical", "communications"} and "function" not in port:
                raise ResolutionError(
                    "Mechanical power/control interfaces require an explicit function"
                )
            if medium == "electrical" and "electrical" not in definition:
                raise ResolutionError(
                    "Powered mechanical equipment requires electrical ratings"
                )
        if (
            role == "refrigerantUnit"
            and sum(port["medium"] == "refrigerant" for port in ports.values()) < 2
        ):
            raise ResolutionError(
                "A refrigerant unit requires two refrigerant interfaces"
            )
        if role == "heatRecoveryVentilator":
            cls._heat_recovery_passages(definition, air)
        if role == "coil":
            required = {
                "dxCooling": "refrigerant",
                "hydronic": "water",
                "waterCooling": "water",
                "waterHeating": "water",
                "gasHeating": "gas",
                "electricHeating": "electrical",
            }.get(Authoring.text(specification.get("coilType", "other")))
            minimum = 2 if required in {"water", "refrigerant"} else 1
            if (
                required is not None
                and sum(port["medium"] == required for port in ports.values()) < minimum
            ):
                raise ResolutionError(
                    f"The authored coil type requires {minimum} {required} interfaces"
                )

    @staticmethod
    def _heat_recovery_passages(definition: JsonObject, air: set[str]) -> None:
        """Keep two authored air streams separate while allowing independent power/control groups."""
        groups = [
            {Authoring.text(key) for key in Authoring.array(value)} & air
            for value in Authoring.array(definition.get("portGroups", []))
        ]
        groups = [group for group in groups if group]
        if (
            len(groups) != 2
            or any(len(group) < 2 for group in groups)
            or groups[0] & groups[1]
            or groups[0] | groups[1] != air
        ):
            raise ResolutionError(
                "Heat recovery requires two disjoint air passage groups covering every air interface"
            )
