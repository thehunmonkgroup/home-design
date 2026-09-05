import { describe, expect, it } from 'vitest';
import { Box3, BoxGeometry, DirectionalLight, Group, Mesh, MeshBasicMaterial, PerspectiveCamera, Vector3 } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { canonicalSectionPlane, configureCameraDepth, configureDirectionalShadow, configureOrbitControls, disposeSceneResources, frameModel, modelNorthRotation } from './scene';

const MODEL_BOUNDS = new Box3(new Vector3(0, 0, -8), new Vector3(10, 5, 0));

describe('model framing', () => {
  it.each([
    [11.2, 5.6, 11.6], [30, 1, 3], [2, 40, 2], [3, 2, 30],
  ])('fits all corners of a %s × %s × %s model with a consistent margin', (width, height, depth) => {
    const model = new Mesh(new BoxGeometry(width, height, depth), new MeshBasicMaterial());
    model.position.set(13, -7, 21);
    model.rotation.y = 0.3;
    const bounds = new Box3().setFromObject(model);
    for (const aspect of [0.25, 0.5, 0.75, 1, 1.6, 3]) {
      for (const fov of [25, 42, 70]) {
        const camera = new PerspectiveCamera(fov, aspect);
        const controls = new OrbitControls(camera);
        configureOrbitControls(controls);
        camera.zoom = 1.3;
        camera.position.set(-4, -20, 17);
        controls.target.set(100, 200, 300);
        frameModel(camera, controls, model);
        expect(controls.target.distanceTo(bounds.getCenter(new Vector3()))).toBeLessThan(1e-10);
        let largestExtent = 0;
        for (const x of [bounds.min.x, bounds.max.x]) {
          for (const y of [bounds.min.y, bounds.max.y]) {
            for (const z of [bounds.min.z, bounds.max.z]) {
              const projected = new Vector3(x, y, z).project(camera);
              largestExtent = Math.max(largestExtent, Math.abs(projected.x), Math.abs(projected.y));
              expect(projected.z).toBeGreaterThan(-1);
              expect(projected.z).toBeLessThan(1);
            }
          }
        }
        expect(largestExtent).toBeCloseTo(1 / 1.15);
        const framedPosition = camera.position.clone();
        for (let frame = 0; frame < 20; frame++) controls.update();
        expect(camera.position.distanceTo(framedPosition)).toBeLessThan(1e-10);
        expect(controls.enableDamping).toBe(true);
      }
    }
    disposeSceneResources(model);
  });

  it('refits after a viewport resize and remains repeatable', () => {
    const model = new Mesh(new BoxGeometry(11.2, 5.6, 11.6), new MeshBasicMaterial());
    const camera = new PerspectiveCamera(42, 2);
    const controls = new OrbitControls(camera);
    frameModel(camera, controls, model);
    const landscapeDistance = controls.getDistance();
    camera.aspect = 0.5;
    frameModel(camera, controls, model);
    expect(controls.getDistance()).toBeGreaterThan(landscapeDistance);
    const portraitPosition = camera.position.clone();
    frameModel(camera, controls, model);
    expect(camera.position.distanceTo(portraitPosition)).toBeLessThan(1e-10);
    expect(controls.enableDamping).toBe(false);
    disposeSceneResources(model);
  });

  it('keeps the camera unchanged for an empty model', () => {
    const camera = new PerspectiveCamera();
    const controls = new OrbitControls(camera);
    camera.position.set(5, 6, 7);
    controls.target.set(1, 2, 3);
    frameModel(camera, controls, new Group());
    expect(camera.position.toArray()).toEqual([5, 6, 7]);
    expect(controls.target.toArray()).toEqual([1, 2, 3]);
  });

  it('keeps tiny geometry in front of the near clipping plane', () => {
    const model = new Mesh(new BoxGeometry(0.001, 0.001, 0.001), new MeshBasicMaterial());
    const camera = new PerspectiveCamera(42, 0.5);
    const controls = new OrbitControls(camera);
    frameModel(camera, controls, model);
    expect(Number.isFinite(controls.getDistance())).toBe(true);
    expect(controls.getDistance()).toBeGreaterThan(camera.near);
    expect(new Vector3().project(camera).z).toBeGreaterThan(-1);
    expect(new Vector3().project(camera).z).toBeLessThan(1);
    disposeSceneResources(model);
  });
});

