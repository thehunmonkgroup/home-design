"""Command-line workflows for validation, inspection, changes, and builds."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from home_design.build import BuildService
from home_design.batch import ModelBatch
from home_design.changes import ChangeEngine
from home_design.change_preview import ChangePreview
from home_design.command_output import CommandOutput
from home_design.change_preparation import ChangePreparation
from home_design.json_types import JsonValue
from home_design.errors import HomeDesignError
from home_design.inspection import InspectionPage, ModelInspection
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.validation import ModelValidator
from home_design.survey import SurveyImporter
from home_design.solar import SolarAnalysis
from home_design.reports import ModelReports
from home_design.website import WebsiteExporter, DEFAULT_WEB_PROJECT
from home_design.transactions import DesignTransaction
from home_design.units import LengthConverter
from home_design.constants import resource_root
from home_design.capabilities import ComponentRegistry
from home_design.migrations import ModelMigration
from home_design.recipe_commands import RecipeCommands

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
        try:
            if args.command == "resources":
                root = resource_root()
                print(
                    json.dumps(
                        {
                            "root": str(root),
                            "schema": str(root / "schema"),
                            "skill": str(root / "skills/home-design/SKILL.md"),
                            "examples": str(root / "examples"),
                            "recipes": str(root / "recipes"),
                            "documentation": str(root / "docs"),
                        },
                        indent=2,
                    )
                )
                return 0
            if args.command == "convert-length":
                print(
                    json.dumps(
                        LengthConverter.report(
                            args.measurement,
                            args.target,
                            args.precision,
                            args.fraction_denominator,
                        ),
                        indent=2,
                    )
                )
                return 0
            loader = ModelLoader(args.schema)
            validator = ModelValidator(loader)
            commands: dict[
                str, Callable[[argparse.Namespace, ModelLoader, ModelValidator], int]
            ] = {
                "validate": self._validate,
                "inspect": self._inspect,
                "apply": self._apply,
                "preview": self._preview,
                "build": self._build,
                "import-survey": self._survey,
                "solar": self._solar,
            }
            if args.command in commands:
                return commands[args.command](args, loader, validator)
            if args.command == "recipes":
                return RecipeCommands.discover(args)
            if args.command == "migrate":
                return self._migrate(args, loader)
            if args.command == "capabilities":
                issues = ComponentRegistry.audit(loader.schema)
                items = (
                    [ComponentRegistry.get(args.kind)]
                    if args.kind
                    else list(ComponentRegistry.components.values())
                )
                print(
                    json.dumps(
                        {
                            "valid": not issues,
                            "issues": issues,
                            "fieldSemantics": {
                                "hostModes": "Coordinate frames this family provides to hosted components, not its own mounting destinations.",
                                "hostTargets": "Allowed kinds for a direct host field; empty does not prohibit placement.host mounting.",
                            },
                            "components": [item.to_dict() for item in items],
                        },
                        indent=2,
                    )
                )
                return 1 if issues else 0
            if args.command == "prepare":
                return self._prepare(args, loader)
            if args.command == "transact":
                result = DesignTransaction(BuildService(loader, validator)).apply(
                    args.model,
                    args.change,
                    args.output,
                    args.build_directory,
                    args.web_assets,
                    args.dry_run,
                )
                print(json.dumps(result, indent=2))
                return 0
            if args.command == "recover":
                result = DesignTransaction(BuildService(loader, validator)).recover(
                    args.journal
                )
                print(json.dumps(result, indent=2))
                return 0
            if args.command == "website-export":
                result = WebsiteExporter(BuildService(loader, validator)).export(
                    ModelBatch.expand(args.models), args.output, args.web_project
                )
                print(json.dumps(result, indent=2))
                return 0
            self.parser.error("A command is required")
        except (HomeDesignError, OSError, ValueError, KeyError) as error:
            LOGGER.debug("Command failure", exc_info=True)
            detail = (
                error.to_dict()
                if isinstance(error, HomeDesignError)
                else {"code": "workflow.failed", "message": str(error)}
            )
            print(
                json.dumps({"valid": False, "error": detail}, indent=2), file=sys.stderr
            )
            return 1

    @staticmethod
    def _migrate(args: argparse.Namespace, loader: ModelLoader) -> int:
        """Prepare a reviewable version changeset in a separate destination."""
        if args.output is not None and args.output.resolve() == args.model.resolve():
            raise HomeDesignError(
                "Migration output is a changeset and must be separate from its source model"
            )
        change = ModelMigration(loader).prepare(loader.load(args.model), args.target)
        CommandOutput.change(change, args.output)
        return 0

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
        subparsers.add_parser(
            "resources",
            help="Locate installed schemas, progressive skill, examples and documentation",
        )
        capabilities = subparsers.add_parser(
            "capabilities",
            help="Inspect registered component capabilities and schema coverage",
        )
        capabilities.add_argument("--kind", help="Return one component family")
        RecipeCommands.add_discovery_options(
            subparsers.add_parser(
                "recipes",
                help="Discover installed assembly recipes and inspect their named interfaces",
            )
        )
        migration = subparsers.add_parser(
            "migrate",
            help="Prepare a version migration changeset; source remains unchanged",
        )
        migration.add_argument("model", type=Path, help="Canonical model to migrate")
        migration.add_argument(
            "--to",
            dest="target",
            default="0.2",
            help="Target model version (default: %(default)s)",
        )
        migration.add_argument(
            "--output",
            type=Path,
            help="Write a separate changeset for preview and transact",
        )

        conversion = subparsers.add_parser(
            "convert-length",
            help="Convert an architectural length through canonical millimetres",
        )
        conversion.add_argument(
            "measurement", help="Explicit-unit length, e.g. '8 ft 6 1/2 in'"
        )
        conversion.add_argument(
            "--to",
            dest="target",
            choices=("mm", "cm", "m", "in", "ft", "yd", "ft-in"),
            default="mm",
        )
        conversion.add_argument("--precision", type=int, default=6)
        conversion.add_argument("--fraction-denominator", type=int, default=16)

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
            "inspect",
            help="Inspect source objects, dependencies and optional resolved measurements",
        )
        inspect_parser.add_argument(
            "model", type=Path, help="Canonical model JSON file"
        )
        inspect_parser.add_argument(
            "--element",
            "--object",
            dest="element",
            help="Inspect one stable object ID in any registry",
        )
        inspect_parser.add_argument(
            "--relationships",
            action="store_true",
            help="Include relationships involving the element",
        )
        inspect_parser.add_argument(
            "--registry",
            choices=(
                "elements",
                "types",
                "anchors",
                "materials",
                "levels",
                "relationships",
            ),
            help="Select a registry; summaries default to elements",
        )
        inspect_parser.add_argument("--kind", help="Filter an object summary by kind")
        inspect_parser.add_argument(
            "--query", default="", help="Filter summary names or IDs"
        )
        inspect_parser.add_argument(
            "--view",
            choices=("source", "resolved", "assembly"),
            default="source",
            help="Select authored fields or resolved measurements (default: %(default)s)",
        )
        inspect_parser.add_argument(
            "--field",
            action="append",
            default=[],
            help="Select a source-relative JSON Pointer; repeat for multiple fields",
        )
        inspect_parser.add_argument(
            "--references",
            action="store_true",
            help="List incoming and outgoing typed references",
        )
        inspect_parser.add_argument(
            "--type-users",
            action="store_true",
            help="List direct and indirect users of the object's reusable type",
        )
        inspect_parser.add_argument(
            "--dependents", action="store_true", help="Traverse incoming references"
        )
        inspect_parser.add_argument(
            "--dependencies", action="store_true", help="Traverse outgoing references"
        )
        inspect_parser.add_argument(
            "--role",
            choices=(
                "placement",
                "type",
                "material",
                "containment",
                "ownership",
                "connection",
                "relationship",
                "requirement",
                "reference",
            ),
            help="Filter reference traversal by semantic role",
        )
        inspect_parser.add_argument(
            "--depth",
            type=int,
            default=2,
            help="Maximum traversal depth, 1–64 (default: %(default)s)",
        )
        inspect_parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Records per result page, 1–1000 (default: %(default)s)",
        )
        inspect_parser.add_argument(
            "--offset", type=int, default=0, help="Page start (default: %(default)s)"
        )
        inspect_parser.add_argument(
            "--parts", action="store_true", help="Resolve and inspect generated members"
        )
        inspect_parser.add_argument(
            "--part", help="Resolve one generated member by scoped key"
        )
        inspect_parser.add_argument(
            "--meshes",
            action="store_true",
            help="Include resolved vertices, faces and construction masks",
        )

        preview_parser = subparsers.add_parser(
            "preview",
            help="Review a changeset's authored and resolved effects without saving",
        )
        preview_parser.add_argument("model", type=Path, help="Current canonical model")
        preview_parser.add_argument("change", type=Path, help="Proposed changeset")
        preview_parser.add_argument(
            "--output", type=Path, help="Write the preview report to a separate file"
        )
        preview_parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Records per section, 1–1000 (default: %(default)s)",
        )
        preview_parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="Start each result page here (default: %(default)s)",
        )

        prepare_parser = subparsers.add_parser(
            "prepare",
            help="Create a guarded changeset for a coordinated authoring operation",
        )
        prepare_parser.add_argument("model", type=Path, help="Current canonical model")
        prepare_parser.add_argument(
            "action",
            choices=(
                "local-type",
                "rehost",
                "remove",
                "instantiate",
                "adapt",
                "duplicate",
            ),
        )
        prepare_parser.add_argument(
            "--object", required=True, dest="element", help="Target stable object ID"
        )
        prepare_parser.add_argument(
            "--new-type", help="New type ID for an occurrence-only change"
        )
        prepare_parser.add_argument(
            "--set",
            action="append",
            default=[],
            dest="edits",
            help="Type-relative JSON Pointer=JSON value; repeat for multiple fields",
        )
        prepare_parser.add_argument("--host", help="New host element ID")
        prepare_parser.add_argument(
            "--from-host", help="Select which existing host reference to rebind"
        )
        prepare_parser.add_argument(
            "--include",
            action="append",
            default=[],
            help="Additional explicitly selected object ID; repeat as needed",
        )
        prepare_parser.add_argument(
            "--output",
            type=Path,
            help="Write the changeset to a separate file; source remains unchanged",
        )
        RecipeCommands.add_prepare_options(prepare_parser)

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

        transaction = subparsers.add_parser(
            "transact",
            help="Prepare adapters, save a guarded revision and publish recoverably",
        )
        transaction.add_argument("model", type=Path, help="Current canonical model")
        transaction.add_argument("change", type=Path, help="Proposed changeset")
        transaction.add_argument(
            "--output", type=Path, help="Save to a separate model file"
        )
        transaction.add_argument("--build-directory", type=Path, default=Path("build"))
        transaction.add_argument(
            "--web-assets", type=Path, help="Optional viewer collection"
        )
        transaction.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate without writing or exporting",
        )
        recovery = subparsers.add_parser(
            "recover", help="Publish the saved revision from a transaction journal"
        )
        recovery.add_argument(
            "journal", type=Path, help="Transaction journal returned by transact"
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
            "--output",
            type=Path,
            default=Path("build/website"),
            help="Dedicated website directory (default: %(default)s)",
        )
        website.add_argument(
            "--web-project",
            type=Path,
            default=DEFAULT_WEB_PROJECT,
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
        inspection = ModelInspection(model)
        page = InspectionPage(args.limit, args.offset)
        if not args.element:
            if any(
                (
                    args.references,
                    args.type_users,
                    args.relationships,
                    args.dependents,
                    args.dependencies,
                    args.parts,
                    args.part,
                    args.field,
                    args.meshes,
                    args.view != "source",
                )
            ):
                raise HomeDesignError(
                    "Select --object ID for fields, relationships, dependencies or geometry"
                )
            print(
                json.dumps(
                    inspection.summary(
                        page, args.registry or "elements", args.kind, args.query
                    ),
                    indent=2,
                )
            )
            return 0
        value = inspection.source(args.element, args.registry, tuple(args.field))
        if args.view == "assembly":
            value.pop("authored", None)
            value["assembly"] = inspection.assembly(args.element, page)
        if args.type_users:
            value["typeUsers"] = inspection.type_users(args.element, page)
        if args.references:
            value["incoming"] = inspection.references(
                args.element, page, "incoming", args.role
            )
            value["outgoing"] = inspection.references(
                args.element, page, "outgoing", args.role
            )
        if args.dependents:
            value["dependents"] = inspection.closure(
                args.element, page, "incoming", args.depth, args.role
            )
        if args.dependencies:
            value["dependencies"] = inspection.closure(
                args.element, page, "outgoing", args.depth, args.role
            )
        if args.relationships:
            relationships = inspection.relationships(args.element, page)
            value["relationships"] = relationships["items"]
            value["relationshipPage"] = {
                key: item for key, item in relationships.items() if key != "items"
            }
        if args.view == "resolved" or args.meshes or args.parts or args.part:
            if value["registry"] != "elements":
                raise HomeDesignError(
                    "Resolved inspection requires an element; use --view source for other registries"
                )
            evaluation = validator.evaluate(model)
            if not evaluation.report.is_valid or evaluation.resolved is None:
                raise HomeDesignError(
                    "Model must be valid for resolved inspection; use --view source and validate --json to repair it"
                )
            resolved = evaluation.resolved
            if args.parts or args.part:
                value["parts"] = inspection.parts(
                    resolved, args.element, page, args.part, args.meshes
                )
            else:
                value.update(
                    inspection.resolved(resolved.element(args.element), args.meshes)
                )
        print(json.dumps(value, indent=2))
        return 0

    @staticmethod
    def _prepare(args: argparse.Namespace, loader: ModelLoader) -> int:
        if args.output is not None and args.output.resolve() == args.model.resolve():
            raise HomeDesignError(
                "Prepared changeset must be separate from its source model"
            )
        preparation = ChangePreparation(loader.load(args.model), loader)
        if args.action in {"instantiate", "adapt", "duplicate"}:
            change = RecipeCommands.prepare(args, preparation.source, loader)
            CommandOutput.change(change, args.output)
            return 0
        if any(
            (
                args.recipe,
                args.new_object,
                args.param,
                args.bind,
                args.override,
                args.share_type,
                args.previous_recipe,
                args.clear_override,
                args.local_type,
            )
        ):
            raise HomeDesignError(
                "Recipe options apply only to instantiate, adapt and duplicate"
            )
        if args.action == "local-type" and any(
            (args.host, args.from_host, args.include)
        ):
            raise HomeDesignError(
                "local-type uses --new-type and --set; host/include options belong to other actions"
            )
        if args.action != "local-type" and any((args.new_type, args.edits)):
            raise HomeDesignError("--new-type and --set apply only to local-type")
        if args.action == "remove" and any((args.host, args.from_host)):
            raise HomeDesignError("Host options apply only to rehost")
        if args.action == "local-type":
            if not args.new_type:
                raise HomeDesignError("local-type requires --new-type ID")
            fields: list[tuple[str, JsonValue]] = []
            for value in args.edits:
                pointer, separator, encoded = value.partition("=")
                if not separator:
                    raise HomeDesignError("Each --set uses /field=JSON-value")
                fields.append((pointer, json.loads(encoded)))
            change = preparation.local_type(args.element, args.new_type, tuple(fields))
        elif args.action == "rehost":
            if not args.host:
                raise HomeDesignError("rehost requires --host ID")
            change = preparation.rehost(
                args.element, args.host, args.from_host, tuple(args.include)
            )
        else:
            change = preparation.remove(args.element, tuple(args.include))
        ChangeEngine(loader).validate_change(change)
        CommandOutput.change(change, args.output)
        return 0

    @staticmethod
    def _preview(
        args: argparse.Namespace, loader: ModelLoader, validator: ModelValidator
    ) -> int:
        engine = ChangeEngine(loader, validator)
        if args.output is not None and args.output.resolve() in {
            args.model.resolve(),
            args.change.resolve(),
        }:
            raise HomeDesignError(
                "Preview output must be separate from its model and changeset"
            )
        result = ChangePreview(engine).evaluate(
            loader.load(args.model),
            engine.load_change(args.change),
            InspectionPage(args.limit, args.offset),
        )
        CommandOutput.preview(result.report, args.output)
        return 0 if result.evaluation.report.is_valid else 1

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


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the home design command-line application.

    :param arguments: Optional arguments excluding program name.
    :returns: Process exit code.
    """
    return HomeDesignCli().run(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
