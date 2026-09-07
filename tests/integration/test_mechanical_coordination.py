"""Connected mechanical branches, supports, access and host penetrations through coordinated edits."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class AirBranchFixture:
    """Author an air handler, inline damper, insulated tee and two physical terminals."""

    @staticmethod
    def port(end: bool, depth: float) -> JsonObject:
        """Expose opposed local interfaces matching the physical rectangular passage."""
        return {
            "position": [0, 0, depth if end else 0],
            "direction": [0, 0, 1 if end else -1],
            "section": {"kind": "rectangle", "width": 60, "height": 40},
            "medium": "air",
            "flow": "bidirectional",
            "connectionType": "illustrativeFlange",
        }

    @staticmethod
    def offset(element: str, point: list[JsonValue]) -> JsonObject:
        """Keep a model-space location dependent on one equipment frame."""
        return {"host": {"kind": "component", "element": element, "offset": point}}

    @staticmethod
    def mate(element: str, port: str) -> JsonObject:
        """Locate a part from a resolved mating interface."""
        return {"port": {"element": element, "port": port}}

    @classmethod
    def configure(cls, model: JsonObject) -> None:
        """Resolve a complete branched air network independently of the public reference geometry."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        Authoring.object(model["anchors"])["anchor.mechanical"] = {
            "kind": "point3",
            "name": "Mechanical network origin",
            "position": [0, 0, 0],
        }
        materials = Authoring.object(model["materials"])
        materials["material.cover"] = {"name": "Illustrative service insulation"}
        materials["material.support"] = {"name": "Illustrative support stock"}
        types = Authoring.object(model["types"])
        port_keys: dict[str, list[str]] = {}
        for key, role, depth in (
            ("ahu", "airHandler", 100),
            ("damper", "damper", 50),
            ("terminal", "airTerminal", 50),
        ):
            ports: JsonObject = {"in": cls.port(False, depth)}
            if role != "airTerminal":
                ports["out"] = cls.port(True, depth)
            types[f"type.{key}"] = {
                "kind": "serviceDeviceType",
                "name": f"Illustrative {role}",
                "role": role,
                "material": "material.timber",
                "mechanical": {"designation": role},
                "solids": {
                    "body": {
                        "section": {"kind": "rectangle", "width": 100, "depth": 80},
                        "depth": depth,
                    }
                },
                "cuts": {
                    "passage": {
                        "section": {"kind": "rectangle", "width": 60, "depth": 40},
                        "depth": depth,
                    }
                },
                "ports": ports,
                "portGroups": [list(ports)] if len(ports) > 1 else [],
            }
        Authoring.object(Authoring.object(types["type.damper"])["mechanical"])[
            "damperType"
        ] = "balancing"
        Authoring.object(Authoring.object(types["type.terminal"])["mechanical"])[
            "terminalType"
        ] = "register"
        section: JsonObject = {"kind": "rectangle", "width": 60, "height": 40}
        types["type.duct"] = {
            "kind": "serviceRouteType",
            "name": "Illustrative branch duct",
            "family": "duct",
            "material": "material.timber",
            "section": section,
            "wallThickness": 1,
            "medium": "air",
            "connectionType": "illustrativeFlange",
            "duct": {"designation": "Branch stock", "construction": "rigid"},
        }
        types["type.branch"] = {
            "kind": "serviceFittingType",
            "name": "Illustrative duct tee",
            "family": "duct",
            "material": "material.timber",
            "wallThickness": 1,
            "chordTolerance": 0.1,
            "medium": "air",
            "connectionType": "illustrativeFlange",
            "geometry": {
                "kind": "branch",
                "trunk": {
                    "section": section,
                    "path": [[0, 0, 0], [0, 0, 400]],
                    "up": [0, 1, 0],
                },
                "branches": {
                    "side": {
                        "section": section,
                        "path": [[0, 0, 200], [200, 0, 200]],
                        "up": [0, 1, 0],
                    }
                },
            },
        }
        types["type.cover"] = {
            "kind": "serviceInsulationType",
            "name": "Ten millimetre covering",
            "material": "material.cover",
            "thickness": 10,
        }
        types["type.support"] = {
            "kind": "hardwareType",
            "name": "Illustrative insulated duct strap",
            "role": "hanger",
            "material": "material.support",
            "solids": {
                "ring": {
                    "section": {"kind": "rectangle", "width": 100, "depth": 80},
                    "depth": 6,
                },
                "arm": {
                    "section": {"kind": "rectangle", "width": 20, "depth": 80},
                    "depth": 6,
                    "placement": {"origin": [0, -70, 0]},
                },
            },
            "cuts": {
                "passage": {
                    "section": {"kind": "rectangle", "width": 84, "depth": 64},
                    "depth": 6,
                }
            },
        }
        types["type.beam"] = {
            "kind": "memberType",
            "name": "Illustrative support framing",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 20, "depth": 20},
        }
        elements: JsonObject = {
            "device.ahu": {
                "kind": "serviceDevice",
                "name": "Air handler",
                "type": "type.ahu",
                "placement": {"origin": {"anchor": "anchor.mechanical"}},
                "portStates": {"in": "open"},
            },
            "device.damper": {
                "kind": "serviceDevice",
                "name": "Branch damper",
                "type": "type.damper",
                "placement": {"origin": cls.mate("duct.feed", "end")},
            },
            "fitting.branch": {
                "kind": "serviceFitting",
                "name": "Branch tee",
                "type": "type.branch",
                "placement": {"origin": cls.mate("duct.trunk", "end")},
            },
        }
        port_keys.update(
            {
                "device.ahu": ["in", "out"],
                "device.damper": ["in", "out"],
                "fitting.branch": ["start", "end", "side"],
            }
        )
        for key, parent, port, end in (
            ("feed", "device.ahu", "out", [0, 0, 400]),
            ("trunk", "device.damper", "out", [0, 0, 350]),
            ("end", "fitting.branch", "end", [0, 0, 700]),
            ("side", "fitting.branch", "side", [500, 0, 200]),
        ):
            identity = f"duct.{key}"
            elements[identity] = {
                "kind": "serviceRoute",
                "name": f"Duct {key}",
                "type": "type.duct",
                "chordTolerance": 0.1,
                "path": [cls.mate(parent, port), cls.offset(parent, list(end))],
            }
            port_keys[identity] = ["start", "end"]
        for key in ("end", "side"):
            identity = f"terminal.{key}"
            elements[identity] = {
                "kind": "serviceDevice",
                "name": f"Register {key}",
                "type": "type.terminal",
                "placement": {"origin": cls.mate(f"duct.{key}", "end")},
            }
            port_keys[identity] = ["in"]
        for identity in (
            "duct.feed",
            "duct.trunk",
            "duct.end",
            "duct.side",
            "fitting.branch",
        ):
            elements[f"cover.{identity}"] = {
                "kind": "serviceInsulation",
                "name": f"Cover for {identity}",
                "type": "type.cover",
                "host": identity,
                "chordTolerance": 0.1,
            }
        elements["member.support"] = {
            "kind": "member",
            "name": "Support framing",
            "type": "type.beam",
            "role": "beam",
            "axis": [
                cls.offset("device.ahu", [-200, -100, 240]),
                cls.offset("device.ahu", [200, -100, 240]),
            ],
        }
        elements["hardware.support"] = {
            "kind": "hardware",
            "name": "Duct support",
            "type": "type.support",
            "discipline": "services",
            "placement": {
                "origin": {
                    "host": {"kind": "route", "element": "duct.feed", "station": 150}
                }
            },
            "participants": [
                {"element": identity}
                for identity in ("duct.feed", "cover.duct.feed", "member.support")
            ],
        }
        elements["zone.access"] = {
            "kind": "clearanceZone",
            "name": "Equipment maintenance access",
            "owner": "device.ahu",
            "purpose": "maintenance",
            "placement": {"origin": cls.offset("device.ahu", [0, -200, 0])},
            "geometry": {
                "section": {"kind": "rectangle", "width": 300, "depth": 200},
                "depth": 200,
            },
        }
        elements["system.air"] = {
            "kind": "serviceSystem",
            "name": "Connected supply air",
            "systemType": "supplyAir",
            "members": [
                {"element": identity, "port": key}
                for identity, keys in port_keys.items()
                for key in keys
            ],
        }
        model["elements"] = elements
        relationships = Authoring.object(model["relationships"])
        for index, (a, pa, b, pb) in enumerate(
            (
                ("device.ahu", "out", "duct.feed", "start"),
                ("duct.feed", "end", "device.damper", "in"),
                ("device.damper", "out", "duct.trunk", "start"),
                ("duct.trunk", "end", "fitting.branch", "start"),
                ("fitting.branch", "end", "duct.end", "start"),
                ("duct.end", "end", "terminal.end", "in"),
                ("fitting.branch", "side", "duct.side", "start"),
                ("duct.side", "end", "terminal.side", "in"),
            )
        ):
            relationships[f"connection.{index}"] = {
                "kind": "connectsPorts",
                "a": {"element": a, "port": pa},
                "b": {"element": b, "port": pb},
            }


