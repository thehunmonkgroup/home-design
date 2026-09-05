import type { Object3D } from 'three';

export type ElementKind =
  | 'assembly'
  | 'member'
  | 'framing'
  | 'footing'
  | 'stair'
  | 'railing'
  | 'panel'
  | 'terrain'
  | 'sweep'
  | 'load'
  | 'detail'
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
  requirements?: DesignRequirement[];
  requirementResults?: RequirementResult[];
  solarStudies?: SolarStudy[];
  reports?: { schedules: string; envelope: string; drawings: string };
}

export interface DesignRequirement {
  id: string;
  statement: string;
  severity: string;
  appliesTo?: string[];
  check?: { property: string; operator: 'atMost' | 'atLeast' | 'equals'; value: number };
}

export interface RequirementResult {
  id: string;
  status: 'satisfied' | 'violated' | 'notChecked';
  checks: Array<{
    elementId: string;
    property: string;
    operator: 'atMost' | 'atLeast' | 'equals';
    expected: number;
    actual: unknown;
    status: 'satisfied' | 'violated';
  }>;
}

export function requirementStatusLabel(result?: RequirementResult): string {
  switch (result?.status) {
    case 'satisfied': return 'Satisfied';
    case 'violated': return 'Violated';
    case 'notChecked': return 'Not automatically checked';
    default: return 'Status unavailable';
  }
}

export interface SolarStudy {
  id: string;
  name: string;
  at: string;
  altitudeDegrees: number;
  azimuthDegrees: number;
  sunDirection: [number, number, number];
  openings: Array<{ elementId: string; facesSun: boolean; unshadedFraction: number; sampleCount: number }>;
}

export interface ElementGroup {
  kind: ElementKind;
  label: string;
  elements: Array<[string, ManifestElement]>;
}

const KIND_LABELS: Record<ElementKind, string> = {
  assembly: 'Assemblies',
  member: 'Structural members',
  framing: 'Framing',
  footing: 'Footings',
  stair: 'Stairs',
  railing: 'Guards & handrails',
  panel: 'Screens & panels',
  terrain: 'Terrain',
  sweep: 'Drainage & trim',
  load: 'Design loads',
  detail: 'Interface details',
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
  'member',
  'framing',
  'footing',
  'stair',
  'railing',
  'panel',
  'terrain',
  'sweep',
  'load',
  'detail',
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

export function canToggleVisibility(element: ManifestElement): boolean {
  return element.nodes.length > 0;
}

export function defaultHiddenElementIds(manifest: RenderManifest): Set<string> {
  return new Set(
    Object.entries(manifest.elements)
      .filter(([, element]) => canToggleVisibility(element) && !element.defaultVisible)
      .map(([elementId]) => elementId),
  );
}

export function withElementVisibility(
  manifest: RenderManifest,
  hiddenIds: ReadonlySet<string>,
  elementIds: Iterable<string>,
  visible: boolean,
): Set<string> {
  const next = new Set([...hiddenIds].filter((id) => {
    const element = manifest.elements[id];
    return element && canToggleVisibility(element);
  }));
  for (const id of elementIds) {
    const element = manifest.elements[id];
    if (!element || !canToggleVisibility(element)) continue;
    if (visible) next.delete(id);
    else next.add(id);
  }
  return next;
}

export function applyElementVisibility(
  root: Object3D,
  element: ManifestElement,
  visible: boolean,
): void {
  if (!canToggleVisibility(element)) return;
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

export function formatProperty(key: string, value: unknown): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  if (/area$/i.test(key)) return formatMetric(value / 1e6, 'm²');
  if (/volume$/i.test(key)) return formatMetric(value / 1e9, 'm³');
  if (key === 'forceN' || key === 'capacityN') return formatMetric(value / 1000, 'kN');
  if (/degrees$|angle$|^pitch$|^roll$/i.test(key)) return formatMetric(value, '°');
  if (/length$|width$|height$|depth$|thickness$|elevation$|spacing$|^station$|^run$|^rise$/i.test(key)) return formatMetric(value);
  return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
}
