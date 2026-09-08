import { describe, expect, it } from 'vitest';
import { emptySelectionHistory, selectionHistoryReducer as reduce } from './selection-history';

describe('component selection history', () => {
  it('returns through nested selections, forward visits and deselection without appending navigation', () => {
    let history = emptySelectionHistory;
    for (const id of ['assembly', 'wall', 'frame', 'stud', null]) history = reduce(history, { type: 'visit', id });
    history = reduce(history, { type: 'go', index: 3 });
    expect(history.entries[history.index]).toBe('frame');
    expect(history.entries).toEqual([null, 'assembly', 'wall', 'frame', 'stud', null]);
    history = reduce(history, { type: 'go', index: 4 });
    expect(history.entries[history.index]).toBe('stud');
    expect(reduce(history, { type: 'visit', id: 'stud' })).toBe(history);
    history = reduce(history, { type: 'visit', id: 'box' });
    expect(history.entries).toEqual([null, 'assembly', 'wall', 'frame', 'stud', 'box']);
  });

  it('bounds memory and ignores invalid history destinations', () => {
    let history = emptySelectionHistory;
    for (let index = 0; index < 110; index++) history = reduce(history, { type: 'visit', id: String(index) });
    expect(history.entries).toHaveLength(100);
    expect(history.entries[history.index]).toBe('109');
    for (const index of [-1, 100, NaN, 1.5]) expect(reduce(history, { type: 'go', index })).toBe(history);
    expect(emptySelectionHistory).toEqual({ entries: [null], index: 0 });
  });
});
