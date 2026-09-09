import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { ReviewPanel } from '../lib/panels';
import { hasSeenQuickStart, rememberQuickStart } from '../lib/quick-start';

const basicSteps: Array<{ title: string; text: string; target: string; panel?: ReviewPanel }> = [
  {
    title: 'Choose a model', target: '.model-switcher',
    text: 'Use the model menu in the top bar to switch homes. You can restart this quick start any time with the ? button.',
  },
  {
    title: 'Find components', target: '#component-filter', panel: 'components',
    text: 'Search by name or ID. Matching components stay under their section headings. Select a row to inspect it; use its eye to change visibility. Section eyes control the entire group.',
  },
  {
    title: 'Explore the 3D view', target: '.axis-key',
    text: 'Drag to orbit, right-drag or Shift-drag to pan, and scroll to zoom. On touchscreens, drag with one finger to orbit, two to pan, or pinch to zoom. The compass and gesture hints help you stay oriented. Click a component to select it.',
  },
  {
    title: 'Inspect details', target: '#details-panel .panel-heading', panel: 'details',
    text: 'The Details panel shows the selected component’s ID, measurements, and design properties. Use Show or Hide Components and Details below the top bar to make room for the model.',
  },
  {
    title: 'Control the view', target: '.viewport-tools',
    text: 'Frame model resets the camera. Show all reveals every component. Enable Isolate on eye click, then click an eye to show only that component or group. Turn it off to hide or show individual items while keeping that view. The other controls show spaces, make section cuts, and offer sun studies and reports when available.',
  },
];

const savedViewSteps = [...basicSteps.slice(0, 3), {
  title: 'Explore saved views', target: '.named-view-tools',
  text: 'Choose a Saved view to jump to a prepared viewpoint, with its layers, highlights and cuts. Move around or inspect components from there. Restore view returns to those settings; Reset presentation restores the complete model’s default presentation.',
}, ...basicSteps.slice(3)];
const navigationSteps = [basicSteps[2]];

export default function QuickStart({ ready, automatic = 'full', hasSavedViews = false, onPanelFocus }: {
  ready: boolean;
  automatic?: 'full' | 'navigation' | 'none';
  hasSavedViews?: boolean;
  onPanelFocus: (panel: ReviewPanel | 'none' | null) => void;
}) {
  const [seen, setSeen] = useState(hasSeenQuickStart);
  const [requested, setRequested] = useState(false);
  const [navigationDismissed, setNavigationDismissed] = useState(false);
  const restartButton = useRef<HTMLButtonElement>(null);
  const mini = !requested && automatic === 'navigation';
  const open = ready && (requested || (mini ? !navigationDismissed : automatic === 'full' && !seen));
  const dismiss = () => {
    if (mini) setNavigationDismissed(true);
    else {
      rememberQuickStart();
      setSeen(true);
    }
    setRequested(false);
    restartButton.current?.focus();
  };

  return <>
    <button ref={restartButton} type="button" className="quick-start-button" aria-label="Start quick-start tour"
      title="Quick start" disabled={!ready} onClick={() => setRequested(true)}>?</button>
    {open && createPortal(<Tour mini={mini} hasSavedViews={hasSavedViews} onDismiss={dismiss} onPanelFocus={onPanelFocus} />, document.body)}
  </>;
}

function Tour({ mini, hasSavedViews, onDismiss, onPanelFocus }: {
  mini: boolean;
  hasSavedViews: boolean;
  onDismiss: () => void;
  onPanelFocus: (panel: ReviewPanel | 'none' | null) => void;
}) {
  const [index, setIndex] = useState(0);
  const steps = mini ? navigationSteps : hasSavedViews ? savedViewSteps : basicSteps;
  const dialog = useRef<HTMLDialogElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const spotlight = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const step = steps[index];

  useLayoutEffect(() => {
    onPanelFocus(mini ? null : step.panel ?? 'none');
    return () => onPanelFocus(null);
  }, [step, mini, onPanelFocus]);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useLayoutEffect(() => {
    const target = document.querySelector<HTMLElement>(step.target);
    const place = () => {
      if (!card.current || !spotlight.current) return;
      const rect = target?.getBoundingClientRect();
      const width = window.innerWidth;
      const height = window.innerHeight;
      const cardRect = card.current.getBoundingClientRect();
      const clamp = (value: number, max: number) => Math.max(12, Math.min(value, max));
      const hasTarget = rect && rect.width > 0 && rect.height > 0;
      spotlight.current.hidden = !hasTarget;
      if (hasTarget) {
        Object.assign(spotlight.current.style, {
          left: `${Math.max(2, rect.left - 4)}px`, top: `${Math.max(2, rect.top - 4)}px`,
          width: `${Math.min(rect.width + 8, width - 4)}px`, height: `${Math.min(rect.height + 8, height - 4)}px`,
        });
      }
      const top = hasTarget && rect.bottom + 16 + cardRect.height <= height - 12
        ? rect.bottom + 16
        : hasTarget && rect.top - 16 - cardRect.height >= 12
          ? rect.top - 16 - cardRect.height
          : (height - cardRect.height) / 2;
      Object.assign(card.current.style, {
        left: `${clamp(hasTarget ? rect.left : (width - cardRect.width) / 2, width - cardRect.width - 12)}px`,
        top: `${clamp(top, height - cardRect.height - 12)}px`,
      });
    };
    place();
    const frame = requestAnimationFrame(() => { place(); heading.current?.focus(); });
    const observer = new ResizeObserver(place);
    if (target) observer.observe(target);
    if (card.current) observer.observe(card.current);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [step]);

  return <dialog ref={dialog} className="quick-start-dialog" aria-labelledby="tour-title" aria-describedby="tour-description"
    onCancel={(event) => { event.preventDefault(); onDismiss(); }}>
    <div ref={spotlight} className="tour-spotlight" aria-hidden="true" />
    <div ref={card} className="tour-card">
      <div className="tour-progress"><span>{mini ? 'Quick start · Navigation' : `Quick start · ${index + 1} of ${steps.length}`}</span>
        <button type="button" onClick={onDismiss}>Skip tour</button>
      </div>
      <h2 ref={heading} tabIndex={-1} id="tour-title">{step.title}</h2>
      <p id="tour-description">{step.text}</p>
      <div className="tour-actions">
        {!mini && <button type="button" disabled={index === 0} onClick={() => setIndex(index - 1)}>Back</button>}
        <button type="button" className="tour-next" onClick={() => index === steps.length - 1 ? onDismiss() : setIndex(index + 1)}>
          {mini ? 'Got it' : index === steps.length - 1 ? 'Finish' : 'Next'}
        </button>
      </div>
    </div>
  </dialog>;
}
