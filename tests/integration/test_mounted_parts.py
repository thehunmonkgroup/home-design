"""Physical hosted accessories, envelope seams and nonmaterial coordination exports."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
import pytest

from home_design.adapters.ifc import IfcExporter
from home_design.build import BuildService
from home_design.fabrication import FabricationGeometry
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solar import SolarAnalysis
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class MountedFixture:
    """Author isolated illustrative wall-mounted parts using public material definitions."""

    @staticmethod
    def configure(model: JsonObject) -> None:
        """Use one unjoined wall with predictable millimetre geometry."""
        model["relationships"] = {}
        model["requirements"] = []
        model["solarStudies"] = []
        model["elements"] = {
            "wall.host": {
                "kind": "wall",
                "name": "Mounting wall",
                "storey": "level.ground",
                "type": "wallType.exterior.wood-185",
                "locationLine": "center",
                "path": {
                    "kind": "line",
                    "start": {"point": [0, 0]},
                    "end": {"point": [4000, 0]},
                },
                "base": {"kind": "level", "level": "level.ground", "offset": 0},
                "top": {"kind": "height", "height": 2700},
            }
        }
        Authoring.object(model["types"])["type.shelf"] = {
            "kind": "accessoryType",
            "name": "Timber ledge",
            "role": "shelf",
            "material": "material.timber",
            "solids": {
                "board": {
                    "section": {"kind": "rectangle", "width": 600, "depth": 100},
                    "depth": 200,
                }
            },
        }
        Authoring.object(model["elements"])["accessory.shelf"] = {
            "kind": "accessory",
            "name": "Mounted ledge",
            "type": "type.shelf",
            "placement": {
                "origin": {
                    "host": {
                        "kind": "wall",
                        "element": "wall.host",
                        "surface": "interior",
                        "station": 2000,
                        "height": 1000,
                    }
                }
            },
        }

    @staticmethod
    def access(model: JsonObject) -> JsonObject:
        """Reserve the space immediately in front of the ledge."""
        zone: JsonObject = {
            "kind": "clearanceZone",
            "name": "Ledge access",
            "owner": "accessory.shelf",
            "purpose": "maintenance",
            "placement": {
                "origin": {"host": {"kind": "component", "element": "accessory.shelf"}}
            },
            "geometry": {
                "section": {"kind": "rectangle", "width": 500, "depth": 100},
                "depth": 100,
                "placement": {"origin": [0, 0, 200]},
            },
        }
        Authoring.object(model["elements"])["zone.access"] = zone
        return zone

    @staticmethod
    def membranes(model: JsonObject) -> JsonObject:
        """Join two thin weather sheets with a probe straddling their seam."""
        Authoring.object(model["types"])["type.membrane"] = {
            "kind": "envelopePartType",
            "name": "Illustrative weather sheet",
            "role": "membrane",
            "material": "material.timber",
            "solids": {
                "sheet": {
                    "section": {"kind": "rectangle", "width": 100, "depth": 200},
                    "depth": 1,
                }
            },
        }
        elements = Authoring.object(model["elements"])
        for name, station in (("left", 1000), ("right", 1100)):
            elements[f"envelope.{name}"] = {
                "kind": "envelopePart",
                "name": f"Sheet {name}",
                "type": "type.membrane",
                "placement": {
                    "origin": {
                        "host": {
                            "kind": "wall",
                            "element": "wall.host",
                            "surface": "exterior",
                            "station": station,
                            "height": 1000,
                        }
                    }
                },
            }
        check: JsonObject = {
            "kind": "barrierCheck",
            "name": "Weather seam",
            "purpose": "water",
            "placement": {
                "origin": {
                    "host": {
                        "kind": "wall",
                        "element": "wall.host",
                        "surface": "exterior",
                        "station": 1050,
                        "height": 1000,
                    }
                }
            },
            "geometry": {
                "section": {"kind": "rectangle", "width": 20, "depth": 100},
                "depth": 1,
            },
            "participants": [
                {"element": "envelope.left"},
                {"element": "envelope.right"},
            ],
        }
        elements["check.seam"] = check
        return check

    @staticmethod
    def mount(source: JsonObject) -> JsonObject:
        """Return the authored host frame for a mounted element."""
        return Authoring.object(
            Authoring.object(Authoring.object(source["placement"])["origin"])["host"]
        )


def test_tapered_boot_follows_sloped_roof_and_exports_covering(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """A hollow tapered roof boot and flange remain normal to their edited roof surface."""
    MountedFixture.configure(reference_model)
    elements = Authoring.object(reference_model["elements"])
    elements["roof.host"] = {
        "kind": "roof",
        "name": "Sloping roof",
        "storey": "level.ground",
        "type": "roofType.shingle-250",
        "geometry": {
            "kind": "faceSet",
            "faces": [
                {
                    "id": "face.slope",
                    "boundary": {
                        "outer": [
                            [0, 0, 3000],
                            [4000, 0, 3000],
                            [4000, 4000, 5000],
                            [0, 4000, 5000],
                        ]
                    },
                }
            ],
        },
    }
    boot: JsonObject = {
        "kind": "envelopePartType",
        "name": "Tapered boot with flange",
        "role": "roofBoot",
        "material": "material.timber",
        "solids": {
            "boot": {
                "kind": "revolve",
                "profile": {
                    "outer": [
                        [40, 0],
                        [150, 0],
                        [150, 3],
                        [80, 3],
                        [45, 120],
                        [42, 120],
                        [77, 3],
                        [40, 3],
                    ]
                },
                "chordTolerance": 0.1,
            }
        },
    }
    Authoring.object(reference_model["types"])["type.boot"] = boot
    elements["envelope.boot"] = {
        "kind": "envelopePart",
        "name": "Roof boot",
        "type": "type.boot",
        "placement": {
            "origin": {
                "host": {
                    "kind": "surface",
                    "element": "roof.host",
                    "surface": "top",
                    "face": "face.slope",
                    "point": [2000, 2000],
                }
            }
        },
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    before = ModelResolver(reference_model).resolve().element("envelope.boot")
    assert before.data["mountingRangeMm"] == pytest.approx([0, 120])
    assert before.data["netVolumeMm3"] == pytest.approx(
        SolidOperations.volume(FabricationGeometry.resolve(boot))
    )
    frame = Authoring.object(before.data["placement"])
    assert Authoring.array(frame["z"])[1] == pytest.approx(-1 / 5**0.5)
    model_file = tmp_path / "boot.json"
    model_file.write_text(json.dumps(reference_model), encoding="utf-8")
    result = BuildService().build(model_file, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    product = ifc.by_guid(IfcExporter.stable_guid("envelope.boot"))
    assert product.is_a("IfcCovering")
    assert product.IsTypedBy[0].RelatingType.ElementType == "roofBoot"
    roof = Authoring.object(elements["roof.host"])
    faces = Authoring.array(Authoring.object(roof["geometry"])["faces"])
    Authoring.object(Authoring.object(faces[0])["boundary"])["outer"] = [
        [0, 0, 3000],
        [4000, 0, 3000],
        [4000, 4000, 7000],
        [0, 4000, 7000],
    ]
    after = ModelResolver(reference_model).resolve().element("envelope.boot")
    assert Authoring.array(Authoring.object(after.data["placement"])["z"])[
        1
    ] == pytest.approx(-1 / 2**0.5)
    assert after.data["netVolumeMm3"] == pytest.approx(before.data["netVolumeMm3"])


def test_hosted_ledge_projection_and_access_follow_wall_edits(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Real board extents and a following access volume retain their offsets after a host move."""
    MountedFixture.configure(reference_model)
    MountedFixture.access(reference_model)
    elements = Authoring.object(reference_model["elements"])
    shelf = Authoring.object(elements["accessory.shelf"])
    shelf["projection"] = 25
    assert validator.validate(reference_model).is_valid
    first = ModelResolver(reference_model).resolve()
    assert first.element("accessory.shelf").data["mountingRangeMm"] == pytest.approx(
        [25, 225]
    )
    assert first.element("accessory.shelf").data["netVolumeMm3"] == pytest.approx(
        12_000_000
    )
    assert first.element("zone.access").data["status"] == "clear"
    Authoring.object(Authoring.object(elements["wall.host"])["base"])["offset"] = 300
    second = ModelResolver(reference_model).resolve()
    for key in ("accessory.shelf", "zone.access"):
        before = first.element(key).meshes[0].vertices
        after = second.element(key).meshes[0].vertices
        assert [point[2] for point in after] == pytest.approx(
            [point[2] + 300 for point in before]
        )


