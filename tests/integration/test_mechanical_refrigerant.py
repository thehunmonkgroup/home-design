"""Connected refrigerant loops and gravity condensate routes through equipment edits."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.errors import ModelValidationError
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.resolver import ModelResolver
from home_design.service_ports import ServicePorts
from home_design.validation import ModelValidator


class RefrigerantFixture:
    """Keep equipment placement dependencies independent of the physical refrigerant loop."""

    @staticmethod
    def port(
        medium: str, position: list[JsonValue], direction: list[JsonValue]
    ) -> JsonObject:
        """Describe an illustrative equipment interface without inferred internal heat-exchanger geometry."""
        return {
            "position": position,
            "direction": direction,
            "medium": medium,
            "section": {"kind": "circle", "diameter": 10},
            "connectionType": "illustrativeCoupling",
            "flow": "bidirectional",
        }

    @classmethod
    def configure(cls, model: JsonObject) -> None:
        """Connect a refrigerant unit and DX coil with two insulated lines and a separate drain."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        Authoring.object(model["anchors"])["anchor.refrigeration"] = {
            "kind": "point3",
            "name": "Refrigeration origin",
            "position": [0, 0, 0],
        }
        Authoring.object(model["materials"])["material.cover"] = {
            "name": "Illustrative refrigerant insulation"
        }
        types = Authoring.object(model["types"])
        for device, role in (("unit", "refrigerantUnit"), ("coil", "coil")):
            ports: JsonObject = {
                "liquid": cls.port(
                    "refrigerant",
                    [-30, 0, 100 if device == "unit" else 0],
                    [0, 0, 1 if device == "unit" else -1],
                ),
                "vapor": cls.port(
                    "refrigerant",
                    [30, 0, 100 if device == "unit" else 0],
                    [0, 0, 1 if device == "unit" else -1],
                ),
            }
            groups: list[JsonValue] = [["liquid", "vapor"]]
            if device == "coil":
                ports["air.in"] = cls.port("air", [-50, 0, 50], [-1, 0, 0])
                ports["air.out"] = cls.port("air", [50, 0, 50], [1, 0, 0])
                ports["drain"] = cls.port("condensate", [0, -50, 20], [0, -1, -0.02])
                groups.append(["air.in", "air.out"])
            types[f"type.{device}"] = {
                "kind": "serviceDeviceType",
                "name": f"Illustrative {role}",
                "role": role,
                "material": "material.timber",
                "mechanical": {
                    "designation": role,
                    **({"coilType": "dxCooling"} if device == "coil" else {}),
                },
                "solids": {
                    "housing": {
                        "section": {"kind": "rectangle", "width": 100, "depth": 100},
                        "depth": 100,
                    }
                },
                "ports": ports,
                "portGroups": groups,
            }
        for name, medium in (("refrigerant", "refrigerant"), ("drain", "condensate")):
            types[f"type.{name}"] = {
                "kind": "serviceRouteType",
                "name": f"Illustrative {name} line",
                "family": "pipe",
                "material": "material.timber",
                "medium": medium,
                "connectionType": "illustrativeCoupling",
                "section": {"kind": "circle", "diameter": 10},
                "wallThickness": 1,
                "pipe": {"designation": "Authored line stock"},
            }
        types["type.cover"] = {
            "kind": "serviceInsulationType",
            "name": "Five millimetre cover",
            "material": "material.cover",
            "thickness": 5,
        }
        elements: JsonObject = {
            "device.unit": {
                "kind": "serviceDevice",
                "name": "Refrigerant unit",
                "type": "type.unit",
                "placement": {"origin": {"anchor": "anchor.refrigeration"}},
            },
            "device.coil": {
                "kind": "serviceDevice",
                "name": "DX coil",
                "type": "type.coil",
                "placement": {
                    "origin": {
                        "host": {
                            "kind": "component",
                            "element": "device.unit",
                            "offset": [0, 0, 1000],
                        }
                    }
                },
                "portStates": {"air.in": "open", "air.out": "open"},
            },
        }
        members: list[JsonValue] = []
        relationships = Authoring.object(model["relationships"])
        for name in ("liquid", "vapor"):
            identity = f"pipe.{name}"
            elements[identity] = {
                "kind": "serviceRoute",
                "name": f"Refrigerant {name} line",
                "type": "type.refrigerant",
                "chordTolerance": 0.1,
                "path": [
                    {"port": {"element": device, "port": name}}
                    for device in ("device.unit", "device.coil")
                ],
            }
            elements[f"cover.{name}"] = {
                "kind": "serviceInsulation",
                "name": f"Cover for {name}",
                "type": "type.cover",
                "host": identity,
                "chordTolerance": 0.1,
            }
            for device, port in (("device.unit", "start"), ("device.coil", "end")):
                relationships[f"connect.{name}.{port}"] = {
                    "kind": "connectsPorts",
                    "a": {"element": device, "port": name},
                    "b": {"element": identity, "port": port},
                }
                members.extend(
                    [
                        {"element": device, "port": name},
                        {"element": identity, "port": port},
                    ]
                )
        elements["pipe.drain"] = {
            "kind": "serviceRoute",
            "name": "Gravity condensate drain",
            "type": "type.drain",
            "chordTolerance": 0.1,
            "path": [
                {"port": {"element": "device.coil", "port": "drain"}},
                {
                    "host": {
                        "kind": "component",
                        "element": "device.coil",
                        "offset": [0, -550, 10],
                    }
                },
            ],
            "fallCheck": {"minimumFall": 0.02, "direction": "startToEnd"},
            "portStates": {"end": "open"},
        }
        relationships["connect.drain"] = {
            "kind": "connectsPorts",
            "a": {"element": "device.coil", "port": "drain"},
            "b": {"element": "pipe.drain", "port": "start"},
        }
        elements["system.refrigerant"] = {
            "kind": "serviceSystem",
            "name": "Closed refrigerant network",
            "systemType": "refrigerant",
            "members": members,
        }
        elements["system.air"] = {
            "kind": "serviceSystem",
            "name": "Coil air passage",
            "systemType": "supplyAir",
            "members": [
                {"element": "device.coil", "port": name}
                for name in ("air.in", "air.out")
            ],
        }
        elements["system.drain"] = {
            "kind": "serviceSystem",
            "name": "Condensate drainage",
            "systemType": "condensate",
            "members": [
                {"element": "device.coil", "port": "drain"},
                {"element": "pipe.drain", "port": "start"},
                {"element": "pipe.drain", "port": "end"},
            ],
        }
        model["elements"] = elements


