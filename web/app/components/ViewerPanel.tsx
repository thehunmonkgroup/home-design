import { useEffect, useRef, useState, type ReactNode } from 'react';

/** A shared, nonmodal inspection surface: the uncovered canvas stays interactive. */
export default function ViewerPanel({ id, title, className = '', open, onClose, children }: {
  id: string; title: string; className?: string; open: boolean; onClose: () => void; children: ReactNode;
}) {
  const panel = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    close.current?.focus({ preventScroll: true });
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || document.querySelector('dialog[open]')) return;
      // A focused drawer handles Escape; canvas tools retain their own Escape action.
      if (panel.current?.contains(document.activeElement)) {
        event.preventDefault();
        onCloseRef.current();
      }
    };
    document.addEventListener('keydown', escape);
    const element = panel.current;
    return () => {
      document.removeEventListener('keydown', escape);
      if (element?.contains(document.activeElement) || document.activeElement === document.body) {
        previous?.focus({ preventScroll: true });
      }
    };
  }, [open]);
  return <aside ref={panel} id={id} className={`viewer-panel ${className} ${expanded ? 'sheet-expanded' : ''}`}
    hidden={!open} aria-label={title}>
    <div className="drawer-heading">
      <h2>{title}</h2>
      <button className="sheet-expand" type="button" aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}>{expanded ? 'Reduce' : 'Expand'}</button>
      <button ref={close} type="button" className="drawer-close" aria-label={`Close ${title}`} onClick={onClose}>×</button>
    </div>
    <div className="panel-body">{children}</div>
  </aside>;
}
