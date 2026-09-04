"""Unit tests for exact architectural length conversion."""

from __future__ import annotations

from decimal import Decimal

import pytest

from home_design.units import LengthConversionError, LengthConverter


@pytest.mark.parametrize(
    ("expression", "millimetres"),
    [
        ("8 ft 6 1/2 in", Decimal("2603.50")),
        ("10' 2\"", Decimal("3098.8")),
        ("2.6 m", Decimal("2600")),
        ("-6 1/2 in", Decimal("-165.10")),
    ],
)
def test_parse_metric_and_us_customary_lengths(
    expression: str,
    millimetres: Decimal,
) -> None:
    assert LengthConverter.parse_millimetres(expression) == millimetres


def test_convert_uses_exact_factors_and_plain_decimal_formatting() -> None:
    inches = LengthConverter.convert("254 mm", "in")
    assert inches == Decimal("10")
    assert LengthConverter.format_decimal(inches) == "10"


def test_format_feet_inches_reduces_fraction_and_carries_rounding() -> None:
    assert LengthConverter.format_feet_inches("2603.5 mm") == "8 ft 6 1/2 in"
    assert LengthConverter.format_feet_inches("3047.9 mm") == "10 ft 0 in"


@pytest.mark.parametrize(
    "expression",
    ["8", "eight feet", "8 ft and approximately 6 in", "1 parsec"],
)
def test_invalid_or_ambiguous_expressions_are_rejected(expression: str) -> None:
    with pytest.raises(LengthConversionError):
        LengthConverter.parse_millimetres(expression)


def test_formatting_limits_guard_against_unintended_precision() -> None:
    with pytest.raises(LengthConversionError, match="Decimal places"):
        LengthConverter.format_decimal(Decimal("1"), 20)
    with pytest.raises(LengthConversionError, match="denominator"):
        LengthConverter.format_feet_inches("1 m", 128)