def test_refrigerant_loop_condensate_fall_and_insulation_follow_equipment_edit(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
) -> None:
    """Connected loops remain distinct from geometry cycles and from the falling condensate system."""
    RefrigerantFixture.configure(reference_model)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.refrigeration",
            "description": "Move connected refrigeration equipment",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "moveAnchor",
                    "anchorId": "anchor.refrigeration",
                    "position": [300, 400, 500],
                }
            ],
        },
    )
    before, after = (
        ModelResolver(reference_model).resolve(),
        ModelResolver(changed).resolve(),
    )
    for identity in (
        "pipe.liquid",
        "pipe.vapor",
        "pipe.drain",
        "cover.liquid",
        "cover.vapor",
    ):
        old, new = before.element(identity), after.element(identity)
        assert number(old.data["netVolumeMm3"], "volume") == pytest.approx(
            number(new.data["netVolumeMm3"], "volume"), rel=1e-9
        )
    for name in ("liquid", "vapor", "drain"):
        identity = f"pipe.{name}"
        for port in ("start", "end"):
            old = ServicePorts.frame(
                Authoring.object(
                    Authoring.object(before.element(identity).data["ports"])[port]
                )
            )
            new = ServicePorts.frame(
                Authoring.object(
                    Authoring.object(after.element(identity).data["ports"])[port]
                )
            )
            assert new.origin == pytest.approx(
                [old.origin[i] + shift for i, shift in enumerate((300, 400, 500))]
            )
    fall = Authoring.object(after.element("pipe.drain").data["fallCheck"])
    assert fall["status"] == "satisfied" and fall[
        "minimumObservedFall"
    ] == pytest.approx(0.02)
    output = tmp_path / "refrigeration.ifc"
    IfcExporter().export(after, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert len(ifc.by_type("IfcRelConnectsPorts")) == 5
    assert len(ifc.by_type("IfcDistributionSystem")) == 3
    assert {port.SystemType for port in ifc.by_type("IfcDistributionPort")} == {
        "REFRIGERATION",
        "DRAINAGE",
        "VENTILATION",
    }
    manifest = GltfExporter().export(
        after, tmp_path / "refrigeration.glb", tmp_path / "manifest.json"
    )
    assert Authoring.object(Authoring.object(manifest["elements"])["cover.liquid"])[
        "nodes"
    ]


def test_refrigeration_rejects_a_reversed_condensate_fall(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
) -> None:
    """A coordinated edit cannot silently turn the declared drain direction uphill."""
    RefrigerantFixture.configure(reference_model)
    with pytest.raises(ModelValidationError, match="Drainage path span"):
        ChangeEngine(loader, validator).apply(
            reference_model,
            {
                "changeVersion": "0.1",
                "id": "change.bad-fall",
                "description": "Reverse the drain reference",
                "baseRevision": reference_model["revision"],
                "operations": [
                    {
                        "op": "set",
                        "path": "/elements/pipe.drain/fallCheck/direction",
                        "value": "endToStart",
                    }
                ],
            },
        )
