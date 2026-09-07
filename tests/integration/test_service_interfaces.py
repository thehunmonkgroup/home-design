"""Physical service sleeves, protective plates and seals with durable construction identity."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
import pytest

from home_design.adapters.gltf import GltfExporter
from home_design.adapters.ifc import IfcExporter
from home_design.changes import ChangeEngine
from home_design.construction import Authoring
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class InterfaceFixture:
    """Author a rectangular duct crossing a slab through independently fabricated interface stock."""

    ROLES: tuple[str, ...] = (
        "sleeve",
        "protectivePlate",
        "fireStop",
        "acousticSeal",
        "weatherSeal",
    )

    @staticmethod
    def configure(model: JsonObject, explicit: bool = False) -> None:
        """Use exact rectangular quantities without inferring fire or weather performance."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        types = Authoring.object(model["types"])
        types["type.host"] = {
            "kind": "slabType",
            "name": "Illustrative penetration host",
            "layerOrder": "topToBottom",
            "layers": [
                {
                    "name": "Host material",
                    "material": "material.timber",
                    "thickness": 100,
                    "function": "structure",
                    **({"representation": "explicit"} if explicit else {}),
                }
            ],
        }
        types["type.route"] = {
            "kind": "serviceRouteType",
            "name": "Illustrative square duct",
            "family": "duct",
            "medium": "air",
            "connectionType": "illustrativeFace",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 40, "height": 40},
            "wallThickness": 2,
        }
        elements: JsonObject = {
            "host.floor": {
                "kind": "slab",
                "name": "Service host",
                "type": "type.host",
                "storey": "level.ground",
                "role": "floor",
                "extrusionDirection": "down",
                "datum": {"kind": "level", "level": "level.ground", "offset": 100},
                "footprint": {
                    "outer": [
                        {"point": [-200, -200]},
                        {"point": [200, -200]},
                        {"point": [200, 200]},
                        {"point": [-200, 200]},
                    ]
                },
            },
            "route.run": {
                "kind": "serviceRoute",
                "name": "Crossing duct",
                "type": "type.route",
                "path": [{"point": [0, 0, -200]}, {"point": [0, 0, 300]}],
                "up": [0, 1, 0],
                "bendRadius": 100,
                "chordTolerance": 0.1,
                "portStates": {"start": "open", "end": "open"},
                "clearance": 15,
                "coordinationChecks": {
                    "interference": "error",
                    "clearance": {"severity": "error"},
                },
                **(
                    {
                        "occupies": {
                            "regions": [{"host": "host.floor", "layer": 0}],
                            "fit": "intersect",
                        }
                    }
                    if explicit
                    else {}
                ),
            },
            "system.air": {
                "kind": "serviceSystem",
                "name": "Air system",
                "systemType": "supplyAir",
                "members": [
                    {"element": "route.run", "port": key} for key in ("start", "end")
                ],
            },
            "cut.host": {
                "kind": "penetration",
                "name": "Owned sleeve clearance",
                "host": "host.floor",
                "owner": "part.sleeve",
                "purpose": "service",
                "placement": {
                    "origin": {
                        "host": {
                            "kind": "route",
                            "element": "route.run",
                            "station": 200,
                        }
                    }
                },
                "section": {"kind": "rectangle", "width": 80, "depth": 80},
                "depth": 100,
                "limits": {
                    "hostHole": {
                        "host": {
                            "kind": "surface",
                            "element": "host.floor",
                            "surface": "layerTop",
                            "layer": 0,
                            "point": [0, 0],
                        },
                        "maximumExtent": {"x": 80, "y": 80, "z": 100},
                        "maximumExtentFraction": {"x": 0.2, "y": 0.2, "z": 1},
                    }
                },
            },
        }
        for role, outside, inside, depth, offset in (
            ("sleeve", 64, 60, 100, 0),
            ("protectivePlate", 100, 80, 2, 100),
            ("fireStop", 80, 64, 10, 0),
            ("acousticSeal", 80, 64, 10, 45),
            ("weatherSeal", 80, 64, 10, 90),
        ):
            types[f"type.{role}"] = {
                "kind": "envelopePartType",
                "name": f"Illustrative {role}",
                "role": role,
                "material": "material.timber",
                "solids": {
                    "stock": {
                        "section": {
                            "kind": "rectangle",
                            "width": outside,
                            "depth": outside,
                        },
                        "depth": depth,
                    }
                },
                "cuts": {
                    "passage": {
                        "section": {
                            "kind": "rectangle",
                            "width": inside,
                            "depth": inside,
                        },
                        "depth": depth,
                    }
                },
            }
            elements[f"part.{role}"] = {
                "kind": "envelopePart",
                "name": f"Service {role}",
                "type": f"type.{role}",
                "placement": {
                    "origin": {
                        "host": {
                            "kind": "route",
                            "element": "route.run",
                            "station": 200 + offset,
                        }
                    }
                },
                "interface": {
                    "host": {"element": "host.floor"},
                    "services": [{"element": "route.run"}],
                },
                **(
                    {"occupies": {"regions": [{"host": "host.floor", "layer": 0}]}}
                    if explicit and role != "protectivePlate"
                    else {}
                ),
            }
        model["elements"] = elements


