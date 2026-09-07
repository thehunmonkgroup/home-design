import { generatedElementIds, groupElements, type ElementGroup, type NavigationLink, type RenderManifest } from './model';

export type NavigationGrouping = 'kind' | 'assembly' | 'room' | 'host' | 'system';
export type ReviewScope = 'contents' | 'system' | 'connected';

const CONTENT_LINKS = new Set<NavigationLink['kind']>(['assembly', 'room', 'host', 'ownership', 'system', 'generated']);

export function contextElementIds(manifest: RenderManifest, identity: string, scope: ReviewScope = 'contents'): string[] {
  const links = manifest.navigation?.links ?? [];
  const selected = new Set<string>(manifest.elements[identity] ? [identity] : []);
  if (scope === 'system') {
    for (const link of links) if (link.sourceId === identity && link.kind === 'system') selected.add(link.targetId);
  }
  const pending = [...selected];
  for (let index = 0; index < pending.length; index++) {
    const current = pending[index];
    for (const link of links) {
      const adjacent = scope === 'connected' && link.kind === 'connection'
        ? link.sourceId === current ? link.targetId : link.targetId === current ? link.sourceId : null
        : link.targetId === current && CONTENT_LINKS.has(link.kind) ? link.sourceId : null;
      if (adjacent && manifest.elements[adjacent] && !selected.has(adjacent)) {
        selected.add(adjacent);
        pending.push(adjacent);
      }
    }
  }
  return [...generatedElementIds(manifest, selected)];
}

export function relatedElements(manifest: RenderManifest, identity: string): Array<{ id: string; label: string; kind: NavigationLink['kind'] }> {
  const result = new Map<string, { id: string; label: string; kind: NavigationLink['kind'] }>();
  for (const link of manifest.navigation?.links ?? []) {
    const id = link.sourceId === identity ? link.targetId : link.targetId === identity ? link.sourceId : null;
    if (!id || !manifest.elements[id]) continue;
    result.set(`${link.kind}:${id}`, { id, label: link.sourceId === identity ? link.sourceLabel : link.targetLabel, kind: link.kind });
  }
  return [...result.values()].sort((left, right) => left.label.localeCompare(right.label) || manifest.elements[left.id].name.localeCompare(manifest.elements[right.id].name));
}

export function navigationGroups(manifest: RenderManifest, grouping: NavigationGrouping, includeGenerated = false): ElementGroup[] {
  if (grouping === 'kind') return groupElements(manifest, includeGenerated);
  const links = manifest.navigation?.links ?? [];
  const containers = new Set(links.filter((link) => link.kind === grouping && manifest.elements[link.targetId]).map((link) => link.targetId));
  const grouped = new Set<string>();
  const result: ElementGroup[] = [];
  for (const id of [...containers].sort((left, right) => manifest.elements[left].name.localeCompare(manifest.elements[right].name))) {
    const root = manifest.elements[id];
    if (!root) continue;
    const ids = contextElementIds(manifest, id).filter((child) => child === id || includeGenerated || !manifest.elements[child].parentId);
    ids.forEach((child) => grouped.add(child));
    result.push({ id, kind: root.kind, label: root.name, elements: ids.map((child) => [child, manifest.elements[child]]) });
  }
  const rest = Object.entries(manifest.elements).filter(([id, element]) => !grouped.has(id) && (includeGenerated || !element.parentId));
  if (rest.length) result.push({ id: 'ungrouped', kind: 'other', label: 'Other components', elements: rest });
  return result;
}

export function selectionNodes(manifest: RenderManifest, identity: string): string[] {
  const own = manifest.elements[identity]?.nodes ?? [];
  if (own.length) return own;
  return [...new Set(contextElementIds(manifest, identity).flatMap((id) => manifest.elements[id].nodes))];
}
