"""glTF/GLB export for the Three.js inspection client."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import trimesh
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial

from home_design.errors import ExportError
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import MeshData, ResolvedModel


class GltfExporter:
    """Export resolved meshes with stable, selectable node names."""

    def export(
        self, model: ResolvedModel, glb_path: Path, manifest_path: Path
    ) -> JsonObject:
        """Write a binary glTF scene and its element manifest.

        :param model: Adapter-neutral resolved model.
        :param glb_path: Destination GLB path.
        :param manifest_path: Destination JSON manifest path.
        :returns: Manifest mapping.
        :raises ExportError: If serialization fails.
        """
        scene = trimesh.Scene(base_frame="home-design-root")
        materials = self._materials(model.materials)
        element_entries: dict[str, JsonValue] = {}
        for element in model.elements:
            node_names: list[JsonValue] = []
            visible_meshes = [mesh for mesh in element.meshes if mesh.role != "void"]
            for index, mesh_data in enumerate(visible_meshes):
                node_name = self._node_name(
                    element.element_id, index, len(visible_meshes)
                )
                mesh = self._mesh(mesh_data, materials)
                mesh.metadata = {
                    "homeDesignId": element.element_id,
                    "kind": element.kind,
                    "role": mesh_data.role,
                }
                scene.add_geometry(mesh, node_name=node_name, geom_name=node_name)
                node_names.append(node_name)
            element_entries[element.element_id] = {
                "kind": element.kind,
                "name": element.name,
                "storeyId": element.storey_id,
                "nodes": node_names,
                "defaultVisible": element.kind != "space",
                "data": element.data,
            }
        manifest: JsonObject = {
            "format": "home-design-render-manifest-0.1",
            "modelVersion": model.model_version,
            "sourceRevision": model.source_revision,
            "project": {
                "id": model.project.get("id"),
                "name": model.project.get("name"),
            },
            "coordinateTransform": {
                "source": "right-handed Z-up millimetres",
                "target": "right-handed Y-up metres",
                "mapping": ["x/1000", "z/1000", "-y/1000"],
            },
            "elements": element_entries,
        }
        try:
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            exported = scene.export(file_type="glb")
            if not isinstance(exported, bytes):
                raise ExportError("Trimesh did not return a binary GLB payload")
            glb_path.write_bytes(exported)
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
        except (OSError, ValueError) as error:
            raise ExportError(f"Cannot export GLB scene: {error}") from error
        return manifest

    @staticmethod
    def _mesh(
        mesh_data: MeshData, materials: dict[str, PBRMaterial]
    ) -> trimesh.Trimesh:
        vertices = np.array(
            [(x / 1000.0, z / 1000.0, -y / 1000.0) for x, y, z in mesh_data.vertices],
            dtype=np.float64,
        )
        faces = np.array(mesh_data.faces, dtype=np.int64)
        mesh = trimesh.Trimesh(
            vertices=vertices, faces=faces, process=False, validate=False
        )
        material = materials.get(mesh_data.material_id or "")
        if mesh_data.role == "space":
            material = PBRMaterial(
                name="Space", baseColorFactor=[90, 170, 210, 35], roughnessFactor=1.0
            )
        elif mesh_data.role == "window-glass":
            material = PBRMaterial(
                name="Glass",
                baseColorFactor=[135, 205, 225, 90],
                metallicFactor=0.05,
                roughnessFactor=0.15,
                alphaMode="BLEND",
            )
        if material is not None:
            mesh.visual = TextureVisuals(material=material)
        return mesh

    @staticmethod
    def _materials(materials: JsonObject) -> dict[str, PBRMaterial]:
        result: dict[str, PBRMaterial] = {}
        for material_id, value in materials.items():
            if not isinstance(value, dict):
                continue
            appearance = value.get("appearance")
            appearance = appearance if isinstance(appearance, dict) else {}
            color = str(appearance.get("color", "#B8B4AC"))
            opacity_value = appearance.get("opacity", 1.0)
            opacity = (
                float(opacity_value) if isinstance(opacity_value, (int, float)) else 1.0
            )
            roughness_value = appearance.get("roughness", 0.8)
            roughness = (
                float(roughness_value)
                if isinstance(roughness_value, (int, float))
                else 0.8
            )
            metalness_value = appearance.get("metalness", 0.0)
            metalness = (
                float(metalness_value)
                if isinstance(metalness_value, (int, float))
                else 0.0
            )
            rgba = [int(color[index : index + 2], 16) for index in (1, 3, 5)] + [
                round(opacity * 255)
            ]
            result[material_id] = PBRMaterial(
                name=str(value.get("name", material_id)),
                baseColorFactor=rgba,
                roughnessFactor=roughness,
                metallicFactor=metalness,
                alphaMode="BLEND" if opacity < 1 else "OPAQUE",
            )
        return result

    @staticmethod
    def _node_name(element_id: str, index: int, count: int) -> str:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", element_id).strip("_")
        digest = hashlib.sha1(
            element_id.encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:8]
        base = f"hd_{slug}_{digest}"
        return base if count == 1 else f"{base}_part{index + 1}"
