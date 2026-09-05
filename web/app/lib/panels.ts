export type ReviewPanel = 'components' | 'details';
export type PanelVisibility = Record<ReviewPanel, boolean>;

const storageKey = (panel: ReviewPanel) => `home-design.viewer.panels.${panel}`;

export function readPanelVisibility(): PanelVisibility {
  const width = typeof window === 'undefined' ? 1200 : window.innerWidth;
  const visibility = { components: width > 680, details: width > 1000 };
  for (const panel of ['components', 'details'] as const) {
    try {
      const saved = window.localStorage.getItem(storageKey(panel));
      if (saved === 'true' || saved === 'false') visibility[panel] = saved === 'true';
    } catch {
      // Storage may be disabled; the viewer still works with in-memory choices.
    }
  }
  return visibility;
}

export function savePanelVisibility(panel: ReviewPanel, visible: boolean): void {
  try {
    window.localStorage.setItem(storageKey(panel), String(visible));
  } catch {
    // Keep the current session usable when browser storage is unavailable.
  }
}
