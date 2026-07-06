import { describe, it, expect } from 'vitest';
import {
  catalogEntryToColumn,
  catalogParamsToBackendParams,
  formatOverlayLabel,
  idFromCatalog,
  paramsFromId,
} from './indicatorMap';

describe('catalogEntryToColumn', () => {
  it('maps RSI to momentum_rsi', () => {
    expect(catalogEntryToColumn('RSI')).toBe('momentum_rsi');
  });
  it('maps EMA to trend_ema_fast', () => {
    expect(catalogEntryToColumn('EMA')).toBe('trend_ema_fast');
  });
  it('maps MACD to trend_macd', () => {
    expect(catalogEntryToColumn('MACD')).toBe('trend_macd');
  });
  it('returns input as-is for unknown indicators', () => {
    expect(catalogEntryToColumn('FooBar')).toBe('FooBar');
  });
});

describe('catalogParamsToBackendParams', () => {
  it('translates WilliamsR lbp to window', () => {
    expect(catalogParamsToBackendParams('WilliamsR', { lbp: 21 })).toEqual({ window: 21 });
  });
  it('passes through standard window param', () => {
    expect(catalogParamsToBackendParams('RSI', { window: 21 })).toEqual({ window: 21 });
  });
  it('passes through MACD triple-window', () => {
    expect(
      catalogParamsToBackendParams('MACD', { window_fast: 12, window_slow: 26, window_sign: 9 }),
    ).toEqual({ window_fast: 12, window_slow: 26, window_sign: 9 });
  });
});

describe('formatOverlayLabel', () => {
  it('formats RSI with single window', () => {
    expect(formatOverlayLabel('RSI', { window: 21 })).toBe('RSI (21)');
  });
  it('formats MACD with three windows', () => {
    expect(
      formatOverlayLabel('MACD', { window_fast: 12, window_slow: 26, window_sign: 9 }),
    ).toBe('MACD (12,26,9)');
  });
  it('returns name alone when no params', () => {
    expect(formatOverlayLabel('ATR', {})).toBe('ATR');
  });
});

describe('idFromCatalog / paramsFromId', () => {
  it('round-trips a single-window id', () => {
    const id = idFromCatalog('RSI', { window: 14 });
    expect(id).toMatch(/^ta__RSI__/);
    expect(paramsFromId(id)).toEqual({ window: 14 });
  });
  it('round-trips a multi-param id', () => {
    const params = { window_fast: 12, window_slow: 26, window_sign: 9 };
    const id = idFromCatalog('MACD', params);
    expect(id).toMatch(/^ta__MACD__/);
    expect(paramsFromId(id)).toEqual(params);
  });
  it('produces distinct ids for distinct params', () => {
    expect(idFromCatalog('EMA', { window: 20 })).not.toBe(
      idFromCatalog('EMA', { window: 200 }),
    );
  });
});
