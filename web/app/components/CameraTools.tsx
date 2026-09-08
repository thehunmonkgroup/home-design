import { useState } from 'react';
import type { NavigationMode, ViewpointTool } from '../lib/camera-navigation';

export default function CameraTools({ ready, mode, orthographic, tool, onMode, onTool, canGoBack, onBack, rooms, roomId, onRoom, onPreset, height, onHeight, message }: {
  ready: boolean; mode: NavigationMode; orthographic: boolean; tool: ViewpointTool;
  onMode: (mode: NavigationMode) => void; onTool: (tool: ViewpointTool) => void;
  canGoBack: boolean; onBack: () => void; rooms: Array<{ id: string; name: string }>;
  roomId: string; onRoom: (id: string) => void; onPreset: (preset: 'center' | 'corner' | 'overview') => void;
  height: number; onHeight: (height: number) => void; message: string;
}) {
  const [expanded, setExpanded] = useState(() => window.innerWidth > 600);
  return <details className="camera-tools" open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
    <summary>View navigation</summary>
    <div className="camera-actions">
      <button disabled={!ready} aria-pressed={mode === 'orbit'} onClick={() => onMode('orbit')}>Orbit</button>
      <button disabled={!ready || orthographic} aria-pressed={mode === 'look'} onClick={() => onMode('look')}
        title={orthographic ? 'Choose a perspective room view to look around' : 'Drag to look around from a fixed position'}>Look around</button>
      <button disabled={!ready} aria-pressed={tool === 'pivot'} onClick={() => onTool(tool === 'pivot' ? null : 'pivot')}>Set orbit center</button>
      <button disabled={!ready || !roomId} aria-pressed={tool === 'position'} onClick={() => onTool(tool === 'position' ? null : 'position')}>Place viewpoint</button>
      <button disabled={!canGoBack} onClick={onBack}>Previous view</button>
      {tool && <button onClick={() => onTool(null)}>Cancel</button>}
    </div>
    <div className="camera-actions">
      <label>Room or deck <select aria-label="Room or deck" value={roomId} onChange={(event) => onRoom(event.target.value)}>
        <option value="">Choose a space…</option>
        {rooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
      </select></label>
      <label>Eye height (mm) <input aria-label="Eye height in millimetres" type="number" min="100" max="4000" step="50" value={height}
        onChange={(event) => { const value = Number(event.target.value); if (Number.isFinite(value)) onHeight(Math.max(100, Math.min(4000, value))); }} /></label>
      <button disabled={!ready || !roomId} onClick={() => onPreset('center')}>Center at eye level</button>
      <button disabled={!ready || !roomId} onClick={() => onPreset('corner')}>Upper corner</button>
      <button disabled={!ready || !roomId} onClick={() => onPreset('overview')}>Overview</button>
    </div>
    <p role="status">{message || (mode === 'look' ? 'Drag to look around. Shift/right-drag to pan; scroll to move forward or back.' : 'Drag to orbit. Shift/right-drag to pan; scroll to zoom.')}</p>
  </details>;
}
