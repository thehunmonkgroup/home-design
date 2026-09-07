import { describe, expect, it } from 'vitest';
import { Group, Mesh } from 'three';
import { applyElementVisibility, isRenderManifest, isolateElements, nodeElementIndex, withElementVisibility, type ManifestElement, type NavigationLink, type RenderManifest } from './model';
import { contextElementIds, navigationGroups, relatedElements, selectionNodes } from './navigation';

function element(name: string, nodes: string[] = []): ManifestElement {
  return { kind: 'member', name, nodes, storeyId: null, defaultVisible: true, data: {} };
}

const link = (sourceId: string, targetId: string, kind: NavigationLink['kind']): NavigationLink => ({ sourceId, targetId, kind, sourceLabel: 'Belongs to', targetLabel: 'Contains' });

export const navigationFixture: RenderManifest = {
  format: 'home-design-render-manifest-0.1', modelVersion: '0.2', sourceRevision: 4,
  project: { id: 'project.test', name: 'Test' }, coordinateTransform: { source: 'mm', target: 'm', mapping: ['x', 'z', '-y'] },
  elements: {
    group: { ...element('Partition package'), kind: 'assembly' },
    room: { ...element('Living room', ['room']), kind: 'space', defaultVisible: false },
    wall: { ...element('Partition', ['wall']), kind: 'wall' },
    frame: { ...element('Studs', ['stud1', 'stud2']), kind: 'wallFraming', children: ['first', 'second'] },
    first: { ...element('First stud', ['stud1']), parentId: 'frame' },
    second: { ...element('Second stud', ['stud2']), parentId: 'frame' },
    box: { ...element('Electrical box', ['box']), kind: 'serviceDevice' },
    cut: { ...element('Box recess'), kind: 'penetration' },
    system: { ...element('Power system'), kind: 'serviceSystem' },
    wire: { ...element('Cable', ['wire']), kind: 'serviceRoute' },
    outside: element('Unrelated member', ['outside']),
  },
  navigation: { format: 'home-design-navigation-0.1', links: [link('wall', 'group', 'assembly'), link('wall', 'room', 'room'), link('frame', 'wall', 'host'), link('first', 'frame', 'generated'), link('second', 'frame', 'generated'), link('box', 'wall', 'host'), link('cut', 'box', 'ownership'), link('box', 'system', 'system'), link('wire', 'system', 'system'), link('wire', 'box', 'connection')] },
};

describe('construction navigation', () => {
  it('isolates a wall with its hosted and owned contents without pulling in a whole room or system', () => {
    const selected = contextElementIds(navigationFixture, 'wall');
    expect(new Set(selected)).toEqual(new Set(['wall', 'frame', 'first', 'second', 'box', 'cut']));
    expect(isolateElements(navigationFixture, selected)).toEqual(new Set(['room', 'wire', 'outside']));
    expect(contextElementIds(navigationFixture, 'box', 'system')).toEqual(expect.arrayContaining(['system', 'box', 'wire', 'cut']));
    expect(contextElementIds(navigationFixture, 'box', 'system')).not.toContain('wall');
  });

  it('exposes nested assembly/room geometry and links in both directions', () => {
    expect(selectionNodes(navigationFixture, 'group')).toEqual(expect.arrayContaining(['wall', 'stud1', 'box']));
    expect(relatedElements(navigationFixture, 'wall')).toEqual(expect.arrayContaining([{ id: 'group', label: 'Belongs to', kind: 'assembly' }, { id: 'frame', label: 'Contains', kind: 'host' }]));
    expect(navigationGroups(navigationFixture, 'system')[0].label).toBe('Power system');
    expect(navigationGroups(navigationFixture, 'kind').flatMap((group) => group.elements.map(([id]) => id))).not.toContain('first');
    expect(navigationGroups(navigationFixture, 'kind', true).flatMap((group) => group.elements.map(([id]) => id))).toContain('first');
  });

  it('keeps individual member visibility and picking correct regardless of manifest key order', () => {
    const reordered = { ...navigationFixture, elements: Object.fromEntries(Object.entries(navigationFixture.elements).reverse()) };
    expect(nodeElementIndex(reordered).get('stud1')).toBe('first');
    const hidden = withElementVisibility(reordered, new Set(), ['frame'], false);
    expect(hidden).toEqual(new Set(['frame', 'first', 'second']));
    const restored = withElementVisibility(reordered, hidden, ['first'], true);
    const root = new Group();
    for (const name of ['stud1', 'stud2']) { const mesh = new Mesh(); mesh.name = name; root.add(mesh); }
    for (const [id, value] of Object.entries(reordered.elements).sort(([, left], [, right]) => Number(Boolean(left.parentId)) - Number(Boolean(right.parentId)))) applyElementVisibility(root, value, !restored.has(id));
    expect(root.getObjectByName('stud1')?.visible).toBe(true);
    expect(root.getObjectByName('stud2')?.visible).toBe(false);
    expect(isolateElements(reordered, ['first'])).toContain('second');
  });

  it('rejects malformed properties and missing link or generated-child participants', () => {
    expect(isRenderManifest(navigationFixture)).toBe(true);
    expect(isRenderManifest({ ...navigationFixture, elements: { wall: { ...navigationFixture.elements.wall, nodes: [2] } } })).toBe(false);
    expect(isRenderManifest({ ...navigationFixture, navigation: { ...navigationFixture.navigation, links: [link('missing', 'wall', 'host')] } })).toBe(false);
    expect(isRenderManifest({ ...navigationFixture, elements: { frame: navigationFixture.elements.frame } })).toBe(false);
  });
});
