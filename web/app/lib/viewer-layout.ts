import { useEffect, useSyncExternalStore } from 'react';

export type ViewerDrawer = 'components' | 'details' | 'views' | 'tools' | 'info';
export type TourFocus = ViewerDrawer | 'none' | null;
export const compactQuery = '(max-width: 1000px), (max-height: 520px)';

function subscribe(callback: () => void) {
  const media = window.matchMedia(compactQuery);
  media.addEventListener('change', callback);
  return () => media.removeEventListener('change', callback);
}

export function useCompactLayout() {
  return useSyncExternalStore(subscribe, () => window.matchMedia(compactQuery).matches, () => false);
}

function subscribeTouch(callback: () => void) {
  const media = window.matchMedia('(pointer: coarse)');
  media.addEventListener('change', callback);
  return () => media.removeEventListener('change', callback);
}

export function useTouchInput() {
  return useSyncExternalStore(subscribeTouch, () => window.matchMedia('(pointer: coarse)').matches, () => false);
}

// Keep controls above the software keyboard without disabling browser zoom.
export function useVisibleViewport() {
  useEffect(() => {
    const viewport = window.visualViewport;
    const update = () => {
      const height = viewport && viewport.scale === 1 ? viewport.height : window.innerHeight;
      document.documentElement.style.setProperty('--viewer-height', `${height}px`);
    };
    update();
    viewport?.addEventListener('resize', update);
    window.addEventListener('resize', update);
    return () => {
      viewport?.removeEventListener('resize', update);
      window.removeEventListener('resize', update);
      document.documentElement.style.removeProperty('--viewer-height');
    };
  }, []);
}
