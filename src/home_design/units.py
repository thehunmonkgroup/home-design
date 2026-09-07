"""Parse and convert architectural lengths with exact decimal factors."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
from typing import ClassVar

from home_design.json_types import JsonObject


class LengthConversionError(ValueError):
    """Report an invalid or unsupported architectural length expression."""


class LengthConverter:
    """Convert metric and US customary architectural lengths through millimetres."""

    _MILLIMETRES_PER_UNIT: ClassVar[dict[str, Decimal]] = {
        "mm": Decimal("1"),
        "cm": Decimal("10"),
        "m": Decimal("1000"),
        "in": Decimal("25.4"),
        "ft": Decimal("304.8"),
        "yd": Decimal("914.4"),
    }
    _UNIT_ALIASES: ClassVar[dict[str, str]] = {
        "mm": "mm",
        "millimeter": "mm",
        "millimeters": "mm",
        "millimetre": "mm",
        "millimetres": "mm",
        "cm": "cm",
        "centimeter": "cm",
        "centimeters": "cm",
        "centimetre": "cm",
        "centimetres": "cm",
        "m": "m",
        "meter": "m",
        "meters": "m",
        "metre": "m",
        "metres": "m",
        "in": "in",
        "inch": "in",
        "inches": "in",
        '"': "in",
        "″": "in",
        "ft": "ft",
        "foot": "ft",
        "feet": "ft",
        "'": "ft",
        "′": "ft",
        "yd": "yd",
        "yard": "yd",
        "yards": "yd",
    }
    _NUMBER_PATTERN: ClassVar[str] = (
        r"[+-]?(?:\d+\s+\d+/\d+|\d+/\d+|(?:\d+(?:\.\d*)?|\.\d+))"
    )
    _UNIT_PATTERN: ClassVar[str] = "|".join(
        re.escape(alias) for alias in sorted(_UNIT_ALIASES, key=len, reverse=True)
    )
    _TERM_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        rf"(?P<number>{_NUMBER_PATTERN})\s*(?P<unit>{_UNIT_PATTERN})(?![A-Za-z])",
        re.IGNORECASE,
    )
    _SEPARATOR_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[\s,+]*$")

    @classmethod
    def report(
        cls,
        expression: str,
        target: str = "mm",
        precision: int = 6,
        denominator: int = 16,
    ) -> JsonObject:
        """Return canonical millimetres and a requested human-readable unit value."""
        millimetres = cls.parse_millimetres(expression)
        value = (
            cls.format_feet_inches(expression, denominator)
            if target == "ft-in"
            else cls.format_decimal(cls.convert(expression, target), precision)
        )
        return {
            "input": expression,
            "millimetres": cls.format_decimal(millimetres, precision),
            "targetUnit": target,
            "value": value,
        }

    @classmethod
    def parse_millimetres(cls, expression: str) -> Decimal:
        """Parse a compound metric or US customary length.

        :param expression: One or more number-unit terms, such as
            ``8 ft 6 1/2 in`` or ``2.6 m``.
        :return: Exact length in millimetres.
        :raises LengthConversionError: If the expression is incomplete or invalid.
        """
        matches = list(cls._TERM_PATTERN.finditer(expression))
        if not matches:
            raise LengthConversionError(
                "Length must contain a number and unit, such as '8 ft 6 in' or '2500 mm'"
            )
        remainder = cls._TERM_PATTERN.sub("", expression)
        if not cls._SEPARATOR_PATTERN.fullmatch(remainder):
            raise LengthConversionError(f"Unsupported length expression: {expression}")

        total = Decimal("0")
        try:
            for match in matches:
                number = cls._parse_number(match.group("number"))
                unit = cls._canonical_unit(match.group("unit"))
                total += number * cls._MILLIMETRES_PER_UNIT[unit]
        except (InvalidOperation, ZeroDivisionError) as error:
            raise LengthConversionError(
                f"Invalid number in length: {expression}"
            ) from error
        return total

    @classmethod
    def convert(cls, expression: str, target_unit: str) -> Decimal:
        """Convert a length expression to one metric or customary unit.

        :param expression: Source length expression with explicit units.
        :param target_unit: Target unit name or abbreviation.
        :return: Length expressed in the target unit.
        :raises LengthConversionError: If an expression or unit is unsupported.
        """
        target = cls._canonical_unit(target_unit)
        return cls.parse_millimetres(expression) / cls._MILLIMETRES_PER_UNIT[target]

    @classmethod
    def format_feet_inches(cls, expression: str, denominator: int = 16) -> str:
        """Format a length as feet and fractional inches.

        :param expression: Source length expression with explicit units.
        :param denominator: Inch fraction denominator used for rounding.
        :return: Feet-and-inches display text.
        :raises LengthConversionError: If the denominator is outside ``1..64``.
        """
        if denominator < 1 or denominator > 64:
            raise LengthConversionError("Fraction denominator must be between 1 and 64")

        millimetres = cls.parse_millimetres(expression)
        sign = "-" if millimetres < 0 else ""
        total_inches = abs(millimetres) / cls._MILLIMETRES_PER_UNIT["in"]
        increments = int(
            (total_inches * denominator).to_integral_value(rounding=ROUND_HALF_UP)
        )
        increments_per_foot = 12 * denominator
        feet, remaining_increments = divmod(increments, increments_per_foot)
        whole_inches, fraction_numerator = divmod(remaining_increments, denominator)
        inch_text = str(whole_inches)
        if fraction_numerator:
            fraction = Fraction(fraction_numerator, denominator)
            inch_text = f"{inch_text} {fraction.numerator}/{fraction.denominator}"
        return f"{sign}{feet} ft {inch_text} in"

    @staticmethod
    def format_decimal(value: Decimal, decimal_places: int = 6) -> str:
        """Format a decimal without scientific notation or insignificant zeros.

        :param value: Decimal value to format.
        :param decimal_places: Maximum number of fractional decimal places.
        :return: Plain decimal text.
        :raises LengthConversionError: If decimal places are outside ``0..12``.
        """
        if decimal_places < 0 or decimal_places > 12:
            raise LengthConversionError("Decimal places must be between 0 and 12")
        quantum = Decimal("1").scaleb(-decimal_places)
        rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
        text = format(rounded, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in {"-0", ""} else text

    @classmethod
    def _canonical_unit(cls, unit: str) -> str:
        normalized = unit.strip().lower()
        try:
            return cls._UNIT_ALIASES[normalized]
        except KeyError as error:
            raise LengthConversionError(f"Unsupported length unit: {unit}") from error

    @staticmethod
    def _parse_number(value: str) -> Decimal:
        normalized = " ".join(value.split())
        if " " in normalized:
            whole_text, fraction_text = normalized.split(" ", 1)
            whole = Decimal(whole_text)
            fraction = LengthConverter._fraction_decimal(fraction_text)
            return whole - fraction if whole < 0 else whole + fraction
        if "/" in normalized:
            return LengthConverter._fraction_decimal(normalized)
        return Decimal(normalized)

    @staticmethod
    def _fraction_decimal(value: str) -> Decimal:
        numerator_text, denominator_text = value.split("/", 1)
        return Decimal(numerator_text) / Decimal(denominator_text)
