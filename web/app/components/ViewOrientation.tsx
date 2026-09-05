'use client';

import { useEffect, useState } from 'react';

const GESTURES = [
  { word: 'Orbit', help: 'Mouse or touchpad: click and drag. Touchscreen: drag with one finger.' },
  { word: 'Pan', help: 'Mouse: right-click and drag. Touchpad: hold Shift and drag. Touchscreen: drag with two fingers.' },
  { word: 'Zoom', help: 'Mouse: scroll wheel. Touchpad: two-finger scroll. Touchscreen: pinch with two fingers.' },
];

export default function ViewOrientation({ northRotation }: { northRotation: number }) {
  const [activeHint, setActiveHint] = useState<string | null>(null);
  useEffect(() => {
    if (!activeHint) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setActiveHint(null);
    };
    window.addEventListener('keydown', dismiss);
    return () => window.removeEventListener('keydown', dismiss);
  }, [activeHint]);
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
      <span className="orientation-caption">Model north</span>
      <div className="gesture-hints" aria-label="View navigation help" onMouseLeave={() => setActiveHint(null)}>
        {GESTURES.map(({ word, help }) => (
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
