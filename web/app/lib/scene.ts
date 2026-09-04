import { Box3, DirectionalLight, PerspectiveCamera, Sphere, Vector3 } from 'three';

const CAMERA_FAR_SPAN_MULTIPLIER = 20;
const CAMERA_NEAR_SPAN_DIVISOR = 200;
const LIGHT_DISTANCE_RADIUS_MULTIPLIER = 3;
const MIN_CAMERA_NEAR = 0.02;
const MIN_SHADOW_NORMAL_BIAS = 0.01;
const MIN_SHADOW_RADIUS = 0.1;
const SHADOW_BIAS = -0.0002;
const SHADOW_FRUSTUM_MARGIN = 1.25;
const SHADOW_MAP_SIZE = 2048;
const SHADOW_NORMAL_BIAS_RADIUS_MULTIPLIER = 0.0025;

export function configureDirectionalShadow(light: DirectionalLight, bounds: Box3): void {
  if (bounds.isEmpty()) return;

  const sphere = bounds.getBoundingSphere(new Sphere());
  const radius = Math.max(sphere.radius, MIN_SHADOW_RADIUS);
  const direction = new Vector3(-0.7, 1.2, 0.5).normalize();
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

export function configureCameraDepth(camera: PerspectiveCamera, bounds: Box3): void {
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
