import { Box3, BufferGeometry, DirectionalLight, Material, Object3D, OrthographicCamera, PerspectiveCamera, Plane, Sphere, Texture, Vector3 } from 'three';
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export function configureOrbitControls(controls: OrbitControls): void {
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.screenSpacePanning = true;
  controls.minPolarAngle = 0;
  controls.maxPolarAngle = Math.PI;
}

export function isObjectVisible(object: Object3D): boolean {
  for (let current: Object3D | null = object; current; current = current.parent) {
    if (!current.visible) return false;
  }
  return true;
}

export function disposeSceneResources(root: Object3D): void {
  const geometries = new Set<BufferGeometry>();
  const materials = new Set<Material>();
  const textures = new Set<Texture>();
  root.traverse((object) => {
    if ('geometry' in object && object.geometry instanceof BufferGeometry) geometries.add(object.geometry);
    if ('material' in object) {
      const entries: unknown[] = Array.isArray(object.material) ? object.material : [object.material];
      for (const material of entries) if (material instanceof Material) materials.add(material);
    }
  });
  for (const material of materials) {
    for (const value of Object.values(material)) if (value instanceof Texture) textures.add(value);
    material.dispose();
  }
  for (const texture of textures) texture.dispose();
  for (const geometry of geometries) geometry.dispose();
}

export function modelNorthRotation(camera: PerspectiveCamera | OrthographicCamera): number {
  const right = new Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
  return Math.atan2(-right.z, right.x) * 180 / Math.PI;
}

export function canonicalSectionPlane(axis: 'x' | 'y' | 'z', millimetres: number): Plane {
  const normals = { x: new Vector3(-1, 0, 0), y: new Vector3(0, 0, 1), z: new Vector3(0, -1, 0) };
  return new Plane(normals[axis], millimetres / 1000);
}

const CAMERA_FAR_SPAN_MULTIPLIER = 20;
const CAMERA_NEAR_SPAN_DIVISOR = 200;
const FRAME_MARGIN = 1.15;
const LIGHT_DISTANCE_RADIUS_MULTIPLIER = 3;
const MIN_CAMERA_NEAR = 0.02;
const MIN_SHADOW_NORMAL_BIAS = 0.01;
const MIN_SHADOW_RADIUS = 0.1;
const SHADOW_BIAS = -0.0002;
const SHADOW_FRUSTUM_MARGIN = 1.25;
const SHADOW_MAP_SIZE = 2048;
const SHADOW_NORMAL_BIAS_RADIUS_MULTIPLIER = 0.0025;

export function frameModel(camera: PerspectiveCamera | OrthographicCamera, controls: OrbitControls, model: Object3D): void {
  const bounds = new Box3().setFromObject(model);
  frameBounds(camera, controls, bounds);
}

export function frameBounds(camera: PerspectiveCamera | OrthographicCamera, controls: OrbitControls, bounds: Box3): void {
  if (bounds.isEmpty()) return;
  if (camera instanceof OrthographicCamera) {
    const aspect = (camera.right - camera.left) / (camera.top - camera.bottom);
    const center = bounds.getCenter(new Vector3());
    const span = Math.max(bounds.getSize(new Vector3()).length(), 0.01) * FRAME_MARGIN;
    camera.zoom = 1;
    camera.left = -span * aspect / 2; camera.right = span * aspect / 2;
    camera.top = span / 2; camera.bottom = -span / 2;
    camera.position.copy(center).add(new Vector3(1.15, 0.85, 1.25).normalize().multiplyScalar(span));
    camera.up.set(0, 1, 0); camera.lookAt(center);
    configureCameraDepth(camera, bounds);
    controls.target.copy(center); controls.update();
    return;
  }
  if (camera.aspect <= 0) return;

  const damping = controls.enableDamping;
  controls.enableDamping = false;
  controls.update();

  const center = bounds.getCenter(new Vector3());
  const direction = new Vector3(1.15, 0.85, 1.25).normalize();
  camera.position.copy(center).add(direction);
  camera.lookAt(center);
  const inverseOrientation = camera.quaternion.clone().invert();
  const verticalSlope = Math.tan(camera.getEffectiveFOV() * Math.PI / 360);
  const horizontalSlope = verticalSlope * camera.aspect;
  const size = bounds.getSize(new Vector3());
  const nearClearance = 2 * Math.max(Math.max(size.x, size.y, size.z) / CAMERA_NEAR_SPAN_DIVISOR, MIN_CAMERA_NEAR);
  let distance = nearClearance;
  for (const x of [bounds.min.x, bounds.max.x]) {
    for (const y of [bounds.min.y, bounds.max.y]) {
      for (const z of [bounds.min.z, bounds.max.z]) {
        const corner = new Vector3(x, y, z).sub(center).applyQuaternion(inverseOrientation);
        distance = Math.max(distance, corner.z + Math.max(
          FRAME_MARGIN * Math.abs(corner.x) / horizontalSlope,
          FRAME_MARGIN * Math.abs(corner.y) / verticalSlope,
          nearClearance,
        ));
      }
    }
  }

  camera.position.copy(center).addScaledVector(direction, distance);
  configureCameraDepth(camera, bounds);
  controls.target.copy(center);
  controls.update();
  controls.enableDamping = damping;
  camera.updateMatrixWorld();
}

export function configureDirectionalShadow(light: DirectionalLight, bounds: Box3, sunDirection?: Vector3): void {
  if (bounds.isEmpty()) return;

  const sphere = bounds.getBoundingSphere(new Sphere());
  const radius = Math.max(sphere.radius, MIN_SHADOW_RADIUS);
  const direction = sunDirection?.clone().normalize() ?? new Vector3(-0.7, 1.2, 0.5).normalize();
  const lightDistance = radius * LIGHT_DISTANCE_RADIUS_MULTIPLIER;
  const shadowExtent = radius * SHADOW_FRUSTUM_MARGIN;

  light.position.copy(sphere.center).addScaledVector(direction, lightDistance);
  light.target.position.copy(sphere.center);
  light.shadow.mapSize.set(SHADOW_MAP_SIZE, SHADOW_MAP_SIZE);
  light.shadow.bias = SHADOW_BIAS;
  light.shadow.normalBias = Math.max(
    MIN_SHADOW_NORMAL_BIAS,
    radius * SHADOW_NORMAL_BIAS_RADIUS_MULTIPLIER,
  );

  const shadowCamera = light.shadow.camera;
  shadowCamera.left = -shadowExtent;
  shadowCamera.right = shadowExtent;
  shadowCamera.top = shadowExtent;
  shadowCamera.bottom = -shadowExtent;
  shadowCamera.near = Math.max(lightDistance - shadowExtent, MIN_SHADOW_RADIUS);
  shadowCamera.far = lightDistance + shadowExtent;
  shadowCamera.updateProjectionMatrix();
}

export function configureCameraDepth(camera: PerspectiveCamera | OrthographicCamera, bounds: Box3): void {
  if (bounds.isEmpty()) return;

  const size = bounds.getSize(new Vector3());
  const center = bounds.getCenter(new Vector3());
  const span = Math.max(size.x, size.y, size.z, MIN_SHADOW_RADIUS);
  camera.near = Math.max(span / CAMERA_NEAR_SPAN_DIVISOR, MIN_CAMERA_NEAR);
  camera.far = Math.max(
    span * CAMERA_FAR_SPAN_MULTIPLIER,
    camera.position.distanceTo(center) + span * 2,
  );
  camera.updateProjectionMatrix();
}
