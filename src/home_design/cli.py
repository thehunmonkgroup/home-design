"""Command-line workflows for validation, inspection, changes, and builds."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from home_design.build import BuildService
from home_design.batch import ModelBatch
from home_design.changes import ChangeEngine
from home_design.errors import HomeDesignError
from home_design.graph import ModelIndex
from home_design.json_types import JsonValue
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator
from home_design.survey import SurveyImporter
from home_design.solar import SolarAnalysis
from home_design.reports import ModelReports
from home_design.website import WebsiteExporter, DEFAULT_WEB_PROJECT

LOGGER = logging.getLogger("home_design")


class HomeDesignCli:
    """Parse and run command-line authoring workflows."""

    def __init__(self) -> None:
        """Initialize the CLI parser."""
        self.parser: argparse.ArgumentParser = self._create_parser()

    def run(self, arguments: Sequence[str] | None = None) -> int:
        """Run a CLI command.

        :param arguments: Optional arguments excluding program name.
        :returns: Process exit code.
        """
        args = self.parser.parse_args(arguments)
        self._configure_logging(args.debug)
        loader = ModelLoader(args.schema)
        validator = ModelValidator(loader)
        try:
            if args.command == "validate":
                return self._validate(args, loader, validator)
            if args.command == "inspect":
                return self._inspect(args, loader, validator)
            if args.command == "apply":
                return self._apply(args, loader, validator)
            if args.command == "build":
                return self._build(args, loader, validator)
            if args.command == "website-export":
                result = WebsiteExporter(BuildService(loader, validator)).export(
                    ModelBatch.expand(args.models), args.output, args.web_project
                )
                print(json.dumps(result, indent=2))
                return 0
            if args.command == "import-survey":
                return self._survey(args, loader, validator)
            if args.command == "solar":
                return self._solar(args, loader, validator)
            self.parser.error("A command is required")
        except (HomeDesignError, OSError, ValueError, KeyError) as error:
            LOGGER.debug("Command failure", exc_info=True)
            print(f"error: {error}", file=sys.stderr)
            return 1

    @staticmethod
    def _create_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="home-design",
            description="Validate, modify, resolve, and export IFC-aligned home models.",
        )
        parser.add_argument(
            "--schema", type=Path, help="Override the model JSON Schema path"
        )
        parser.add_argument(
            "--debug", action="store_true", help="Show debug logging and tracebacks"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)

        validate_parser = subparsers.add_parser(
            "validate", help="Run every model validation layer"
        )
        validate_parser.add_argument(
            "models", nargs="+", help="Canonical model JSON files or glob patterns"
        )
        validate_parser.add_argument(
            "--json", action="store_true", help="Print the structured JSON report"
        )

        inspect_parser = subparsers.add_parser(
            "inspect", help="Summarize IDs and resolved measurements"
        )
        inspect_parser.add_argument(
            "model", type=Path, help="Canonical model JSON file"
        )
        inspect_parser.add_argument(
            "--element", help="Limit output to one stable element ID"
        )
        inspect_parser.add_argument(
            "--relationships",
            action="store_true",
            help="Include relationships involving the element",
        )

        apply_parser = subparsers.add_parser(
            "apply", help="Apply one transactional change set"
        )
        apply_parser.add_argument(
            "model", type=Path, help="Current canonical model JSON file"
        )
        apply_parser.add_argument(
            "change", type=Path, help="Transactional change-set JSON file"
        )
        apply_parser.add_argument(
            "--output",
            type=Path,
            help="Write a new model instead of replacing the source",
        )
        apply_parser.add_argument(
            "--dry-run", action="store_true", help="Validate without writing the result"
        )

        build_parser = subparsers.add_parser(
            "build", help="Generate resolved JSON, IFC, GLB, and manifests"
        )
        build_parser.add_argument(
            "models", nargs="+", help="Canonical model JSON files or glob patterns"
        )
        build_parser.add_argument(
            "--output", type=Path, default=Path("build"), help="Artifact directory"
        )
        build_parser.add_argument(
            "--web-assets",
            type=Path,
            help="Also publish GLB and manifest for the web viewer",
        )
        build_parser.add_argument(
            "--web-assets-mode",
            choices=("merge", "replace"),
            default="merge",
            help="Keep other published models or replace the collection (default: %(default)s)",
        )
        website = subparsers.add_parser(
            "website-export", help="Build selected homes and a portable static website"
        )
        website.add_argument(
            "models", nargs="+", help="Canonical model JSON files or glob patterns"
        )
        website.add_argument(
            "--output", type=Path, default=Path("build/website"),
            help="Dedicated website directory (default: %(default)s)",
        )
        website.add_argument(
            "--web-project", type=Path, default=DEFAULT_WEB_PROJECT,
            help="Viewer checkout with npm dependencies (default: %(default)s)",
        )
        survey = subparsers.add_parser(
            "import-survey", help="Prepare a terrain transaction from x,y,z CSV"
        )
        survey.add_argument("model", type=Path, help="Existing canonical model")
        survey.add_argument("survey", type=Path, help="Survey CSV with x,y,z columns")
        survey.add_argument("--id", required=True, help="Stable terrain element ID")
        survey.add_argument(
            "--state",
            choices=("existing", "proposed"),
            default="existing",
            help="Survey state (default: %(default)s)",
        )
        survey.add_argument(
            "--units",
            choices=("mm", "m", "ft"),
            default="mm",
            help="Units for survey and origin coordinates (default: %(default)s)",
        )
        survey.add_argument(
            "--origin",
            type=float,
            nargs=3,
            default=(0.0, 0.0, 0.0),
            metavar=("X", "Y", "Z"),
            help="Source-coordinate origin subtracted before unit conversion",
        )
        survey.add_argument("--name", help="Terrain display name")
        survey.add_argument(
            "--output",
            type=Path,
            required=True,
            help="Change-set JSON destination; model remains unchanged",
        )
        solar = subparsers.add_parser(
            "solar",
            help="Evaluate direct-sun shading at an explicit geographic date/time",
        )
        solar.add_argument(
            "model", type=Path, help="Canonical model with site latitude/longitude"
        )
        solar.add_argument(
            "--at",
            required=True,
            help="ISO timestamp with UTC offset, e.g. 2026-12-21T12:00:00-05:00",
        )
        solar.add_argument(
            "--samples",
            type=int,
            default=5,
            help="Opening samples per side, 1..20 (default: %(default)s)",
        )
        solar.add_argument(
            "--output",
            type=Path,
            help="Optional JSON report destination; otherwise print",
        )
        return parser

    @staticmethod
    def _survey(
        args: argparse.Namespace, loader: ModelLoader, validator: ModelValidator
    ) -> int:
        model = loader.load(args.model)
        report = validator.validate(model)
        if not report.is_valid:
            raise HomeDesignError(
                "Existing model must validate before preparing a survey transaction"
            )
        origin = (float(args.origin[0]), float(args.origin[1]), float(args.origin[2]))
        change = SurveyImporter.change(
            model, args.survey, args.id, args.state, args.units, origin, args.name
        )
        ChangeEngine(loader, validator).apply(model, change)
        ModelLoader.write(change, args.output)
        print(
            json.dumps(
                {
                    "change": str(args.output),
                    "baseRevision": model["revision"],
                    "modelWritten": False,
                }
            )
        )
        return 0

    @staticmethod
    def _solar(
        args: argparse.Namespace, loader: ModelLoader, validator: ModelValidator
    ) -> int:
        model = loader.load(args.model)
        report = validator.validate(model)
        if not report.is_valid:
            raise HomeDesignError("Model must validate before a solar study")
        resolved = ModelResolver(model).resolve()
        result = SolarAnalysis(resolved).study(
            {
                "id": "study.cli",
                "name": "Requested solar study",
                "at": args.at,
                "samplesPerSide": args.samples,
            }
        )
        if args.output is not None:
            ModelReports.write(args.output, result)
        print(json.dumps(result, indent=2))
        return 0

    @staticmethod
    def _configure_logging(debug: bool) -> None:
        logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )

    @staticmethod
    def _validate(
        args: argparse.Namespace, loader: ModelLoader, validator: ModelValidator
    ) -> int:
        paths = ModelBatch.expand(args.models)
        report = ModelBatch.validate(paths, loader, validator)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(ModelBatch.format_text(report))
        return 0 if report["valid"] is True else 1

    @staticmethod
    def _inspect(
        args: argparse.Namespace, loader: ModelLoader, validator: ModelValidator
    ) -> int:
        model = loader.load(args.model)
        report = validator.validate(model)
        if not report.is_valid:
            raise HomeDesignError("Model must be valid before inspection")
        resolved = ModelResolver(model).resolve()
        index = ModelIndex(model)
        if args.element:
            element = resolved.element(args.element)
            value = element.to_dict()
            if args.relationships:
                relationships: list[JsonValue] = []
                for relationship_id, relationship in index.registries[
                    "relationships"
                ].items():
                    if args.element in _nested_strings(relationship):
                        relationships.append({"id": relationship_id, **relationship})
                value["relationships"] = relationships
            print(json.dumps(value, indent=2))
            return 0
        summary = {
            "project": resolved.project.get("name"),
            "modelVersion": resolved.model_version,
            "revision": resolved.source_revision,
            "elementCounts": {
                kind: sum(element.kind == kind for element in resolved.elements)
                for kind in sorted({element.kind for element in resolved.elements})
            },
            "elements": [
                {"id": element.element_id, "kind": element.kind, "name": element.name}
                for element in resolved.elements
            ],
        }
        print(json.dumps(summary, indent=2))
        return 0

    @staticmethod
    def _apply(
        args: argparse.Namespace, loader: ModelLoader, validator: ModelValidator
    ) -> int:
        engine = ChangeEngine(loader, validator)
        if args.dry_run:
            candidate = engine.apply(
                loader.load(args.model), engine.load_change(args.change)
            )
            print(
                json.dumps(
                    {
                        "valid": True,
                        "nextRevision": candidate["revision"],
                        "written": False,
                    },
                    indent=2,
                )
            )
        else:
            candidate = engine.apply_to_file(args.model, args.change, args.output)
            destination = args.output or args.model
            print(
                json.dumps(
                    {
                        "valid": True,
                        "nextRevision": candidate["revision"],
                        "written": str(destination),
                    },
                    indent=2,
                )
            )
        return 0

    @staticmethod
    def _build(
        args: argparse.Namespace, loader: ModelLoader, validator: ModelValidator
    ) -> int:
        paths = ModelBatch.expand(args.models)
        batch = BuildService(loader, validator).build_many(
            paths, args.output, args.web_assets, args.web_assets_mode
        )
        print(
            json.dumps(
                {
                    "models": [
                        {
                            "key": result.output_directory.name,
                            "output": str(result.output_directory),
                            "artifacts": [
                                str(result.resolved_model),
                                str(result.ifc_model),
                                str(result.glb_model),
                                str(result.render_manifest),
                                str(result.diagnostics),
                                str(result.metadata),
                                str(result.schedules),
                                str(result.envelope),
                                str(result.drawings),
                            ],
                        }
                        for result in batch.models
                    ],
                    "publication": batch.publication,
                },
                indent=2,
            )
        )
        return 0


def _nested_strings(value: object) -> set[str]:
    """Collect all strings inside nested JSON-like values.

    :param value: Arbitrarily nested value.
    :returns: Contained strings.
    """
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return set().union(*(_nested_strings(item) for item in value), set())
    if isinstance(value, dict):
        return set().union(*(_nested_strings(item) for item in value.values()), set())
    return set()


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the home design command-line application.

    :param arguments: Optional arguments excluding program name.
    :returns: Process exit code.
    """
    return HomeDesignCli().run(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
