import { Box3, EdgesGeometry, LineBasicMaterial, LineSegments, Mesh, type Group, type Material } from 'three';
import type { RenderManifest } from './model';
import { clippedBounds, fromCanonical, highlightedMaterial, inspectionCamera, selectorNodes, viewPlanes, visibleNodes, type VisualView } from './visual-view';

export class NamedViewPresentation {
  private outlines: LineSegments[] = [];
  private originals = new Map<Mesh, Material | Material[]>();

  clear(): void {
    for (const line of this.outlines) {
      line.removeFromParent(); line.geometry.dispose();
      const materials = Array.isArray(line.material) ? line.material : [line.material];
      materials.forEach((material) => material.dispose());
    }
    this.outlines = [];
    for (const [mesh, original] of this.originals) {
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      materials.forEach((material) => material.dispose());
      mesh.material = original;
    }
    this.originals.clear();
  }

  apply(model: Group, manifest: RenderManifest, view: VisualView, width: number, height: number) {
    const visible = visibleNodes(manifest, view);
    const highlighted = view.highlight ? selectorNodes(manifest, view.highlight) : new Set<string>();
    const planes = viewPlanes(view);
    const previous = new Map<Mesh, boolean>();
    model.traverse((object) => { if (object instanceof Mesh) previous.set(object, object.visible); });
    let bounds: Box3;
    let camera: ReturnType<typeof inspectionCamera>;
    try {
      bounds = new Box3();
      clippedBounds(model, visible, planes).forEach((box) => bounds.union(box));
      camera = inspectionCamera({ ...view, width, height }, bounds);
    } catch (error) {
      previous.forEach((visibility, mesh) => { mesh.visible = visibility; });
      throw error;
    }
    this.clear();
    const meshes: Mesh[] = [];
    model.traverse((object) => { if (object instanceof Mesh) meshes.push(object); });
    for (const mesh of meshes) {
      if (view.edges !== false) {
        const line = new LineSegments(new EdgesGeometry(mesh.geometry, 25), new LineBasicMaterial({ color: '#43505a', transparent: true, opacity: 0.35 }));
        mesh.add(line); this.outlines.push(line);
      }
      if (highlighted.has(mesh.name)) {
        this.originals.set(mesh, mesh.material);
        mesh.material = highlightedMaterial(mesh.material);
      }
    }
    const hidden = new Set(Object.entries(manifest.elements).filter(([, element]) => element.nodes.length && !element.nodes.some((node) => visible.has(node))).map(([id]) => id));
    return { camera, target: view.camera?.target ? fromCanonical(view.camera.target) : bounds.getCenter(camera.position.clone()), planes, visible, hidden };
  }
}
