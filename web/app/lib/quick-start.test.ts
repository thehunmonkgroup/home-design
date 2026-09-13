import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('quick-start visit memory', () => {
  it('remembers the brief tour across linked pages and reloads independently of the full tour', async () => {
    const storage = new Map<string, string>();
    vi.stubGlobal('window', { localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    } });
    const firstVisit = await import('./quick-start');
    expect(firstVisit.hasSeenQuickStart('navigation')).toBe(false);
    firstVisit.rememberQuickStart('navigation');
    expect(firstVisit.hasSeenQuickStart()).toBe(false);
    vi.resetModules();
    const nextVisit = await import('./quick-start');
    expect(nextVisit.hasSeenQuickStart('navigation')).toBe(true);
    expect(nextVisit.hasSeenQuickStart()).toBe(false);
    nextVisit.rememberQuickStart();
    expect(nextVisit.hasSeenQuickStart()).toBe(true);
    expect(nextVisit.hasSeenQuickStart('navigation')).toBe(true);
  });

  it('keeps separate session memories for both tours when storage is blocked', async () => {
    vi.stubGlobal('window', { get localStorage() { throw new Error('Blocked'); } });
    const tour = await import('./quick-start');
    expect(() => tour.rememberQuickStart('navigation')).not.toThrow();
    expect(tour.hasSeenQuickStart('navigation')).toBe(true);
    expect(tour.hasSeenQuickStart()).toBe(false);
    tour.rememberQuickStart();
    expect(tour.hasSeenQuickStart()).toBe(true);
  });

  it('starts for a new visitor and remembers dismissal across reloads', async () => {
    const storage = new Map<string, string>();
    vi.stubGlobal('window', { localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    } });
    const firstVisit = await import('./quick-start');
    expect(firstVisit.hasSeenQuickStart()).toBe(false);
    firstVisit.rememberQuickStart();
    vi.resetModules();
    const nextVisit = await import('./quick-start');
    expect(nextVisit.hasSeenQuickStart()).toBe(true);
  });

  it('remembers dismissal for the session when storage is blocked', async () => {
    vi.stubGlobal('window', { get localStorage() { throw new Error('Blocked'); } });
    const tour = await import('./quick-start');
    expect(tour.hasSeenQuickStart()).toBe(false);
    expect(() => tour.rememberQuickStart()).not.toThrow();
    expect(tour.hasSeenQuickStart()).toBe(true);
  });
});