@pytest.mark.parametrize("explicit", [False, True])
def test_interfaces_preserve_material_cavities_connections_and_exports(
    reference_model: JsonObject,
    validator: ModelValidator,
    tmp_path: Path,
    explicit: bool,
) -> None:
    """Host cuts and cavity ownership leave disjoint stock and native, selectable interface products."""
    InterfaceFixture.configure(reference_model, explicit)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    volumes = {
        "sleeve": 49600,
        "protectivePlate": 7200,
        "fireStop": 23040,
        "acousticSeal": 23040,
        "weatherSeal": 23040,
    }
    for role, volume in volumes.items():
        part = resolved.element(f"part.{role}")
        assert part.data["netVolumeMm3"] == pytest.approx(volume)
        assert part.data["interfaceHostId"] == "host.floor"
        assert part.data["interfaceServiceIds"] == ["route.run"]
        assert part.data["discipline"] == "services"
        for other in resolved.elements:
            if other.element_id == part.element_id or other.kind == "penetration":
                continue
            assert all(
                SolidOperations.intersection(a, b) is None
                for a in part.meshes
                for b in other.meshes
            )
    host = resolved.element("host.floor")
    coordination = Authoring.object(
        resolved.element("route.run").data["serviceCoordination"]
    )
    assert Authoring.object(coordination["interference"])["status"] == "clear"
    clearance = Authoring.object(coordination["clearance"])
    assert clearance["status"] == "clear"
    assert len(Authoring.array(clearance["exclusions"])) == 5
    assert all(
        Authoring.object(value)["reason"] == "serviceInterface"
        for value in Authoring.array(clearance["exclusions"])
    )
    assert sum(SolidOperations.volume(mesh) for mesh in host.meshes) == pytest.approx(
        400 * 400 * 100 - 80 * 80 * 100
    )
    if explicit:
        cavity = Authoring.object(Authoring.array(host.data["cavities"])[0])
        occupied = 49600 + 3 * 23040 + (40 * 40 - 36 * 36) * 100
        assert cavity["occupiedVolumeMm3"] == pytest.approx(occupied)
        assert cavity["voidVolumeMm3"] == pytest.approx(80 * 80 * 100 - occupied)
        assert number(cavity["grossVolumeMm3"], "gross") == pytest.approx(
            sum(
                number(cavity[key], key)
                for key in ("infillVolumeMm3", "occupiedVolumeMm3", "voidVolumeMm3")
            )
        )
    schedules = ModelReports(resolved).schedules()
    assert len(Authoring.array(schedules["envelopeParts"])) == 5
    expected_total = (
        400 * 400 * 100
        - 80 * 80 * 100
        + sum(volumes.values())
        + (40 * 40 - 36 * 36) * 500
    )
    assert sum(
        number(Authoring.object(row)["volumeM3"], "volume")
        for row in Authoring.array(schedules["materials"])
    ) == pytest.approx(expected_total / 1e9)
    output = tmp_path / "interfaces.ifc"
    IfcExporter().export(resolved, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    manifest = GltfExporter().export(
        resolved, tmp_path / "interfaces.glb", tmp_path / "manifest.json"
    )
    for role in InterfaceFixture.ROLES:
        product = ifc.by_guid(IfcExporter.stable_guid(f"part.{role}"))
        native = "IfcPlate" if role == "protectivePlate" else "IfcCovering"
        assert product.is_a(native)
        assert product.IsTypedBy[0].RelatingType.is_a(native + "Type")
        assert ifcopenshell.util.element.get_predefined_type(product) == (
            "SLEEVING" if role == "sleeve" else role
        )
        connection = next(
            item
            for item in ifc.by_type("IfcRelConnectsWithRealizingElements")
            if product in item.RealizingElements
        )
        assert (connection.RelatingElement.Tag, connection.RelatedElement.Tag) == (
            "host.floor",
            "route.run",
        )
        assert connection.ConnectionType == role
        entry = Authoring.object(Authoring.object(manifest["elements"])[f"part.{role}"])
        assert (
            entry["nodes"]
            and Authoring.object(entry["data"])["interfaceHostId"] == "host.floor"
        )
    assert len(ifc.by_type("IfcDistributionPort")) == 2
    assert (
        ifc.by_type("IfcRelVoidsElement")[0].RelatingBuildingElement.Tag == "host.floor"
    )


def test_interface_station_edits_move_parts_and_owned_host_cut(
    reference_model: JsonObject, validator: ModelValidator, loader: ModelLoader
) -> None:
    """A revised route location carries interface solids and its opening without changing quantities."""
    InterfaceFixture.configure(reference_model, True)
    before = ModelResolver(reference_model).resolve()
    changed = ChangeEngine(loader, validator).apply(
        reference_model,
        {
            "changeVersion": "0.1",
            "id": "change.interface",
            "description": "Move the duct and its construction interface parts",
            "baseRevision": reference_model["revision"],
            "operations": [
                {
                    "op": "set",
                    "path": "/elements/route.run/path",
                    "value": [{"point": [50, 20, -200]}, {"point": [50, 20, 300]}],
                }
            ],
        },
    )
    after = ModelResolver(changed).resolve()
    for identity in [
        "route.run",
        "cut.host",
        *(f"part.{role}" for role in InterfaceFixture.ROLES),
    ]:
        old, new = before.element(identity), after.element(identity)
        assert sum(
            SolidOperations.volume(mesh) for mesh in new.meshes
        ) == pytest.approx(
            sum(SolidOperations.volume(mesh) for mesh in old.meshes), rel=1e-9
        )
        assert [
            min(point[i] for mesh in new.meshes for point in mesh.vertices)
            for i in range(3)
        ] == pytest.approx(
            [
                min(point[i] for mesh in old.meshes for point in mesh.vertices) + delta
                for i, delta in enumerate((50, 20, 0))
            ]
        )


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("missingInterface", "explicit service interface"),
        ("missingHost", "missing"),
        ("nonConstructionHost", "construction host"),
        ("nonService", "serviceRoute"),
        ("missingService", "missing"),
        ("hostOverlap", "overlaps participant host.floor"),
        ("serviceOverlap", "overlaps host route.run"),
        ("invalidScopedHost", "scoped component reference"),
    ],
)
def test_interface_participants_and_material_conflicts_reject_invalid_models(
    reference_model: JsonObject, validator: ModelValidator, failure: str, expected: str
) -> None:
    """Semantic participants remain checked separately from mounting coordinates and physical cuts."""
    InterfaceFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    sleeve = Authoring.object(elements["part.sleeve"])
    interface = Authoring.object(sleeve["interface"])
    if failure == "missingInterface":
        del sleeve["interface"]
    elif failure == "missingHost":
        interface["host"] = {"element": "host.missing"}
    elif failure == "nonConstructionHost":
        interface["host"] = {"element": "route.run"}
    elif failure == "nonService":
        interface["services"] = [{"element": "host.floor"}]
    elif failure == "missingService":
        interface["services"] = [{"element": "route.missing"}]
    elif failure == "hostOverlap":
        del elements["cut.host"]
    elif failure == "serviceOverlap":
        del Authoring.object(Authoring.object(reference_model["types"])["type.sleeve"])[
            "cuts"
        ]
    else:
        interface["host"] = {"element": "host.floor", "part": "missing"}
    report = validator.validate(reference_model)
    assert not report.is_valid
    assert expected.lower() in str(report.to_dict()).lower()


