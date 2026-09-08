import type { RenderManifest } from '../lib/model';
import type { SelectionHistory as History } from '../lib/selection-history';

export default function SelectionHistory({ history, manifest, onGo, onClear }: {
  history: History;
  manifest: RenderManifest | null;
  onGo: (index: number) => void;
  onClear: () => void;
}) {
  const name = (index: number) => {
    const id = history.entries[index];
    return id ? manifest?.elements[id]?.name ?? id : 'Nothing selected';
  };
  return <nav className="selection-history" aria-label="Component navigation">
    <div>
      <button disabled={history.index === 0} onClick={() => onGo(history.index - 1)}
        title={history.index > 0 ? `Back to ${name(history.index - 1)}` : 'No previous selection'}>← Back</button>
      <button disabled={history.index === history.entries.length - 1} onClick={() => onGo(history.index + 1)}
        title={history.index < history.entries.length - 1 ? `Forward to ${name(history.index + 1)}` : 'No next selection'}>Forward →</button>
      <button disabled={!history.entries[history.index]} onClick={onClear}>Clear selection</button>
    </div>
    <label>Selection history
      <select value={history.index} onChange={(event) => onGo(Number(event.target.value))} disabled={history.entries.length < 2}>
        {history.entries.map((id, index) => <option key={index} value={index}>{index + 1}. {name(index)}{id ? ` — ${id}` : ''}</option>)}
      </select>
    </label>
  </nav>;
}
