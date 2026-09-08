"""Public assembly coordination across framing, mounted services and sealed interfaces."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
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


class ShellFixture:
    """Load the distributable example with its own authored component and service relationships."""

    @staticmethod
    def load() -> JsonObject:
        """Read the public canonical model independently for each regression."""
        return ModelLoader().load(
            Path(__file__).resolve().parents[2] / "examples" / "assemblies.json"
        )


def test_public_shell_has_physical_framing_services_and_deterministic_scene(
    tmp_path: Path, validator: ModelValidator
) -> None:
    """The example contains the advertised families and repeated resolution produces identical selectable geometry."""
    model = ShellFixture.load()
    report = validator.validate(model)
    assert report.is_valid, report.to_dict()
    first, second = ModelResolver(model).resolve(), ModelResolver(model).resolve()
    assert first.to_dict() == second.to_dict()
    for identity in (
        "assembly.exterior-wall.framing.wall",
        "assembly.interior-wet-wall.framing.partition",
        "assembly.insulated-floor.framing.joists",
        "assembly.complete-deck.framing.joists",
        "assembly.insulated-roof.rafters.south",
        "assembly.insulated-roof.rafters.north",
    ):
        assert first.element(identity).data["memberCount"]
    schedules = ModelReports(first).schedules()
    assert len(Authoring.array(schedules["foundations"])) == 13
    assert len(Authoring.array(schedules["circuitSchedules"])) == 1
    assert {
        "serviceDevices",
        "serviceRoutes",
        "serviceFittings",
        "serviceInsulation",
        "hardware",
        "accessories",
        "penetrations",
    }.issubset(schedules)
    for category in (
        "serviceDevices",
        "serviceRoutes",
        "serviceFittings",
        "serviceInsulation",
        "hardware",
        "accessories",
        "penetrations",
    ):
        assert Authoring.array(schedules[category])
    first_scene = GltfExporter().export(
        first, tmp_path / "first.glb", tmp_path / "first.json"
    )
    second_scene = GltfExporter().export(
        second, tmp_path / "second.glb", tmp_path / "second.json"
    )
    assert first_scene == second_scene
    assert (tmp_path / "first.glb").read_bytes() == (
        tmp_path / "second.glb"
    ).read_bytes()


def test_partition_rotation_coordinates_branches_cuts_and_native_identity(
    tmp_path: Path, loader: ModelLoader, validator: ModelValidator
) -> None:
    """A wet-wall rotation carries plumbing, sleeve seals and a ledge while preserving quantities and identities."""
    model = ShellFixture.load()
    engine = ChangeEngine(loader, validator)
    changed = engine.apply(
        model,
        engine.load_change(
            Path(__file__).resolve().parents[2]
            / "examples/change-sets/rotate-service-partition.json"
        ),
    )
    before, after = ModelResolver(model).resolve(), ModelResolver(changed).resolve()
    identities = {element.element_id for element in before.elements}
    assert identities == {element.element_id for element in after.elements}
    for identity in identities:
        old, new = before.element(identity), after.element(identity)
        if old.meshes and identity not in {"space.living"}:
            assert sum(
                SolidOperations.volume(mesh) for mesh in old.meshes
            ) == pytest.approx(
                sum(SolidOperations.volume(mesh) for mesh in new.meshes),
                rel=1e-7,
                abs=1e-5,
            ), identity
    assert (
        before.element("assembly.interior-wet-wall.plumbing.pipe.supply").data["path"]
        != after.element("assembly.interior-wet-wall.plumbing.pipe.supply").data["path"]
    )
    assert (
        before.element("assembly.ventilation-branch.mechanical.device.ahu").meshes
        == after.element("assembly.ventilation-branch.mechanical.device.ahu").meshes
    )
    old_schedules, new_schedules = (
        ModelReports(before).schedules(),
        ModelReports(after).schedules(),
    )
    assert [
        number(Authoring.object(row)["routeLengthMm"], "circuit length")
        for row in Authoring.array(old_schedules["circuitSchedules"])
    ] == pytest.approx(
        [
            number(Authoring.object(row)["routeLengthMm"], "circuit length")
            for row in Authoring.array(new_schedules["circuitSchedules"])
        ]
    )
    roots: list[set[str]] = []
    for name, resolved in (("before", before), ("after", after)):
        path = tmp_path / f"{name}.ifc"
        IfcExporter().export(resolved, path)
        native = ifcopenshell.open(path)
        roots.append({entity.GlobalId for entity in native.by_type("IfcRoot")})
    assert roots[0] == roots[1]


@pytest.mark.parametrize(
    "failure,code",
    [("limit", "penetration.limit-violated"), ("obstacle", "service.interference")],
)
def test_public_shell_reports_specific_coordination_failures(
    failure: str, code: str, validator: ModelValidator
) -> None:
    """Authored opening limits and new physical obstructions produce actionable diagnostics."""
    model = ShellFixture.load()
    elements = Authoring.object(model["elements"])
    if failure == "limit":
        cut = Authoring.object(
            elements["assembly.interior-wet-wall.interface.cut.partition"]
        )
        limit = Authoring.object(Authoring.object(cut["limits"])["authoredOpening"])
        Authoring.object(limit["maximumExtent"])["x"] = 30
    else:
        elements["member.obstruction"] = {
            "kind": "member",
            "name": "New service obstruction",
            "type": "assembly.interior-wet-wall.memberType.shell.stud",
            "role": "brace",
            "axis": [
                {
                    "host": {
                        "kind": "route",
                        "element": "assembly.interior-wet-wall.plumbing.pipe.supply",
                        "station": station,
                    }
                }
                for station in (100, 200)
            ],
        }
    report = validator.validate(model)
    assert not report.is_valid
    assert code in {diagnostic.code for diagnostic in report.diagnostics}
