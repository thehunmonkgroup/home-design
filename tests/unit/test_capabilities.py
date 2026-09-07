"""Cross-layer component registration and explicit unsupported-family rejection."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import ifcopenshell.ifcopenshell_wrapper

from home_design.capabilities import ComponentCapability, ComponentRegistry
from home_design.cli import main
from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.graph import ModelIndex
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.adapters.gltf import GltfExporter


def test_schema_and_ifc_cover_every_registered_component() -> None:
    assert ComponentRegistry.audit(ModelLoader().schema) == []
    ifc = ifcopenshell.ifcopenshell_wrapper.schema_by_name("IFC4")
    for capability in ComponentRegistry.components.values():
        assert ifc.declaration_by_name(capability.ifc_class)
        if capability.ifc_type_class is not None:
            assert ifc.declaration_by_name(capability.ifc_type_class)


def test_schema_extension_requires_explicit_registration() -> None:
    schema = deepcopy(ModelLoader().schema)
    definitions = Authoring.object(schema["$defs"])
    element = Authoring.object(definitions["Element"])
    Authoring.array(element["oneOf"]).append(
        {"properties": {"kind": {"const": "unregisteredPart"}}}
    )
    assert (
        "Unregistered Element kinds: ['unregisteredPart']"
        in ComponentRegistry.audit(schema)
    )


def test_unknown_component_cannot_resolve_as_empty_assembly(
    reference_model: JsonObject,
) -> None:
    Authoring.object(reference_model["elements"])["unknown.part"] = {
        "kind": "unregisteredPart",
        "name": "Unknown part",
    }
    with pytest.raises(ResolutionError, match="Unsupported component kind"):
        ModelResolver(reference_model).resolve()


def test_registration_requires_a_bound_resolver(
    reference_model: JsonObject, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ComponentRegistry,
        "components",
        {
            **ComponentRegistry.components,
            "newFamily": ComponentCapability(
                "newFamily", "New family", "unbound-route", "IfcBuildingElementPart"
            ),
        },
    )
    with pytest.raises(ResolutionError, match="unbound resolvers"):
        ModelResolver(reference_model)


def test_type_reference_validation_uses_registered_pairing(
    reference_model: JsonObject,
) -> None:
    elements = Authoring.object(reference_model["elements"])
    window = Authoring.object(elements["window.north"])
    window["type"] = Authoring.object(elements["wall.north"])["type"]
    errors = ModelIndex(reference_model).diagnostics()
    mismatch = next(item for item in errors if item.code == "reference.kind-mismatch")
    assert mismatch.subject_id == "window.north"
    assert "windowType" in mismatch.message


def test_manifest_publishes_registry_labels_and_defaults(
    reference_model: JsonObject, tmp_path: Path
) -> None:
    resolved = ModelResolver(reference_model).resolve()
    manifest = GltfExporter().export(
        resolved, tmp_path / "model.glb", tmp_path / "manifest.json"
    )
    elements = Authoring.object(manifest["elements"])
    for element in resolved.elements:
        entry = Authoring.object(elements[element.element_id])
        capability = ComponentRegistry.get(element.kind)
        assert entry["kindLabel"] == capability.label
        assert entry["defaultVisible"] == capability.default_visible


def test_capability_cli_rejects_unknown_kind(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["capabilities", "--kind", "wallFraming"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert report["components"][0]["scopedMemberHost"] is True
    assert main(["capabilities", "--kind", "unregisteredPart"]) == 1
    failure = json.loads(capsys.readouterr().err)
    assert failure["error"]["code"] == "component.unsupported-kind"
