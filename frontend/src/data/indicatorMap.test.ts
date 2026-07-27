import { describe, it, expect } from 'vitest';
import {
  catalogEntryToColumn,
  catalogParamsToBackendParams,
  formatOverlayLabel,
  idFromCatalog,
  paramsFromId,
  isOverlayColumn,
  midlineForColumn,
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
  // Full catalog names — the catalog endpoint returns these friendly
  // names, so they MUST resolve to a real backend column or the chart
  // endpoint silently drops the overlay (the "indicator doesn't show"
  // symptom). Regression guard for the gaps that existed before.
  it('maps full-name catalog indicators to real backend columns', () => {
    expect(catalogEntryToColumn('Bollinger Bands')).toBe('volatility_bbm');
    expect(catalogEntryToColumn('Average True Range')).toBe('volatility_atr');
    expect(catalogEntryToColumn('Chaikin Money Flow')).toBe('volume_cmf');
    expect(catalogEntryToColumn('Volume Price Trend')).toBe('volume_vpt');
    expect(catalogEntryToColumn('Ichimoku Cloud')).toBe('trend_ichimoku_conv');
  });
  it('maps Aroon to a real ta-bundle column (not bare trend_aroon)', () => {
    expect(catalogEntryToColumn('Aroon')).toBe('trend_aroon_ind');
  });
  it('maps PSAR to the single continuous series column', () => {
    // The ta bundle only emits trend_psar_up / trend_psar_down
    // (two half-series). The screening registry's PSARIndicator
    // compute path produces a single continuous series instead.
    expect(catalogEntryToColumn('PSAR')).toBe('trend_psar');
  });
  it('maps pandas-ta-only indicators to their backend compute columns', () => {
    expect(catalogEntryToColumn('KDJ')).toBe('momentum_kdj');
    expect(catalogEntryToColumn('Supertrend')).toBe('trend_supertrend');
    expect(catalogEntryToColumn('TTM Squeeze')).toBe('volatility_ttm_squeeze');
  });
});

describe('isOverlayColumn', () => {
  it('classifies moving averages as overlays', () => {
    expect(isOverlayColumn('trend_sma_fast')).toBe(true);
    expect(isOverlayColumn('trend_ema_fast')).toBe(true);
    expect(isOverlayColumn('momentum_kama')).toBe(true);
  });
  it('classifies Bollinger/Ichimoku as overlays (price-scaled)', () => {
    expect(isOverlayColumn('volatility_bbm')).toBe(true);
    expect(isOverlayColumn('trend_ichimoku_conv')).toBe(true);
  });
  it('classifies oscillators as non-overlay (separate pane)', () => {
    expect(isOverlayColumn('momentum_rsi')).toBe(false);
    expect(isOverlayColumn('trend_macd')).toBe(false);
    expect(isOverlayColumn('trend_adx')).toBe(false);
    expect(isOverlayColumn('volatility_atr')).toBe(false);
    expect(isOverlayColumn('volume_obv')).toBe(false);
  });
  it('defaults unknown columns to oscillator (safer separate pane)', () => {
    expect(isOverlayColumn('some_unknown_col')).toBe(false);
  });
});

describe('midlineForColumn', () => {
  it('returns the trading-convention midline for 0-100 oscillators', () => {
    expect(midlineForColumn('momentum_rsi')).toBe(50);
    expect(midlineForColumn('momentum_stoch_rsi')).toBe(50);
    expect(midlineForColumn('volume_mfi')).toBe(50);
    expect(midlineForColumn('trend_aroon_ind')).toBe(50);
  });
  it('returns 0 for signed momentum / MACD-style oscillators', () => {
    expect(midlineForColumn('momentum_roc')).toBe(0);
    expect(midlineForColumn('trend_macd')).toBe(0);
    expect(midlineForColumn('trend_macd_diff')).toBe(0);
    expect(midlineForColumn('momentum_ao')).toBe(0);
    expect(midlineForColumn('volume_cmf')).toBe(0);
    expect(midlineForColumn('volume_fi')).toBe(0);
    expect(midlineForColumn('volatility_ttm_squeeze')).toBe(0);
  });
  it('returns 50 for the KDJ K-line (0-100 oscillator)', () => {
    expect(midlineForColumn('momentum_kdj')).toBe(50);
  });
  it('returns the indicator-specific midpoint for non-zero midlines', () => {
    // Williams %R is -100..0
    expect(midlineForColumn('momentum_wr')).toBe(-50);
    // ADX 0-100; 25 is the conventional "trending" threshold
    expect(midlineForColumn('trend_adx')).toBe(25);
  });
  it('returns null for unbounded / asymmetric indicators', () => {
    // No meaningful midline — drawing a fake one would mislead.
    expect(midlineForColumn('volume_obv')).toBeNull();
    expect(midlineForColumn('volume_ad')).toBeNull();
    expect(midlineForColumn('volume_vpt')).toBeNull();
    expect(midlineForColumn('volatility_atr')).toBeNull();
    expect(midlineForColumn('volume_nvi')).toBeNull();
  });
  it('returns null for unknown columns', () => {
    expect(midlineForColumn('not_a_real_column')).toBeNull();
  });
});

describe('catalogParamsToBackendParams', () => {
  it('passes through lbp for WilliamsR (matches the registry param name)', () => {
    // The WilliamsR catalog param is `lbp`; the registry's
    // WilliamsRIndicator also takes `lbp`. The frontend should
    // pass it through unchanged (no translation needed).
    expect(catalogParamsToBackendParams('WilliamsR', { lbp: 21 })).toEqual({ lbp: 21 });
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
