import { afterEach, describe, expect, it, vi } from 'vitest';
import { BoxGeometry, Group, Mesh, MeshStandardMaterial, Texture } from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { initialModelKey, loadCatalog, loadModelAssets, modelAssetUrl, modelLabel, parseCatalog, sortModels, type CatalogModel } from './catalog';
import { disposeSceneResources } from './scene';
import { gzipSync } from 'node:zlib';
import type { ModelLoadProgress } from './catalog';

const version = 'a'.repeat(64);
const entry: CatalogModel = {
  key: 'sample', name: 'Sample home', sourceRevision: 2, version,
  baseUrl: `sample/${version}/`,
};

describe('initial model selection from a URL', () => {
  const other: CatalogModel = { ...entry, key: 'other', name: 'Other home', baseUrl: `other/${version}/` };

  it('defaults to the first catalog entry only when the parameter is absent', () => {
    expect(initialModelKey([entry, other], null)).toBe(entry.key);
    expect(initialModelKey([], null)).toBe('');
  });

  it('accepts an exact key or unique project name', () => {
    expect(initialModelKey([entry, other], 'other')).toBe(other.key);
    expect(initialModelKey([entry, other], 'Other home')).toBe(other.key);
  });

  it('prefers an exact key when another model has that project name', () => {
    expect(initialModelKey([{ ...entry, name: other.key }, other], other.key)).toBe(other.key);
  });

  it('requires a key when project names are duplicated', () => {
    const models = [entry, { ...other, name: entry.name }];
    expect(() => initialModelKey(models, entry.name)).toThrow('matches more than one model');
    expect(initialModelKey(models, other.key)).toBe(other.key);
  });

  it.each(['', 'missing', 'SAMPLE', '../sample'])('rejects an unmatched value %s without loading another home', (requested) => {
    expect(() => initialModelKey([entry], requested)).toThrow('was not found');
  });
});

const manifest = {
  format: 'home-design-render-manifest-0.1', modelVersion: '0.1', sourceRevision: 2,
  project: { id: 'project.sample', name: entry.name }, elements: {},
};

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('model catalog', () => {
  it('sorts human names independently of filenames, with stable ties', () => {
    const models = [
      { ...entry, key: 'a', name: 'Zulu' },
      { ...entry, key: 'z', name: 'alpha' },
      { ...entry, key: 'b', name: 'alpha' },
    ];
    expect(sortModels(models).map((model) => model.key)).toEqual(['b', 'z', 'a']);
    expect(models[0].key).toBe('a');
    expect(modelLabel(models[1], models)).toBe('alpha (z)');
    expect(modelLabel(models[0], models)).toBe('Zulu');
  });

  it('accepts empty catalogs and URL-encoded filenames', () => {
    expect(parseCatalog({ format: 'home-design-model-catalog-0.1', models: [] }).models).toEqual([]);
    const special = { ...entry, key: 'Home ! café', baseUrl: `Home%20%21%20caf%C3%A9/${version}/` };
    const catalog = parseCatalog({ format: 'home-design-model-catalog-0.1', models: [special] });
    expect(modelAssetUrl(catalog.models[0], 'drawings.svg')).toBe(`./model/${special.baseUrl}drawings.svg`);
  });

  it.each([
    { format: 'unknown', models: [] },
    { format: 'home-design-model-catalog-0.1', models: [entry, entry] },
    { format: 'home-design-model-catalog-0.1', models: [{ ...entry, baseUrl: 'https://example.com/' }] },
    { format: 'home-design-model-catalog-0.1', models: [{ ...entry, key: '..' }] },
    { format: 'home-design-model-catalog-0.1', models: [{ ...entry, sourceRevision: '2' }] },
    ...[null, [], {}, { 'model.glb': -1, 'render-manifest.json': 1 }, { 'model.glb': 1, 'render-manifest.json': 1.5 }].map(compressedAssets => ({ format: 'home-design-model-catalog-0.1', models: [{ ...entry, compressedAssets }] })),
  ])('rejects malformed or unsafe catalogs', (value) => {
    expect(() => parseCatalog(value)).toThrow();
  });

  it('rejects report paths outside the active asset directory', () => {
    expect(() => modelAssetUrl(entry, '../other/schedules.json')).toThrow();
  });

  it.each(['https://example.com/', 'https://example.com/homes/', 'https://example.com/homes/index.html'])('keeps all model URLs under the website at %s', async (base) => {
    const expectedRoot = new URL('./', base);
    const requests: string[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      requests.push(new URL(url, base).href);
      return Promise.resolve(new Response(JSON.stringify({
        format: 'home-design-model-catalog-0.1', models: [entry],
      })));
    }));
    await loadCatalog(new AbortController().signal);
    expect(requests).toEqual([new URL('model/index.json', expectedRoot).href]);
    for (const artifact of ['model.glb', 'render-manifest.json', 'drawings.svg', 'schedules.json', 'envelope.json']) {
      expect(new URL(modelAssetUrl(entry, artifact), base).href).toBe(
        new URL(`model/${entry.baseUrl}${artifact}`, expectedRoot).href,
      );
    }
  });

  it('loads catalog metadata without preloading geometry', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      format: 'home-design-model-catalog-0.1', models: [entry],
    })));
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();
    expect((await loadCatalog(controller.signal)).models).toEqual([entry]);
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('./model/index.json', {
      signal: controller.signal, cache: 'no-cache',
    });
  });
});

