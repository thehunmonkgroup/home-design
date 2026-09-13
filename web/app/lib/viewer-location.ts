export interface ViewerLocation {
  model: string | null;
  view: string | null;
}

export function readViewerLocation(): ViewerLocation {
  const params = new URL(window.location.href).searchParams;
  return { model: params.get('model'), view: params.get('view') };
}

export function writeViewerLocation(model: string | null, view: string | null, mode: 'push' | 'replace' = 'push'): void {
  const url = new URL(window.location.href);
  if (model === null) url.searchParams.delete('model');
  else url.searchParams.set('model', model);
  if (view === null || view === '') url.searchParams.delete('view');
  else url.searchParams.set('view', view);
  if (url.href === window.location.href) return;
  window.history[mode === 'push' ? 'pushState' : 'replaceState'](window.history.state, '', url.href);
}

export function clearViewerView(): void {
  writeViewerLocation(readViewerLocation().model, null, 'replace');
}
