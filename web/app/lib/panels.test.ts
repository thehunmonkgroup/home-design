import { afterEach, describe, expect, it, vi } from 'vitest';
import { readPanelVisibility, savePanelVisibility } from './panels';

afterEach(() => vi.unstubAllGlobals());

function browser(width = 1400, saved: Record<string, string> = {}) {
  const entries = new Map(Object.entries(saved));
  const localStorage = {
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => entries.set(key, value),
  };
  vi.stubGlobal('window', { innerWidth: width, localStorage });
  return localStorage;
}

describe('side panel preferences', () => {
  it.each([
    [1400, true, true], [1000, true, false], [680, false, false],
  ])('uses space-aware defaults at width %s', (width, components, details) => {
    browser(width as number);
    expect(readPanelVisibility()).toEqual({ components, details });
  });

  it('remembers each explicit choice independently across reads', () => {
    const storage = browser();
    savePanelVisibility('components', false);
    expect(readPanelVisibility()).toEqual({ components: false, details: true });
    expect(storage.getItem('home-design.viewer.panels.details')).toBeNull();
    savePanelVisibility('details', false);
    savePanelVisibility('components', true);
    expect(readPanelVisibility()).toEqual({ components: true, details: false });
  });

  it('honors saved preferences on small screens and ignores malformed values', () => {
    browser(400, {
      'home-design.viewer.panels.components': 'true',
      'home-design.viewer.panels.details': 'invalid',
    });
    expect(readPanelVisibility()).toEqual({ components: true, details: false });
  });

  it('survives blocked storage access', () => {
    vi.stubGlobal('window', {
      innerWidth: 1400,
      get localStorage() { throw new Error('Storage blocked'); },
    });
    expect(readPanelVisibility()).toEqual({ components: true, details: true });
    expect(() => savePanelVisibility('components', false)).not.toThrow();
  });

  it('survives a write failure', () => {
    const storage = browser();
    vi.spyOn(storage, 'setItem').mockImplementation(() => { throw new Error('Quota exceeded'); });
    expect(() => savePanelVisibility('details', false)).not.toThrow();
  });
});