describe('scene precision configuration', () => {
  it('allows orbit positions above, beside and below a panned target', () => {
    const camera = new PerspectiveCamera();
    const controls = new OrbitControls(camera);
    configureOrbitControls(controls);
    controls.target.set(12, 7, -3);

    for (const angle of [0.001, Math.PI / 4, Math.PI / 2, Math.PI * 0.75, Math.PI - 0.001]) {
      for (const distance of [2, 20]) {
        const offset = new Vector3(0, Math.cos(angle), Math.sin(angle)).multiplyScalar(distance);
        camera.position.copy(controls.target).add(offset);
        controls.update();
        expect(controls.getPolarAngle()).toBeCloseTo(angle);
        expect(camera.position.distanceTo(controls.target)).toBeCloseTo(distance);
        expect(camera.position.clone().sub(controls.target).distanceTo(offset)).toBeLessThan(1e-10);
        expect(Number.isFinite(modelNorthRotation(camera))).toBe(true);
      }
    }

    expect(controls.enableDamping).toBe(true);
    expect(controls.dampingFactor).toBe(0.08);
    expect(controls.screenSpacePanning).toBe(true);
    expect(controls.enablePan).toBe(true);
    expect(controls.enableZoom).toBe(true);
  });

  it.each([
    [0, 10, 0], [10, 0, 90], [0, -10, 180], [-10, 0, -90],
  ])('orients model north for a camera at X=%s, Z=%s', (x, z, degrees) => {
    const camera = new PerspectiveCamera();
    camera.position.set(x, 5, z);
    camera.lookAt(0, 0, 0);
    expect((modelNorthRotation(camera) - degrees + 540) % 360 - 180).toBeCloseTo(0);
  });

  it('keeps compass heading stable during tilt, pan and zoom, including top view', () => {
    const camera = new PerspectiveCamera();
    for (const height of [1, 20, 1000]) {
      camera.position.set(10, height, 10);
      camera.lookAt(0, 0, 0);
      expect(modelNorthRotation(camera)).toBeCloseTo(45);
      camera.position.multiplyScalar(3).add(new Vector3(50, 20, -30));
      expect(modelNorthRotation(camera)).toBeCloseTo(45);
    }
    camera.position.set(0, 10, 0);
    camera.lookAt(0, 0, 0);
    expect(Number.isFinite(modelNorthRotation(camera))).toBe(true);
  });

  it('clips at canonical millimetre coordinates after the Z-up to Y-up transform', () => {
    const viewerPoint = new Vector3(2, 4, -3);
    expect(canonicalSectionPlane('x', 2000).distanceToPoint(viewerPoint)).toBe(0);
    expect(canonicalSectionPlane('y', 3000).distanceToPoint(viewerPoint)).toBe(0);
    expect(canonicalSectionPlane('z', 4000).distanceToPoint(viewerPoint)).toBe(0);
    expect(canonicalSectionPlane('z', 3000).distanceToPoint(viewerPoint)).toBeLessThan(0);
  });

  it('places the shadow light along the selected solar direction', () => {
    const light = new DirectionalLight();
    const sun = new Vector3(0.2, 0.5, -0.8).normalize();
    configureDirectionalShadow(light, MODEL_BOUNDS, sun);
    const actual = light.position.clone().sub(light.target.position).normalize();
    expect(actual.distanceTo(sun)).toBeLessThan(1e-12);
  });
  it('fits a high-resolution biased directional shadow to model bounds', () => {
    const light = new DirectionalLight();

    configureDirectionalShadow(light, MODEL_BOUNDS);

    expect(light.shadow.mapSize.toArray()).toEqual([2048, 2048]);
    expect(light.shadow.bias).toBeLessThan(0);
    expect(light.shadow.normalBias).toBeGreaterThan(0);
    expect(light.target.position.toArray()).toEqual([5, 2.5, -4]);
    expect(light.shadow.camera.right).toBeGreaterThan(5);
    expect(light.shadow.camera.left).toBe(-light.shadow.camera.right);
    expect(light.shadow.camera.far).toBeGreaterThan(light.shadow.camera.near);
  });

  it('uses model-scaled camera planes with a bounded depth ratio', () => {
    const camera = new PerspectiveCamera();
    camera.position.set(15, 12, 14);

    configureCameraDepth(camera, MODEL_BOUNDS);

    expect(camera.near).toBe(0.05);
    expect(camera.far).toBe(200);
    expect(camera.far / camera.near).toBeLessThanOrEqual(4000);
  });
});
