"""Compact discovery of installed and workspace assembly recipes."""

from __future__ import annotations

from pathlib import Path

from home_design.constants import resource_root
from home_design.construction import Authoring
from home_design.errors import HomeDesignError
from home_design.json_types import JsonObject
from home_design.recipes import AssemblyRecipe


class RecipeCatalog:
    """Expose recipe interfaces separately from potentially large component templates."""

    @staticmethod
    def installed() -> tuple[tuple[Path, AssemblyRecipe], ...]:
        """Read the public recipe documents bundled with the authoring package."""
        return tuple(
            (path, AssemblyRecipe.load(path))
            for path in sorted((resource_root() / "recipes").glob("*.json"))
        )

    @classmethod
    def load(cls, selection: str) -> AssemblyRecipe:
        """Accept an explicit path, installed recipe ID or installed filename stem."""
        path = Path(selection).expanduser()
        if path.is_file():
            return AssemblyRecipe.load(path)
        matches = [
            recipe
            for path, recipe in cls.installed()
            if selection in {path.stem, path.name, recipe.identity}
        ]
        if len(matches) != 1:
            raise HomeDesignError(
                f"Recipe {selection} is unavailable or ambiguous; use home-design recipes to list installed recipes or provide its JSON path",
                code="recipe.unavailable",
            )
        return matches[0]

    @staticmethod
    def describe(recipe: AssemblyRecipe) -> JsonObject:
        """Return only interface choices and object counts until detailed templates are requested."""
        return {
            "id": recipe.identity,
            "name": recipe.source["name"],
            "description": recipe.source.get("description", ""),
            "recipeVersion": recipe.source["recipeVersion"],
            "modelVersion": recipe.source["modelVersion"],
            "digest": recipe.digest,
            "assembly": recipe.assembly,
            "parameters": {
                name: {
                    **{
                        key: value
                        for key, value in Authoring.object(raw).items()
                        if key != "targets"
                    },
                    "targetCount": len(
                        Authoring.array(Authoring.object(raw)["targets"])
                    ),
                }
                for name, raw in Authoring.object(
                    recipe.source.get("parameters", {})
                ).items()
            },
            "bindings": recipe.source.get("bindings", {}),
            "connectionPoints": recipe.source.get("connectionPoints", {}),
            "overridePaths": recipe.source.get("overridePaths", []),
            "objectCounts": {
                registry: len(objects)
                for registry, objects in recipe.index.registries.items()
            },
        }

    @classmethod
    def catalog(cls) -> JsonObject:
        """List concise recipe identities and purposes for task routing."""
        return {
            "format": "home-design-recipe-catalog-0.1",
            "recipes": [
                {
                    "id": recipe.identity,
                    "name": recipe.source["name"],
                    "description": recipe.source.get("description", ""),
                    "source": str(path),
                }
                for path, recipe in cls.installed()
            ],
        }
