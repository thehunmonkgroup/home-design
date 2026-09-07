import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { isRenderManifest, nodeElementIndex } from '../app/lib/model';
import { contextElementIds, navigationGroups } from '../app/lib/navigation';
import { formatDisplayProperty } from '../app/lib/properties';

describe('Python to TypeScript render contract', () => {
  it('loads dimensioned properties, construction links and generated IDs from the public Python export', async () => {
    const manifest: unknown = JSON.parse(await readFile(resolve(process.cwd(), 'tests/fixtures/component-navigation.json'), 'utf8'));
    expect(isRenderManifest(manifest)).toBe(true);
    if (!isRenderManifest(manifest)) return;
    const wall = 'electrical.wall.host';
    const frame = 'framing.partition';
    const children = manifest.elements[frame].children!;
    expect(children.length).toBeGreaterThan(10);
    expect(contextElementIds(manifest, wall)).toEqual(expect.arrayContaining([frame, ...children, 'electrical.device.flushBox', 'electrical.cut.flushBox']));
    const child = manifest.elements[children[0]];
    expect(nodeElementIndex(manifest).get(child.nodes[0])).toBe(children[0]);
    expect(child.parentId).toBe(frame);
    expect(child.properties!.some((property) => property.unit === 'mm3')).toBe(true);
    const length = child.properties!.find((property) => property.id === '/lengthMm')!;
    expect(formatDisplayProperty(length, 'imperial')).toContain(' ft ');
    expect(navigationGroups(manifest, 'host').some((group) => group.id === wall)).toBe(true);
    expect(navigationGroups(manifest, 'assembly').some((group) => group.id === 'assembly.roof-system')).toBe(true);
  });
  it('loads the generated reference manifest with unique stable scene nodes', async () => {
    const path = resolve(process.cwd(), 'tests/fixtures/single-story-gable-house-render-manifest.json');
    const manifest: unknown = JSON.parse(await readFile(path, 'utf8'));
    expect(isRenderManifest(manifest)).toBe(true);
    if (!isRenderManifest(manifest)) return;
    const nodes = Object.values(manifest.elements).flatMap((element) => element.nodes);
    expect(new Set(nodes).size).toBe(nodes.length);
    expect(nodeElementIndex(manifest).size).toBe(nodes.length);
    expect(manifest.elements['opening.window.north'].nodes).toEqual([]);
    expect(manifest.elements['wall.north'].nodes.length).toBeGreaterThan(0);
  });
});
