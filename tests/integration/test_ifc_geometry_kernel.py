"""Independent IFC geometry-kernel conversion preserves final material volumes and placements."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import ifcopenshell.validate
import numpy as np
import pytest
import trimesh
from ifcopenshell.ifcopenshell_wrapper import TriangulationElement

from home_design.adapters.ifc import IfcExporter
from home_design.adapters.gltf import GltfExporter
from home_design.construction import Authoring
from home_design.json_types import JsonObject
from home_design.loader import ModelLoader
from home_design.resolved import ResolvedElement, ResolvedModel
from home_design.reports import ModelReports
from home_design.resolver import ModelResolver
from home_design.solids import SolidOperations
from home_design.validation import ModelValidator


class KernelFixture(IfcExporter):
    """Compare exported physical products independently of IFC face-list serialization."""

    EXCLUDED: frozenset[str] = frozenset(
        {
            "terrain",
            "space",
            "opening",
            "penetration",
            "clearanceZone",
            "barrierCheck",
            "load",
            "detail",
        }
    )

    @classmethod
    def physical_elements(cls, model: ResolvedModel) -> tuple[ResolvedElement, ...]:
        """Expose physical export inputs to compare each generated child without assembly duplication."""
        return tuple(
            element
            for element in cls._expanded_elements(model)
            if element.meshes and element.kind not in cls.EXCLUDED
        )

    @staticmethod
    def scene_and_schedule(
        model: ResolvedModel, native_volumes: dict[str, float], directory: Path
    ) -> None:
        """Verify one selectable scene owner per physical node and matching independent schedule quantities."""
        glb = directory / "scene.glb"
        manifest = GltfExporter().export(model, glb, directory / "manifest.json")
        scene = trimesh.load_scene(glb)
        entries = Authoring.object(manifest["elements"])
        rows = {
            Authoring.text(Authoring.object(value)["id"]): Authoring.object(value)
            for value in Authoring.array(ModelReports(model).schedules()["components"])
        }
        owners: dict[str, str] = {}
        resolved_elements = {element.element_id: element for element in model.elements}
        for identity, volume in native_volumes.items():
            assert rows[identity]["volumeM3"] == pytest.approx(
                volume, rel=1e-7, abs=1e-9
            )
            entry = Authoring.object(entries[identity])
            nodes = Authoring.array(entry["nodes"])
            assert nodes
            scene_volume = 0.0
            source_meshes = [
                mesh
                for mesh in resolved_elements[identity].meshes
                if mesh.role != "void"
            ]
            assert len(nodes) == len(source_meshes)
            for value, source_mesh in zip(nodes, source_meshes):
                node = Authoring.text(value)
                assert node not in owners
                owners[node] = identity
                transform, geometry = scene.graph[node]
                mesh = scene.geometry[geometry].copy()
                assert isinstance(mesh, trimesh.Trimesh)
                mesh.apply_transform(transform)
                scene_volume += abs(float(mesh.volume))
                assert mesh.metadata["homeDesignId"] == identity
                expected_points = np.asarray(
                    [
                        (x / 1000, z / 1000, -y / 1000)
                        for x, y, z in source_mesh.vertices
                    ]
                )
                assert mesh.bounds == pytest.approx(
                    np.asarray(
                        [expected_points.min(axis=0), expected_points.max(axis=0)]
                    ),
                    abs=1e-6,
                )
            # GLB vertices store float32 coordinates, unlike IFC's decimal doubles.
            assert scene_volume == pytest.approx(volume, rel=5e-5, abs=1e-9), identity

    @staticmethod
    def cut_member(model: JsonObject) -> None:
        """Use a slanted member whose two end trims change its original stock geometry."""
        model["relationships"], model["requirements"], model["solarStudies"] = (
            {},
            [],
            [],
        )
        Authoring.object(model["types"])["type.stock"] = {
            "kind": "memberType",
            "name": "Oblique trimmed stock",
            "material": "material.timber",
            "section": {"kind": "rectangle", "width": 100, "depth": 50},
        }
        model["elements"] = {
            "member.cut": {
                "kind": "member",
                "name": "Trimmed beam",
                "type": "type.stock",
                "role": "beam",
                "axis": [{"point": [500, 600, 700]}, {"point": [1100, 1400, 1700]}],
                "endCuts": {
                    "start": {"normal": [0, 0, 1], "offset": 100},
                    "end": {"normal": [0, 0, -1], "offset": 200},
                },
            }
        }


@pytest.mark.parametrize(
    "case",
    [
        "single-story-gable-house",
        "hillside-deck-house",
        "complete-shell-coordination-house",
        "trimmed-member",
    ],
)
def test_kernel_preserves_material_volume_and_world_extents(
    case: str, reference_model: JsonObject, validator: ModelValidator, tmp_path: Path
) -> None:
    """Native conversion preserves cuts, layered stock, sloped roofs and individually placed framing."""
    if case == "trimmed-member":
        source = reference_model
        KernelFixture.cut_member(source)
    else:
        source = ModelLoader().load(
            Path(__file__).resolve().parents[2] / "examples" / f"{case}.json"
        )
    report = validator.validate(source)
    assert report.is_valid, report.to_dict()
    resolved = ModelResolver(source).resolve()
    output = tmp_path / "kernel.ifc"
    IfcExporter().export(resolved, output)
    native = ifcopenshell.open(output)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(native, logger)
    assert not logger.statements
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    checked: set[str] = set()
    owner_volumes: dict[str, float] = {}
    for element in KernelFixture.physical_elements(resolved):
        product = native.by_guid(IfcExporter.stable_guid(element.element_id))
        shape = ifcopenshell.geom.create_shape(settings, product)
        assert isinstance(shape, TriangulationElement)
        volume = ifcopenshell.util.shape.get_volume(shape.geometry)
        expected = sum(SolidOperations.volume(mesh) for mesh in element.meshes) / 1e9
        assert volume == pytest.approx(expected, rel=1e-7, abs=1e-9), element.element_id
        actual_vertices = ifcopenshell.util.shape.get_vertices(shape.geometry)
        expected_vertices = (
            np.asarray([vertex for mesh in element.meshes for vertex in mesh.vertices])
            / 1000
        )
        assert actual_vertices.min(axis=0) == pytest.approx(
            expected_vertices.min(axis=0), abs=1e-7
        )
        assert actual_vertices.max(axis=0) == pytest.approx(
            expected_vertices.max(axis=0), abs=1e-7
        )
        checked.add(element.element_id)
        owner = Authoring.text(element.data.get("generatedFrom", element.element_id))
        owner_volumes[owner] = owner_volumes.get(owner, 0) + volume
    KernelFixture.scene_and_schedule(resolved, owner_volumes, tmp_path)
    if case == "trimmed-member":
        assert checked == {"member.cut"}
    else:
        assert {"wall.south", "roof.main"}.issubset(checked)
