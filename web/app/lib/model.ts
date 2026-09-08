import type { Object3D } from 'three';

type KnownElementKind =
  | 'assembly'
  | 'member'
  | 'framing'
  | 'wallFraming'
  | 'planarFraming'
  | 'memberAssembly'
  | 'curvedMember'
  | 'hardware'
  | 'masonryPart'
  | 'accessory'
  | 'envelopePart'
  | 'clearanceZone'
  | 'barrierCheck'
  | 'serviceDevice'
  | 'serviceRoute'
  | 'serviceFitting'
  | 'serviceInsulation'
  | 'serviceSystem'
  | 'serviceCircuit'
  | 'reinforcingBar'
  | 'reinforcingMesh'
  | 'fastenerGroup'
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
  | 'penetration'
  | 'roof'
  | 'slab'
  | 'space'
  | 'wall'
  | 'window';

export type ElementKind = KnownElementKind | (string & Record<never, never>);

export interface ManifestElement {
  kind: ElementKind;
  kindLabel?: string;
  name: string;
  storeyId: string | null;
  nodes: string[];
  defaultVisible: boolean;
  data: Record<string, unknown>;
  parentId?: string;
  children?: string[];
  properties?: DisplayProperty[];
}

export interface DisplayProperty {
  id: string;
  label: string;
  value: number | string;
  unit: string | null;
  group: string;
}

export interface NavigationLink {
  sourceId: string;
  targetId: string;
  kind: 'assembly' | 'room' | 'host' | 'ownership' | 'system' | 'connection' | 'support' | 'placement' | 'reference' | 'generated';
  sourceLabel: string;
  targetLabel: string;
  path?: string;
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
  meshes?: Record<string, { elementId: string; role: string; materialId: string | null; layerId?: string | number; inspectionCap?: boolean; capOf?: string; section?: { axis: 'x' | 'y' | 'z'; position: number; keep: 'below' | 'above' } }>;
  namedViews?: Array<{ id: string; title: string; description: string; file: string; view: import('./visual-view').VisualView }>;
  requirements?: DesignRequirement[];
  requirementResults?: RequirementResult[];
  solarStudies?: SolarStudy[];
  reports?: { schedules: string; envelope: string; drawings: string };
  navigation?: { format: 'home-design-navigation-0.1'; links: NavigationLink[] };
  propertyFormat?: 'home-design-view-properties-0.1';
  storeys?: Record<string, { name?: string }>;
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
  id?: string;
  kind: ElementKind;
  label: string;
  elements: Array<[string, ManifestElement]>;
}

