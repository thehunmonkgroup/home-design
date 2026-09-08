import { Box3, Matrix4, Mesh, MeshStandardMaterial, Object3D, OrthographicCamera, PerspectiveCamera, Plane, Vector3, type Material } from 'three';
import { canonicalSectionPlane } from './scene';
import { contextElementIds, reinforcementElementIds } from './navigation';
import { reviewElementIds, type RenderManifest, type ReviewPreset } from './model';

export interface MeshSelector {
  ids?: string[];
  kinds?: string[];
  storeys?: string[];
  contents?: boolean;
  layers?: Array<{ elementId: string; layerId: string | number }>;
  materials?: string[];
  roles?: string[];
}

export function highlightedMaterial(material: Material | Material[]): Material | Material[] {
  const originals = Array.isArray(material) ? material : [material];
  const replacements = originals.map((original) => {
    const copy = original.clone();
    if (copy instanceof MeshStandardMaterial) { copy.color.set('#ffc14d'); copy.emissive.set('#523200'); }
    return copy;
  });
  return Array.isArray(material) ? replacements : replacements[0];
}
export interface VisualView {
  name?: string;
  width?: number;
  height?: number;
  camera?: {
    projection?: 'perspective' | 'orthographic';
    preset?: 'ne' | 'nw' | 'se' | 'sw' | 'top' | 'north' | 'south' | 'east' | 'west';
    position?: [number, number, number];
    target?: [number, number, number];
    up?: [number, number, number];
    fov?: number;
    padding?: number;
  };
  isolate?: MeshSelector;
  hide?: MeshSelector[];
  show?: MeshSelector[];
  highlight?: MeshSelector;
  reveal?: { id: string; mode: 'contents' | 'reinforcement' | 'system' | 'connected' };
  discipline?: ReviewPreset;
  sections?: Array<{ axis: 'x' | 'y' | 'z'; position: number; keep?: 'below' | 'above' }>;
  labels?: boolean;
  sectionCaps?: boolean;
  edges?: boolean;
}

export function selectorNodes(manifest: RenderManifest, selector: MeshSelector): Set<string> {
  const entries = Object.entries(manifest.elements);
  for (const id of selector.ids ?? []) if (!manifest.elements[id]) throw new Error(`Unknown component ID: ${id}`);
  for (const kind of selector.kinds ?? []) if (!entries.some(([, e]) => e.kind === kind)) throw new Error(`No components of kind: ${kind}`);
  for (const storey of selector.storeys ?? []) if (!manifest.storeys?.[storey]) throw new Error(`Unknown storey: ${storey}`);
  let ids = entries.filter(([id, e]) => (!selector.ids || selector.ids.includes(id))
    && (!selector.kinds || selector.kinds.includes(e.kind))
    && (!selector.storeys || selector.storeys.includes(e.storeyId ?? ''))).map(([id]) => id);
  if (selector.contents) ids = [...new Set(ids.flatMap((id) => contextElementIds(manifest, id)))];
  const nodes = new Set(ids.flatMap((id) => manifest.elements[id].nodes));
  if (selector.layers || selector.roles || selector.materials) {
    if (!manifest.meshes) throw new Error('This view requires mesh metadata; regenerate the GLB and manifest');
    for (const layer of selector.layers ?? []) {
      if (!Object.values(manifest.meshes).some((m) => m.elementId === layer.elementId && m.layerId === layer.layerId)) {
        throw new Error(`No rendered layer ${layer.layerId} on ${layer.elementId}`);
      }
    }
    for (const name of nodes) {
      const mesh = manifest.meshes[name];
      if (!mesh || (selector.layers && !selector.layers.some((l) => l.elementId === mesh.elementId && l.layerId === mesh.layerId))
        || (selector.roles && !selector.roles.includes(mesh.role))
        || (selector.materials && !selector.materials.includes(mesh.materialId ?? ''))) nodes.delete(name);
    }
  }
  if (!nodes.size) throw new Error(`Selector has no rendered geometry: ${JSON.stringify(selector)}`);
  return nodes;
}

export function visibleNodes(manifest: RenderManifest, view: VisualView): Set<string> {
  let visible = new Set(Object.values(manifest.elements).filter((e) => e.defaultVisible).flatMap((e) => e.nodes));
  if (view.discipline) visible = selectorNodes(manifest, { ids: reviewElementIds(manifest, view.discipline) });
  if (view.isolate) visible = selectorNodes(manifest, view.isolate);
  if (view.reveal) {
    const { id, mode } = view.reveal;
    if (!manifest.elements[id]) throw new Error(`Unknown reveal component: ${id}`);
    const ids = mode === 'reinforcement' ? reinforcementElementIds(manifest, id)
      : contextElementIds(manifest, id, mode).filter((child) => mode !== 'contents' || child !== id);
    visible = selectorNodes(manifest, { ids });
  }
  for (const selector of view.show ?? []) for (const name of selectorNodes(manifest, selector)) visible.add(name);
  for (const selector of view.hide ?? []) for (const name of selectorNodes(manifest, selector)) visible.delete(name);
  if (!visible.size) throw new Error('The requested visibility hides all geometry');
  return activeCapNodes(manifest, visible, view);
}

export function activeCapNodes(manifest: RenderManifest, selected: Set<string>, view: VisualView): Set<string> {
  const result = new Set(selected);
  for (const [name, mesh] of Object.entries(manifest.meshes ?? {})) {
    if (!mesh.inspectionCap) continue;
    const section = mesh.section;
    const active = view.sectionCaps !== false && section && mesh.capOf && selected.has(mesh.capOf)
      && view.sections?.some((cut) => cut.axis === section.axis && cut.position === section.position && (cut.keep ?? 'below') === section.keep);
    if (active) result.add(name); else result.delete(name);
  }
  return result;
}

