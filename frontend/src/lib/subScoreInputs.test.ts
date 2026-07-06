import { describe, it, expect } from 'vitest';
import { getSubScoreInputs, getSubScoreTooltip, SUB_SCORE_KEYS } from './subScoreInputs';

const SAMPLE_ROW = {
  trend_adx: 22.4,
  trend_sma_fast: 198.3,
  trend_sma_slow: 192.1,
  close: 201.45,
  trend_macd_diff: 0.42,
  momentum_rsi: 65.0,
  momentum_roc: 2.0,
  momentum_stoch: 50.0,
  volatility_atr: 3.0,
  volatility_bbw: 8.0,
  volume_ratio: 1.2,
  volume_mfi: 60.0,
};

describe('SUB_SCORE_KEYS', () => {
  it('has the four sub-scores in display order', () => {
    expect(SUB_SCORE_KEYS).toEqual(['trend_score', 'momentum_score', 'volatility_score', 'volume_score']);
  });
});

describe('getSubScoreInputs', () => {
  it('returns trend inputs in order with the right labels', () => {
    const inputs = getSubScoreInputs('trend_score', SAMPLE_ROW);
    expect(inputs.map((i) => i.label)).toEqual(['ADX', 'SMA(20)', 'SMA(50)', 'Close', 'MACD diff']);
    expect(inputs[0].value).toBe(22.4);
  });

  it('returns momentum inputs in order', () => {
    const inputs = getSubScoreInputs('momentum_score', SAMPLE_ROW);
    expect(inputs.map((i) => i.label)).toEqual(['RSI(14)', 'ROC', 'Stoch %K']);
  });

  it('computes ATR% from ATR and close when both are present', () => {
    const inputs = getSubScoreInputs('volatility_score', SAMPLE_ROW);
    const atrPct = inputs.find((i) => i.label === 'ATR %');
    expect(atrPct).toBeDefined();
    expect(atrPct!.value).toBeCloseTo(3.0 / 201.45 * 100, 4);
  });

  it('returns volume inputs in order', () => {
    const inputs = getSubScoreInputs('volume_score', SAMPLE_ROW);
    expect(inputs.map((i) => i.label)).toEqual(['Vol ratio', 'MFI']);
  });

  it('handles missing columns gracefully (returns null values, no throw)', () => {
    const inputs = getSubScoreInputs('trend_score', { close: 100 });
    expect(inputs[0].value).toBeNull();
    expect(inputs[1].value).toBeNull();
  });

  it('falls back to the friendly name when the ta name is missing', () => {
    // Backend sometimes renames `trend_sma_fast` to `sma_20`. Verify fallback.
    const inputs = getSubScoreInputs('trend_score', { sma_20: 100, sma_50: 95 });
    expect(inputs[1].value).toBe(100);
    expect(inputs[2].value).toBe(95);
  });
});

describe('getSubScoreTooltip', () => {
  it('produces a one-line summary for trend', () => {
    const s = getSubScoreTooltip('trend_score', SAMPLE_ROW);
    expect(s).toContain('ADX');
    expect(s).toContain('SMA(20)');
    expect(s).toContain('MACD diff');
    expect(s).not.toContain('null');
  });
});
