import { describe, expect, it } from 'vitest';
import { Group, Mesh } from 'three';
import {
  applyElementVisibility,
  canToggleVisibility,
  defaultHiddenElementIds,
  elementIdForObject,
  formatMetric,
  formatProperty,
  filterElementGroups,
  groupElements,
  isolateElements,
  isRenderManifest,
  nodeElementIndex,
  reviewElementIds,
  withElementVisibility,
  type ElementKind,
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
  it('keeps service insulation independently selectable in the services view', () => {
    const parts: RenderManifest = { ...manifest, elements: {
      cover: { kind: 'serviceInsulation', name: 'Pipe insulation', storeyId: null, nodes: ['cover'], defaultVisible: true, data: { discipline: 'services' } },
      pipe: { kind: 'serviceRoute', name: 'Pipe', storeyId: null, nodes: ['pipe'], defaultVisible: true, data: { discipline: 'services' } },
    } };
    expect(isRenderManifest(parts)).toBe(true);
    expect(groupElements(parts).map((group) => group.label)).toEqual(['Service routes', 'Service insulation']);
    expect(reviewElementIds(parts, 'services')).toEqual(['cover', 'pipe']);
    expect([...isolateElements(parts, ['pipe'])]).toEqual(['cover']);
  });
  it('provides discipline views without exposing space or property-only geometry', () => {
    const parts: RenderManifest = { ...manifest, elements: {
      ...manifest.elements,
      'stud': { kind: 'member', name: 'Stud', storeyId: null, nodes: ['stud'], defaultVisible: true, data: {} },
      'run': { kind: 'sweep', name: 'Drain', storeyId: null, nodes: ['run'], defaultVisible: true, data: { role: 'drain' } },
      'box': { kind: 'member', name: 'Service box', storeyId: null, nodes: ['box'], defaultVisible: true, data: { discipline: 'services' } },
      'detail': { kind: 'detail', name: 'Service detail', storeyId: null, nodes: [], defaultVisible: true, data: { discipline: 'services' } },
      'shelf': { kind: 'member', name: 'Shelf', storeyId: null, nodes: ['shelf'], defaultVisible: true, data: { discipline: 'accessories' } },
    } };
    expect(reviewElementIds(parts, 'framing')).toEqual(['stud']);
    expect(reviewElementIds(parts, 'services')).toEqual(['run', 'box']);
    expect(reviewElementIds(parts, 'envelope')).toEqual(['roof.main', 'wall.north', 'shelf']);
    const hidden = isolateElements(parts, reviewElementIds(parts, 'framing'));
    expect(hidden.has('wall.north')).toBe(true);
    expect(hidden.has('stud')).toBe(false);
    expect(hidden.has('detail')).toBe(false);
  });
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

  it('filters names and IDs without case sensitivity and retains only matching sections', () => {
    const groups = groupElements(manifest);
    expect(filterElementGroups(groups, '  MAIN ROOF  ').map((group) => group.kind)).toEqual(['roof']);
    expect(filterElementGroups(groups, 'WALL.NORTH')[0].elements[0][0]).toBe('wall.north');
    expect(filterElementGroups(groups, 'north')[0].label).toBe('Walls');
    expect(filterElementGroups(groups, 'no-such-component')).toEqual([]);
    expect(filterElementGroups(groups, '   ')).toBe(groups);
    expect(groups).toHaveLength(3);
  });

  it('isolates a group and lets later individual visibility edits keep the remaining isolation', () => {
    const isolated = isolateElements(manifest, ['wall.north', 'roof.main']);
    expect(isolated).toEqual(new Set(['space.living']));
    const edited = withElementVisibility(manifest, isolated, ['wall.north'], false);
    expect(edited).toEqual(new Set(['space.living', 'wall.north']));
    expect(withElementVisibility(manifest, edited, ['wall.north'], true)).toEqual(isolated);
    expect(isolateElements(manifest, ['space.living'])).toEqual(new Set(['wall.north', 'roof.main']));
  });

  it('does not hide property-only entries during isolation', () => {
    const mixed = { ...manifest, elements: {
      ...manifest.elements,
      'space.record': { ...manifest.elements['space.living'], nodes: [] },
    } };
    expect(isolateElements(mixed, ['roof.main'])).toEqual(new Set(['wall.north', 'space.living']));
  });

  it.each<ElementKind>(['wall', 'opening', 'load', 'detail', 'assembly', 'space'])(
    'derives visibility capability from nodes rather than the %s kind or default visibility',
    (kind) => {
      for (const defaultVisible of [true, false]) {
        const element = { ...manifest.elements['wall.north'], kind, defaultVisible };
        expect(canToggleVisibility({ ...element, nodes: [] })).toBe(false);
        expect(canToggleVisibility({ ...element, nodes: ['test.geometry'] })).toBe(true);
      }
    },
  );

  it('keeps geometry-free records inspectable without initial hidden state', () => {
    const mixed: RenderManifest = {
      ...manifest,
      elements: {
        ...manifest.elements,
        'space.record': { ...manifest.elements['space.living'], nodes: [] },
      },
    };
    expect([...defaultHiddenElementIds(mixed)]).toEqual(['space.living']);
    expect(groupElements(mixed).flatMap((group) => group.elements.map(([id]) => id)))
      .toContain('space.record');
  });

  it('updates single and bulk visibility only for geometry-bearing records', () => {
    const mixed: RenderManifest = {
      ...manifest,
      elements: {
        ...manifest.elements,
        'space.record': { ...manifest.elements['space.living'], nodes: [] },
      },
    };
    const initial = defaultHiddenElementIds(mixed);
    const unchanged = withElementVisibility(mixed, initial, ['space.record', 'missing'], false);
    expect(unchanged).toEqual(initial);
    const hidden = withElementVisibility(mixed, initial, ['wall.north'], false);
    expect([...hidden]).toEqual(['space.living', 'wall.north']);
    expect([...initial]).toEqual(['space.living']);

    const allIds = Object.keys(mixed.elements);
    const allHidden = withElementVisibility(mixed, hidden, allIds, false);
    expect(allHidden).toEqual(new Set(['roof.main', 'wall.north', 'space.living']));
    expect(withElementVisibility(mixed, allHidden, allIds, true)).toEqual(new Set());
    expect([...allHidden]).toHaveLength(3);
  });

  it('discards stale or geometry-free hidden IDs during visibility updates', () => {
    const changed: RenderManifest = {
      ...manifest,
      elements: {
        ...manifest.elements,
        'wall.north': { ...manifest.elements['wall.north'], nodes: [] },
      },
    };
    const hidden = new Set(['space.living', 'wall.north', 'missing']);
    expect(withElementVisibility(changed, hidden, ['roof.main'], false))
      .toEqual(new Set(['space.living', 'roof.main']));
    expect(hidden.size).toBe(3);
  });

  it('leaves scene geometry untouched when toggling a nonvisual record', () => {
    const root = new Group();
    const mesh = new Mesh();
    mesh.name = 'wall.north';
    root.add(mesh);
    applyElementVisibility(root, { ...manifest.elements['wall.north'], nodes: [] }, false);
    expect(mesh.visible).toBe(true);
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

  it('distinguishes counts, forces, areas and lengths in construction metadata', () => {
    expect(formatProperty('riserCount', 16)).toBe('16');
    expect(formatProperty('forceN', 12000)).toBe('12 kN');
    expect(formatProperty('netArea', 12500000)).toBe('12.5 m²');
    expect(formatProperty('volume', 2000000000)).toBe('2 m³');
    expect(formatProperty('clearWidth', 1220)).toBe('1.22 m');
  });
});
