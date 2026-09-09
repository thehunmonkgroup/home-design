import { describe, expect, it } from 'vitest';
import { Box3, PerspectiveCamera, OrthographicCamera, Vector2, Vector3 } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CameraNavigation, lookDirection, regionContains, roomPoints, roomPose, roomRegion, type RoomRegion } from './camera-navigation';

const rectangle: RoomRegion = { outer: [[0, 0], [4000, 0], [4000, 3000], [0, 3000]].map(([x, y]) => new Vector2(x, y)), holes: [], floor: 3000, height: 2600 };

class Canvas extends EventTarget {
  clientHeight = 800;
  setPointerCapture() {}
}
function fixture() {
  const camera = new PerspectiveCamera();
  camera.position.set(2, 4.65, -1.5); camera.lookAt(2, 4.65, -3);
  const controls = new OrbitControls(camera);
  controls.target.set(2, 4.65, -3); controls.update();
  const canvas = new Canvas();
  const nav = new CameraNavigation(camera, controls, canvas as unknown as HTMLElement, () => {});
  return { camera, controls, canvas, nav };
}
function pointer(canvas: Canvas, type: string, x: number, y: number, id = 1) {
  const event = new Event(type);
  Object.assign(event, { pointerId: id, clientX: x, clientY: y, button: 0 });
  canvas.dispatchEvent(event);
}

describe('stationary look navigation', () => {
  it('spins fully in place, keeps the horizon level and never flips over', () => {
    const camera = new PerspectiveCamera(); camera.position.set(2, 1.65, 3);
    const origin = camera.position.clone();
    lookDirection(camera, 1600, 0, 800);
    expect(camera.position.equals(origin)).toBe(true);
    expect(camera.getWorldDirection(new Vector3()).distanceTo(new Vector3(0, 0, -1))).toBeLessThan(1e-10);
    lookDirection(camera, 0, 10000, 800);
    expect(camera.getWorldDirection(new Vector3()).y).toBeGreaterThan(-1);
    expect(new Vector3(0, 1, 0).applyQuaternion(camera.quaternion).y).toBeGreaterThan(0);
  });
  it('hands gestures between modes without changing position or direction', () => {
    const { camera, controls, canvas, nav } = fixture();
    const position = camera.position.clone(), quaternion = camera.quaternion.clone();
    nav.setMode('look');
    expect(controls.enabled).toBe(false);
    pointer(canvas, 'pointerdown', 0, 0); pointer(canvas, 'pointermove', 200, 50); pointer(canvas, 'pointerup', 200, 50);
    expect(camera.position.equals(position)).toBe(true);
    expect(camera.quaternion.equals(quaternion)).toBe(false);
    const direction = camera.getWorldDirection(new Vector3());
    nav.setMode('orbit'); controls.update();
    expect(camera.position.distanceTo(position)).toBeLessThan(1e-10);
    expect(camera.getWorldDirection(new Vector3()).distanceTo(direction)).toBeLessThan(1e-10);
    nav.tool = 'pivot'; nav.sync(); expect(controls.enabled).toBe(false);
    nav.dispose();
  });
  it('clears pending orbit inertia without jumping the viewpoint', () => {
    const { camera, controls, nav } = fixture();
    controls.enableDamping = true; controls.autoRotate = true; controls.update();
    controls.autoRotate = false;
    const position = camera.position.clone(), direction = camera.getWorldDirection(new Vector3());
    nav.setMode('look');
    expect(camera.position.distanceTo(position)).toBeLessThan(1e-10);
    expect(camera.getWorldDirection(new Vector3()).distanceTo(direction)).toBeLessThan(1e-10);
    nav.setMode('orbit'); controls.update();
    expect(camera.position.distanceTo(position)).toBeLessThan(1e-10);
    nav.dispose();
  });
  it('moves camera and target together for scrolling and ignores gestures after disposal', () => {
    const { camera, controls, canvas, nav } = fixture(); nav.setMode('look');
    const offset = camera.position.clone().sub(controls.target);
    const event = new Event('wheel', { cancelable: true }); Object.assign(event, { deltaY: -100, deltaMode: 0 });
    canvas.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(camera.position.clone().sub(controls.target).distanceTo(offset)).toBeLessThan(1e-10);
    const position = camera.position.clone(); nav.dispose(); canvas.dispatchEvent(event);
    expect(camera.position.equals(position)).toBe(true);
  });
  it('supports two-finger pan and pinch without leaving stale pointer state', () => {
    const { camera, canvas, nav } = fixture(); nav.setMode('look');
    const start = camera.position.clone();
    pointer(canvas, 'pointerdown', 100, 100, 1); pointer(canvas, 'pointerdown', 200, 100, 2);
    pointer(canvas, 'pointermove', 240, 120, 2);
    expect(camera.position.distanceTo(start)).toBeGreaterThan(0.01);
    pointer(canvas, 'pointercancel', 100, 100, 1); pointer(canvas, 'pointerup', 240, 120, 2);
    const position = camera.position.clone(); pointer(canvas, 'pointermove', 250, 150, 2);
    expect(camera.position.equals(position)).toBe(true); nav.dispose();
  });
  it('keeps an orthographic plan in orbit mode', () => {
    const camera = new OrthographicCamera(); const controls = new OrbitControls(camera);
    const nav = new CameraNavigation(camera, controls, new Canvas() as unknown as HTMLElement, () => {});
    nav.setMode('look'); expect(nav.mode).toBe('orbit'); nav.dispose();
  });
});

