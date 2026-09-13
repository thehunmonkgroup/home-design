import type { VisualView } from './visual-view';

export interface SavedViewGroup {
  id: string;
  title: string;
  order: number;
}

export interface NamedView {
  id: string;
  title: string;
  description: string;
  file: string;
  view: VisualView;
  group?: SavedViewGroup;
}

export interface SavedViewSection {
  group?: SavedViewGroup;
  views: NamedView[];
}

export function validSavedViewGroups(entries: readonly { group?: unknown }[]): boolean {
  const groups = new Map<string, SavedViewGroup>();
  for (const entry of entries) {
    if (entry.group === undefined) continue;
    if (!entry.group || typeof entry.group !== 'object' || Array.isArray(entry.group)) return false;
    const group = entry.group as SavedViewGroup;
    if (Object.keys(group).some((key) => !['id', 'title', 'order'].includes(key)) ||
        typeof group.id !== 'string' || !/^[a-z][a-z0-9-]*$/.test(group.id) ||
        typeof group.title !== 'string' || !group.title.trim() || !Number.isInteger(group.order)) return false;
    const previous = groups.get(group.id);
    if (previous && (previous.title !== group.title || previous.order !== group.order)) return false;
    groups.set(group.id, group);
  }
  return true;
}

const alphabetical = new Intl.Collator('en', { sensitivity: 'base', numeric: true });

function compareNames(a: { title: string; id: string }, b: { title: string; id: string }): number {
  return alphabetical.compare(a.title, b.title) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
}

export function groupSavedViews(views: readonly NamedView[]): SavedViewSection[] {
  const groups = new Map<string, SavedViewSection>();
  const ungrouped: NamedView[] = [];
  for (const view of views) {
    if (!view.group) {
      ungrouped.push(view);
      continue;
    }
    let section = groups.get(view.group.id);
    if (!section) {
      section = { group: view.group, views: [] };
      groups.set(view.group.id, section);
    }
    section.views.push(view);
  }
  const sections = [...groups.values()].sort((a, b) =>
    a.group!.order - b.group!.order || compareNames(a.group!, b.group!));
  if (ungrouped.length) sections.push({ views: ungrouped });
  sections.forEach((section) => section.views.sort(compareNames));
  return sections;
}
