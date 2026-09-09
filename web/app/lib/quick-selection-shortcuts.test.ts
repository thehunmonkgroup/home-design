import { describe, expect, it } from 'vitest';
import { quickSelectionShortcut } from './quick-selection-shortcuts';

const event = { key: ' ', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, isComposing: false, defaultPrevented: false };

describe('quick selection shortcuts', () => {
  it.each([
    ['ArrowUp', 'parent'], ['k', 'parent'], ['ArrowDown', 'child'], ['j', 'child'],
    ['ArrowLeft', 'previous'], ['h', 'previous'], ['ArrowRight', 'next'], ['l', 'next'], [' ', 'toggle'], ['Escape', 'clear'],
  ])('maps %s to %s', (key, action) => {
    expect(quickSelectionShortcut({ ...event, key })).toBe(action);
  });
  it.each(['altKey', 'ctrlKey', 'metaKey', 'shiftKey', 'isComposing', 'defaultPrevented'] as const)('ignores %s events', (flag) => {
    for (const key of [' ', 'ArrowUp', 'j']) expect(quickSelectionShortcut({ ...event, key, [flag]: true })).toBeNull();
  });
  it.each(['Enter', 'Tab', 'a', 'J'])('leaves %s to its normal handler', (key) => {
    expect(quickSelectionShortcut({ ...event, key })).toBeNull();
  });
});
