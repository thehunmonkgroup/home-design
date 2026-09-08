import { describe, expect, it } from 'vitest';
import { Box3, BoxGeometry, Group, Mesh, MeshBasicMaterial, Vector3 } from 'three';
import { clippedBounds, inspectionCamera, selectorNodes, toCanonical, viewPlanes, visibleNodes, type VisualView } from './visual-view';
import type { RenderManifest } from './model';

const manifest: RenderManifest = {
  format: 'home-design-render-manifest-0.1', modelVersion: '0.2', sourceRevision: 1,
  project: { id: 'test', name: 'Test' }, coordinateTransform: { source: '', target: '', mapping: ['', '', ''] },
  elements: {
    wall: { kind: 'wall', name: 'Wall', storeyId: 'ground', nodes: ['finish', 'core'], defaultVisible: true, data: {} },
    studs: { kind: 'wallFraming', name: 'Studs', storeyId: 'ground', nodes: ['stud'], defaultVisible: true, data: {}, children: ['studs/member/a'] },
    'studs/member/a': { kind: 'member', name: 'Stud A', storeyId: 'ground', nodes: ['stud'], defaultVisible: true, data: {}, parentId: 'studs' },
    probe: { kind: 'barrierCheck', name: 'Probe', storeyId: 'ground', nodes: ['probe'], defaultVisible: false, data: {} },
  },
  storeys: { ground: { name: 'Ground' } },
  meshes: {
    finish: { elementId: 'wall', role: 'layer:0', materialId: 'gypsum', layerId: 'finish' },
    core: { elementId: 'wall', role: 'layer:1', materialId: 'insulation', layerId: 'cavity' },
    stud: { elementId: 'studs/member/a', role: 'stud:a', materialId: 'wood' },
    probe: { elementId: 'probe', role: 'coordination', materialId: null },
  },
  navigation: { format: 'home-design-navigation-0.1', links: [{ sourceId: 'studs', targetId: 'wall', kind: 'host', sourceLabel: 'Host', targetLabel: 'Contents' }] },
};

describe('visual selectors', () => {
  it('retains hosted members while hiding only a named finish', () => {
    expect([...visibleNodes(manifest, { isolate: { ids: ['wall'], contents: true }, hide: [{ layers: [{ elementId: 'wall', layerId: 'finish' }] }] })].sort()).toEqual(['core', 'stud']);
  });
  it('isolates generated children and keeps probes hidden unless requested', () => {
    expect([...visibleNodes(manifest, { isolate: { ids: ['studs/member/a'] } })]).toEqual(['stud']);
    expect(visibleNodes(manifest, {}).has('probe')).toBe(false);
    expect(visibleNodes(manifest, { show: [{ ids: ['probe'] }] }).has('probe')).toBe(true);
  });
  it('reveals contents independently from whole-model discipline presets', () => {
    expect([...visibleNodes(manifest, { reveal: { id: 'wall', mode: 'contents' } })]).toEqual(['stud']);
  });
  it('rejects selectors that could silently produce misleading views', () => {
    for (const selector of [{ ids: ['missing'] }, { kinds: ['roof'] }, { storeys: ['attic'] }, { materials: ['steel'] }, { layers: [{ elementId: 'wall', layerId: 'missing' }] }]) {
      expect(() => selectorNodes(manifest, selector)).toThrow();
    }
    expect(() => visibleNodes(manifest, { hide: [{ ids: ['wall', 'studs'] }] })).toThrow('all geometry');
  });
});

describe('section and camera geometry', () => {
  it('fits the retained triangle geometry after a canonical millimetre cut', () => {
    const model = new Group(); const mesh = new Mesh(new BoxGeometry(2, 2, 2), new MeshBasicMaterial()); mesh.name = 'box'; model.add(mesh);
    const below = clippedBounds(model, new Set(['box']), viewPlanes({ sections: [{ axis: 'z', position: 250 }] })).get('box')!;
    expect(below.max.y).toBeCloseTo(0.25);
    expect(below.min.y).toBe(-1);
    const above = clippedBounds(model, new Set(['box']), viewPlanes({ sections: [{ axis: 'z', position: 250, keep: 'above' }] })).get('box')!;
    expect(above.min.y).toBeCloseTo(0.25);
    expect(above.max.y).toBe(1);
    expect(() => clippedBounds(model, new Set(['box']), viewPlanes({ sections: [{ axis: 'z', position: -2000 }] }))).toThrow('remove all');
  });
  it.each(['perspective', 'orthographic'] as const)('frames all corners with %s projection and enough depth precision for thin layers', (projection) => {
    const bounds = new Box3(new Vector3(-5, -0.2, -8), new Vector3(5, 5, 0));
    const view: VisualView = { width: 1280, height: 960, camera: { projection, preset: 'se' } };
    const camera = inspectionCamera(view, bounds);
    expect(camera.near).toBeGreaterThan(1);
    for (const x of [bounds.min.x, bounds.max.x]) for (const y of [bounds.min.y, bounds.max.y]) for (const z of [bounds.min.z, bounds.max.z]) {
      const point = new Vector3(x, y, z).project(camera);
      expect(Math.abs(point.x)).toBeLessThan(1); expect(Math.abs(point.y)).toBeLessThan(1); expect(Math.abs(point.z)).toBeLessThan(1);
    }
  });
  it('uses exact interior camera positions and rejects an ambiguous up direction', () => {
    const bounds = new Box3(new Vector3(0, 0, -8), new Vector3(10, 3, 0));
    const camera = inspectionCamera({ camera: { position: [2000, 2000, 1600], target: [8000, 4000, 1600] } }, bounds);
    expect(toCanonical(camera.position)).toEqual([2000, 2000, 1600]);
    expect(() => inspectionCamera({ camera: { position: [0, 0, 0], target: [0, 0, 1000] } }, bounds)).toThrow('nondegenerate');
  });
});
