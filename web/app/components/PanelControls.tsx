import type { PanelVisibility } from '../lib/panels';
import type { ViewerDrawer } from '../lib/viewer-layout';

const controls = [
  { id: 'views', label: 'Views', path: 'M3 4h18v16H3z M3 9h18 M7 6h.01 M10 6h.01' },
  { id: 'components', label: 'Components', path: 'm12 3 9 5-9 5-9-5z M3 12l9 5 9-5 M3 16l9 5 9-5' },
  { id: 'details', label: 'Details', path: 'M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h5' },
  { id: 'tools', label: 'Tools', path: 'M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6' },
] as const;

export default function PanelControls({ visibility, active, onToggle, onFrame, ready }: {
  visibility: PanelVisibility; active: ViewerDrawer | null;
  onToggle: (panel: ViewerDrawer) => void; onFrame: () => void; ready: boolean;
}) {
  return <nav className="viewer-toolbar" aria-label="Viewer controls">
    {controls.map(({ id, label, path }) => <button key={id} type="button" aria-controls={`${id}-panel`}
      aria-expanded={id === 'components' || id === 'details' ? visibility[id] : active === id}
      onClick={() => onToggle(id)}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={path} /></svg><span>{label}</span>
    </button>)}
    <button type="button" onClick={onFrame} disabled={!ready} aria-label="Frame model" title="Frame the complete model">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5 M16 3h5v5 M3 16v5h5 M21 16v5h-5 M8 8h8v8H8z" /></svg><span>Frame</span>
    </button>
  </nav>;
}
