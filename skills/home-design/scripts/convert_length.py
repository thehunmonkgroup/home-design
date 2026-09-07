"""Convert user-supplied architectural lengths through canonical millimetres."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence

from home_design.units import LengthConversionError, LengthConverter

LOGGER = logging.getLogger("home_design.skill.units")
TARGET_UNITS = ("mm", "cm", "m", "in", "ft", "yd", "ft-in")


class LengthConversionCli:
    """Parse length conversion arguments and emit structured output."""

    def __init__(self) -> None:
        """Initialize the command-line parser."""
        self.parser: argparse.ArgumentParser = self._create_parser()

    def run(self, arguments: Sequence[str] | None = None) -> int:
        """Convert one length expression.

        :param arguments: Optional arguments excluding the program name.
        :return: Process exit code.
        """
        args = self.parser.parse_args(arguments)
        logging.basicConfig(
            level=logging.DEBUG if args.debug else logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )
        try:
            result = LengthConverter.report(
                args.measurement, args.target, args.precision, args.fraction_denominator
            )
            LOGGER.debug("Converted length: %s", result)
            print(json.dumps(result, indent=2))
            return 0
        except LengthConversionError as error:
            LOGGER.debug("Length conversion failed", exc_info=True)
            print(f"error: {error}", file=sys.stderr)
            return 1

    @staticmethod
    def _create_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="Convert metric or US customary architectural lengths.",
        )
        parser.add_argument(
            "measurement",
            help="Explicit-unit length, such as '8 ft 6 1/2 in' or '2600 mm'",
        )
        parser.add_argument(
            "--to",
            dest="target",
            choices=TARGET_UNITS,
            default="mm",
            help="Output unit (default: %(default)s)",
        )
        parser.add_argument(
            "--precision",
            type=int,
            default=6,
            help="Maximum decimal places (default: %(default)s)",
        )
        parser.add_argument(
            "--fraction-denominator",
            type=int,
            default=16,
            help="Feet/inches rounding denominator (default: %(default)s)",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Show diagnostic logging and tracebacks",
        )
        return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the length conversion command.

    :param arguments: Optional arguments excluding the program name.
    :return: Process exit code.
    """
    return LengthConversionCli().run(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
