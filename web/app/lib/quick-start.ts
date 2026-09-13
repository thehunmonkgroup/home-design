type TourKind = 'full' | 'navigation';
const storageKeys = {
  full: 'home-design.viewer.quick-start.v1',
  navigation: 'home-design.viewer.quick-start.navigation.v1',
};
const seenThisSession = new Set<TourKind>();

export function hasSeenQuickStart(kind: TourKind = 'full'): boolean {
  if (seenThisSession.has(kind)) return true;
  try {
    return window.localStorage.getItem(storageKeys[kind]) === 'seen';
  } catch {
    return false;
  }
}

export function rememberQuickStart(kind: TourKind = 'full'): void {
  seenThisSession.add(kind);
  try {
    window.localStorage.setItem(storageKeys[kind], 'seen');
  } catch {
    // Remember dismissal for this session even when browser storage is unavailable.
  }
}