const KIND_LABELS: Partial<Record<ElementKind, string>> = {
  assembly: 'Assemblies',
  member: 'Structural members',
  framing: 'Framing',
  wallFraming: 'Wall framing',
  planarFraming: 'Floor and roof framing',
  memberAssembly: 'Trusses and member assemblies',
  curvedMember: 'Curved structural members',
  hardware: 'Connection hardware',
  masonryPart: 'Masonry and grout',
  accessory: 'Interior accessories',
  envelopePart: 'Envelope interfaces',
  clearanceZone: 'Access and clearance zones',
  barrierCheck: 'Barrier continuity checks',
  serviceDevice: 'Service devices',
  serviceRoute: 'Service routes',
  serviceFitting: 'Service fittings',
  serviceInsulation: 'Service insulation',
  serviceSystem: 'Service systems',
  serviceCircuit: 'Service circuits',
  reinforcingBar: 'Reinforcing bars and ties',
  reinforcingMesh: 'Reinforcement mesh',
  fastenerGroup: 'Fastener groups',
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
  penetration: 'Penetrations & recesses',
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
  'penetration',
  'assembly',
  'member',
  'framing',
  'wallFraming',
  'planarFraming',
  'memberAssembly',
  'curvedMember',
  'hardware',
  'masonryPart',
  'accessory',
  'envelopePart',
  'clearanceZone',
  'barrierCheck',
  'serviceDevice',
  'serviceRoute',
  'serviceFitting',
  'serviceInsulation',
  'serviceSystem',
  'serviceCircuit',
  'reinforcingBar',
  'reinforcingMesh',
  'fastenerGroup',
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
    typeof candidate.elements === 'object' &&
    !Array.isArray(candidate.elements) &&
    Object.values(candidate.elements).every(isManifestElement) &&
    Object.entries(candidate.elements).every(([id, element]) =>
      (!element.parentId || Boolean(candidate.elements?.[element.parentId])) &&
      (element.children ?? []).every((child) => candidate.elements?.[child]?.parentId === id)) &&
    (candidate.meshes === undefined || Boolean(candidate.meshes) && typeof candidate.meshes === 'object' && !Array.isArray(candidate.meshes) &&
      Object.entries(candidate.meshes).every(([node, mesh]) => mesh &&
        typeof mesh.elementId === 'string' && Boolean(candidate.elements?.[mesh.elementId]?.nodes.includes(node)) &&
        typeof mesh.role === 'string' && (mesh.materialId === null || typeof mesh.materialId === 'string') &&
        (mesh.layerId === undefined || typeof mesh.layerId === 'string' || Number.isInteger(mesh.layerId) && Number(mesh.layerId) >= 0) &&
        (mesh.inspectionCap === undefined || mesh.inspectionCap === true && typeof mesh.capOf === 'string' && Boolean(candidate.meshes?.[mesh.capOf]) && Boolean(mesh.section) &&
          ['x', 'y', 'z'].includes(mesh.section!.axis) && Number.isFinite(mesh.section!.position) && ['below', 'above'].includes(mesh.section!.keep)))) &&
    (candidate.namedViews === undefined || Array.isArray(candidate.namedViews) &&
      new Set(candidate.namedViews.map((view) => view?.id)).size === candidate.namedViews.length &&
      candidate.namedViews.every((entry) => entry && typeof entry.id === 'string' && /^[a-z][a-z0-9-]*$/.test(entry.id) &&
        typeof entry.title === 'string' && Boolean(entry.title) && typeof entry.description === 'string' &&
        typeof entry.file === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_-]*\.json$/.test(entry.file) &&
        entry.view && typeof entry.view === 'object' && !Array.isArray(entry.view))) &&
    (candidate.navigation === undefined || validNavigation(candidate.navigation, candidate.elements)) &&
    (candidate.propertyFormat === undefined || candidate.propertyFormat === 'home-design-view-properties-0.1')
  );
}

function isManifestElement(value: unknown): value is ManifestElement {
  if (!value || typeof value !== 'object') return false;
  const element = value as Partial<ManifestElement>;
  return typeof element.kind === 'string' && typeof element.name === 'string'
    && (element.storeyId === null || typeof element.storeyId === 'string')
    && Array.isArray(element.nodes) && element.nodes.every((node) => typeof node === 'string')
    && typeof element.defaultVisible === 'boolean' && Boolean(element.data) && typeof element.data === 'object' && !Array.isArray(element.data)
    && (element.parentId === undefined || typeof element.parentId === 'string')
    && (element.children === undefined || Array.isArray(element.children) && element.children.every((child) => typeof child === 'string'))
    && (element.properties === undefined || Array.isArray(element.properties) && element.properties.every((property) =>
      property && typeof property.id === 'string' && typeof property.label === 'string' && typeof property.group === 'string'
      && (property.unit === null || typeof property.unit === 'string')
      && (typeof property.value === 'string' || typeof property.value === 'number' && Number.isFinite(property.value))));
}

function validNavigation(navigation: NonNullable<RenderManifest['navigation']>, elements: Record<string, ManifestElement>): boolean {
  return navigation !== null && navigation.format === 'home-design-navigation-0.1' && Array.isArray(navigation.links)
    && navigation.links.every((link) => link && Boolean(elements[link.sourceId]) && Boolean(elements[link.targetId])
      && ['assembly', 'room', 'host', 'ownership', 'system', 'connection', 'support', 'placement', 'reference', 'generated'].includes(link.kind)
      && typeof link.sourceLabel === 'string' && typeof link.targetLabel === 'string');
}

