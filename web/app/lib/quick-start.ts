const storageKey = 'home-design.viewer.quick-start.v1';
let seenThisSession = false;

export function hasSeenQuickStart(): boolean {
  if (seenThisSession) return true;
  try {
    return window.localStorage.getItem(storageKey) === 'seen';
  } catch {
    return false;
  }
}

export function rememberQuickStart(): void {
  seenThisSession = true;
  try {
    window.localStorage.setItem(storageKey, 'seen');
  } catch {
    // Remember dismissal for this session even when browser storage is unavailable.
  }
}
