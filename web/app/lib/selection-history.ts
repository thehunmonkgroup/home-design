export interface SelectionHistory {
  entries: Array<string | null>;
  index: number;
}

export type SelectionAction = { type: 'visit'; id: string | null } | { type: 'go'; index: number };

export const emptySelectionHistory: SelectionHistory = { entries: [null], index: 0 };

// Presentation history belongs to one loaded model, including deselection.
export function selectionHistoryReducer(history: SelectionHistory, action: SelectionAction): SelectionHistory {
  if (action.type === 'go') {
    if (!Number.isInteger(action.index) || action.index < 0 || action.index >= history.entries.length) return history;
    return { ...history, index: action.index };
  }
  if (history.entries[history.index] === action.id) return history;
  const entries = [...history.entries.slice(0, history.index + 1), action.id].slice(-100);
  return { entries, index: entries.length - 1 };
}