describe('keyboard camera movement', () => {
  const motion = { x: 0, y: 0, zoom: 0, pan: false };
  it.each([1, -1])('rotates vertically in the requested model direction (%s)', (y) => {
    const { nav, camera } = fixture();
    const height = camera.position.y;
    nav.keyboardMotion({ ...motion, y }, 0.25);
    expect((camera.position.y - height) * y).toBeLessThan(0);
    nav.dispose();
  });
  it.each(['orbit', 'look'] as const)('pans the model in the pressed screen direction in %s mode', (mode) => {
    for (const [x, y] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const { nav, camera, controls } = fixture(); nav.setMode(mode);
      const point = controls.target.clone(), before = point.clone().project(camera);
      nav.keyboardMotion({ ...motion, x, y, pan: true }, 0.25);
      const delta = point.project(camera).sub(before);
      expect(delta.x * x + delta.y * y).toBeGreaterThan(0);
      nav.dispose();
    }
  });
  it('orbits around the same target at a frame-rate independent speed and stops without inertia', () => {
    const one = fixture(), many = fixture();
    const target = one.controls.target.clone(), distance = one.camera.position.distanceTo(target);
    one.controls.enableDamping = true;
    one.nav.keyboardMotion({ ...motion, x: 1 }, 1);
    for (let i = 0; i < 60; i++) many.nav.keyboardMotion({ ...motion, x: 1 }, 1 / 60);
    expect(one.camera.position.distanceTo(many.camera.position)).toBeLessThan(1e-9);
    expect(one.controls.target.equals(target)).toBe(true);
    expect(one.camera.position.distanceTo(target)).toBeCloseTo(distance);
    const stopped = one.camera.position.clone();
    for (let i = 0; i < 30; i++) one.controls.update();
    expect(one.camera.position.distanceTo(stopped)).toBeLessThan(1e-9);
    one.nav.dispose(); many.nav.dispose();
  });
  it('pans camera and target together and respects perspective zoom and orbit limits', () => {
    const { nav, controls, camera } = fixture();
    const offset = camera.position.clone().sub(controls.target), before = camera.position.clone();
    nav.keyboardMotion({ ...motion, x: 1, pan: true }, 1);
    expect(camera.position.distanceTo(before)).toBeGreaterThan(0.1);
    expect(camera.position.clone().sub(controls.target).distanceTo(offset)).toBeLessThan(1e-9);
    controls.minDistance = 0.5; controls.maxDistance = 4;
    nav.keyboardMotion({ ...motion, zoom: 1 }, 100);
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(0.5);
    nav.keyboardMotion({ ...motion, zoom: -1 }, 100);
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(4);
    controls.minPolarAngle = 0.2; controls.maxPolarAngle = 2.8;
    nav.keyboardMotion({ ...motion, y: 1 }, 100);
    expect(controls.getPolarAngle()).toBeCloseTo(2.8);
    nav.keyboardMotion({ ...motion, y: -1 }, 100);
    expect(controls.getPolarAngle()).toBeCloseTo(0.2);
    nav.dispose();
  });
  it('looks in place, moves along the viewing direction, and pauses for placement tools', () => {
    const { nav, camera, controls } = fixture(); nav.setMode('look');
    const position = camera.position.clone(), direction = camera.getWorldDirection(new Vector3());
    nav.keyboardMotion({ ...motion, x: 1, y: 1 }, 0.5);
    expect(camera.position.equals(position)).toBe(true);
    expect(camera.getWorldDirection(new Vector3()).distanceTo(direction)).toBeGreaterThan(0.1);
    const forward = camera.getWorldDirection(new Vector3()), offset = camera.position.clone().sub(controls.target);
    nav.keyboardMotion({ ...motion, zoom: 1 }, 0.5);
    expect(camera.position.clone().sub(position).normalize().distanceTo(forward)).toBeLessThan(1e-9);
    expect(camera.position.clone().sub(controls.target).distanceTo(offset)).toBeLessThan(1e-9);
    const stopped = camera.position.clone(); nav.tool = 'position';
    nav.keyboardMotion({ ...motion, zoom: 1, x: 1 }, 1);
    expect(camera.position.equals(stopped)).toBe(true);
    nav.dispose();
  });
  it('zooms an orthographic camera without moving it and scales panning to its visible extent', () => {
    const camera = new OrthographicCamera(-4, 4, 3, -3, 0.1, 100);
    camera.position.set(4, 4, 4);
    const controls = new OrbitControls(camera); controls.update();
    controls.minZoom = 0.5; controls.maxZoom = 4;
    const nav = new CameraNavigation(camera, controls, new Canvas() as unknown as HTMLElement, () => {});
    const position = camera.position.clone();
    nav.keyboardMotion({ ...motion, zoom: 1 }, 100);
    expect(camera.zoom).toBe(4);
    expect(camera.position.distanceTo(position)).toBeLessThan(1e-9);
    nav.keyboardMotion({ ...motion, x: 1, pan: true }, 1);
    expect(camera.position.distanceTo(position)).toBeCloseTo(6 / 4 * 0.6);
    nav.keyboardMotion({ ...motion, zoom: -1 }, 100);
    expect(camera.zoom).toBe(0.5);
    nav.dispose();
  });
});

