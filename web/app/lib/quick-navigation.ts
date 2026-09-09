import type { RenderManifest } from './model';

export interface SelectionRelations {
  parents: Map<string, string[]>;
  children: Map<string, string[]>;
}

/** Immediate construction relationships, without flattening assemblies or inventing a tree. */
export function selectionRelations(manifest: RenderManifest): SelectionRelations {
  const parents = new Map<string, string[]>();
  const children = new Map<string, string[]>();
  const add = (child: string, parent: string) => {
    if (child === parent || !manifest.elements[child] || !manifest.elements[parent]) return;
    if (!parents.has(child)) parents.set(child, []);
    if (!children.has(parent)) children.set(parent, []);
    if (!parents.get(child)!.includes(parent)) parents.get(child)!.push(parent);
    if (!children.get(parent)!.includes(child)) children.get(parent)!.push(child);
  };
  for (const [id, element] of Object.entries(manifest.elements)) {
    for (const child of element.children ?? []) add(child, id);
    if (element.parentId) add(id, element.parentId);
  }
  for (const kind of ['generated', 'assembly', 'host', 'ownership', 'room', 'system']) {
    for (const link of manifest.navigation?.links ?? []) {
      if (link.kind === kind) add(link.sourceId, link.targetId);
    }
  }
  return { parents, children };
}

export function selectionNeighbors(relations: SelectionRelations, id: string, via?: string, lastChild?: string) {
  const parents = relations.parents.get(id) ?? [];
  const parent = via && parents.includes(via) ? via : parents[0];
  const children = relations.children.get(id) ?? [];
  const child = lastChild && children.includes(lastChild) ? lastChild : children[0];
  const siblings = parent ? relations.children.get(parent) ?? [] : [];
  const index = siblings.indexOf(id);
  return { parents, parent, child, position: index + 1, total: siblings.length, previous: index > 0 ? siblings[index - 1] : undefined, next: index >= 0 ? siblings[index + 1] : undefined };
}
