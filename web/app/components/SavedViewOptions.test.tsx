import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SavedViewOptions } from './SavedViewOptions';
import { groupSavedViews, type NamedView, type SavedViewGroup } from '../lib/saved-view-groups';

const rooms = { id: 'rooms', title: 'Rooms', order: 20 };
const exterior = { id: 'outside', title: 'Exterior', order: 10 };
const view = (id: string, title: string, group?: SavedViewGroup): NamedView =>
  ({ id, title, group, description: title, file: `${id}.json`, view: {} });

describe('saved view menus', () => {
  it('collects nonadjacent members, orders groups and alphabetizes without mutating input', () => {
    const views = [view('kitchen', 'Kitchen', rooms), view('site', 'Site', exterior),
      view('bedroom', 'bedroom', rooms), view('entry', 'Entry', exterior)];
    const before = JSON.stringify(views);
    expect(groupSavedViews(views).map((section) => [section.group?.id, section.views.map((item) => item.id)]))
      .toEqual([['outside', ['entry', 'site']], ['rooms', ['bedroom', 'kitchen']]]);
    expect(JSON.stringify(views)).toBe(before);
    const html = renderToStaticMarkup(<select defaultValue="kitchen"><SavedViewOptions views={views} /></select>);
    expect(html).toBe('<select><optgroup label="Exterior"><option value="entry">Entry</option><option value="site">Site</option></optgroup><optgroup label="Rooms"><option value="bedroom">bedroom</option><option value="kitchen" selected="">Kitchen</option></optgroup></select>');
  });

  it('breaks equal priorities by group title and ID, and equal view titles by ID', () => {
    const views = [view('z', 'Same', { id: 'b', title: 'Details', order: -1 }),
      view('b', 'Same', { id: 'a', title: 'Details', order: -1 }),
      view('a', 'same', { id: 'a', title: 'Details', order: -1 }),
      view('first', 'First', { id: 'z', title: 'Around the house', order: -1 })];
    expect(groupSavedViews(views).map((section) => section.views.map((item) => item.id)))
      .toEqual([['first'], ['a', 'b'], ['z']]);
  });

  it('keeps entirely ungrouped models flat and alphabetized', () => {
    const html = renderToStaticMarkup(<select><SavedViewOptions views={[view('z', 'Zulu'), view('a', 'Alpha')]} /></select>);
    expect(html).toBe('<select><option value="a">Alpha</option><option value="z">Zulu</option></select>');
    expect(groupSavedViews([])).toEqual([]);
  });

  it('places ungrouped views last without colliding with an authored fallback-like ID', () => {
    const views = [view('z', 'Zulu'), view('a', 'Alpha'),
      view('named', 'Named', { id: 'ungrouped', title: 'Custom', order: 9999 })];
    const html = renderToStaticMarkup(<select><SavedViewOptions views={views} /></select>);
    expect(html).toBe('<select><optgroup label="Custom"><option value="named">Named</option></optgroup><optgroup label="Other views"><option value="a">Alpha</option><option value="z">Zulu</option></optgroup></select>');
  });
});
