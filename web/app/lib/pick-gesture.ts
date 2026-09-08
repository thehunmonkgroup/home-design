// Orbit/pan/pinch gestures must not replace the component being inspected.
export class PickGesture {
  private pointers = new Set<number>();
  private candidate: { id: number; x: number; y: number } | null = null;

  down(event: Pick<PointerEvent, 'pointerId' | 'button' | 'clientX' | 'clientY'>): void {
    this.pointers.add(event.pointerId);
    this.candidate = this.pointers.size === 1 && event.button === 0
      ? { id: event.pointerId, x: event.clientX, y: event.clientY } : null;
  }

  move(event: Pick<PointerEvent, 'pointerId' | 'clientX' | 'clientY'>): void {
    const start = this.candidate;
    if (start?.id === event.pointerId && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5) this.candidate = null;
  }

  up(event: Pick<PointerEvent, 'pointerId' | 'clientX' | 'clientY'>): boolean {
    this.move(event);
    const pick = this.candidate?.id === event.pointerId;
    this.cancel(event.pointerId);
    return pick;
  }

  cancel(id: number): void {
    this.pointers.delete(id);
    this.candidate = null;
  }
}
