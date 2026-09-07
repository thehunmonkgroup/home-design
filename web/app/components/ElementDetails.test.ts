import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import ElementDetails from './ElementDetails';
import type { RenderManifest } from '../lib/model';

const manifest: RenderManifest = {
  format: 'home-design-render-manifest-0.1', modelVersion: '0.2', sourceRevision: 3,
  project: { id: 'test', name: 'Test' }, coordinateTransform: { source: 'mm', target: 'm', mapping: ['x', 'z', '-y'] },
  elements: {
    wall: { kind: 'wall', kindLabel: 'Walls', name: 'Office wall', storeyId: 'ground', nodes: ['wall'], defaultVisible: true, data: { netVolumeMm3: 1000000000 }, properties: [{ id: '/width', label: 'Wall length', value: 2438.4, unit: 'mm', group: 'Dimensions' }] },
    frame: { kind: 'wallFraming', name: 'Office studs', storeyId: 'ground', nodes: ['stud'], defaultVisible: true, data: {}, children: ['stud'] },
    stud: { kind: 'member', name: 'Office stud', storeyId: 'ground', nodes: ['stud'], defaultVisible: true, parentId: 'frame', data: { key: 'run.main/stud/0' } },
  },
  storeys: { ground: { name: 'Ground floor' } },
  navigation: { format: 'home-design-navigation-0.1', links: [{ sourceId: 'frame', targetId: 'wall', kind: 'host', sourceLabel: 'Host', targetLabel: 'Hosted component' }] },
};

describe('component inspector', () => {
  it('shows friendly units and navigable wall contents while keeping technical values expandable', () => {
    const html = renderToStaticMarkup(createElement(ElementDetails, { manifest, elementId: 'wall', units: 'imperial', onUnits: () => {}, onSelect: () => {}, onIsolate: () => {} }));
    expect(html).toContain('Ground floor');
    expect(html).toContain('8 ft 0 in');
    expect(html).toContain('Reveal wall contents');
    expect(html).toContain('Hosted component');
    expect(html).toContain('Office studs');
    expect(html).toContain('<summary>Technical properties</summary>');
    expect(html).not.toContain('Isolate system');
  });
  it('offers generated-member discovery and a return link to the generating assembly', () => {
    const props = { manifest, units: 'metric' as const, onUnits: () => {}, onSelect: () => {}, onIsolate: () => {} };
    const parent = renderToStaticMarkup(createElement(ElementDetails, { ...props, elementId: 'frame' }));
    expect(parent).toContain('Find generated members');
    expect(parent).toContain('run.main/stud/0');
    const child = renderToStaticMarkup(createElement(ElementDetails, { ...props, elementId: 'stud' }));
    expect(child).toContain('Back to Office studs');
  });
});
