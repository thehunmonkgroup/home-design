import { describe, expect, it } from 'vitest';
import { BoxGeometry, Group, Mesh, MeshStandardMaterial, OrthographicCamera, PerspectiveCamera } from 'three';
import { NamedViewPresentation } from './named-views';
import { visibleNodes } from './visual-view';
import { isObjectVisible } from './scene';
import type { RenderManifest } from './model';

function fixture() {
  const model = new Group();
  for (const name of ['wall', 'cap', 'other']) {
    const mesh = new Mesh(new BoxGeometry(1, 2, 1), new MeshStandardMaterial());
    mesh.name = name; model.add(mesh);
  }
  const manifest: RenderManifest = {
    format: 'home-design-render-manifest-0.1', modelVersion: '0.2', sourceRevision: 1,
    project: { id: 'test', name: 'Test' }, coordinateTransform: { source: '', target: '', mapping: ['', '', ''] },
    elements: {
      wall: { kind: 'wall', name: 'Wall', storeyId: null, nodes: ['wall', 'cap'], defaultVisible: true, data: {} },
      other: { kind: 'wall', name: 'Other wall', storeyId: null, nodes: ['other'], defaultVisible: true, data: {} },
    },
    meshes: {
      wall: { elementId: 'wall', role: 'body', materialId: 'wood' },
      other: { elementId: 'other', role: 'body', materialId: 'wood' },
      cap: { elementId: 'wall', role: 'body', materialId: 'wood', inspectionCap: true, capOf: 'wall', section: { axis: 'z', position: 500, keep: 'below' } },
    },
  };
  return { model, manifest };
}

describe('named view presentation', () => {
  it('does not pick decoration belonging to a hidden layer', () => {
    const { model, manifest } = fixture();
    const presentation = new NamedViewPresentation();
    presentation.apply(model, manifest, { isolate: { ids: ['wall'] } }, 800, 600);
    const other = model.getObjectByName('other')!;
    expect(other.children).toHaveLength(1);
    expect(other.children[0].visible).toBe(true);
    expect(isObjectVisible(other.children[0])).toBe(false);
    presentation.clear();
  });
  it('shows caps only for their active plane and visible owner', () => {
    const { manifest } = fixture();
    expect(visibleNodes(manifest, {}).has('cap')).toBe(false);
    expect(visibleNodes(manifest, { sections: [{ axis: 'z', position: 500 }] }).has('cap')).toBe(true);
    expect(visibleNodes(manifest, { sections: [{ axis: 'z', position: 501 }] }).has('cap')).toBe(false);
    expect(visibleNodes(manifest, { sections: [{ axis: 'z', position: 500 }], hide: [{ ids: ['wall'] }] }).has('cap')).toBe(false);
    expect(visibleNodes(manifest, { sections: [{ axis: 'z', position: 500 }], sectionCaps: false }).has('cap')).toBe(false);
  });
  it('restores materials and switches cameras, cuts and visibility independently', () => {
    const { model, manifest } = fixture();
    const presentation = new NamedViewPresentation();
    const wall = model.getObjectByName('wall') as Mesh;
    const original = wall.material;
    const plan = presentation.apply(model, manifest, { camera: { preset: 'top', projection: 'orthographic' }, sections: [{ axis: 'z', position: 500 }], isolate: { ids: ['wall'] }, highlight: { ids: ['wall'] } }, 800, 600);
    expect(plan.camera).toBeInstanceOf(OrthographicCamera);
    expect(plan.planes).toHaveLength(1);
    expect(model.getObjectByName('other')!.visible).toBe(false);
    expect(wall.material).not.toBe(original);
    expect(wall.material).toBeInstanceOf(MeshStandardMaterial);
    expect((wall.material as MeshStandardMaterial).color.getHexString()).toBe('ffc14d');
    const overview = presentation.apply(model, manifest, { edges: false }, 600, 800);
    expect(overview.camera).toBeInstanceOf(PerspectiveCamera);
    expect(overview.planes).toHaveLength(0);
    expect(model.getObjectByName('other')!.visible).toBe(true);
    expect(model.getObjectByName('cap')!.visible).toBe(false);
    expect(wall.material).toBe(original);
    expect(wall.children).toHaveLength(0);
    presentation.clear();
  });
  it('preserves the current geometry on invalid or empty views', () => {
    const { model, manifest } = fixture();
    const presentation = new NamedViewPresentation();
    presentation.apply(model, manifest, { isolate: { ids: ['wall'] } }, 800, 600);
    const before = model.children.map((object) => object.visible);
    expect(() => presentation.apply(model, manifest, { sections: [{ axis: 'z', position: -2000 }] }, 800, 600)).toThrow();
    expect(model.children.map((object) => object.visible)).toEqual(before);
    presentation.clear();
  });
});
