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
  entry: CatalogModel, signal: AbortSignal,
): Promise<{ manifest: RenderManifest; model: Group }> {
  const [manifest, bytes]: [unknown, ArrayBuffer] = await Promise.all([
    checkedFetch(modelAssetUrl(entry, 'render-manifest.json'), signal).then((response) => response.json()),
    checkedFetch(modelAssetUrl(entry, 'model.glb'), signal).then((response) => response.arrayBuffer()),
  ]);
  if (!isRenderManifest(manifest)) throw new Error('The render manifest has an unsupported format');
  if (manifest.sourceRevision !== entry.sourceRevision || manifest.project.name !== entry.name) {
    throw new Error('The model assets do not match the catalog; reload the page');
  }
  signal.throwIfAborted();
  const gltf = await new GLTFLoader().parseAsync(bytes, `./model/${entry.baseUrl}`);
  if (signal.aborted) {
    disposeSceneResources(gltf.scene);
    signal.throwIfAborted();
  }
  return { manifest, model: gltf.scene };
}
