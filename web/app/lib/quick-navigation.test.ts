import { describe, expect, it } from 'vitest';
import type { RenderManifest, ManifestElement, NavigationLink } from './model';
import { selectionNeighbors, selectionRelations } from './quick-navigation';

const element = (name: string): ManifestElement => ({ kind: 'assembly', name, nodes: [], defaultVisible: true, storeyId: null, data: {} });
const link = (sourceId: string, targetId: string, kind: NavigationLink['kind']): NavigationLink => ({ sourceId, targetId, kind, sourceLabel: 'Container', targetLabel: 'Contents' });
const manifest: RenderManifest = {
  format: 'home-design-render-manifest-0.1', modelVersion: '0.2', sourceRevision: 1,
  project: { id: 'test', name: 'Test' }, coordinateTransform: { source: 'mm', target: 'm', mapping: ['x', 'z', '-y'] },
  elements: {
    roof: element('Roof'), room: element('Room'),
    frame: { ...element('Rafters'), children: ['a', 'b'] },
    a: { ...element('Rafter A'), parentId: 'frame' }, b: { ...element('Rafter B'), parentId: 'frame' },
    skin: element('Roof covering'), isolated: element('Unrelated'),
  },
  navigation: { format: 'home-design-navigation-0.1', links: [
    link('frame', 'room', 'room'), link('frame', 'roof', 'assembly'), link('skin', 'roof', 'assembly'),
    link('a', 'frame', 'generated'), link('a', 'skin', 'connection'), link('roof', 'roof', 'assembly'),
  ] },
};

describe('quick selection navigation', () => {
  it('climbs from a generated rafter to its group and roof, with immediate children and bounded siblings', () => {
    const relations = selectionRelations(manifest);
    expect(selectionNeighbors(relations, 'a')).toMatchObject({ parent: 'frame', next: 'b', previous: undefined, child: undefined });
    expect(selectionNeighbors(relations, 'b')).toMatchObject({ previous: 'a', next: undefined });
    expect(selectionNeighbors(relations, 'frame')).toMatchObject({ parent: 'roof', child: 'a', next: 'skin' });
    expect(selectionNeighbors(relations, 'roof')).toMatchObject({ parent: undefined, child: 'frame' });
    expect(relations.children.get('roof')).toEqual(['frame', 'skin']);
    expect(relations.children.get('frame')).toEqual(['a', 'b']);
    expect(selectionNeighbors(relations, 'isolated')).toMatchObject({ parent: undefined, child: undefined, next: undefined, previous: undefined });
  });
  it('uses the chosen container and remembers the child on return without following connections', () => {
    const relations = selectionRelations(manifest);
    expect(selectionNeighbors(relations, 'frame', 'room', 'b')).toMatchObject({ parents: ['roof', 'room'], parent: 'room', child: 'b', next: undefined });
    expect(selectionNeighbors(relations, 'frame', 'missing', 'missing')).toMatchObject({ parent: 'roof', child: 'a' });
    expect(relations.parents.get('a')).toEqual(['frame']);
  });
  it('supports generated members in older manifests without navigation links', () => {
    const relations = selectionRelations({ ...manifest, navigation: undefined });
    expect(selectionNeighbors(relations, 'b')).toMatchObject({ parent: 'frame', previous: 'a' });
  });
});
