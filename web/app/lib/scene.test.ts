import { describe, expect, it } from 'vitest';
import { Box3, DirectionalLight, PerspectiveCamera, Vector3 } from 'three';
import { configureCameraDepth, configureDirectionalShadow } from './scene';

const MODEL_BOUNDS = new Box3(new Vector3(0, 0, -8), new Vector3(10, 5, 0));

describe('scene precision configuration', () => {
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
