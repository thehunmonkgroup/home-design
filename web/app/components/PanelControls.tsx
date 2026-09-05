import type { PanelVisibility, ReviewPanel } from '../lib/panels';

export default function PanelControls({ visibility, onToggle }: {
  visibility: PanelVisibility;
  onToggle: (panel: ReviewPanel) => void;
}) {
  return <nav className="panel-controls" aria-label="Side panels">
    {(['components', 'details'] as const).map((panel) => {
      const label = panel === 'components' ? 'Components' : 'Details';
      const open = visibility[panel];
      return <button
        key={panel} type="button" aria-controls={`${panel}-panel`}
        aria-expanded={open} onClick={() => onToggle(panel)}
      >
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <rect x="2" y="3" width="16" height="14" rx="2" />
          <path d={panel === 'components' ? 'M7 3v14' : 'M13 3v14'} />
          {open && <path className="panel-icon-fill" d={panel === 'components' ? 'M3 4h3v12H3z' : 'M14 4h3v12h-3z'} />}
        </svg>
        {open ? 'Hide' : 'Show'} {label}
      </button>;
    })}
  </nav>;
}
