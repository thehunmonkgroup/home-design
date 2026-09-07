import type { DisplayProperty } from './model';

export type DisplayUnits = 'metric' | 'imperial';

function scalar(value: number, digits = 3): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function feetInches(millimetres: number): string {
  const ticks = Math.round(Math.abs(millimetres) / 25.4 * 16);
  const feet = Math.floor(ticks / 192);
  const remaining = ticks % 192;
  const inches = Math.floor(remaining / 16);
  let numerator = remaining % 16;
  let denominator = 16;
  while (numerator > 0 && numerator % 2 === 0) { numerator /= 2; denominator /= 2; }
  return `${millimetres < 0 && ticks > 0 ? '−' : ''}${feet} ft ${inches}${numerator ? ` ${numerator}/${denominator}` : ''} in`;
}

export function formatDisplayProperty(property: DisplayProperty, units: DisplayUnits): string {
  const value = property.value;
  if (typeof value === 'string') return value;
  if (!Number.isFinite(value)) return 'Unavailable';
  switch (property.unit) {
    case 'mm': return units === 'imperial' ? feetInches(value) : Math.abs(value) >= 1000 ? `${scalar(value / 1000)} m` : `${scalar(value)} mm`;
    case 'mm2': return units === 'imperial' ? `${scalar(value / 92903.04)} ft²` : `${scalar(value / 1e6)} m²`;
    case 'mm3': return units === 'imperial' ? `${scalar(value / 28316846.592)} ft³` : `${scalar(value / 1e9, 6)} m³`;
    case 'deg': return `${scalar(value)}°`;
    case 'N': return `${scalar(value / 1000)} kN`;
    case 'count': return scalar(value, 0);
    case null: return scalar(value);
    default: return `${scalar(value)} ${property.unit}`;
  }
}
