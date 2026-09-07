"""Select relevant schema failures using authored kind discriminators."""

from __future__ import annotations

from jsonschema.exceptions import ValidationError

from home_design.diagnostics import Diagnostic
from home_design.json_types import JsonObject, JsonPointer, JsonValue


class SchemaDiagnostics:
    """Report the selected component's fields instead of every union alternative."""

    def __init__(self, schema: JsonObject) -> None:
        """Use the authoritative schema to interpret local discriminator branches."""
        self.schema: JsonObject = schema

    def relevant(self, error: ValidationError) -> list[Diagnostic]:
        """Retain field-level errors for an unambiguous authored kind."""
        instance = error.instance
        branches = (
            error.schema.get(str(error.validator))
            if isinstance(error.schema, dict)
            else None
        )
        if (
            error.validator in {"oneOf", "anyOf"}
            and isinstance(instance, dict)
            and isinstance(branches, list)
        ):
            discriminator = "kind" if "kind" in instance else "op"
            kind = instance.get(discriminator)
            matches = [
                index
                for index, branch in enumerate(branches)
                if isinstance(kind, str)
                and kind in self.kinds(branch, field=discriminator)
            ]
            if len(matches) == 1:
                children = [
                    child
                    for child in error.context
                    if child.schema_path and child.schema_path[0] == matches[0]
                ]
                if children:
                    return [
                        diagnostic
                        for child in children
                        for diagnostic in self.relevant(child)
                    ]
        path = list(error.absolute_path)
        pointer = "".join(
            f"/{str(part).replace('~', '~0').replace('/', '~1')}" for part in path
        )
        message = error.message
        if error.validator in {"oneOf", "anyOf"}:
            kind = instance.get("kind") if isinstance(instance, dict) else None
            message = (
                f"Object kind {kind!r} does not match an allowed schema variant"
                if kind is not None
                else "Value does not match an allowed schema variant; inspect the selected source field"
            )
        return [
            Diagnostic(
                severity="error",
                code=f"schema.{error.validator}",
                message=message,
                path=pointer,
                subject_id=(
                    str(path[1])
                    if len(path) > 1
                    and path[0]
                    in {
                        "elements",
                        "types",
                        "anchors",
                        "materials",
                        "levels",
                        "relationships",
                    }
                    else None
                ),
            )
        ]

    def kinds(
        self,
        value: JsonValue,
        active: frozenset[str] | None = None,
        field: str = "kind",
    ) -> set[str]:
        """Find allowed discriminator values through local references and schema unions."""
        if not isinstance(value, dict):
            return set()
        active = active or frozenset()
        reference = value.get("$ref")
        if (
            isinstance(reference, str)
            and reference.startswith("#/")
            and reference not in active
        ):
            return self.kinds(
                JsonPointer.get(self.schema, reference[1:]), active | {reference}, field
            )
        properties = value.get("properties")
        kind = properties.get(field) if isinstance(properties, dict) else None
        if isinstance(kind, dict):
            if isinstance(kind.get("const"), str):
                return {str(kind["const"])}
            choices = kind.get("enum")
            if isinstance(choices, list):
                return {item for item in choices if isinstance(item, str)}
        conjunction = value.get("allOf")
        if isinstance(conjunction, list):
            constraints = [
                result
                for branch in conjunction
                if (result := self.kinds(branch, active, field))
            ]
            return set.intersection(*constraints) if constraints else set()
        for keyword in ("oneOf", "anyOf"):
            branches = value.get(keyword)
            if isinstance(branches, list):
                return set().union(
                    *(self.kinds(branch, active, field) for branch in branches)
                )
        return set()
