import { useState } from 'react';
import { canToggleVisibility, formatProperty, type RenderManifest } from '../lib/model';
import { relatedElements, type ReviewScope } from '../lib/navigation';
import { formatDisplayProperty, type DisplayUnits } from '../lib/properties';

export default function ElementDetails({ elementId, manifest, units, onUnits, onSelect, onIsolate }: {
  elementId: string;
  manifest: RenderManifest;
  units: DisplayUnits;
  onUnits: (units: DisplayUnits) => void;
  onSelect: (id: string) => void;
  onIsolate: (scope: ReviewScope | 'reveal') => void;
}) {
  const element = manifest.elements[elementId];
  const [limit, setLimit] = useState(20);
  const [memberQuery, setMemberQuery] = useState('');
  const [memberLimit, setMemberLimit] = useState(30);
  const relations = relatedElements(manifest, elementId).filter((entry) => entry.kind !== 'generated');
  const children = (element.children ?? []).filter((id) => {
    const child = manifest.elements[id];
    return child && `${id} ${child.name} ${child.data.constructionRole ?? ''}`.toLowerCase().includes(memberQuery.toLowerCase());
  });
  const hasSystem = ['serviceSystem', 'serviceCircuit'].includes(element.kind) || relations.some((entry) => entry.kind === 'system');
  const measurements = element.properties?.map((property) => ({ id: property.id, label: property.label, value: formatDisplayProperty(property, units) }))
    ?? Object.entries(element.data).flatMap(([key, value]) => {
      const formatted = formatProperty(key, value);
      return formatted ? [{ id: key, label: key.replace(/([A-Z])/g, ' $1'), value: formatted }] : [];
    });
  return <div className="element-details">
    <h3>{element.name}</h3>
    <code>{elementId}</code>
    {element.parentId && <button className="related-link parent-link" onClick={() => onSelect(element.parentId!)}>Back to {manifest.elements[element.parentId]?.name ?? 'assembly'}</button>}
    {!canToggleVisibility(element) && <p className="component-note">This component groups or describes other parts. Select its contents to review geometry.</p>}
    <label className="display-units">Display units
      <select aria-label="Display units" value={units} onChange={(event) => onUnits(event.target.value as DisplayUnits)}>
        <option value="metric">Metric</option><option value="imperial">Feet and inches</option>
      </select>
    </label>
    {manifest.navigation && <div className="context-actions">
      <button onClick={() => onIsolate('contents')}>Isolate with contents</button>
      {element.kind === 'wall' && <button onClick={() => onIsolate('reveal')}>Reveal wall contents</button>}
      {hasSystem && <button onClick={() => onIsolate('system')}>Isolate system</button>}
      {relations.some((entry) => entry.kind === 'connection') && <button onClick={() => onIsolate('connected')}>Isolate connected parts</button>}
    </div>}
    <dl>
      <div><dt>Component</dt><dd>{element.kindLabel ?? element.kind}</dd></div>
      <div><dt>Storey</dt><dd>{element.storeyId ? manifest.storeys?.[element.storeyId]?.name ?? element.storeyId : 'Follows its host'}</dd></div>
      {measurements.map(({ id, label, value }) => <div key={id}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
    {relations.length > 0 && <section className="related-components" aria-label="Related components">
      <h4>Related components <span>{relations.length}</span></h4>
      {relations.slice(0, limit).map((entry) => <button className="related-link" key={`${entry.kind}:${entry.id}`} onClick={() => onSelect(entry.id)}>
        <small>{entry.label}</small><span>{manifest.elements[entry.id].name}</span>
      </button>)}
      {relations.length > limit && <button className="more-components" onClick={() => setLimit(limit + 20)}>Show more relationships</button>}
    </section>}
    {(element.children?.length ?? 0) > 0 && <section className="generated-components" aria-label="Generated members">
      <h4>Generated members <span>{element.children!.length}</span></h4>
      <input type="search" aria-label="Find generated members" placeholder="Find a member…" value={memberQuery} onChange={(event) => { setMemberQuery(event.target.value); setMemberLimit(30); }} />
      {children.slice(0, memberLimit).map((id) => <button className="related-link" key={id} onClick={() => onSelect(id)}>
        <span>{manifest.elements[id].name}</span>
        <small>{String(manifest.elements[id].data.key ?? manifest.elements[id].data.memberIndex ?? id)}</small>
      </button>)}
      {children.length === 0 && <p>No matching members.</p>}
      {children.length > memberLimit && <button className="more-components" onClick={() => setMemberLimit(memberLimit + 30)}>Show more members</button>}
    </section>}
    <details><summary>Technical properties</summary><pre>{JSON.stringify(element.data, null, 2)}</pre></details>
  </div>;
}
