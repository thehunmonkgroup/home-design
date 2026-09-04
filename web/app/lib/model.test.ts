import { describe, expect, it } from 'vitest';
import { Group, Mesh } from 'three';
import {
  applyElementVisibility,
  defaultHiddenElementIds,
  elementIdForObject,
  formatMetric,
  groupElements,
  isRenderManifest,
  nodeElementIndex,
  type RenderManifest,
} from './model';

const manifest: RenderManifest = {
  format: 'home-design-render-manifest-0.1',
  modelVersion: '0.1',
  sourceRevision: 3,
  project: { id: 'project.test', name: 'Test home' },
  coordinateTransform: {
    source: 'right-handed Z-up millimetres',
    target: 'right-handed Y-up metres',
    mapping: ['x/1000', 'z/1000', '-y/1000'],
  },
  elements: {
    'roof.main': { kind: 'roof', name: 'Main roof', storeyId: 'level.ground', nodes: ['roof.main#1'], defaultVisible: true, data: {} },
    'space.living': { kind: 'space', name: 'Living space', storeyId: 'level.ground', nodes: ['space.living'], defaultVisible: false, data: {} },
    'wall.north': { kind: 'wall', name: 'North wall', storeyId: 'level.ground', nodes: ['wall.north'], defaultVisible: true, data: {} },
  },
};

describe('render manifest helpers', () => {
  it('rejects incompatible payloads and accepts the contract shape', () => {
    expect(isRenderManifest({ ...manifest, format: 'unknown' })).toBe(false);
    expect(isRenderManifest(manifest)).toBe(true);
  });

  it('groups components in architectural display order', () => {
    expect(groupElements(manifest).map((group) => group.kind)).toEqual(['wall', 'roof', 'space']);
  });

  it('derives initial hidden state from manifest defaults', () => {
    expect([...defaultHiddenElementIds(manifest)]).toEqual(['space.living']);
  });

  it('applies component visibility to every generated scene node', () => {
    const root = new Group();
    const firstRoofFace = new Group();
    firstRoofFace.name = 'roof.main#1';
    const secondRoofFace = new Group();
    secondRoofFace.name = 'roof.main#2';
    root.add(firstRoofFace, secondRoofFace);

    applyElementVisibility(
      root,
      { ...manifest.elements['roof.main'], nodes: ['roof.main#1', 'roof.main#2'] },
      false,
    );

    expect(firstRoofFace.visible).toBe(false);
    expect(secondRoofFace.visible).toBe(false);
  });

  it('resolves a selected descendant through a named scene ancestor', () => {
    const root = new Group();
    root.name = 'wall.north';
    const mesh = new Mesh();
    root.add(mesh);
    expect(elementIdForObject(mesh, nodeElementIndex(manifest))).toBe('wall.north');
  });

  it('formats design lengths without inventing precision', () => {
    expect(formatMetric(185)).toBe('185 mm');
    expect(formatMetric(2700)).toBe('2.7 m');
    expect(formatMetric('2700')).toBeNull();
  });
});
