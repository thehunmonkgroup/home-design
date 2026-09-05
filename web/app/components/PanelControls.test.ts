import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PanelControls from './PanelControls';

describe('panel controls', () => {
  it.each([true, false])('keeps both controls available when visibility is %s', (open) => {
    const html = renderToStaticMarkup(createElement(PanelControls, {
      visibility: { components: open, details: open }, onToggle: () => {},
    }));
    expect(html).toContain(`${open ? 'Hide' : 'Show'} Components`);
    expect(html).toContain(`${open ? 'Hide' : 'Show'} Details`);
    expect(html).toContain('aria-controls="components-panel"');
    expect(html).toContain('aria-controls="details-panel"');
    expect(html.match(new RegExp(`aria-expanded="${open}"`, 'g'))).toHaveLength(2);
    expect(html.match(/type="button"/g)).toHaveLength(2);
  });
});
