"""Explicit version migrations expressed as ordinary guarded authoring changesets."""

from __future__ import annotations

from copy import deepcopy

from home_design.changes import ChangeEngine
from home_design.boundaries import BoundaryIdentity
from home_design.construction import Authoring
from home_design.errors import HomeDesignError, ModelValidationError
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.validation import ModelValidator
from home_design.resolved import ResolvedModel


class ModelMigration:
    """Prepare deterministic migrations without silently rewriting a source on load."""

    def __init__(self, loader: ModelLoader | None = None) -> None:
        """Use the installed versioned schemas and ordinary transaction contract."""
        self.loader: ModelLoader = loader or ModelLoader()

    def prepare(self, source: JsonObject, target: str = "0.2") -> JsonObject:
        """Produce a reviewable migration changeset with full changed-object preconditions."""
        version = source.get("modelVersion")
        if version != "0.1" or target != "0.2":
            raise HomeDesignError(
                f"No migration from {version} to {target}; supported migration is 0.1 to 0.2",
                code="migration.unsupported-transition",
            )
        evaluation = ModelValidator(self.loader).evaluate(source)
        if not evaluation.report.is_valid or evaluation.resolved is None:
            raise ModelValidationError(
                "Migration requires a valid source model", evaluation.report
            )
        candidate = deepcopy(source)
        for definition in Authoring.object(candidate["types"]).values():
            value = Authoring.object(definition)
            if "layers" in value:
                for position, layer in enumerate(Authoring.array(value["layers"])):
                    Authoring.object(layer)["id"] = f"layer.legacy.{position}"
        for value in Authoring.object(candidate["elements"]).values():
            self._layer_references(value, candidate)
            self._topology(value)
        for value in Authoring.object(candidate["elements"]).values():
            self._topology_references(
                Authoring.object(value), candidate, evaluation.resolved
            )
        resolved = evaluation.resolved
        for element in resolved.elements:
            authored = Authoring.object(
                Authoring.object(candidate["elements"])[element.element_id]
            )
            if element.kind == "roof" and element.data.get("faceIdentities"):
                Authoring.object(authored["geometry"])["faceIds"] = deepcopy(
                    element.data["faceIdentities"]
                )
            if element.kind == "planarFraming":
                host = next(
                    host
                    for host in resolved.elements
                    if host.element_id == authored["host"]
                )
                if host.kind == "roof":
                    plane = next(
                        Authoring.object(plane)
                        for plane in Authoring.array(host.data["planes"])
                        if Authoring.object(plane)["id"] == authored["face"]
                    )
                    authored["originBoundary"] = Authoring.array(
                        Authoring.object(plane["boundaryIds"])["outer"]
                    )[0]
            if "memberIdentities" in element.data:
                Authoring.object(
                    Authoring.object(candidate["elements"])[element.element_id]
                )["memberIds"] = deepcopy(element.data["memberIdentities"])
        candidate["modelVersion"] = target
        if "$schema" in candidate:
            candidate["$schema"] = f"urn:home-design:schema:home-model:{target}"
        change = self._changeset(source, candidate)
        ChangeEngine(self.loader).validate_change(change)
        report = self.loader.validate_schema(candidate)
        if not report.is_valid:
            raise ModelValidationError(
                "Migration candidate does not match the target schema", report
            )
        return change

    @classmethod
    def _topology(cls, value: JsonValue) -> None:
        """Name declared profiles and wall paths without touching user specification data."""
        if isinstance(value, list):
            for child in value:
                cls._topology(child)
        elif isinstance(value, dict):
            if "outer" in value:
                value["boundaryIds"] = BoundaryIdentity.metadata(value)
            if isinstance(value.get("edgeOverhangs"), list):
                names = BoundaryIdentity.profile(Authoring.object(value["footprint"]))[
                    0
                ]
                offsets = Authoring.array(value["edgeOverhangs"])
                if len(names) != len(offsets):
                    raise HomeDesignError(
                        "Cannot migrate mismatched roof edge overhangs",
                        code="migration.edge-overhang-identities",
                    )
                value["edgeOverhangs"] = dict(zip(names, offsets))
            if value.get("kind") == "wall" and "path" in value:
                path = Authoring.object(value["path"])
                count = (
                    len(Authoring.array(path["points"])) - 1
                    if path.get("kind") == "polyline"
                    else 1
                )
                path["segmentIds"] = list(BoundaryIdentity.path(path, count))
            for key, child in list(value.items()):
                if key not in {
                    "properties",
                    "specifications",
                    "performance",
                    "externalIds",
                    "boundaryIds",
                }:
                    cls._topology(child)

    @staticmethod
    def _topology_references(
        value: JsonObject, candidate: JsonObject, resolved: ResolvedModel
    ) -> None:
        """Pin previous implicit selections to their original named spans."""
        elements = Authoring.object(candidate["elements"])
        if value.get("kind") == "wallFraming":
            host = Authoring.object(elements[Authoring.text(value["host"])])
            path = Authoring.object(host["path"])
            names = tuple(
                Authoring.text(name) for name in Authoring.array(path["segmentIds"])
            )
            value["segment"] = names[
                BoundaryIdentity.select(names, value.get("segment", 0))
            ]
        follow = value.get("follow")
        if isinstance(follow, dict):
            host = Authoring.object(elements[Authoring.text(follow["element"])])
            if host.get("kind") in {"slab", "footing"}:
                profile = Authoring.object(
                    host.get(
                        "footprint",
                        resolved.element(Authoring.text(follow["element"])).data.get(
                            "footprint"
                        ),
                    ),
                    "followed footprint",
                )
                names = BoundaryIdentity.profile(profile)[0]
                follow["edge"] = names[
                    BoundaryIdentity.select(names, follow.pop("edgeIndex", 0))
                ]
        if value.get("kind") == "planarFraming":
            host = Authoring.object(elements[Authoring.text(value["host"])])
            if host.get("kind") == "roof":
                geometry = Authoring.object(host["geometry"])
                if geometry.get("kind") == "faceSet":
                    faces = [
                        Authoring.object(face)
                        for face in Authoring.array(geometry["faces"])
                    ]
                    profile = Authoring.object(
                        next(face for face in faces if face["id"] == value["face"])[
                            "boundary"
                        ]
                    )
                    value["originBoundary"] = BoundaryIdentity.profile(profile)[0][0]
                else:
                    value["originBoundary"] = "boundary.legacy.0.0"
            else:
                value["originBoundary"] = BoundaryIdentity.profile(
                    Authoring.object(host["footprint"])
                )[0][0]

    @classmethod
    def _layer_references(
        cls, value: JsonValue, candidate: JsonObject, host: str | None = None
    ) -> None:
        """Rebind declared layer selections while preserving unrelated specifications verbatim."""
        if isinstance(value, list):
            for item in value:
                cls._layer_references(item, candidate, host)
            return
        if not isinstance(value, dict):
            return
        selected = value.get("host", value.get("element"))
        if isinstance(selected, str):
            host = selected
        if "layer" in value:
            value["layer"] = cls._layer_id(candidate, host, value["layer"])
        if isinstance(value.get("layers"), list):
            value["layers"] = [
                cls._layer_id(candidate, host, selection)
                for selection in Authoring.array(value["layers"])
            ]
        for key, child in value.items():
            if key not in {
                "properties",
                "specifications",
                "performance",
                "externalIds",
                "layer",
                "layers",
            }:
                cls._layer_references(child, candidate, host)

    @staticmethod
    def _layer_id(
        candidate: JsonObject, host_id: str | None, selection: JsonValue
    ) -> str:
        """Resolve a legacy index against the exact host type before assigning its durable ID."""
        elements = Authoring.object(candidate["elements"])
        types = Authoring.object(candidate["types"])
        if host_id is None or host_id not in elements:
            raise HomeDesignError(
                "Cannot migrate a layer selection without its host",
                code="migration.layer-host",
            )
        host = Authoring.object(elements[host_id])
        type_id = Authoring.text(host.get("type"), "layer host type")
        definition = Authoring.object(types[type_id])
        if (
            host.get("kind") == "footing"
            and selection == 0
            and definition.get("representation") == "explicit"
        ):
            return "layer.legacy.0"
        layers = Authoring.array(definition.get("layers", []))
        if (
            not isinstance(selection, int)
            or isinstance(selection, bool)
            or not 0 <= selection < len(layers)
        ):
            raise HomeDesignError(
                f"Cannot migrate unavailable layer {selection} on {host_id}",
                code="migration.layer-selection",
            )
        return Authoring.text(Authoring.object(layers[selection])["id"])

    @staticmethod
    def _changeset(source: JsonObject, candidate: JsonObject) -> JsonObject:
        """Keep source-object identity and preserve standard revision/precondition checks."""
        preconditions: list[JsonValue] = []
        operations: list[JsonValue] = []
        for field in ("modelVersion", "$schema"):
            if field in candidate and source.get(field) != candidate[field]:
                preconditions.append({"path": f"/{field}", "equals": source.get(field)})
                operations.append(
                    {"op": "set", "path": f"/{field}", "value": candidate[field]}
                )
        for registry in (
            "levels",
            "anchors",
            "materials",
            "types",
            "elements",
            "relationships",
        ):
            before = Authoring.object(source[registry])
            after = Authoring.object(candidate[registry])
            for identity, value in after.items():
                if before[identity] != value:
                    preconditions.append(
                        {"path": f"/{registry}/{identity}", "equals": before[identity]}
                    )
                    operations.append(
                        {
                            "op": "putObject",
                            "registry": registry,
                            "objectId": identity,
                            "value": value,
                        }
                    )
        return {
            "changeVersion": "0.1",
            "id": "change.migrate-0.1-to-0.2",
            "description": "Migrate to durable component substructure identities in model version 0.2.",
            "baseRevision": source["revision"],
            "preconditions": preconditions,
            "operations": operations,
        }
