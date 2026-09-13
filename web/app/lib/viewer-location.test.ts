import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearViewerView, readViewerLocation, writeViewerLocation } from './viewer-location';

afterEach(() => vi.unstubAllGlobals());

function browser(href: string) {
  const location = { href };
  const state = { existing: 'state' };
  const write = (_state: unknown, _title: string, url: string) => { location.href = url; };
  const history = { state, pushState: vi.fn(write), replaceState: vi.fn(write) };
  vi.stubGlobal('window', { location, history });
  return { location, history };
}

describe('shareable model and view selection', () => {
  it('preserves subdirectory hosting, unrelated parameters, fragments and history state', () => {
    const { location, history } = browser('https://example.com/homes/?theme=dark#details');
    writeViewerLocation('sample-house', 'living-room');
    expect(location.href).toBe('https://example.com/homes/?theme=dark&model=sample-house&view=living-room#details');
    expect(history.pushState).toHaveBeenCalledWith(history.state, '', location.href);
    expect(history.replaceState).not.toHaveBeenCalled();
    expect(readViewerLocation()).toEqual({ model: 'sample-house', view: 'living-room' });
  });

  it('records deliberate transitions but avoids duplicate entries', () => {
    const { history } = browser('https://example.com/?model=house&view=kitchen');
    writeViewerLocation('house', 'kitchen');
    expect(history.pushState).not.toHaveBeenCalled();
    writeViewerLocation('house', 'bedroom');
    writeViewerLocation('house', 'bedroom');
    writeViewerLocation('other', null);
    expect(history.pushState).toHaveBeenCalledTimes(2);
    expect(readViewerLocation()).toEqual({ model: 'other', view: null });
    writeViewerLocation('other', null);
    expect(history.pushState).toHaveBeenCalledTimes(2);
  });

  it('normalizes an initial model alias without adding a navigation step', () => {
    const { history } = browser('https://example.com/?model=Sample%20House&view=plan');
    writeViewerLocation('sample-house', 'plan', 'replace');
    expect(history.replaceState).toHaveBeenCalledOnce();
    expect(history.pushState).not.toHaveBeenCalled();
    expect(readViewerLocation()).toEqual({ model: 'sample-house', view: 'plan' });
  });

  it('pushes a reset to the default view and replaces stale IDs for custom presentation', () => {
    const { history } = browser('https://example.com/?model=house&view=plan');
    writeViewerLocation('house', null);
    expect(history.pushState).toHaveBeenCalledOnce();
    expect(readViewerLocation().view).toBeNull();
    writeViewerLocation('house', 'kitchen');
    clearViewerView();
    expect(history.replaceState).toHaveBeenCalledOnce();
    expect(readViewerLocation()).toEqual({ model: 'house', view: null });
  });

  it('distinguishes missing and invalid empty parameters and reads the current URL', () => {
    const { location } = browser('https://example.com/');
    expect(readViewerLocation()).toEqual({ model: null, view: null });
    location.href = 'https://example.com/?model=&view=';
    expect(readViewerLocation()).toEqual({ model: '', view: '' });
    location.href = 'https://example.com/?model=House%20%26%20Garden&view=plan';
    expect(readViewerLocation()).toEqual({ model: 'House & Garden', view: 'plan' });
  });
});
