import type { Object3D } from 'three';

export type ElementKind =
  | 'assembly'
  | 'door'
  | 'opening'
  | 'roof'
  | 'slab'
  | 'space'
  | 'wall'
  | 'window';

export interface ManifestElement {
  kind: ElementKind;
  name: string;
  storeyId: string | null;
  nodes: string[];
  defaultVisible: boolean;
  data: Record<string, unknown>;
}

export interface RenderManifest {
  format: 'home-design-render-manifest-0.1';
  modelVersion: string;
  sourceRevision: number;
  project: { id: string; name: string };
  coordinateTransform: {
    source: string;
    target: string;
    mapping: [string, string, string];
  };
  elements: Record<string, ManifestElement>;
}

export interface ElementGroup {
  kind: ElementKind;
  label: string;
  elements: Array<[string, ManifestElement]>;
}

const KIND_LABELS: Record<ElementKind, string> = {
  assembly: 'Assemblies',
  door: 'Doors',
  opening: 'Openings',
  roof: 'Roofs',
  slab: 'Slabs & decks',
  space: 'Spaces',
  wall: 'Walls',
  window: 'Windows',
};

const KIND_ORDER: ElementKind[] = [
  'wall',
  'slab',
  'roof',
  'door',
  'window',
  'space',
  'opening',
  'assembly',
];

export function isRenderManifest(value: unknown): value is RenderManifest {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<RenderManifest>;
  return (
    candidate.format === 'home-design-render-manifest-0.1' &&
    typeof candidate.modelVersion === 'string' &&
    Number.isInteger(candidate.sourceRevision) &&
    !!candidate.project &&
    typeof candidate.project.name === 'string' &&
    !!candidate.elements &&
    typeof candidate.elements === 'object'
  );
}

export function groupElements(manifest: RenderManifest): ElementGroup[] {
  const entries = Object.entries(manifest.elements);
  return KIND_ORDER.map((kind) => ({
    kind,
    label: KIND_LABELS[kind],
    elements: entries
      .filter(([, element]) => element.kind === kind)
      .sort(([, left], [, right]) => left.name.localeCompare(right.name)),
  })).filter((group) => group.elements.length > 0);
}

export function nodeElementIndex(manifest: RenderManifest): Map<string, string> {
  const index = new Map<string, string>();
  for (const [elementId, element] of Object.entries(manifest.elements)) {
    for (const node of element.nodes) index.set(node, elementId);
  }
  return index;
}

export function defaultHiddenElementIds(manifest: RenderManifest): Set<string> {
  return new Set(
    Object.entries(manifest.elements)
      .filter(([, element]) => !element.defaultVisible)
      .map(([elementId]) => elementId),
  );
}

export function applyElementVisibility(
  root: Object3D,
  element: ManifestElement,
  visible: boolean,
): void {
  for (const nodeName of element.nodes) {
    const object = root.getObjectByName(nodeName);
    if (object) object.visible = visible;
  }
}

export function elementIdForObject(
  object: Object3D | null,
  index: ReadonlyMap<string, string>,
): string | null {
  let current = object;
  while (current) {
    const exact = index.get(current.name);
    if (exact) return exact;
    current = current.parent;
  }
  return null;
}

export function formatMetric(value: unknown, unit = 'mm'): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  if (unit === 'mm' && Math.abs(value) >= 1000) {
    return `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 })} m`;
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${unit}`;
}
