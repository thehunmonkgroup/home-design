import { useMemo, useState } from 'react';
import type { RenderManifest } from '../lib/model';
import { selectionNeighbors, selectionRelations } from '../lib/quick-navigation';

export default function QuickSelection({ manifest, elementId, hidden, fullyVisible, hasGeometry, onToggle, onSelect, onClear }: {
  manifest: RenderManifest;
  elementId: string;
  hidden: boolean;
  fullyVisible: boolean;
  hasGeometry: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
  onClear: () => void;
}) {
  const relations = useMemo(() => selectionRelations(manifest), [manifest]);
  const [via, setVia] = useState<Record<string, string>>({});
  const [lastChild, setLastChild] = useState<Record<string, string>>({});
  const neighbors = selectionNeighbors(relations, elementId, via[elementId], lastChild[elementId]);
  const name = (id: string) => manifest.elements[id].name;
  const move = (id: string, parent: string, child: string) => {
    setVia((current) => ({ ...current, [child]: parent }));
    setLastChild((current) => ({ ...current, [parent]: child }));
    onSelect(id);
  };
  const up = (id: string) => move(id, id, elementId);
  const arrow = (label: string, glyph: string, shortcut: string, keys: string, id: string | undefined, action: () => void) =>
    <button type="button" aria-label={label} data-shortcut={shortcut} aria-keyshortcuts={hidden ? undefined : keys}
      title={id ? `${label}: ${name(id)} (${keys.replace(' ', ' / ')})` : `No ${label.toLowerCase()}`}
      disabled={!id} onClick={action}><span aria-hidden="true">{glyph}</span><small>{label.replace(' sibling', '')}</small></button>;
  return <section className="quick-selection" aria-label="Quick component controls" data-selection-id={elementId} hidden={hidden}>
    <div className="quick-selection-heading">
      <strong title={`${name(elementId)} — ${elementId}`} aria-live="polite">{name(elementId)}
        {neighbors.total > 1 && <small title={`Within ${name(neighbors.parent!)}`}> · {neighbors.position} of {neighbors.total}</small>}
      </strong>
      <button type="button" aria-label="Clear quick selection" data-shortcut="clear" aria-keyshortcuts={hidden ? undefined : 'Escape'}
        title="Clear selection (Esc)" onClick={onClear}>×</button>
    </div>
    <div className="quick-selection-actions">
      {arrow('Parent', '↑', 'parent', 'ArrowUp k', neighbors.parent, () => up(neighbors.parent!))}
      {arrow('Previous sibling', '←', 'previous', 'ArrowLeft h', neighbors.previous, () => move(neighbors.previous!, neighbors.parent!, neighbors.previous!))}
      <button type="button" className="quick-visibility" data-shortcut="toggle" aria-keyshortcuts={hidden ? undefined : 'Space'}
        aria-label={fullyVisible ? 'Hide' : 'Show'} disabled={!hasGeometry} onClick={onToggle}
        title={`${fullyVisible ? 'Hide' : 'Show'} this component or assembly without moving the camera`}>
        {fullyVisible ? 'Hide' : 'Show'}
        <small aria-hidden="true">Space</small>
      </button>
      {arrow('Next sibling', '→', 'next', 'ArrowRight l', neighbors.next, () => move(neighbors.next!, neighbors.parent!, neighbors.next!))}
      {arrow('Child', '↓', 'child', 'ArrowDown j', neighbors.child, () => move(neighbors.child!, elementId, neighbors.child!))}
    </div>
    {neighbors.parents.length > 1 && <select aria-label="Navigate to parent" value="" onChange={(event) => up(event.target.value)}>
      <option value="" disabled>Choose another parent…</option>
      {neighbors.parents.map((id) => <option key={id} value={id}>{name(id)}</option>)}
    </select>}
  </section>;
}