def test_interface_host_can_reference_a_generated_member(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """The realizing connection names the surviving member rather than its assembly container."""
    InterfaceFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    types["type.beam"] = {
        "kind": "memberType",
        "name": "Illustrative beam",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 400, "depth": 100},
    }
    elements = Authoring.object(reference_model["elements"])
    elements["host.floor"] = {
        "kind": "memberAssembly",
        "name": "Host assembly",
        "assemblyType": "other",
        "placement": {"origin": {"point": [0, 0, 50]}},
        "nodes": {"left": {"local": [-200, 0, 0]}, "right": {"local": [200, 0, 0]}},
        "members": {
            "beam": {
                "start": "left",
                "end": "right",
                "memberType": "type.beam",
                "role": "beam",
            }
        },
    }
    for role in InterfaceFixture.ROLES:
        Authoring.object(Authoring.object(elements[f"part.{role}"])["interface"])[
            "host"
        ] = {"element": "host.floor", "part": "beam"}
    Authoring.object(elements["cut.host"])["limits"] = {
        "beamHole": {
            "host": {
                "kind": "member",
                "element": "host.floor",
                "part": "beam",
                "surface": "axis",
                "station": 200,
            },
            "maximumExtent": {"x": 80, "y": 100, "z": 80},
            "minimumEdgeDistance": {"positiveZ": 160, "negativeZ": 160},
        }
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    identity = Authoring.text(resolved.element("part.sleeve").data["interfaceHostId"])
    assert identity != "host.floor"
    output = tmp_path / "member-interface.ifc"
    IfcExporter().export(resolved, output)
    ifc = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert not logger.statements
    assert all(
        item.RelatingElement.Tag == identity
        for item in ifc.by_type("IfcRelConnectsWithRealizingElements")
    )
    broken = deepcopy(reference_model)
    Authoring.object(
        Authoring.object(Authoring.object(broken["elements"])["part.sleeve"])[
            "interface"
        ]
    )["host"] = {"element": "host.floor", "part": "missing"}
    assert not validator.validate(broken).is_valid
