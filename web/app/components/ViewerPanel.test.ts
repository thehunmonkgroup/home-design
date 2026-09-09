import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import ViewerPanel from './ViewerPanel';

// Drawers remain mounted so switching tools does not discard filters or details.
// Hidden surfaces must still leave the accessibility and keyboard navigation tree.
describe('viewer drawers', () => {
  it.each([true, false])('keeps content mounted with open=%s', (open) => {
    const html = renderToStaticMarkup(createElement(ViewerPanel, {
      id: 'components-panel', title: 'Components', open, onClose: () => {},
      children: createElement('input', { 'aria-label': 'Filter', defaultValue: 'wall' }),
    }));
    expect(html.includes('hidden=""')).toBe(!open);
    expect(html).toContain('value="wall"');
    expect(html).toContain('aria-label="Close Components"');
    expect(html).toContain('aria-label="Components"');
    expect(html).not.toContain('aria-modal');
  });
});
