"""Validate, apply, and rebuild one AI-authored home design transaction."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject
from home_design.transactions import DesignTransaction

LOGGER = logging.getLogger("home_design.skill")


class DesignTransactionWorkflow:
    """Constrain model edits to the project's validated transaction API."""

    def __init__(self) -> None:
        """Initialize the guarded workflow parser."""
        self.parser: argparse.ArgumentParser = self._parser()

    def run(self, arguments: Sequence[str] | None = None) -> int:
        """Apply one transaction or prove it safe without writing.

        :param arguments: Optional arguments excluding program name.
        :returns: Process exit code.
        """
        args = self.parser.parse_args(arguments)
        logging.basicConfig(
            level=logging.DEBUG if args.debug else logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )
        try:
            result = DesignTransaction().apply(
                args.model,
                args.change,
                args.output,
                args.build_directory,
                args.web_assets,
                args.dry_run,
            )
            self._print_result(result)
            return 0
        except (HomeDesignError, OSError, ValueError, KeyError) as error:
            LOGGER.debug("Guarded design transaction failed", exc_info=True)
            detail = (
                error.to_dict()
                if isinstance(error, HomeDesignError)
                else {"message": str(error)}
            )
            print(
                json.dumps({"valid": False, "error": detail}, indent=2), file=sys.stderr
            )
            return 1

    @staticmethod
    def _parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="Apply a revision-checked home design change and rebuild all adapters.",
        )
        parser.add_argument("model", type=Path, help="Canonical home model JSON")
        parser.add_argument("change", type=Path, help="Transactional change-set JSON")
        parser.add_argument(
            "--output", type=Path, help="Write the next revision to a new model file"
        )
        parser.add_argument(
            "--build-directory",
            type=Path,
            default=Path("build"),
            help="Generated artifact root; each model uses its filename stem (default: %(default)s)",
        )
        parser.add_argument(
            "--web-assets",
            type=Path,
            default=Path("web/public/model"),
            help="Viewer collection to merge this model into (default: %(default)s)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate without writing or building",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Show diagnostic logging and tracebacks",
        )
        return parser

    @staticmethod
    def _print_result(result: JsonObject) -> None:
        """Preserve the legacy success shape; the package CLI exposes journal status."""
        keys = ("valid", "revision", "written", "buildDirectory", "ifc", "viewerModel")
        print(json.dumps({key: result[key] for key in keys}, indent=2))


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the guarded design transaction workflow.

    :param arguments: Optional arguments excluding program name.
    :returns: Process exit code.
    """
    return DesignTransactionWorkflow().run(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
