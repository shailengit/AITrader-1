/**
 * Maps each sub-score to the raw indicator values that fed it, plus a
 * one-line tooltip summary. Pure helpers — no React, no I/O.
 *
 * The mapping is documented in the spec (2026-07-05-screener-scoring-design.md
 * §2.3 and §4). Backend already returns the raw indicator values on each
 * result row; the frontend just maps them.
 *
 * Some indicators are exposed under two names because the backend's
 * `ta_to_friendly` map renames known columns but leaves the rest as the
 * raw `ta` names. We try both keys.
 */

export type SubScoreKey = 'trend_score' | 'momentum_score' | 'volatility_score' | 'volume_score';

export const SUB_SCORE_KEYS: readonly SubScoreKey[] = [
  'trend_score', 'momentum_score', 'volatility_score', 'volume_score',
] as const;

export interface IndicatorInput {
  label: string;
  value: number | string | null;
  note?: string;
}

function pick(row: Record<string, any>, ...keys: string[]): number | string | null {
  for (const k of keys) {
    if (row[k] !== undefined && row[k] !== null && !Number.isNaN(row[k])) {
      return row[k];
    }
  }
  return null;
}

function fmt(v: number | string | null, digits = 2): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string') return v;
  return v.toFixed(digits);
}

export function getSubScoreInputs(subScore: SubScoreKey, row: Record<string, any>): IndicatorInput[] {
  switch (subScore) {
    case 'trend_score':
      return [
        { label: 'ADX',          value: pick(row, 'trend_adx'),                note: 'peak at 50' },
        { label: 'SMA(20)',      value: pick(row, 'trend_sma_fast', 'sma_20'), note: 'close > fast > slow = 100' },
        { label: 'SMA(50)',      value: pick(row, 'trend_sma_slow', 'sma_50') },
        { label: 'Close',        value: pick(row, 'close') },
        { label: 'MACD diff',    value: pick(row, 'trend_macd_diff'),          note: 'positive = 100' },
      ];
    case 'momentum_score':
      return [
        { label: 'RSI(14)',      value: pick(row, 'momentum_rsi', 'rsi'),     note: 'peak at 65' },
        { label: 'ROC',          value: pick(row, 'momentum_roc'),             note: 'positive adds, negative subtracts' },
        { label: 'Stoch %K',     value: pick(row, 'momentum_stoch'),          note: 'peak at 55' },
      ];
    case 'volatility_score': {
      const atr = pick(row, 'volatility_atr');
      const close = pick(row, 'close');
      let atrPct: number | null = null;
      if (typeof atr === 'number' && typeof close === 'number' && close > 0) {
        atrPct = (atr / close) * 100;
      }
      return [
        { label: 'ATR',          value: atr },
        { label: 'ATR %',        value: atrPct,                                 note: 'peak band 1–5%' },
        { label: 'BBW',          value: pick(row, 'volatility_bbw'),           note: 'peak band 2–15' },
      ];
    }
    case 'volume_score':
      return [
        { label: 'Vol ratio',    value: pick(row, 'volume_ratio'),             note: 'peak 1–2x' },
        { label: 'MFI',          value: pick(row, 'volume_mfi'),               note: 'peak at 100' },
      ];
  }
}

export function getSubScoreTooltip(subScore: SubScoreKey, row: Record<string, any>): string {
  const inputs = getSubScoreInputs(subScore, row);
  return inputs
    .filter((i) => i.value !== null)
    .map((i) => `${i.label} ${fmt(i.value)}${i.note ? ` (${i.note})` : ''}`)
    .join(' · ');
}
