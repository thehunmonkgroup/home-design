import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ModelLoading } from './ModelLoading';

describe('visible model loading feedback', () => {
  it('shows a determinate, accessible bar with bytes and percentage', () => {
    const html = renderToStaticMarkup(<ModelLoading progress={{ phase: 'downloading', loadedBytes: 250000, totalBytes: 1000000 }} />);
    expect(html).toContain('aria-label="Model download"');
    expect(html).toContain('value="25"');
    expect(html).toContain('25%');
    expect(html).toContain('0.25 MB of 1.00 MB downloaded');
  });

  it('shows an indeterminate bar when a total is unavailable', () => {
    const html = renderToStaticMarkup(<ModelLoading progress={{ phase: 'downloading', loadedBytes: 250000 }} />);
    expect(html).not.toContain('value=');
    expect(html).not.toContain('%');
    expect(html).toContain('0.25 MB downloaded');
  });

  it('distinguishes download completion from model preparation', () => {
    const html = renderToStaticMarkup(<ModelLoading progress={{ phase: 'preparing', loadedBytes: 100, totalBytes: 100 }} />);
    expect(html).toContain('Preparing model');
    expect(html).not.toContain('100%');
    expect(html).toContain('Download complete. Preparing the 3D view');
  });
});
