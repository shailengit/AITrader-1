/**
 * Helpers that translate the public /api/indicators/catalog vocabulary
 * (e.g. "RSI", "EMA", "MACD") into the backend's column vocabulary
 * (e.g. "momentum_rsi", "trend_ema_fast", "trend_macd") and produce
 * stable, URL-safe indicator ids.
 *
 * The catalog is the same one QuantGen's IndicatorBrowser uses; the chart
 * endpoint and INDICATOR_REGISTRY use the column names. This file is the
 * bridge.
 *
 * The mapping is hand-curated. It covers the ~25 entries the catalog
 * actually returns. Unknown names fall through to the name as-is — the
 * chart endpoint will silently skip an unknown column rather than fail.
 */

/** Map catalog name → backend column. */
const NAME_TO_COLUMN: Record<string, string> = {
  // Momentum
  RSI: 'momentum_rsi',
  StochRSI: 'momentum_stoch_rsi',
  MACD: 'trend_macd',
  'Williams %R': 'momentum_wr',
  WilliamsR: 'momentum_wr',
  ROC: 'momentum_roc',
  'Awesome Oscillator': 'momentum_ao',
  AO: 'momentum_ao',
  KAMA: 'momentum_kama',
  // Trend
  SMA: 'trend_sma_fast',
  EMA: 'trend_ema_fast',
  WMA: 'trend_wma',
  DEMA: 'trend_dema',
  TEMA: 'trend_tema',
  TRIX: 'trend_trix',
  ADX: 'trend_adx',
  CCI: 'trend_cci',
  Aroon: 'trend_aroon',
  // Volatility
  BB: 'volatility_bbm', // Bollinger middle band
  ATR: 'volatility_atr',
  Donchian: 'volatility_dcl',
  Keltner: 'volatility_kcc',
  // Volume
  OBV: 'volume_obv',
  MFI: 'volume_mfi',
  AD: 'volume_ad',
  CMF: 'volume_cmf',
  FI: 'volume_fi',
  EOM: 'volume_eom',
  VPT: 'volume_vpt',
  NVI: 'volume_nvi',
  PVI: 'volume_pvi',
};

/** Translate a catalog param name to the registry's param name. */
const PARAM_NAME_OVERRIDES: Record<string, Record<string, string>> = {
  WilliamsR: { lbp: 'window' },
  'Williams %R': { lbp: 'window' },
  // Most catalog params already match the registry (e.g. 'window', 'smooth1').
};

/** Stable signature for a params dict. Base64(JSON([[key,value],…]))
 *  keeps the id URL-safe (no commas/brackets in the id) and unambiguous
 *  (key/value boundaries are explicit, not inferred from key prefixes).
 *  The encoded form decodes losslessly via `paramsFromId`. */
function paramsSig(params: Record<string, number>): string {
  const sorted = Object.keys(params).sort();
  const json = JSON.stringify(sorted.map((k) => [k, params[k]]));
  // btoa is available in browsers and in Node 16+; works for ASCII JSON.
  return btoa(json);
}

export function catalogEntryToColumn(name: string): string {
  return NAME_TO_COLUMN[name] ?? name;
}

export function catalogParamsToBackendParams(
  name: string,
  values: Record<string, number>,
): Record<string, number> {
  const overrides = PARAM_NAME_OVERRIDES[name] ?? {};
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(values)) {
    out[overrides[k] ?? k] = v;
  }
  return out;
}

export function formatOverlayLabel(
  name: string,
  params: Record<string, number>,
): string {
  const keys = Object.keys(params);
  if (keys.length === 0) return name;
  // Special-case: MACD / MACD-like → use the three-window convention
  if (
    'window_fast' in params &&
    'window_slow' in params &&
    'window_sign' in params
  ) {
    return `${name} (${params.window_fast},${params.window_slow},${params.window_sign})`;
  }
  // Default: stable order by key, comma-joined
  const ordered = Object.entries(params)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, v]) => v);
  return `${name} (${ordered.join(',')})`;
}

/** Stable short signature for an indicator-params dict.
 *  Mirrors the backend's `_params_signature` in
 *  `app/services/screening/chart_data.py`. Two requests with the same
 *  params collapse to the same signature, so the dedup key in
 *  `getColumnsForFilters` only collapses genuinely-duplicate columns.
 *
 *  Examples:
 *    None        → ""
 *    {w:20}      → "w20"
 *    {w:200}     → "w200"
 *    {w:20,b:2}  → "b2_w20"  (sorted keys for determinism)
 */
export function paramsSignature(params?: Record<string, number>): string {
  if (!params || Object.keys(params).length === 0) return "";
  const items = Object.entries(params).sort(([a], [b]) => a.localeCompare(b));
  return items.map(([k, v]) => `${k}${v}`).join("_");
}

/** Build the chart-endpoint payload key for a (column, params) pair. */
export function chartPayloadKey(
  column: string,
  params?: Record<string, number>,
): string {
  const sig = paramsSignature(params);
  return sig ? `${column}__${sig}` : column;
}

export function idFromCatalog(
  name: string,
  params: Record<string, number>,
): string {
  const sig = paramsSig(params);
  return `ta__${name}__${sig}`;
}

export function paramsFromId(id: string): Record<string, number> {
  // id looks like "ta__<Name>__<base64Sig>". The sig decodes to a JSON
  // array of [key, value] pairs.
  const match = /^([^_]+)__(.+)__(.+)$/.exec(id);
  if (!match) return {};
  try {
    const json = atob(match[3]);
    const arr = JSON.parse(json) as Array<[string, number]>;
    const out: Record<string, number> = {};
    for (const [k, v] of arr) {
      out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}