def test_insulated_air_branch_supports_and_access_follow_equipment_edit(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
) -> None:
    """A complete branched network retains mates, covers, support stock and access through a move."""
    AirBranchFixture.configure(reference_model)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.mechanical",
            "description": "Move the complete mechanical branch",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "moveAnchor",
                    "anchorId": "anchor.mechanical",
                    "position": [300, 400, 500],
                }
            ],
        },
    )
    before, after = (
        ModelResolver(reference_model).resolve(),
        ModelResolver(changed).resolve(),
    )
    old_rows = Authoring.array(ModelReports(before).schedules()["materials"])
    new_rows = Authoring.array(ModelReports(after).schedules()["materials"])
    assert len(old_rows) == len(new_rows)
    for old_value, new_value in zip(old_rows, new_rows):
        old_row, new_row = Authoring.object(old_value), Authoring.object(new_value)
        assert old_row["materialId"] == new_row["materialId"]
        assert old_row["specification"] == new_row["specification"]
        assert number(old_row["volumeM3"], "volume") == pytest.approx(
            number(new_row["volumeM3"], "volume"), rel=1e-9, abs=1e-12
        )
    for element in before.elements:
        if not element.meshes:
            continue
        moved = after.element(element.element_id)
        assert [
            min(p[i] for mesh in moved.meshes for p in mesh.vertices) for i in range(3)
        ] == pytest.approx(
            [
                min(p[i] for mesh in element.meshes for p in mesh.vertices) + offset
                for i, offset in enumerate((300, 400, 500))
            ]
        )
    support = after.element("hardware.support")
    for identity in ("duct.feed", "cover.duct.feed"):
        assert (
            SolidOperations.intersection(
                support.meshes[0], after.element(identity).meshes[0]
            )
            is None
        )
    output = tmp_path / "branches.ifc"
    IfcExporter().export(after, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    assert len(ifc.by_type("IfcRelConnectsPorts")) == 8
    assert len(ifc.by_type("IfcCovering")) == 5
    assert len(ifc.by_type("IfcDuctSegment")) == 4
    assert len(ifc.by_type("IfcDamper")) == 1
    manifest = GltfExporter().export(
        after, tmp_path / "branches.glb", tmp_path / "manifest.json"
    )
    assert Authoring.object(Authoring.object(manifest["elements"])["hardware.support"])[
        "nodes"
    ]


def test_mechanical_maintenance_zone_reports_a_physical_obstruction(
    reference_model: JsonObject,
    validator: ModelValidator,
) -> None:
    """A correctly connected network can still fail its authored equipment-access requirement."""
    AirBranchFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    elements["member.obstruction"] = {
        "kind": "member",
        "name": "Obstructing member",
        "type": "type.beam",
        "role": "beam",
        "axis": [
            AirBranchFixture.offset("device.ahu", [-100, -200, 50]),
            AirBranchFixture.offset("device.ahu", [100, -200, 50]),
        ],
    }
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert any(item.code == "access.obstructed" for item in report.errors)


def test_mechanical_branch_builds_keep_native_identity_and_complete_schedules(
    reference_model: JsonObject,
    tmp_path: Path,
) -> None:
    """The complete build workflow preserves mechanical identities and quantities deterministically."""
    AirBranchFixture.configure(reference_model)
    source = tmp_path / "mechanical-branch.json"
    source.write_text(json.dumps(reference_model), encoding="utf-8")
    first = BuildService().build(source, tmp_path / "first")
    second = BuildService().build(source, tmp_path / "second")
    assert first.glb_model.read_bytes() == second.glb_model.read_bytes()
    first_ifc, second_ifc = ifcopenshell.open(first.ifc_model), ifcopenshell.open(
        second.ifc_model
    )
    assert sorted(
        product.GlobalId for product in first_ifc.by_type("IfcRoot")
    ) == sorted(product.GlobalId for product in second_ifc.by_type("IfcRoot"))
    assert first.schedules.read_bytes() == second.schedules.read_bytes()
    schedules = Authoring.object(
        json.loads(first.schedules.read_text(encoding="utf-8"))
    )
    assert len(Authoring.array(schedules["serviceDevices"])) == 4
    assert len(Authoring.array(schedules["serviceRoutes"])) == 4
    assert len(Authoring.array(schedules["serviceInsulation"])) == 5
    assert len(Authoring.array(schedules["hardware"])) == 1
    for value in Authoring.array(schedules["serviceDevices"]):
        row = Authoring.object(value)
        assert "mechanical" in Authoring.object(row["dimensionsAndSpecifications"])


@pytest.mark.parametrize("sloped", [False, True])
def test_insulated_branch_penetrations_follow_floor_thickness_and_roof_slope(
    reference_model: JsonObject,
    validator: ModelValidator,
    loader: ModelLoader,
    tmp_path: Path,
    sloped: bool,
) -> None:
    """A covering-sized owned cut preserves actual material accounting through host changes."""
    AirBranchFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    types["type.shell"] = {
        "kind": "roofType" if sloped else "slabType",
        "name": "Illustrative shell panel",
        "layers": [
            {
                "name": "Panel stock",
                "material": "material.timber",
                "thickness": 100,
                "function": "structure",
            }
        ],
        "layerOrder": "topToBottom",
    }
    elements = Authoring.object(reference_model["elements"])
    host: JsonObject = {
        "kind": "roof" if sloped else "slab",
        "name": "Mechanical penetration host",
        "type": "type.shell",
        "storey": "level.ground",
    }
    if sloped:
        host["geometry"] = {
            "kind": "faceSet",
            "faces": [
                {
                    "id": "face.slope",
                    "boundary": {
                        "outer": [
                            [-200, -200, 1250],
                            [200, -200, 1250],
                            [200, 200, 1450],
                            [-200, 200, 1450],
                        ]
                    },
                }
            ],
        }
    else:
        host.update(
            {
                "role": "floor",
                "extrusionDirection": "down",
                "datum": {"kind": "level", "level": "level.ground", "offset": 1350},
                "footprint": {
                    "outer": [
                        {"point": [-200, -200]},
                        {"point": [200, -200]},
                        {"point": [200, 200]},
                        {"point": [-200, 200]},
                    ]
                },
            }
        )
    elements["shell.host"] = host
    elements["cut.branch"] = {
        "kind": "penetration",
        "name": "Insulated duct passage",
        "host": "shell.host",
        "owner": "cover.duct.end",
        "purpose": "service",
        "geometrySource": {"element": "cover.duct.end", "volume": "envelope"},
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    operation: JsonObject = (
        {
            "op": "set",
            "path": "/elements/shell.host/geometry/faces/0/boundary/outer",
            "value": [
                [-200, -200, 1250],
                [200, -200, 1250],
                [200, 200, 1550],
                [-200, 200, 1550],
            ],
        }
        if sloped
        else {"op": "set", "path": "/types/type.shell/layers/0/thickness", "value": 120}
    )
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.host",
            "description": "Adjust the penetrated shell panel",
            "baseRevision": reference_model["revision"],
            "operations": [operation],
        },
    )
    removed_volumes: list[float] = []
    for model in (reference_model, changed):
        gross = deepcopy(model)
        del Authoring.object(gross["elements"])["cut.branch"]
        original = ModelResolver(gross).resolve()
        resolved = ModelResolver(model).resolve()
        mask = resolved.element("cover.duct.end").construction_volumes["envelope"]
        expected = sum(
            SolidOperations.volume(shared)
            for mesh in original.element("shell.host").meshes
            if (shared := SolidOperations.intersection(mesh, mask)) is not None
        )
        cut_volume = sum(
            SolidOperations.volume(mesh)
            for mesh in resolved.element("cut.branch").meshes
        )
        assert cut_volume == pytest.approx(expected, rel=1e-9)
        before_volume = sum(
            SolidOperations.volume(mesh)
            for mesh in original.element("shell.host").meshes
        )
        after_volume = sum(
            SolidOperations.volume(mesh)
            for mesh in resolved.element("shell.host").meshes
        )
        assert before_volume - after_volume == pytest.approx(cut_volume, rel=1e-9)
        assert all(
            SolidOperations.intersection(mesh, mask) is None
            for mesh in resolved.element("shell.host").meshes
        )
        removed_volumes.append(cut_volume)
    assert removed_volumes[1] > removed_volumes[0]
    output = tmp_path / "host-cut.ifc"
    IfcExporter().export(ModelResolver(changed).resolve(), output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    opening = ifc.by_guid(IfcExporter.stable_guid("cut.branch"))
    assert opening.is_a("IfcOpeningElement")
    assert opening.VoidsElements[0].RelatingBuildingElement.Tag == "shell.host"
