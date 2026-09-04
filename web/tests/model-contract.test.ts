import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { isRenderManifest, nodeElementIndex } from '../app/lib/model';

describe('Python to TypeScript render contract', () => {
  it('loads the generated reference manifest with unique stable scene nodes', async () => {
    const path = resolve(process.cwd(), 'tests/fixtures/reference-render-manifest.json');
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
