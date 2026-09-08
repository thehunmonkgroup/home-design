import { Box3, Euler, OrthographicCamera, PerspectiveCamera, ShapeUtils, Vector2, Vector3 } from 'three';
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { ManifestElement } from './model';
import { fromCanonical } from './visual-view';

export type NavigationMode = 'orbit' | 'look';
export type Camera = PerspectiveCamera | OrthographicCamera;
export type CameraPose = { camera: Camera; target: Vector3; mode: NavigationMode };
export type ViewpointTool = 'pivot' | 'position' | null;

export function lookDirection(camera: Camera, dx: number, dy: number, height: number): void {
  const angles = new Euler().setFromQuaternion(camera.quaternion, 'YXZ');
  angles.y -= dx * Math.PI / Math.max(height, 1);
  angles.x = Math.max(-Math.PI / 2 + 0.01, Math.min(Math.PI / 2 - 0.01, angles.x - dy * Math.PI / Math.max(height, 1)));
  angles.z = 0;
  camera.quaternion.setFromEuler(angles);
  camera.updateMatrixWorld();
}

/** One owner for camera gestures; OrbitControls remains untouched internally. */
export class CameraNavigation {
  mode: NavigationMode = 'orbit';
  tool: ViewpointTool = null;
  private drag: { id: number; pan: boolean } | null = null;
  private pointers = new Map<number, Vector2>();
  constructor(public camera: Camera, public controls: OrbitControls, private canvas: HTMLElement, private changed: () => void) {
    canvas.addEventListener('pointerdown', this.down, true);
    canvas.addEventListener('pointermove', this.move, true);
    canvas.addEventListener('pointerup', this.up, true);
    canvas.addEventListener('pointercancel', this.up, true);
    canvas.addEventListener('lostpointercapture', this.up, true);
    canvas.addEventListener('wheel', this.wheel, { capture: true, passive: false });
  }
  setMode(mode: NavigationMode): void {
    // Flush orbit inertia before handing the camera to a different gesture owner.
    const position = this.camera.position.clone(), target = this.controls.target.clone();
    const damping = this.controls.enableDamping;
    this.controls.enableDamping = false;
    if (this.mode === 'orbit') this.controls.update();
    this.camera.position.copy(position); this.controls.target.copy(target);
    if (this.mode === 'orbit') this.controls.update();
    this.controls.enableDamping = damping;
    this.mode = this.camera instanceof OrthographicCamera ? 'orbit' : mode;
    this.drag = null;
    this.pointers.clear();
    this.sync();
  }
  sync(): void {
    this.controls.enabled = this.mode === 'orbit' && !this.tool;
  }
  pose(): CameraPose { return { camera: this.camera.clone(), target: this.controls.target.clone(), mode: this.mode }; }
  aimTarget(): void {
    const distance = Math.max(this.camera.position.distanceTo(this.controls.target), 1);
    this.controls.target.copy(this.camera.position).addScaledVector(this.camera.getWorldDirection(new Vector3()), distance);
  }
  private down = (event: PointerEvent): void => {
    if (this.mode !== 'look' || this.tool) return;
    this.pointers.set(event.pointerId, new Vector2(event.clientX, event.clientY));
    if (event.button !== 0 && event.button !== 2) return;
    this.drag = { id: event.pointerId, pan: event.button === 2 || event.shiftKey || event.ctrlKey || event.metaKey };
    this.canvas.setPointerCapture(event.pointerId);
  };
  private move = (event: PointerEvent): void => {
    if (this.mode !== 'look' || this.tool || !this.pointers.has(event.pointerId)) return;
    const previous = this.pointers.get(event.pointerId)!;
    const current = new Vector2(event.clientX, event.clientY);
    const delta = current.clone().sub(previous);
    if (this.pointers.size === 2) {
      const other = [...this.pointers.entries()].find(([id]) => id !== event.pointerId)![1];
      const oldDistance = previous.distanceTo(other);
      const newDistance = current.distanceTo(other);
      this.pan(delta.x / 2, delta.y / 2);
      this.dolly((oldDistance - newDistance) * 0.01);
    } else if (this.drag?.id === event.pointerId) {
      if (this.drag.pan) this.pan(delta.x, delta.y);
      else { lookDirection(this.camera, delta.x, delta.y, this.canvas.clientHeight); this.aimTarget(); }
    }
    this.pointers.set(event.pointerId, current);
    this.changed();
  };
  private up = (event: PointerEvent): void => {
    this.pointers.delete(event.pointerId);
    if (this.drag?.id === event.pointerId) this.drag = null;
  };
  private pan(dx: number, dy: number): void {
    const scale = 3 / Math.max(this.canvas.clientHeight, 1);
    const offset = new Vector3(-dx * scale, dy * scale, 0).applyQuaternion(this.camera.quaternion);
    this.camera.position.add(offset); this.controls.target.add(offset);
  }
  private dolly(distance: number): void {
    const offset = this.camera.getWorldDirection(new Vector3()).multiplyScalar(distance);
    this.camera.position.add(offset); this.controls.target.add(offset);
  }
  private wheel = (event: WheelEvent): void => {
    if (this.mode !== 'look' || this.tool) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? this.canvas.clientHeight : 1;
    this.dolly(Math.max(-0.75, Math.min(0.75, -event.deltaY * unit * 0.002)));
    this.changed();
  };
  dispose(): void {
    this.canvas.removeEventListener('pointerdown', this.down, true);
    this.canvas.removeEventListener('pointermove', this.move, true);
    this.canvas.removeEventListener('pointerup', this.up, true);
    this.canvas.removeEventListener('pointercancel', this.up, true);
    this.canvas.removeEventListener('lostpointercapture', this.up, true);
    this.canvas.removeEventListener('wheel', this.wheel, true);
  }
}