describe('room and deck viewpoints', () => {
  it('places an eye-level camera on the elevated storey and an inset high corner', () => {
    const center = roomPose(rectangle, 'center');
    expect(center.position.y).toBeCloseTo(4.65);
    expect(center.target.y).toBeCloseTo(center.position.y);
    const corner = roomPose(rectangle, 'corner');
    expect(corner.position.y).toBeCloseTo(5.25);
    expect(regionContains(rectangle, new Vector2(corner.position.x * 1000, -corner.position.z * 1000))).toBe(true);
    expect(corner.target.y).toBeLessThan(corner.position.y);
  });
  it('avoids the missing quadrant of an L-shaped room and interior holes', () => {
    const region = { ...rectangle, outer: [[0, 0], [6000, 0], [6000, 1000], [1000, 1000], [1000, 6000], [0, 6000]].map(([x, y]) => new Vector2(x, y)), holes: [] };
    for (const point of Object.values(roomPoints(region))) expect(regionContains(region, point)).toBe(true);
    const withHole = { ...rectangle, holes: [[[1000, 500], [3000, 500], [3000, 2500], [1000, 2500]].map(([x, y]) => new Vector2(x, y))] };
    for (const point of Object.values(roomPoints(withHole))) expect(regionContains(withHole, point)).toBe(true);
    expect(regionContains(withHole, new Vector2(2000, 1500))).toBe(false);
    expect(regionContains(withHole, new Vector2(1000, 1500))).toBe(false);
    expect(regionContains(rectangle, new Vector2(0, 1500))).toBe(false);
  });
  it('handles skinny footprints and limits eye height below the ceiling', () => {
    const narrow = { ...rectangle, outer: [[0, 0], [10, 0], [10, 5000], [0, 5000]].map(([x, y]) => new Vector2(x, y)), height: 900 };
    const pose = roomPose(narrow, 'center', 2000);
    expect(regionContains(narrow, new Vector2(pose.position.x * 1000, -pose.position.z * 1000))).toBe(true);
    expect(pose.position.y).toBeCloseTo(3.75);
    expect(roomPose({ ...rectangle, height: 100 }, 'center').position.y).toBeCloseTo(3.05);
  });
  it('uses the space base and deck surface, even when their geometry is hidden', () => {
    const element = { kind: 'space', name: 'Room', storeyId: null, nodes: [], defaultVisible: false, data: { footprint: { outer: rectangle.outer.map((p) => p.toArray()) }, height: 2600 } };
    const bounds = new Box3(new Vector3(0, 3, -3), new Vector3(4, 5.6, 0));
    expect(roomRegion(element, bounds)?.floor).toBe(3000);
    expect(roomRegion({ ...element, kind: 'slab' }, bounds)?.floor).toBe(5600);
    expect(roomRegion({ ...element, data: {} }, bounds)).toBeNull();
    expect(roomRegion({ ...element, kind: 'slab', data: { ...element.data, topElevation: -25 } }, new Box3())?.floor).toBe(-25);
  });
});
