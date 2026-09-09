import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PanelControls from './PanelControls';

describe('panel controls', () => {
  it('keeps tools available during loading while disabling camera framing', () => {
    const html = renderToStaticMarkup(createElement(PanelControls, {
      visibility: { components: false, details: false }, active: 'tools', onToggle: () => {}, onFrame: () => {}, ready: false,
    }));
    expect(html).toContain('aria-controls="tools-panel" aria-expanded="true"');
    expect(html.match(/disabled=""/g)).toHaveLength(1);
    expect(html).toContain('aria-label="Frame model"');
  });
  it.each([true, false])('keeps both controls available when visibility is %s', (open) => {
    const html = renderToStaticMarkup(createElement(PanelControls, {
      visibility: { components: open, details: open }, onToggle: () => {}, active: null, onFrame: () => {}, ready: true,
    }));
    expect(html).toContain('Components');
    expect(html).toContain('Details');
    expect(html).toContain('aria-controls="components-panel"');
    expect(html).toContain('aria-controls="details-panel"');
    expect(html.match(new RegExp(`aria-expanded="${open}"`, 'g'))).toHaveLength(open ? 2 : 4);
    expect(html.match(/type="button"/g)).toHaveLength(5);
  });
});
