type ShortcutEvent = Pick<KeyboardEvent, 'key' | 'altKey' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'isComposing' | 'defaultPrevented'>;
type SelectionAction = 'parent' | 'child' | 'previous' | 'next' | 'toggle' | 'clear';

export function quickSelectionShortcut(event: ShortcutEvent): SelectionAction | null {
  if (event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return null;
  switch (event.key) {
    case 'ArrowUp': case 'k': return 'parent';
    case 'ArrowDown': case 'j': return 'child';
    case 'ArrowLeft': case 'h': return 'previous';
    case 'ArrowRight': case 'l': return 'next';
    case ' ': return 'toggle';
    case 'Escape': return 'clear';
    default: return null;
  }
}
