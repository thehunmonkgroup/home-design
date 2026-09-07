"""Electrical device specifications and explicit interface-purpose validation."""

from __future__ import annotations

import math

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.geometry import number
from home_design.json_types import JsonObject


class ElectricalDevices:
    """Specialize shared fabricated service devices without inferring product dimensions or ratings."""

    ROLES: frozenset[str] = frozenset(
        {
            "receptacle",
            "switch",
            "deviceBox",
            "junctionBox",
            "distributionPanel",
            "circuitBreaker",
            "fuse",
            "surgeProtector",
            "light",
            "smokeDetector",
            "heatDetector",
            "carbonMonoxideDetector",
            "communicationsOutlet",
            "communicationsPanel",
            "groundingBar",
            "groundingElectrode",
            "bondingClamp",
        }
    )
    GROUNDING_ROLES: frozenset[str] = frozenset(
        {"groundingBar", "groundingElectrode", "bondingClamp"}
    )

    @staticmethod
    def validate_frequency(ratings: JsonObject) -> None:
        """Check authored frequency against its declared supply kind."""
        if "frequencyHz" in ratings:
            frequency = number(ratings["frequencyHz"], "electrical frequency")
            supply = ratings.get("supply")
            if (
                supply not in {"AC", "DC"}
                or (supply == "DC" and frequency != 0)
                or (supply == "AC" and frequency <= 0)
            ):
                raise ResolutionError(
                    "Electrical frequency requires matching AC/DC supply data"
                )

    @classmethod
    def validate(cls, definition: JsonObject) -> None:
        """Require purposeful electrical interfaces and internally consistent authored ratings.

        :raises ResolutionError: For missing port functions, incompatible media or AC/DC data.
        """
        role = Authoring.text(definition["role"])
        if "electrical" in definition:
            cls.validate_frequency(Authoring.object(definition["electrical"]))
        if role not in cls.ROLES:
            return
        ports = [
            Authoring.object(value)
            for value in Authoring.object(definition["ports"]).values()
        ]
        for port in ports:
            if (
                port["medium"] not in {"electrical", "communications"}
                or "function" not in port
            ):
                raise ResolutionError(
                    f"Electrical device {role} requires electrical/communications ports with explicit function"
                )
            if role in cls.GROUNDING_ROLES and port["function"] not in {
                "protectiveEarth",
                "bonding",
            }:
                raise ResolutionError(
                    f"Electrical device {role} requires grounding or bonding ports"
                )
        if role in {"communicationsOutlet", "communicationsPanel"} and not any(
            port["medium"] == "communications" and port["function"] == "signal"
            for port in ports
        ):
            raise ResolutionError(
                f"Electrical device {role} requires a communications signal interface"
            )


class ElectricalStock:
    """Retain cable/conduit specifications without duplicating physical route material."""

    @staticmethod
    def resolve(definition: JsonObject, length: float) -> JsonObject:
        """Check nominal conductor stock against the outside section and schedule authored counts.

        :param length: Analytic route centerline length in millimetres.
        :raises ResolutionError: If authored conductor areas exceed the complete cable section.
        """
        data: JsonObject = {
            key: definition[key] for key in ("cable", "conduit") if key in definition
        }
        if "cable" not in definition:
            return data
        cable = Authoring.object(definition["cable"])
        conductors = [
            Authoring.object(value)
            for value in Authoring.array(cable.get("conductors", []))
        ]
        area = sum(
            number(c["count"], "conductor count")
            * number(c["areaMm2"], "conductor area")
            for c in conductors
        )
        section = Authoring.object(definition["section"])
        outside = (
            math.pi * (number(section["diameter"], "cable diameter") / 2) ** 2
            if section["kind"] == "circle"
            else number(section["width"], "cable width")
            * number(section["height"], "cable height")
        )
        if area > outside:
            raise ResolutionError(
                "Cable conductor areas exceed its complete outside section"
            )
        if (
            cable.get("construction") in {"conductor", "core"}
            and conductors
            and sum(number(c["count"], "conductor count") for c in conductors) != 1
        ):
            raise ResolutionError(
                "Individual conductor/core stock requires one scheduled conductor"
            )
        if (
            cable.get("construction") == "opticalFiber"
            and definition.get("medium") != "communications"
        ):
            raise ResolutionError("Optical fiber stock requires communications medium")
        data["conductorSchedule"] = [
            {
                **conductor,
                "stockLengthMm": number(conductor["count"], "conductor count") * length,
            }
            for conductor in conductors
        ]
        return data
