import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import DesignRequirements from './DesignRequirements';
import { requirementStatusLabel, type RenderManifest, type RequirementResult } from '../lib/model';

const manifest: RenderManifest = {
  format: 'home-design-render-manifest-0.1', modelVersion: '0.1', sourceRevision: 3,
  project: { id: 'test', name: 'Test' },
  coordinateTransform: { source: 'mm', target: 'm', mapping: ['x', 'z', '-y'] },
  elements: {},
  requirements: [{ id: 'width', statement: 'Preserve width.', severity: 'error', appliesTo: ['stair.test'], check: { property: 'clearWidth', operator: 'atLeast', value: 1220 } }],
};

describe('requirement presentation', () => {
  it.each<RequirementResult['status']>(['satisfied', 'violated', 'notChecked'])('displays the exported %s result separately from severity', (status) => {
    const result: RequirementResult = { id: 'width', status, checks: [] };
    const html = renderToStaticMarkup(createElement(DesignRequirements, { manifest: { ...manifest, requirementResults: [result] } }));
    expect(html).toContain(requirementStatusLabel(result));
    expect(html).toContain('Violation severity: error');
    expect(html).not.toContain('<strong>error:');
  });

  it('does not infer success when evaluation results are absent', () => {
    const html = renderToStaticMarkup(createElement(DesignRequirements, { manifest }));
    expect(html).toContain('Status unavailable');
    expect(html).not.toContain('Satisfied');
  });

  it('shows measured and required values from the result without rerunning checks', () => {
    const result: RequirementResult = {
      id: 'width', status: 'satisfied', checks: [{ elementId: 'stair.test', property: 'clearWidth', operator: 'atLeast', actual: 1220, expected: 1220, status: 'satisfied' }],
    };
    const html = renderToStaticMarkup(createElement(DesignRequirements, { manifest: { ...manifest, requirementResults: [result] } }));
    expect(html).toContain('clear width — 1.22 m; required at least 1.22 m. Satisfied.');
  });

  it('presents unchecked guidance as a note, not an error or passed check', () => {
    const html = renderToStaticMarkup(createElement(DesignRequirements, { manifest: {
      ...manifest,
      requirements: [{ id: 'note', statement: 'Obtain review.', severity: 'info' }],
      requirementResults: [{ id: 'note', status: 'notChecked', checks: [] }],
    } }));
    expect(html).toContain('Note level: info');
    expect(html).toContain('Not automatically checked');
    expect(html).not.toContain('Violation severity');
  });
});