export function viewPlanes(view: VisualView): Plane[] {
  return (view.sections ?? []).map((section) => {
    const plane = canonicalSectionPlane(section.axis, section.position);
    return section.keep === 'above' ? plane.negate() : plane;
  });
}

function clippedTriangle(points: Vector3[], planes: Plane[]): Vector3[] {
  let polygon = points;
  for (const plane of planes) {
    const output: Vector3[] = [];
    for (let i = 0; i < polygon.length; i++) {
      const start = polygon[i], end = polygon[(i + 1) % polygon.length];
      const a = plane.distanceToPoint(start), b = plane.distanceToPoint(end);
      if (a >= 0) output.push(start);
      if ((a >= 0) !== (b >= 0)) output.push(start.clone().lerp(end, a / (a - b)));
    }
    polygon = output;
    if (!polygon.length) break;
  }
  return polygon;
}

export function clippedBounds(model: Object3D, visible: Set<string>, planes: Plane[]): Map<string, Box3> {
  model.updateMatrixWorld(true);
  const result = new Map<string, Box3>();
  model.traverse((object) => {
    if (!(object instanceof Mesh)) return;
    object.visible = visible.has(object.name);
    if (!object.visible) return;
    const bounds = new Box3();
    if (!planes.length) bounds.setFromObject(object);
    else {
      const positions = object.geometry.getAttribute('position');
      const indices = object.geometry.index;
      const count = indices?.count ?? positions.count;
      for (let i = 0; i < count; i += 3) {
        const triangle = [0, 1, 2].map((offset) => new Vector3().fromBufferAttribute(positions, indices ? indices.getX(i + offset) : i + offset).applyMatrix4(object.matrixWorld));
        clippedTriangle(triangle, planes).forEach((point) => bounds.expandByPoint(point));
      }
    }
    object.visible = !bounds.isEmpty();
    if (object.visible) result.set(object.name, bounds);
  });
  if (!result.size) throw new Error('The section planes remove all selected geometry');
  return result;
}

export function fromCanonical(point: [number, number, number]): Vector3 {
  return new Vector3(point[0] / 1000, point[2] / 1000, -point[1] / 1000);
}
export function toCanonical(point: Vector3): number[] {
  return [point.x * 1000, -point.z * 1000, point.y * 1000];
}

export function inspectionCamera(view: VisualView, bounds: Box3): PerspectiveCamera | OrthographicCamera {
  const options = view.camera ?? {};
  const aspect = (view.width ?? 1280) / (view.height ?? 960);
  const camera = options.projection === 'orthographic' ? new OrthographicCamera() : new PerspectiveCamera(options.fov ?? 42, aspect);
  const directions = { ne: [1, 1, 0.85], nw: [-1, 1, 0.85], se: [1, -1, 0.85], sw: [-1, -1, 0.85], top: [0, 0, 1], north: [0, 1, 0], south: [0, -1, 0], east: [1, 0, 0], west: [-1, 0, 0] };
  const preset = options.preset ?? 'se';
  const direction = fromCanonical(directions[preset] as [number, number, number]).normalize();
  const center = bounds.getCenter(new Vector3());
  const target = options.target ? fromCanonical(options.target) : center;
  camera.up.copy(options.up ? fromCanonical(options.up).normalize() : preset === 'top' ? new Vector3(0, 0, -1) : new Vector3(0, 1, 0));
  if (!camera.up.lengthSq()) throw new Error('Camera up vector must be nonzero');
  camera.position.copy(options.position ? fromCanonical(options.position) : center.clone().add(direction));
  const forward = target.clone().sub(camera.position);
  if (forward.lengthSq() < 1e-12 || forward.clone().normalize().cross(camera.up).lengthSq() < 1e-10) throw new Error('Camera position, target and up must define a nondegenerate frame');
  camera.lookAt(target);
  const inverse = new Matrix4().makeRotationFromQuaternion(camera.quaternion).invert();
  const padding = options.padding ?? 1.15;
  const corners: Vector3[] = [];
  for (const x of [bounds.min.x, bounds.max.x]) for (const y of [bounds.min.y, bounds.max.y]) for (const z of [bounds.min.z, bounds.max.z]) corners.push(new Vector3(x, y, z).sub(target).applyMatrix4(inverse));
  const span = Math.max(bounds.getSize(new Vector3()).length(), 0.001);
  let distance = span;
  if (camera instanceof PerspectiveCamera) {
    const slope = Math.tan(camera.fov * Math.PI / 360);
    distance = Math.max(...corners.map((p) => p.z + padding * Math.max(Math.abs(p.x) / (slope * aspect), Math.abs(p.y) / slope)), span * 0.05);
  } else {
    const half = padding * Math.max(...corners.map((p) => Math.max(Math.abs(p.y), Math.abs(p.x) / aspect)), 0.001);
    camera.left = -half * aspect; camera.right = half * aspect; camera.top = half; camera.bottom = -half;
  }
  if (!options.position) camera.position.copy(target).addScaledVector(direction, distance);
  const actualDistance = camera.position.distanceTo(target);
  const closestDepth = Math.min(...corners.map((p) => actualDistance - p.z));
  camera.near = Math.max(closestDepth > 0 ? closestDepth * 0.5 : span / 1000, 0.00001);
  camera.far = camera.position.distanceTo(center) + span * 4;
  camera.updateProjectionMatrix(); camera.updateMatrixWorld(true);
  return camera;
}
