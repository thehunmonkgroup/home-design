'use client';

import { useEffect, useState } from 'react';

const GESTURES = [
  { word: 'Orbit', help: 'Mouse or touchpad: click and drag. Touchscreen: drag with one finger.' },
  { word: 'Pan', help: 'Mouse: right-click and drag. Touchpad: hold Shift and drag. Touchscreen: drag with two fingers.' },
  { word: 'Zoom', help: 'Mouse: scroll wheel. Touchpad: two-finger scroll. Touchscreen: pinch with two fingers.' },
];

export default function ViewOrientation({ northRotation, mode = 'orbit', keyboard = 'camera' }: {
  northRotation: number; mode?: 'orbit' | 'look'; keyboard?: 'camera' | 'components' | 'inactive';
}) {
  const [activeHint, setActiveHint] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  useEffect(() => {
    if (!activeHint && !helpOpen) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setActiveHint(null); setHelpOpen(false); }
    };
    window.addEventListener('keydown', dismiss);
    return () => window.removeEventListener('keydown', dismiss);
  }, [activeHint, helpOpen]);
  const gestures = (mode === 'look' ? [
    { word: 'Look', help: 'Drag with one finger or the primary mouse button to look around without moving your viewpoint.' },
    GESTURES[1],
    { word: 'Move', help: 'Scroll to move forward or back. On a touchscreen, pinch to move and drag with two fingers to pan.' },
  ] : GESTURES).map((gesture, index) => ({ ...gesture, help: `${gesture.help} ${keyboard === 'camera'
    ? ['Keyboard: arrows or h j k l while the model has focus.', 'Keyboard: Shift + arrows or H J K L while the model has focus.', `Keyboard: + or = to ${mode === 'look' ? 'move forward' : 'zoom in'}, − to ${mode === 'look' ? 'move backward' : 'zoom out'}; F frames the model.`][index]
    : keyboard === 'components' ? 'Keyboard currently navigates components. Esc clears the selection and returns focus to the model.'
      : 'Keyboard navigation is paused while a panel, dialog, tour or placement tool is active.'}` }));
  const radians = northRotation * Math.PI / 180;
  return (
    <div className="axis-key">
      <svg className="orientation-compass" viewBox="0 0 72 72" role="img" aria-label="Model north orientation">
        <title>Model north (+Y), relative to the camera. Not surveyed true north.</title>
        <circle cx="36" cy="36" r="33" />
        <g data-north-needle transform={`rotate(${northRotation} 36 36)`}>
          <path className="north-needle" d="M36 17 30 40 36 36 42 40Z" />
          <path className="south-needle" d="M36 55 30 40 36 36 42 40Z" />
        </g>
        <text x={36 + 27 * Math.sin(radians)} y={36 - 27 * Math.cos(radians)}>N</text>
      </svg>
      <button className="gesture-help-toggle" type="button" aria-label="Navigation help" aria-expanded={helpOpen} onClick={() => setHelpOpen(!helpOpen)}>Gestures</button>
      <div hidden={!helpOpen} className="gesture-hints" aria-label="View navigation help" onMouseLeave={() => setActiveHint(null)}>
        <p className="keyboard-help">{keyboard === 'camera'
          ? `Focus the model to use keys: arrows / hjkl ${mode === 'look' ? 'look' : 'orbit'} · Shift pans · + / − ${mode === 'look' ? 'moves' : 'zooms'} · F frames.`
          : keyboard === 'components' ? 'Component keys: ↑/k parent · ↓/j child · ←/h and →/l siblings · Space hides/shows · Esc returns to camera.'
            : 'Keyboard navigation is paused. Close the panel or finish the active tool to resume.'}</p>
        {gestures.map(({ word, help }) => (
          <span className="gesture-hint" key={word}>
            <button
              type="button"
              aria-label={`${word} instructions`}
              aria-describedby={activeHint === word ? `gesture-${word}` : undefined}
              onMouseEnter={() => setActiveHint(word)}
              onFocus={() => setActiveHint(word)}
              onBlur={() => setActiveHint(null)}
              onClick={() => setActiveHint(word)}
            >{word}</button>
            {activeHint === word && <span className="gesture-tooltip" id={`gesture-${word}`} role="tooltip">{help}</span>}
          </span>
        ))}
      </div>
    </div>
  );
}
