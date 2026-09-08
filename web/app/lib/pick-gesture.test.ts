import { describe, expect, it } from 'vitest';
import { PickGesture } from './pick-gesture';

const pointer = (pointerId = 1, clientX = 10, button = 0) => ({ pointerId, clientX, clientY: 10, button });

describe('component picking gestures', () => {
  it('accepts a primary click or tap with small jitter, but ignores releases without a press', () => {
    const gesture = new PickGesture();
    expect(gesture.up(pointer())).toBe(false);
    gesture.down(pointer());
    expect(gesture.up(pointer(1, 12))).toBe(true);
  });
  it('does not select after orbiting away and back, panning, pinching or cancellation', () => {
    const gesture = new PickGesture();
    gesture.down(pointer());
    gesture.move(pointer(1, 30));
    expect(gesture.up(pointer())).toBe(false);
    gesture.down(pointer(1, 10, 2));
    expect(gesture.up(pointer())).toBe(false);
    gesture.down(pointer());
    gesture.down(pointer(2));
    expect(gesture.up(pointer(2))).toBe(false);
    expect(gesture.up(pointer())).toBe(false);
    gesture.down(pointer());
    gesture.cancel(1);
    expect(gesture.up(pointer())).toBe(false);
  });
});
