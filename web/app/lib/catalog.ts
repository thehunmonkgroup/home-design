import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { isRenderManifest, type RenderManifest } from './model';
import { disposeSceneResources } from './scene';
import type { Group } from 'three';

export interface CatalogModel {
  key: string;
  name: string;
  sourceRevision: number;
  version: string;
  baseUrl: string;
  compressedAssets?: Record<'model.glb' | 'render-manifest.json', number>;
}

export interface ModelLoadProgress {
  phase: 'downloading' | 'preparing';
  loadedBytes: number;
  totalBytes?: number;
}

export interface ModelCatalog {
  format: 'home-design-model-catalog-0.1';
  models: CatalogModel[];
}

export function parseCatalog(value: unknown): ModelCatalog {
  if (!value || typeof value !== 'object' || !('format' in value) ||
    value.format !== 'home-design-model-catalog-0.1' || !('models' in value) || !Array.isArray(value.models)) {
    throw new Error('The model catalog has an unsupported format');
  }
  const keys = new Set<string>();
  for (const entry of value.models) {
    if (!entry || typeof entry !== 'object' || typeof entry.key !== 'string' || !entry.key ||
      ['.', '..'].includes(entry.key) || /[/\\]/.test(entry.key) || keys.has(entry.key) ||
      typeof entry.name !== 'string' || !Number.isInteger(entry.sourceRevision) ||
      typeof entry.version !== 'string' || !/^[a-f0-9]{64}$/.test(entry.version) ||
      entry.baseUrl !== `${encodeURIComponent(entry.key).replace(/[!'()*]/g, (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`)}/${entry.version}/`) {
      throw new Error('The model catalog contains an invalid model entry');
    }
    if (entry.compressedAssets !== undefined && (!entry.compressedAssets ||
      typeof entry.compressedAssets !== 'object' || Array.isArray(entry.compressedAssets) ||
      !['model.glb', 'render-manifest.json'].every((name) =>
        Number.isSafeInteger(entry.compressedAssets[name]) && entry.compressedAssets[name] > 0))) {
      throw new Error('The model catalog contains invalid compressed asset sizes');
    }
    keys.add(entry.key);
  }
  return { format: value.format, models: sortModels(value.models) };
}

export function sortModels(models: CatalogModel[]): CatalogModel[] {
  return [...models].sort((left, right) =>
    left.name.localeCompare(right.name, 'en', { sensitivity: 'base', numeric: true }) ||
    left.key.localeCompare(right.key, 'en'));
}

export function modelLabel(model: CatalogModel, models: CatalogModel[]): string {
  return models.some((other) => other.key !== model.key && other.name === model.name)
    ? `${model.name} (${model.key})` : model.name;
}

export function modelAssetUrl(model: CatalogModel, artifact: string): string {
  if (!/^[a-zA-Z0-9._-]+$/.test(artifact) || artifact === '.' || artifact === '..') {
    throw new Error('Invalid model asset filename');
  }
  return `./model/${model.baseUrl}${artifact}`;
}

async function checkedFetch(url: string, signal: AbortSignal): Promise<Response> {
  const response = await fetch(url, { signal, cache: 'no-cache' });
  if (!response.ok) throw new Error(`Model asset request failed (${response.status})`);
  return response;
}

export async function loadCatalog(signal: AbortSignal): Promise<ModelCatalog> {
  const response = await checkedFetch('./model/index.json', signal);
  return parseCatalog(await response.json());
}

export async function loadModelAssets(
  entry: CatalogModel, signal: AbortSignal, onProgress?: (progress: ModelLoadProgress) => void,
): Promise<{ manifest: RenderManifest; model: Group }> {
  const controller = new AbortController();
  const cancel = () => controller.abort(signal.reason);
  if (signal.aborted) cancel();
  else signal.addEventListener('abort', cancel, { once: true });
  const requestSignal = controller.signal;
  const compressed = Boolean(entry.compressedAssets && typeof DecompressionStream !== 'undefined');
  const names = ['render-manifest.json', 'model.glb'] as const;
  const received = [0, 0];
  const totals: (number | undefined)[] = names.map((name) => compressed ? entry.compressedAssets![name] : undefined);
  const report = (phase: ModelLoadProgress['phase']) => {
    if (requestSignal.aborted) return;
    const loadedBytes = received[0] + received[1];
    const totalBytes = totals.every((size) => size !== undefined) ? totals.reduce<number>((sum, size) => sum + size!, 0) : undefined;
    onProgress?.({ phase, loadedBytes, totalBytes });
  };
  report('downloading');
  try {
    const downloads = await Promise.all(names.map(async (name, index) => {
      const response = await checkedFetch(modelAssetUrl(entry, name + (compressed ? '.gz' : '')), requestSignal);
      const encoded = Boolean(response.headers.get('content-encoding')?.match(/^(?!identity$).+/i));
      const contentLength = Number(response.headers.get('content-length'));
      if (encoded) totals[index] = undefined;
      else if (!compressed && contentLength > 0) totals[index] = contentLength;
      const bytes = await readDownload(response, requestSignal, (count) => {
        received[index] = count;
        if (totals[index] !== undefined && count > totals[index]!) totals[index] = undefined;
        report('downloading');
      });
      return { bytes, encoded };
    }));
    requestSignal.throwIfAborted();
    report('preparing');
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    const [manifestBytes, bytes] = await Promise.all(downloads.map(async ({ bytes, encoded }) => {
      if (!compressed) return bytes;
      if (new Uint8Array(bytes)[0] === 0x1f && new Uint8Array(bytes)[1] === 0x8b) {
        return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
      }
      if (encoded) return bytes;
      throw new Error('The compressed model download is invalid; export and upload the complete website again');
    }));
    requestSignal.throwIfAborted();
    const manifest: unknown = JSON.parse(new TextDecoder().decode(manifestBytes));
    if (!isRenderManifest(manifest)) throw new Error('The render manifest has an unsupported format');
    if (manifest.sourceRevision !== entry.sourceRevision || manifest.project.name !== entry.name) {
      throw new Error('The model assets do not match the catalog; reload the page');
    }
    requestSignal.throwIfAborted();
    const gltf = await new GLTFLoader().parseAsync(bytes, `./model/${entry.baseUrl}`);
    if (requestSignal.aborted) {
      disposeSceneResources(gltf.scene);
      requestSignal.throwIfAborted();
    }
    return { manifest, model: gltf.scene };
  } catch (error) {
    controller.abort();
    throw error;
  } finally {
    signal.removeEventListener('abort', cancel);
  }
}

async function readDownload(response: Response, signal: AbortSignal, progress: (bytes: number) => void): Promise<ArrayBuffer> {
  if (!response.body) {
    const bytes = await response.arrayBuffer();
    signal.throwIfAborted();
    progress(bytes.byteLength);
    return bytes;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal.addEventListener('abort', cancel, { once: true });
  if (signal.aborted) cancel();
  try {
    while (true) {
      signal.throwIfAborted();
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      chunks.push(value);
      length += value.byteLength;
      progress(length);
    }
  } finally {
    signal.removeEventListener('abort', cancel);
    reader.releaseLock();
  }
  const result = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength; }
  progress(length);
  return result.buffer;
}