def test_recessed_niche_requires_and_owns_real_wall_cut(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A lined recess removes wall material while keeping the accessory's lining volume."""
    MountedFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    types["type.shelf"] = {
        "kind": "accessoryType",
        "name": "Niche liner",
        "role": "niche",
        "material": "material.timber",
        "solids": {
            "stock": {
                "section": {"kind": "rectangle", "width": 600, "depth": 400},
                "depth": 80,
                "placement": {"origin": [0, 0, -80]},
            }
        },
        "cuts": {
            "recess": {
                "section": {"kind": "rectangle", "width": 560, "depth": 360},
                "depth": 60,
                "placement": {"origin": [0, 0, -60]},
            }
        },
    }
    report = validator.validate(reference_model)
    assert any("overlaps host" in item.message for item in report.errors)
    elements = Authoring.object(reference_model["elements"])
    elements["cut.niche"] = {
        "kind": "penetration",
        "name": "Owned niche recess",
        "host": "wall.host",
        "owner": "accessory.shelf",
        "purpose": "recess",
        "section": {"kind": "rectangle", "width": 600, "depth": 400},
        "depth": 80,
        "placement": {
            "origin": {"host": {"kind": "component", "element": "accessory.shelf"}},
            "rotation": [180, 0, 0],
        },
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    result = ModelResolver(reference_model).resolve()
    niche = result.element("accessory.shelf")
    assert niche.data["mountingRangeMm"] == pytest.approx([-80, 0])
    assert niche.data["netVolumeMm3"] == pytest.approx(600 * 400 * 80 - 560 * 360 * 60)
    assert sum(
        SolidOperations.volume(mesh) for mesh in result.element("wall.host").meshes
    ) == pytest.approx(4000 * 2700 * 185 - 600 * 400 * 80)


def test_hosted_backing_owns_only_its_physical_cavity_volume(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """Recessed backing displaces host infill once and retains the mounting storey."""
    MountedFixture.configure(reference_model)
    types = Authoring.object(reference_model["types"])
    wall_type = Authoring.object(types["wallType.exterior.wood-185"])
    layer = Authoring.object(Authoring.array(wall_type["layers"])[2])
    layer["representation"] = "explicit"
    shelf_type = Authoring.object(types["type.shelf"])
    shelf_type["role"] = "backing"
    Authoring.object(Authoring.object(shelf_type["solids"])["board"])["depth"] = 40
    shelf = Authoring.object(
        Authoring.object(reference_model["elements"])["accessory.shelf"]
    )
    mount = MountedFixture.mount(shelf)
    mount["surface"] = "layerInterior"
    mount["layer"] = 2
    Authoring.object(shelf["placement"])["rotation"] = [180, 0, 0]
    shelf["occupies"] = {"regions": [{"host": "wall.host", "layer": 2}]}
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve()
    backing = resolved.element("accessory.shelf")
    assert backing.storey_id == "level.ground"
    assert backing.data["mountingRangeMm"] == pytest.approx([-40, 0])
    assert backing.data["netVolumeMm3"] == pytest.approx(600 * 100 * 40)
    assert sum(
        SolidOperations.volume(mesh)
        for element in resolved.elements
        for mesh in element.meshes
    ) == pytest.approx(4000 * 2700 * 185)
    del shelf["occupies"]
    assert not validator.validate(reference_model).is_valid


def test_barrier_probe_selects_existing_host_layers(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A local interface check can span two adjacent physical layers of the same host."""
    MountedFixture.configure(reference_model)
    check: JsonObject = {
        "kind": "barrierCheck",
        "name": "Layer interface",
        "purpose": "acoustic",
        "placement": {
            "origin": {
                "host": {
                    "kind": "wall",
                    "element": "wall.host",
                    "surface": "interior",
                    "station": 1000,
                    "height": 1000,
                    "offset": [0, 0, -20],
                }
            }
        },
        "geometry": {
            "section": {"kind": "rectangle", "width": 20, "depth": 100},
            "depth": 20,
        },
        "participants": [
            {"element": "wall.host", "layer": 2},
            {"element": "wall.host", "layer": 3},
        ],
    }
    Authoring.object(reference_model["elements"])["check.layers"] = check
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(reference_model).resolve().element("check.layers")
    assert resolved.data["coverageFraction"] == pytest.approx(1)
    assert resolved.data["status"] == "continuous"
    check["participants"] = [
        {"element": "wall.host", "layer": 2},
        {"element": "wall.host", "layer": 20},
    ]
    assert any(
        "no layer 20" in item.message
        for item in validator.validate(reference_model).errors
    )
    check["participants"] = [
        {"element": "wall.host", "layer": 2},
        {"element": "wall.host"},
    ]
    assert any(
        "require an envelope part" in item.message
        for item in validator.validate(reference_model).errors
    )


def test_access_obstructions_have_explicit_exceptions_and_severity(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """An owner is excluded but a separate projecting component blocks its maintenance volume."""
    MountedFixture.configure(reference_model)
    zone = MountedFixture.access(reference_model)
    elements = Authoring.object(reference_model["elements"])
    obstruction = deepcopy(Authoring.object(elements["accessory.shelf"]))
    obstruction["projection"] = 250
    elements["accessory.obstruction"] = obstruction
    report = validator.validate(reference_model)
    assert [item.code for item in report.errors] == ["access.obstructed"]
    resolved = ModelResolver(reference_model).resolve()
    assert resolved.element("zone.access").data["obstructions"] == [
        {"element": "accessory.obstruction", "volumeMm3": pytest.approx(2_500_000)}
    ]
    zone["severity"] = "warning"
    report = validator.validate(reference_model)
    assert report.is_valid
    assert any(
        item.code == "access.obstructed" and item.severity == "warning"
        for item in report.diagnostics
    )
    zone["allow"] = [{"element": "accessory.obstruction"}]
    assert (
        ModelResolver(reference_model).resolve().element("zone.access").data["status"]
        == "clear"
    )


def test_barrier_seam_detects_missing_material_and_duplicate_ownership(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A probe measures actual contact and gap volume between declared thin sheets."""
    MountedFixture.configure(reference_model)
    check = MountedFixture.membranes(reference_model)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    first = ModelResolver(reference_model).resolve().element("check.seam")
    assert first.data["status"] == "continuous"
    assert first.data["connectedRegions"] == 1
    right = Authoring.object(
        Authoring.object(reference_model["elements"])["envelope.right"]
    )
    MountedFixture.mount(right)["station"] = 1105
    report = validator.validate(reference_model)
    assert [item.code for item in report.errors] == ["barrier.discontinuous"]
    gap = ModelResolver(reference_model).resolve().element("check.seam")
    assert gap.data["gapVolumeMm3"] == pytest.approx(500)
    assert gap.data["connectedRegions"] == 2
    check["maximumGapVolumeMm3"] = 600
    assert not validator.validate(reference_model).is_valid
    MountedFixture.mount(right)["station"] = 1095
    report = validator.validate(reference_model)
    assert any("duplicate physical material" in item.message for item in report.errors)


def test_access_exceptions_and_mounts_resolve_individual_assembly_members(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Allowing one post preserves the other obstruction and IFC mounts identify the actual child."""
    MountedFixture.configure(reference_model)
    zone = MountedFixture.access(reference_model)
    types = Authoring.object(reference_model["types"])
    types["type.post"] = {
        "kind": "memberType",
        "name": "Small post",
        "material": "material.timber",
        "section": {"kind": "rectangle", "width": 40, "depth": 40},
    }
    types["type.panel"] = {
        "kind": "accessoryType",
        "name": "Access panel",
        "role": "accessPanel",
        "material": "material.timber",
        "solids": {
            "panel": {
                "section": {"kind": "rectangle", "width": 20, "depth": 20},
                "depth": 5,
            }
        },
    }
    elements = Authoring.object(reference_model["elements"])
    elements["assembly.posts"] = {
        "kind": "memberAssembly",
        "name": "Independent support posts",
        "assemblyType": "other",
        "storey": "level.ground",
        "placement": {"origin": {"point": [1900, -340, 950]}},
        "nodes": {
            "leftBase": {"local": [0, 0, 0]},
            "leftTop": {"local": [0, 0, 100]},
            "rightBase": {"local": [200, 0, 0]},
            "rightTop": {"local": [200, 0, 100]},
        },
        "members": {
            "left": {
                "start": "leftBase",
                "end": "leftTop",
                "memberType": "type.post",
                "role": "column",
            },
            "right": {
                "start": "rightBase",
                "end": "rightTop",
                "memberType": "type.post",
                "role": "column",
            },
        },
    }
    zone["allow"] = [{"element": "assembly.posts", "part": "left"}]
    result = ModelResolver(reference_model).resolve().element("zone.access")
    assert result.data["obstructions"] == [
        {"element": "assembly.posts/member/right", "volumeMm3": pytest.approx(160_000)}
    ]
    zone["allow"] = [{"element": "assembly.posts", "part": "absent"}]
    assert not validator.validate(reference_model).is_valid
    del elements["zone.access"]
    elements["accessory.panel"] = {
        "kind": "accessory",
        "name": "Mounted access panel",
        "type": "type.panel",
        "placement": {
            "origin": {
                "host": {
                    "kind": "member",
                    "element": "assembly.posts",
                    "part": "left",
                    "surface": "positiveX",
                    "station": 50,
                }
            }
        },
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    source = tmp_path / "scoped.json"
    source.write_text(json.dumps(reference_model), encoding="utf-8")
    result = BuildService().build(source, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    relation = ifc.by_guid(IfcExporter.stable_guid("rel.mount.accessory.panel"))
    assert relation.RelatingElement.Tag == "assembly.posts/member/left"
    assert relation.RelatedElement.Tag == "accessory.panel"


def test_flashing_return_uses_shaped_probe_across_a_fold(
    reference_model: JsonObject, validator: ModelValidator
) -> None:
    """A right-angle return and a flat sheet meet through a shaped physical seam."""
    MountedFixture.configure(reference_model)
    MountedFixture.membranes(reference_model)
    elements = Authoring.object(reference_model["elements"])
    types = Authoring.object(reference_model["types"])
    return_type = deepcopy(Authoring.object(types["type.membrane"]))
    return_type["role"] = "flashing"
    return_type["name"] = "Folded flashing return"
    sheet = Authoring.object(Authoring.object(return_type["solids"])["sheet"])
    sheet["placement"] = {"origin": [50, 0, 50], "rotation": [0, 90, 0]}
    types["type.return"] = return_type
    right = Authoring.object(elements["envelope.right"])
    right["type"] = "type.return"
    MountedFixture.mount(right)["station"] = 1000
    check = Authoring.object(elements["check.seam"])
    MountedFixture.mount(check)["station"] = 1000
    check["geometry"] = {
        "section": {
            "kind": "profile",
            "profile": {
                "outer": [[49, 0], [51, 0], [51, 2], [50, 2], [50, 1], [49, 1]]
            },
        },
        "depth": 100,
        "placement": {"origin": [0, 50, 0], "rotation": [90, 0, 0]},
    }
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    assert (
        ModelResolver(reference_model).resolve().element("check.seam").data["status"]
        == "continuous"
    )
    Authoring.object(sheet["placement"])["origin"] = [50.5, 0, 50]
    assert any(
        item.code == "barrier.discontinuous"
        for item in validator.validate(reference_model).errors
    )


def test_mounted_parts_and_coordination_export_native_ifc_without_extra_material(
    reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Full builds retain mount/owner links, typed solids and hidden nonphysical probes."""
    MountedFixture.configure(reference_model)
    MountedFixture.membranes(reference_model)
    MountedFixture.access(reference_model)
    report = validator.validate(reference_model)
    assert report.is_valid, report.to_dict()
    model_file = tmp_path / "mounted.json"
    model_file.write_text(json.dumps(reference_model), encoding="utf-8")
    result = BuildService().build(model_file, tmp_path / "build")
    ifc = ifcopenshell.open(result.ifc_model)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(ifc, logger)
    assert logger.statements == []
    shelf = ifc.by_guid(IfcExporter.stable_guid("accessory.shelf"))
    assert shelf.is_a("IfcBuildingElementPart")
    assert shelf.IsTypedBy[0].RelatingType.ElementType == "shelf"
    membrane = ifc.by_guid(IfcExporter.stable_guid("envelope.left"))
    assert membrane.is_a("IfcCovering")
    assert membrane.IsTypedBy[0].RelatingType.PredefinedType == "MEMBRANE"
    mount = ifc.by_guid(IfcExporter.stable_guid("rel.mount.accessory.shelf"))
    assert mount.RelatingElement.Tag == "wall.host"
    assert mount.RelatedElement == shelf
    zone = ifc.by_guid(IfcExporter.stable_guid("zone.access"))
    assert zone.is_a("IfcVirtualElement")
    assert not any(
        relation.RelatingPropertyDefinition.is_a("IfcElementQuantity")
        for relation in zone.IsDefinedBy
    )
    assert any(relation.RelatingProduct == shelf for relation in zone.HasAssignments)
    manifest = json.loads(result.render_manifest.read_text())
    assert manifest["elements"]["zone.access"]["defaultVisible"] is False
    assert manifest["elements"]["check.seam"]["defaultVisible"] is False
    full = ModelResolver(reference_model).resolve()
    elements = Authoring.object(reference_model["elements"])
    del elements["zone.access"]
    del elements["check.seam"]
    physical = ModelResolver(reference_model).resolve()
    assert (
        ModelReports(full).schedules()["materials"]
        == ModelReports(physical).schedules()["materials"]
    )
    assert (
        ModelReports(full).envelope()["shadingGeometry"]
        == ModelReports(physical).envelope()["shadingGeometry"]
    )
    for model in (full, physical):
        occluder = SolarAnalysis(model).occluder
        assert not occluder.blocked((2000, -350, 1000), (0, -1, 0))
        assert occluder.blocked((2000, -350, 1000), (0, 1, 0))


@pytest.mark.parametrize(
    "failure",
    [
        "missing_owner",
        "missing_participant",
        "wrong_type",
        "cycle",
        "invalid_component_host",
        "empty_probe_allowance",
    ],
)
def test_invalid_mounted_and_coordination_references_are_diagnostic(
    reference_model: JsonObject, validator: ModelValidator, failure: str
) -> None:
    """Malformed dependencies fail through supported validation rather than exporter errors."""
    MountedFixture.configure(reference_model)
    zone = MountedFixture.access(reference_model)
    check = MountedFixture.membranes(reference_model)
    elements = Authoring.object(reference_model["elements"])
    shelf = Authoring.object(elements["accessory.shelf"])
    if failure == "missing_owner":
        zone["owner"] = "missing"
    elif failure == "missing_participant":
        check["participants"] = [{"element": "envelope.left"}, {"element": "missing"}]
    elif failure == "wrong_type":
        shelf["type"] = "type.membrane"
    elif failure == "cycle":
        shelf["placement"] = {
            "origin": {"host": {"kind": "component", "element": "zone.access"}}
        }
    elif failure == "invalid_component_host":
        zone["placement"] = {
            "origin": {"host": {"kind": "component", "element": "wall.host"}}
        }
    else:
        check["maximumGapVolumeMm3"] = 2000
    assert not validator.validate(reference_model).is_valid
