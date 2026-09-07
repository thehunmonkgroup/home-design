"""Validate recorded assembly connection points against actual resolved components."""

from __future__ import annotations

from home_design.construction import Authoring
from home_design.diagnostics import Diagnostic
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedModel


class RecipeInterfaces:
    """Ensure advertised connection points remain available after parameter and local edits."""

    @staticmethod
    def diagnostics(model: JsonObject, resolved: ResolvedModel) -> list[Diagnostic]:
        """Check bound element and scoped port names using the same geometry consumed by exports."""
        diagnostics: list[Diagnostic] = []
        elements = {element.element_id: element for element in resolved.elements}
        for identity, raw in Authoring.object(model["elements"]).items():
            record = Authoring.object(raw).get("recipeInstance")
            if not isinstance(record, dict):
                continue
            for name, value in Authoring.object(
                record.get("connectionPoints", {})
            ).items():
                point = Authoring.object(value)
                target = elements.get(Authoring.text(point["element"]))
                port = point.get("port")
                if target is None or (
                    port is not None
                    and port not in Authoring.object(target.data.get("ports", {}))
                ):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "recipe.connection-point-unavailable",
                            f"Assembly connection point {name} has no matching resolved element or port",
                            f"/elements/{identity}/recipeInstance/connectionPoints/{name}",
                            identity,
                        )
                    )
        return diagnostics
