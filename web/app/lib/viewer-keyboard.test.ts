import { describe, expect, it } from 'vitest';
import { CameraKeys, cameraKey } from './viewer-keyboard';

describe('camera keyboard state', () => {
  it('supports arrows, Vim directions, Shift variants, zoom and framing', () => {
    for (const key of ['ArrowLeft', 'h', 'H']) expect(cameraKey(key)).toBe('left');
    for (const key of ['ArrowDown', 'j', 'J']) expect(cameraKey(key)).toBe('down');
    for (const key of ['ArrowUp', 'k', 'K']) expect(cameraKey(key)).toBe('up');
    for (const key of ['ArrowRight', 'l', 'L']) expect(cameraKey(key)).toBe('right');
    expect(cameraKey('+')).toBe('in'); expect(cameraKey('=')).toBe('in'); expect(cameraKey('-')).toBe('out');
    expect(cameraKey('f')).toBe('frame'); expect(cameraKey(' ')).toBeNull(); expect(cameraKey('Escape')).toBeNull();
  });
  it('combines held directions without multiplying speed for aliases and cancels opposing keys', () => {
    const keys = new CameraKeys();
    keys.press('ArrowRight', 'ArrowRight', false); keys.press('KeyL', 'l', false);
    keys.press('ArrowUp', 'ArrowUp', false); keys.press('Equal', '+', false); keys.pan = true;
    expect(keys.motion()).toEqual({ x: 1, y: 1, zoom: 1, pan: true });
    keys.press('KeyH', 'h', false); expect(keys.motion().x).toBe(0);
    keys.release('KeyH'); keys.release('KeyL'); expect(keys.motion().x).toBe(1);
    keys.release('ArrowRight'); expect(keys.motion().x).toBe(0);
  });
  it('requires a fresh keypress after focus or mode changes and clears modifiers', () => {
    const keys = new CameraKeys(); keys.press('KeyH', 'h', false); keys.pan = true;
    keys.clear(); expect(keys.active).toBe(false); expect(keys.pan).toBe(false);
    expect(keys.press('KeyH', 'h', true)).toBe(false); expect(keys.active).toBe(false);
    expect(keys.press('KeyH', 'h', false)).toBe(true); keys.release('KeyH'); expect(keys.active).toBe(false);
    expect(keys.press('KeyF', 'f', false)).toBe(false);
  });
});
