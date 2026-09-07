import { describe, expect, it } from 'vitest';
import { formatDisplayProperty } from './properties';

describe('dimensioned property presentation', () => {
  it('converts mm, area and volume using their declared dimensions', () => {
    const property = { id: '/measure', label: 'Measure', group: 'Dimensions', value: 304.8, unit: 'mm' };
    expect(formatDisplayProperty(property, 'imperial')).toBe('1 ft 0 in');
    expect(formatDisplayProperty({ ...property, value: 2603.5 }, 'imperial')).toBe('8 ft 6 1/2 in');
    expect(formatDisplayProperty({ ...property, value: -2603.5 }, 'imperial')).toBe('−8 ft 6 1/2 in');
    expect(formatDisplayProperty({ ...property, value: 304.79 }, 'imperial')).toBe('1 ft 0 in');
    expect(formatDisplayProperty({ ...property, value: 92903.04, unit: 'mm2' }, 'imperial')).toBe('1 ft²');
    expect(formatDisplayProperty({ ...property, value: 28316846.592, unit: 'mm3' }, 'imperial')).toBe('1 ft³');
    expect(formatDisplayProperty({ ...property, value: 2000000000, unit: 'mm3' }, 'metric')).toBe('2 m³');
    expect(formatDisplayProperty({ ...property, value: 12, unit: 'count' }, 'imperial')).toBe('12');
    expect(formatDisplayProperty({ ...property, value: 30, unit: 'deg' }, 'imperial')).toBe('30°');
  });
});