export function groupElements(manifest: RenderManifest, includeGenerated = false): ElementGroup[] {
  const entries = Object.entries(manifest.elements).filter(([, element]) => includeGenerated || !element.parentId);
  const kinds = [...new Set(entries.map(([, element]) => element.kind))];
  const order = new Map(KIND_ORDER.map((kind, index) => [kind, index]));
  kinds.sort((left, right) =>
    (order.get(left) ?? Infinity) - (order.get(right) ?? Infinity) || left.localeCompare(right),
  );
  return kinds.map((kind) => ({
    kind,
    label: entries.find(([, element]) => element.kind === kind)?.[1].kindLabel ?? KIND_LABELS[kind] ?? kind,
    elements: entries
      .filter(([, element]) => element.kind === kind)
      .sort(([, left], [, right]) => left.name.localeCompare(right.name)),
  }));
}

export function nodeElementIndex(manifest: RenderManifest): Map<string, string> {
  const index = new Map<string, string>();
  for (const [elementId, element] of Object.entries(manifest.elements).sort(([, left], [, right]) => Number(Boolean(left.parentId)) - Number(Boolean(right.parentId)))) {
    for (const node of element.nodes) index.set(node, elementId);
  }
  return index;
}

export function filterElementGroups(groups: ElementGroup[], query: string): ElementGroup[] {
  const term = query.trim().toLocaleLowerCase();
  if (!term) return groups;
  return groups.map((group) => ({
    ...group,
    elements: group.elements.filter(([id, element]) =>
      id.toLocaleLowerCase().includes(term) || element.name.toLocaleLowerCase().includes(term)),
  })).filter((group) => group.elements.length > 0);
}

export function isolateElements(manifest: RenderManifest, elementIds: Iterable<string>): Set<string> {
  const visibleIds = generatedElementIds(manifest, elementIds);
  return new Set(Object.entries(manifest.elements)
    .filter(([id, element]) => canToggleVisibility(element) && !visibleIds.has(id))
    .map(([id]) => id));
}

export function canToggleVisibility(element: ManifestElement): boolean {
  return element.nodes.length > 0;
}

export type ReviewPreset = 'envelope' | 'framing' | 'services';

export function reviewElementIds(manifest: RenderManifest, preset: ReviewPreset): string[] {
  return Object.entries(manifest.elements).filter(([, element]) => {
    if (!canToggleVisibility(element) || element.kind === 'space') return false;
    let discipline = element.data.discipline;
    if (typeof discipline !== 'string') {
      if (['member', 'framing', 'wallFraming', 'planarFraming', 'memberAssembly', 'curvedMember', 'hardware', 'fastenerGroup', 'masonryPart', 'reinforcingBar', 'reinforcingMesh', 'footing', 'stair'].includes(element.kind)) discipline = 'framing';
      else if (element.kind === 'terrain') discipline = 'site';
      else if (element.kind === 'sweep' && ['gutter', 'downspout', 'drain', 'interceptor'].includes(String(element.data.role))) discipline = 'services';
      else discipline = 'envelope';
    }
    return discipline === preset || (preset === 'envelope' && discipline === 'accessories');
  }).map(([id]) => id);
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
  for (const id of generatedElementIds(manifest, elementIds)) {
    const element = manifest.elements[id];
    if (!element || !canToggleVisibility(element)) continue;
    if (visible) next.delete(id);
    else next.add(id);
  }
  return next;
}

export function generatedElementIds(manifest: RenderManifest, ids: Iterable<string>): Set<string> {
  const result = new Set(ids);
  const pending = [...result];
  for (let index = 0; index < pending.length; index++) {
    for (const child of manifest.elements[pending[index]]?.children ?? []) {
      if (!result.has(child) && manifest.elements[child]) {
        result.add(child);
        pending.push(child);
      }
    }
  }
  return result;
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