describe('model asset lifecycle', () => {
  const geometry = new Uint8Array([103, 108, 84, 70, 2, 0, 0, 0]);
  const packedModel = gzipSync(geometry);
  const packedManifest = gzipSync(JSON.stringify(manifest));
  const packedEntry: CatalogModel = { ...entry, compressedAssets: {
    'model.glb': packedModel.byteLength, 'render-manifest.json': packedManifest.byteLength,
  } };

  it('streams compressed downloads with aggregate progress and decodes exact original bytes', async () => {
    let finishModel!: () => void;
    const halfway = Math.floor(packedModel.byteLength / 2);
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.endsWith('model.glb.gz')
      ? new Response(new ReadableStream({ start(controller) {
        controller.enqueue(packedModel.subarray(0, halfway));
        finishModel = () => { controller.enqueue(packedModel.subarray(halfway)); controller.close(); };
      } })) : new Response(packedManifest)));
    vi.stubGlobal('fetch', fetchMock);
    const parse = vi.spyOn(GLTFLoader.prototype, 'parseAsync').mockResolvedValue({ scene: new Group() } as GLTF);
    const progress: ModelLoadProgress[] = [];
    const loading = loadModelAssets(packedEntry, new AbortController().signal, (value) => progress.push(value));
    await vi.waitFor(() => expect(progress.some(value => value.loadedBytes === packedManifest.length + halfway)).toBe(true));
    expect(parse).not.toHaveBeenCalled();
    finishModel();
    expect((await loading).manifest).toEqual(manifest);
    expect(new Uint8Array(parse.mock.calls[0][0] as ArrayBuffer)).toEqual(geometry);
    expect(progress[0]).toEqual({ phase: 'downloading', loadedBytes: 0, totalBytes: packedModel.length + packedManifest.length });
    expect(progress.at(-1)).toEqual({ phase: 'preparing', loadedBytes: packedModel.length + packedManifest.length, totalBytes: packedModel.length + packedManifest.length });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      `./model/${entry.baseUrl}render-manifest.json.gz`, `./model/${entry.baseUrl}model.glb.gz`,
    ]);
  });

  it('uses original assets when decompression is unavailable', async () => {
    vi.stubGlobal('DecompressionStream', undefined);
    const fetchMock = mockAssets();
    vi.spyOn(GLTFLoader.prototype, 'parseAsync').mockResolvedValue({ scene: new Group() } as GLTF);
    await loadModelAssets(packedEntry, new AbortController().signal);
    expect(fetchMock.mock.calls.every(([url]) => !url.endsWith('.gz'))).toBe(true);
  });

  it('accepts gzip already decoded by HTTP and avoids claiming encoded-byte percentages', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(
      url.endsWith('model.glb.gz') ? geometry : JSON.stringify(manifest),
      { headers: { 'content-encoding': 'gzip' } },
    ))));
    const progress: ModelLoadProgress[] = [];
    vi.spyOn(GLTFLoader.prototype, 'parseAsync').mockResolvedValue({ scene: new Group() } as GLTF);
    expect((await loadModelAssets(packedEntry, new AbortController().signal, value => progress.push(value))).manifest).toEqual(manifest);
    expect(progress.at(-1)?.totalBytes).toBeUndefined();
  });

  it('rejects corrupt compressed assets without falling back to a second large download', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('invalid gzip'))));
    const parse = vi.spyOn(GLTFLoader.prototype, 'parseAsync');
    await expect(loadModelAssets(packedEntry, new AbortController().signal)).rejects.toThrow('compressed model download is invalid');
    expect(parse).not.toHaveBeenCalled();
  });

  it('cancels pending streams on model switch and suppresses late progress', async () => {
    const cancel = vi.fn();
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(new ReadableStream({ cancel })))));
    const controller = new AbortController();
    const progress = vi.fn();
    const loading = loadModelAssets(packedEntry, controller.signal, progress);
    const rejection = expect(loading).rejects.toThrow();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    controller.abort();
    const count = progress.mock.calls.length;
    await rejection;
    expect(cancel).toHaveBeenCalledTimes(2);
    expect(progress).toHaveBeenCalledTimes(count);
  });

  function mockAssets(value: unknown = manifest) {
    const fetchMock = vi.fn((url: string) => Promise.resolve(
      url.endsWith('.json') ? new Response(JSON.stringify(value)) : new Response(new ArrayBuffer(0)),
    ));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
  }

  it('loads the selected model and manifest from the same version', async () => {
    const fetchMock = mockAssets();
    const model = new Group();
    vi.spyOn(GLTFLoader.prototype, 'parseAsync').mockResolvedValue({ scene: model } as GLTF);
    const loaded = await loadModelAssets(entry, new AbortController().signal);
    expect(loaded).toEqual({ manifest, model });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      `./model/${entry.baseUrl}render-manifest.json`, `./model/${entry.baseUrl}model.glb`,
    ]);
  });

  it('rejects mismatched revisions before allocating geometry', async () => {
    mockAssets({ ...manifest, sourceRevision: 3 });
    const parse = vi.spyOn(GLTFLoader.prototype, 'parseAsync');
    await expect(loadModelAssets(entry, new AbortController().signal)).rejects.toThrow('do not match');
    expect(parse).not.toHaveBeenCalled();
  });

  it('reports missing assets', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })));
    await expect(loadModelAssets(entry, new AbortController().signal)).rejects.toThrow('404');
  });

  it('disposes geometry that finishes parsing after a switch aborts the request', async () => {
    mockAssets();
    const controller = new AbortController();
    const mesh = new Mesh(new BoxGeometry(), new MeshStandardMaterial());
    const model = new Group().add(mesh);
    const disposeGeometry = vi.spyOn(mesh.geometry, 'dispose');
    const disposeMaterial = vi.spyOn(mesh.material, 'dispose');
    vi.spyOn(GLTFLoader.prototype, 'parseAsync').mockImplementation(async () => {
      controller.abort();
      return { scene: model } as GLTF;
    });
    await expect(loadModelAssets(entry, controller.signal)).rejects.toThrow();
    expect(disposeGeometry).toHaveBeenCalledOnce();
    expect(disposeMaterial).toHaveBeenCalledOnce();
  });

  it('releases shared GPU resources exactly once', () => {
    const texture = new Texture();
    const material = new MeshStandardMaterial({ map: texture });
    const geometry = new BoxGeometry();
    const model = new Group().add(new Mesh(geometry, material), new Mesh(geometry, material));
    const release = [texture, material, geometry].map((resource) => vi.spyOn(resource, 'dispose'));
    disposeSceneResources(model);
    for (const spy of release) expect(spy).toHaveBeenCalledOnce();
  });
});
