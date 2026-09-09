import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react';
import type { CameraMotion, CameraNavigation, NavigationMode } from './camera-navigation';
import { quickSelectionShortcut } from './quick-selection-shortcuts';

type Direction = 'left' | 'right' | 'up' | 'down' | 'in' | 'out';
export function cameraKey(key: string): Direction | 'frame' | null {
  switch (key.toLowerCase()) {
    case 'arrowleft': case 'h': return 'left';
    case 'arrowright': case 'l': return 'right';
    case 'arrowup': case 'k': return 'up';
    case 'arrowdown': case 'j': return 'down';
    case '+': case '=': return 'in';
    case '-': return 'out';
    case 'f': return 'frame';
    default: return null;
  }
}

/** Tracks physical keys so modifiers and OS repeat cannot leave movement stuck. */
export class CameraKeys {
  private held = new Map<string, Direction>();
  pan = false;
  press(code: string, key: string, repeat: boolean): boolean {
    const action = cameraKey(key);
    if (!action || action === 'frame' || repeat) return false;
    this.held.set(code, action);
    return true;
  }
  release(code: string): void { this.held.delete(code); }
  clear(): void { this.held.clear(); this.pan = false; }
  get active(): boolean { return this.held.size > 0; }
  motion(): CameraMotion {
    const values = new Set(this.held.values());
    return { x: Number(values.has('right')) - Number(values.has('left')), y: Number(values.has('up')) - Number(values.has('down')),
      zoom: Number(values.has('in')) - Number(values.has('out')), pan: this.pan };
  }
}

interface KeyboardOptions {
  host: RefObject<HTMLDivElement | null>;
  ready: boolean;
  selectionActive: boolean;
  blocked: boolean;
  mode: NavigationMode;
  navigation: () => CameraNavigation | undefined;
  onStart: () => void;
  onFrame: () => void;
}

/** One keyboard owner routes either component actions or focused viewport movement. */
export function useViewerKeyboard(options: KeyboardOptions): void {
  const latest = useRef(options);
  useLayoutEffect(() => { latest.current = options; });
  const { host, ready, selectionActive, blocked, mode } = options;
  useEffect(() => {
    if (!ready || blocked) return;
    const canvas = host.current?.querySelector('canvas');
    const viewport = host.current?.closest('.viewport');
    if (!canvas || !viewport) return;
    const keys = new CameraKeys();
    const selectionKeys = new Set<string>();
    let frame = 0, previousTime = 0;
    const clear = () => { keys.clear(); selectionKeys.clear(); cancelAnimationFrame(frame); frame = 0; previousTime = 0; };
    const modal = () => Boolean(document.querySelector('dialog[open], [role="dialog"][aria-modal="true"]'));
    const animate = (time: number) => {
      if (document.activeElement !== canvas || document.hidden || modal()) { clear(); return; }
      const seconds = Math.min((time - previousTime) / 1000, 0.05);
      previousTime = time;
      latest.current.navigation()?.keyboardMotion(keys.motion(), seconds);
      frame = requestAnimationFrame(animate);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || modal()) { clear(); return; }
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"], [role="slider"]')) return;
      if (selectionActive) {
        const bar = viewport.querySelector<HTMLElement>('.quick-selection:not([hidden])');
        const action = quickSelectionShortcut(event);
        if (!bar || !action || (target?.closest('button, a, summary, [role="button"]') && !bar.contains(target))) return;
        event.preventDefault();
        const code = event.code || event.key;
        if (event.repeat && !selectionKeys.has(code)) return;
        selectionKeys.add(code);
        if (event.repeat && (action === 'toggle' || action === 'clear')) return;
        bar.querySelector<HTMLButtonElement>(`button[data-shortcut="${action}"]`)?.click();
        if (action === 'clear') canvas.focus({ preventScroll: true });
        return;
      }
      if (document.activeElement !== canvas) return;
      keys.pan = event.shiftKey;
      const action = cameraKey(event.key);
      if (!action) return;
      event.preventDefault();
      if (action === 'frame') {
        clear();
        if (!event.repeat) latest.current.onFrame();
        return;
      }
      const wasActive = keys.active;
      if (!keys.press(event.code || event.key, event.key, event.repeat)) return;
      if (!wasActive) {
        latest.current.onStart();
        const navigation = latest.current.navigation();
        if (navigation) navigation.setMode(navigation.mode);
        previousTime = performance.now();
        frame = requestAnimationFrame(animate);
      }
    };
    const onUp = (event: KeyboardEvent) => {
      selectionKeys.delete(event.code || event.key);
      keys.release(event.code || event.key); keys.pan = event.shiftKey;
      if (!keys.active) clear();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('keyup', onUp);
    window.addEventListener('blur', clear);
    document.addEventListener('focusin', clear);
    document.addEventListener('visibilitychange', clear);
    viewport.addEventListener('pointerdown', clear, true);
    return () => {
      clear();
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('keyup', onUp);
      window.removeEventListener('blur', clear);
      document.removeEventListener('focusin', clear);
      document.removeEventListener('visibilitychange', clear);
      viewport.removeEventListener('pointerdown', clear, true);
    };
  }, [host, ready, selectionActive, blocked, mode]);
}
