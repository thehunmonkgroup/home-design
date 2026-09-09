import { useLayoutEffect, useRef } from 'react';
import { canToggleVisibility, formatProperty, type RenderManifest } from '../lib/model';
import { containingElements, reinforcementElementIds, relatedElements, type ContextAction } from '../lib/navigation';
import { formatDisplayProperty, type DisplayUnits } from '../lib/properties';
import { useCompactLayout } from '../lib/viewer-layout';

export interface DetailsView {
  limit: number;
  memberQuery: string;
  memberLimit: number;
  scrollTop: number;
  technicalOpen: boolean;
}

export const initialDetailsView: DetailsView = { limit: 20, memberQuery: '', memberLimit: 30, scrollTop: 0, technicalOpen: false };

export default function ElementDetails({ elementId, manifest, units, onUnits, onSelect, onIsolate, view, onView, onFind, onShow, onHide, hasGeometry, hidden }: {
  elementId: string;
  manifest: RenderManifest;
  units: DisplayUnits;
  onUnits: (units: DisplayUnits) => void;
  onSelect: (id: string) => void;
  onIsolate: (scope: ContextAction) => void;
  view: DetailsView;
  onView: (changes: Partial<DetailsView>) => void;
  onFind: () => void;
  onShow: () => void;
  onHide: () => void;
  hasGeometry: boolean;
  hidden: boolean;
}) {
  const element = manifest.elements[elementId];
  const { limit, memberQuery, memberLimit } = view;
  const container = useRef<HTMLDivElement>(null);
  const compact = useCompactLayout();
  useLayoutEffect(() => {
    const scroller = compact ? container.current?.closest('.panel-body') : container.current;
    if (scroller) scroller.scrollTop = view.scrollTop;
  }, [view.scrollTop, compact]);
  useLayoutEffect(() => {
    if (!compact) return;
    const scroller = container.current?.closest('.panel-body');
    const remember = () => { if (scroller) onView({ scrollTop: scroller.scrollTop }); };
    scroller?.addEventListener('scroll', remember);
    return () => scroller?.removeEventListener('scroll', remember);
  }, [compact, onView]);
  const containers = containingElements(manifest, elementId);
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
  return <div className="element-details" ref={container} onScroll={(event) => { if (!compact) onView({ scrollTop: event.currentTarget.scrollTop }); }}>
    <h3>{element.name}</h3>
    <code>{elementId}</code>
    <div className="context-actions" aria-label="Find selected component">
      <button onClick={onFind}>Find in Components</button>
      <button onClick={onShow} disabled={!hasGeometry} title="Show this component and frame it without hiding other components">Show in model</button>
    </div>
    {hidden && <p className="component-note">This component is hidden. Use Show in model to display it.</p>}
    {containers.length > 0 && <nav className="containing-components" aria-label="Containing components">
      {containers.map(({ id, label }) => <button key={id} className="related-link" onClick={() => onSelect(id)}>
        <small>{label}</small><span>↑ {manifest.elements[id].name}</span>
      </button>)}
    </nav>}
    {!canToggleVisibility(element) && <p className="component-note">This component groups or describes other parts. Select its contents to review geometry.</p>}
    <label className="display-units">Display units
      <select aria-label="Display units" value={units} onChange={(event) => onUnits(event.target.value as DisplayUnits)}>
        <option value="metric">Metric</option><option value="imperial">Feet and inches</option>
      </select>
    </label>
    <div className="context-actions">
      {manifest.navigation && <button onClick={() => onIsolate('contents')}>Isolate with contents</button>}
      <button onClick={onHide} disabled={!hasGeometry || hidden} title="Hide this component or assembly without changing the camera or selection">Hide</button>
      {manifest.navigation && <>
      {element.kind === 'wall' && <button onClick={() => onIsolate('reveal')}>Reveal wall contents</button>}
      {reinforcementElementIds(manifest, elementId).length > 0 && <button onClick={() => onIsolate('reinforcement')}>Reveal reinforcement</button>}
      {hasSystem && <button onClick={() => onIsolate('system')}>Isolate system</button>}
      {relations.some((entry) => entry.kind === 'connection') && <button onClick={() => onIsolate('connected')}>Isolate connected parts</button>}
      </>}
    </div>
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
      {relations.length > limit && <button className="more-components" onClick={() => onView({ limit: limit + 20 })}>Show more relationships</button>}
    </section>}
    {(element.children?.length ?? 0) > 0 && <section className="generated-components" aria-label="Generated members">
      <h4>Generated members <span>{element.children!.length}</span></h4>
      <input type="search" aria-label="Find generated members" placeholder="Find a member…" value={memberQuery} onChange={(event) => onView({ memberQuery: event.target.value, memberLimit: 30 })} />
      {children.slice(0, memberLimit).map((id) => <button className="related-link" key={id} onClick={() => onSelect(id)}>
        <span>{manifest.elements[id].name}</span>
        <small>{String(manifest.elements[id].data.key ?? manifest.elements[id].data.memberIndex ?? id)}</small>
      </button>)}
      {children.length === 0 && <p>No matching members.</p>}
      {children.length > memberLimit && <button className="more-components" onClick={() => onView({ memberLimit: memberLimit + 30 })}>Show more members</button>}
    </section>}
    <details open={view.technicalOpen} onToggle={(event) => { if (event.currentTarget.open !== view.technicalOpen) onView({ technicalOpen: event.currentTarget.open }); }}><summary>Technical properties</summary><pre>{JSON.stringify(element.data, null, 2)}</pre></details>
  </div>;
}
