"""Installed CLI discovery and changeset preparation for reusable assemblies."""

from __future__ import annotations

import argparse
import json

from home_design.assembly_duplication import AssemblyDuplication
from home_design.assembly_instantiation import AssemblyInstantiation
from home_design.assembly_updates import AssemblyUpdates
from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.inspection import InspectionPage, ModelInspection
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.recipe_catalog import RecipeCatalog


class RecipeCommands:
    """Keep assembly interfaces explicit and compact in the installed authoring CLI."""

    @staticmethod
    def add_discovery_options(parser: argparse.ArgumentParser) -> None:
        """Register progressively detailed recipe discovery options."""
        parser.add_argument(
            "recipe", nargs="?", help="Installed recipe ID or explicit recipe JSON path"
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--object", dest="element", help="Inspect one local template object"
        )
        group.add_argument(
            "--objects",
            action="store_true",
            help="List local template object IDs and names",
        )
        group.add_argument(
            "--parameter",
            help="Inspect one named input including its explicit target paths",
        )
        parser.add_argument(
            "--registry",
            choices=(
                "levels",
                "anchors",
                "materials",
                "types",
                "elements",
                "relationships",
            ),
            help="Template registry filter; object lists default to elements",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Object records per page (default: %(default)s)",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="First object record (default: %(default)s)",
        )

    @staticmethod
    def add_prepare_options(parser: argparse.ArgumentParser) -> None:
        """Register named inputs, controlled overrides and explicit stock-sharing choices."""
        parser.add_argument(
            "--recipe",
            help="Installed recipe ID or JSON path for instantiate/adapt/duplicate",
        )
        parser.add_argument("--new-object", help="New assembly ID for duplicate")
        parser.add_argument(
            "--param",
            action="append",
            default=[],
            help="Recipe parameter NAME=JSON value; repeat as needed",
        )
        parser.add_argument(
            "--bind",
            action="append",
            default=[],
            help="External recipe binding NAME=CANONICAL-ID; repeat as needed",
        )
        parser.add_argument(
            "--override",
            action="append",
            default=[],
            help="Allowed recipe-local /path=JSON value; repeat as needed",
        )
        parser.add_argument(
            "--share-type",
            action="append",
            default=[],
            help="Use existing stock LOCAL-TYPE=EXISTING-TYPE; instantiate/adapt only",
        )
        parser.add_argument(
            "--previous-recipe",
            help="Exact previous recipe JSON when adapting to an updated recipe",
        )
        parser.add_argument(
            "--clear-override",
            action="append",
            default=[],
            help="Remove a recorded override path when adapting",
        )
        parser.add_argument(
            "--local-type",
            action="append",
            default=[],
            help="Make a recorded shared recipe type local when adapting",
        )

    @staticmethod
    def assignments(values: list[str], encoded: bool) -> JsonObject:
        """Parse repeatable assignments without silently accepting duplicate input names."""
        result: JsonObject = {}
        for argument in values:
            name, separator, value = argument.partition("=")
            if not name or not separator or not value:
                raise HomeDesignError(
                    "Recipe inputs use NAME=VALUE", code="recipe.assignment"
                )
            if name in result:
                raise HomeDesignError(
                    f"Recipe input {name} is supplied more than once",
                    code="recipe.duplicate-input",
                )
            result[name] = json.loads(value) if encoded else value
        return result

    @staticmethod
    def discover(args: argparse.Namespace) -> int:
        """Print a catalog, recipe interface or specifically requested template details."""
        if args.recipe is None:
            if args.element or args.objects or args.parameter:
                raise HomeDesignError(
                    "Select a recipe before requesting template objects",
                    code="recipe.required",
                )
            result = RecipeCatalog.catalog()
        else:
            recipe = RecipeCatalog.load(args.recipe)
            inspection = ModelInspection(recipe.objects)
            if args.parameter:
                declaration = Authoring.object(recipe.source.get("parameters", {})).get(
                    args.parameter
                )
                if declaration is None:
                    raise HomeDesignError(
                        f"Unknown recipe parameter {args.parameter}",
                        code="recipe.unknown-parameter",
                    )
                result = {
                    "recipeId": recipe.identity,
                    "parameter": args.parameter,
                    "definition": declaration,
                }
            elif args.element:
                registry, value = inspection.locate(args.element, args.registry)
                result = {
                    "recipeId": recipe.identity,
                    "registry": registry,
                    "id": args.element,
                    "source": value,
                }
            elif args.objects:
                result = inspection.summary(
                    InspectionPage(args.limit, args.offset), args.registry or "elements"
                )
            else:
                result = RecipeCatalog.describe(recipe)
        print(json.dumps(result, indent=2))
        return 0

    @classmethod
    def prepare(
        cls, args: argparse.Namespace, model: JsonObject, loader: ModelLoader
    ) -> JsonObject:
        """Produce an ordinary assembly changeset without saving the source or exporting it."""
        if any((args.new_type, args.edits, args.host, args.from_host, args.include)):
            raise HomeDesignError(
                "Assembly preparation uses --recipe, --param, --bind and --override; type/host/include options belong to other actions",
                code="recipe.options",
            )
        parameters = cls.assignments(args.param, True)
        bindings = cls.assignments(args.bind, False)
        overrides = cls.assignments(args.override, True)
        shared = cls.assignments(args.share_type, False)
        selection = args.recipe
        if selection is None and args.action == "adapt":
            _, assembly = ModelInspection(model).locate(args.element, "elements")
            selection = Authoring.text(
                Authoring.object(assembly.get("recipeInstance"), "recipe instance")[
                    "recipeId"
                ]
            )
        recipe = RecipeCatalog.load(selection) if selection else None
        if (
            recipe is not None
            and args.output is not None
            and recipe.source_path == args.output.resolve()
        ):
            raise HomeDesignError(
                "Prepared changeset must be separate from its recipe source",
                code="recipe.output-source",
            )
        if args.action == "duplicate":
            if not args.new_object:
                raise HomeDesignError(
                    "duplicate requires --new-object ID", code="recipe.options"
                )
            if shared or args.previous_recipe or args.clear_override or args.local_type:
                raise HomeDesignError(
                    "Duplicate preserves stock choices and overrides; adapt those explicitly before duplication",
                    code="recipe.options",
                )
            return AssemblyDuplication(model, loader).prepare(
                args.element, args.new_object, recipe, parameters, bindings, overrides
            )
        if recipe is None:
            raise HomeDesignError(
                "Assembly preparation requires --recipe ID-OR-PATH",
                code="recipe.required",
            )
        if args.new_object:
            raise HomeDesignError(
                "--new-object applies only to duplicate", code="recipe.options"
            )
        if args.action == "instantiate":
            if args.previous_recipe or args.clear_override or args.local_type:
                raise HomeDesignError(
                    "Previous recipe and override removal apply only to adapt",
                    code="recipe.options",
                )
            return AssemblyInstantiation(model, recipe, loader).prepare(
                args.element, parameters, bindings, overrides, shared
            )
        previous = (
            RecipeCatalog.load(args.previous_recipe) if args.previous_recipe else None
        )
        if (
            previous is not None
            and args.output is not None
            and previous.source_path == args.output.resolve()
        ):
            raise HomeDesignError(
                "Prepared changeset must be separate from its previous recipe",
                code="recipe.output-source",
            )
        return AssemblyUpdates(model, recipe, loader).prepare(
            args.element,
            parameters,
            bindings,
            overrides,
            shared,
            previous,
            tuple(args.clear_override),
            tuple(args.local_type),
        )
