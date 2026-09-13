import { groupSavedViews, type NamedView } from '../lib/saved-view-groups';

export function SavedViewOptions({ views }: { views: readonly NamedView[] }) {
  const sections = groupSavedViews(views);
  const grouped = sections.some((section) => section.group);
  return sections.map((section) => {
    const options = section.views.map((view) => <option key={view.id} value={view.id}>{view.title}</option>);
    return grouped
      ? <optgroup key={section.group ? `group:${section.group.id}` : 'ungrouped'} label={section.group?.title ?? 'Other views'}>{options}</optgroup>
      : options;
  });
}