export interface RoomRegion { outer: Vector2[]; holes: Vector2[][]; floor: number; height: number }
function ring(value: unknown): Vector2[] | null {
  if (!Array.isArray(value) || value.length < 3) return null;
  const result: Vector2[] = [];
  for (const point of value) {
    if (!Array.isArray(point) || point.length !== 2 || !point.every((v) => typeof v === 'number' && Number.isFinite(v))) return null;
    result.push(new Vector2(point[0], point[1]));
  }
  if (result.length > 3 && result[0].equals(result[result.length - 1])) result.pop();
  return result;
}
export function roomRegion(element: ManifestElement, bounds: Box3): RoomRegion | null {
  if (element.kind !== 'space' && element.kind !== 'slab') return null;
  const floor = element.kind === 'slab' && typeof element.data.topElevation === 'number'
    ? element.data.topElevation : bounds.isEmpty() ? NaN : (element.kind === 'space' ? bounds.min.y : bounds.max.y) * 1000;
  if (!Number.isFinite(floor)) return null;
  const footprint = element.data.footprint as { outer?: unknown; holes?: unknown[] } | undefined;
  const outer = ring(footprint?.outer);
  if (!outer) return null;
  const holes = (footprint?.holes ?? []).map(ring);
  if (holes.some((hole) => !hole)) return null;
  return { outer, holes: holes as Vector2[][], floor,
    height: typeof element.data.height === 'number' ? element.data.height : 2700 };
}
function insideRing(point: Vector2, points: Vector2[]): boolean {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const a = points[i], b = points[j];
    if ((a.y > point.y) !== (b.y > point.y) && point.x < (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}
export function regionContains(region: RoomRegion, point: Vector2): boolean {
  for (const ring of [region.outer, ...region.holes]) for (let i = 0; i < ring.length; i++) {
    const a = ring[i], edge = ring[(i + 1) % ring.length].clone().sub(a), relative = point.clone().sub(a);
    if (edge.lengthSq() > 0 && Math.abs(edge.cross(relative)) <= 1e-6 * edge.length()
      && relative.dot(edge) >= 0 && relative.dot(edge) <= edge.lengthSq()) return false;
  }
  return insideRing(point, region.outer) && !region.holes.some((hole) => insideRing(point, hole));
}
function clearance(region: RoomRegion, point: Vector2): number {
  if (!regionContains(region, point)) return -Infinity;
  let distance = Infinity;
  for (const ring of [region.outer, ...region.holes]) for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length], edge = b.clone().sub(a);
    const t = Math.max(0, Math.min(1, point.clone().sub(a).dot(edge) / (edge.lengthSq() || 1)));
    distance = Math.min(distance, point.distanceTo(a.clone().addScaledVector(edge, t)));
  }
  return distance;
}
export function roomPoints(region: RoomRegion): { center: Vector2; corner: Vector2 } {
  const min = new Vector2(Infinity, Infinity), max = new Vector2(-Infinity, -Infinity);
  region.outer.forEach((p) => { min.min(p); max.max(p); });
  const vertices = [...region.outer, ...region.holes.flat()];
  const candidates = ShapeUtils.triangulateShape(region.outer, region.holes).map((face) => face.reduce((p, i) => p.add(vertices[i]), new Vector2()).divideScalar(3));
  candidates.push(min.clone().add(max).multiplyScalar(0.5));
  for (let x = 1; x < 32; x++) for (let y = 1; y < 32; y++) candidates.push(new Vector2(min.x + (max.x - min.x) * x / 32, min.y + (max.y - min.y) * y / 32));
  candidates.sort((a, b) => clearance(region, b) - clearance(region, a));
  const center = candidates[0];
  if (!center || !regionContains(region, center)) throw new Error('No interior viewpoint in this footprint');
  const margin = Math.min(450, clearance(region, center) * 0.6);
  const corners = candidates.filter((p) => clearance(region, p) >= margin);
  corners.sort((a, b) => a.distanceToSquared(max) - b.distanceToSquared(max));
  return { center, corner: corners[0] ?? center };
}
export function viewpointHeight(region: RoomRegion, requested: number): number {
  return Math.min(Math.max(1, requested), Math.max(region.height - 150, region.height / 2));
}
export function roomPose(region: RoomRegion, preset: 'center' | 'corner', height = 1650): { position: Vector3; target: Vector3 } {
  const points = roomPoints(region);
  const point = preset === 'center' ? points.center : points.corner;
  const elevation = region.floor + viewpointHeight(region, preset === 'corner' ? region.height - 350 : height);
  const position = fromCanonical([point.x, point.y, elevation]);
  const targetPoint = preset === 'corner' ? points.center : points.corner;
  const target = fromCanonical([targetPoint.x, targetPoint.y, preset === 'corner' ? region.floor + Math.min(1200, region.height / 2) : elevation]);
  if (position.distanceTo(target) < 0.1) target.z -= 1;
  return { position, target };
}
