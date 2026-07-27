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

/** Map catalog name → backend column.
 *
 *  Keys include BOTH the full names the catalog actually returns (e.g.
 *  "Bollinger Bands", "Average True Range", "Ichimoku Cloud") AND the
 *  short aliases some callers still use (e.g. "BB", "ATR"). An unknown
 *  name falls through to itself, which the chart endpoint silently
 *  drops — so every catalog indicator that should render on the chart
 *  MUST be listed here. */
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
  // Aroon: the ta bundle emits trend_aroon_{up,down,ind}; there is no
  // bare `trend_aroon` column. Map to the oscillator line so it renders.
  Aroon: 'trend_aroon_ind',
  // PSAR: the ta bundle only emits trend_psar_up / trend_psar_down
  // (two half-series). We compute a single continuous series via
  // PSARIndicator(high, low, close).psar() in the screening registry
  // so the chart can render PSAR as one line on the price pane.
  PSAR: 'trend_psar',
  'Ichimoku Cloud': 'trend_ichimoku_conv',
  // Volatility
  'Bollinger Bands': 'volatility_bbm', // middle band (price-scaled)
  BB: 'volatility_bbm',
  'Average True Range': 'volatility_atr',
  ATR: 'volatility_atr',
  Donchian: 'volatility_dcl',
  Keltner: 'volatility_kcc',
  // Volume
  OBV: 'volume_obv',
  MFI: 'volume_mfi',
  AD: 'volume_ad',
  'Chaikin Money Flow': 'volume_cmf',
  CMF: 'volume_cmf',
  FI: 'volume_fi',
  EOM: 'volume_eom',
  'Volume Price Trend': 'volume_vpt',
  VPT: 'volume_vpt',
  NVI: 'volume_nvi',
  PVI: 'volume_pvi',
  // pandas-ta-only indicators (KDJ K-line, Supertrend, TTM Squeeze
  // momentum line). Computed server-side via custom compute
  // functions in the screening registry.
  KDJ: 'momentum_kdj',
  Supertrend: 'trend_supertrend',
  'TTM Squeeze': 'volatility_ttm_squeeze',
};

/**
 * Backend columns whose values live in the SAME units as price and so
 * should be drawn as an OVERLAY on the candle pane (sharing the price
 * scale). Everything else is an oscillator / independent-scale indicator
 * and is drawn in its own pane below the candles so it doesn't get
 * squished against the price axis (RSI 0-100, MACD ~0, ADX 0-100, ATR,
 * volume oscillators, …).
 *
 * Unknown columns default to oscillator (safer — an independent pane is
 * always harmless; a wrongly-shared price scale hides the series). */
const OVERLAY_COLUMNS: ReadonlySet<string> = new Set([
  // Moving averages (price-scaled)
  'trend_sma_fast', 'trend_sma_slow',
  'trend_ema_fast', 'trend_ema_slow',
  'trend_wma', 'trend_dema', 'trend_tema',
  'momentum_kama',
  // Bollinger / Keltner / Donchian bands (price-scaled)
  'volatility_bbm', 'volatility_bbh', 'volatility_bbl', 'volatility_bbp', 'volatility_bbw',
  'volatility_kcc', 'volatility_kch', 'volatility_kcl', 'volatility_kcw',
  'volatility_dcl', 'volatility_dch', 'volatility_dcm',
  // PSAR + Supertrend (price-scaled overlays — drawn on the candle pane)
  'trend_psar', 'trend_supertrend',
  // Ichimoku lines (price-scaled overlays)
  'trend_ichimoku_conv', 'trend_ichimoku_base', 'trend_ichimoku_a', 'trend_ichimoku_b',
  // Legacy friendly column names used by older overlay URLs
  'sma_50', 'sma_100', 'sma_200', 'ema_20', 'ema_50', 'ema_200',
]);

/** True if the indicator column is price-scaled and should overlay the
 *  candles (share the price scale). False → draw in a separate pane. */
export function isOverlayColumn(column: string): boolean {
  return OVERLAY_COLUMNS.has(column);
}

/**
 * Canonical "midline" value for each bounded oscillator.
 *
 *  Trading convention: each bounded oscillator has a midpoint that
 *  represents the "neutral" reading — values above it are bullish,
 *  below it bearish. The chart draws a horizontal reference line at
 *  this value so the user can read the indicator's state at a glance
 *  (RSI > 50 = bullish, MACD > 0 = bullish, etc).
 *
 *  Indicators not in this map are either:
 *    - price-scaled overlays (no midline needed — already on the price
 *      axis), or
 *    - unbounded / asymmetric (OBV, AD, VPT, ATR, …) — no meaningful
 *      midline exists, so the chart draws none rather than a fake one.
 *
 *  Numbers are midpoints of the indicator's natural domain as defined
 *  by the `ta` library / trading convention. Keep in sync with
 *  `INDICATOR_REGISTRY` so the same indicator names map consistently. */
const MIDLINE_BY_COLUMN: Record<string, number> = {
  // 0-100 momentum oscillators
  momentum_rsi: 50,
  momentum_stoch_rsi: 50,
  momentum_wr: -50, // Williams %R is -100..0
  momentum_stoch: 50,
  momentum_stoch_signal: 50,
  momentum_uo: 50, // Ultimate Oscillator 0-100
  momentum_kdj: 50, // KDJ K-line 0-100
  // momentum (rate/oscillator, signed)
  momentum_roc: 0,
  momentum_ao: 0, // Awesome Oscillator
  momentum_ppo: 0, // Percentage Price Oscillator
  momentum_tsi: 0, // True Strength Index
  // trend-based oscillators
  trend_macd: 0, // MACD line
  trend_macd_diff: 0, // MACD histogram
  trend_adx: 25, // ADX 0-100; 25 = "trending" threshold
  trend_cci: 0, // CCI typically -200..200, midline 0
  trend_trix: 0, // TRIX percentage, signed
  trend_aroon_ind: 50, // 0-100
  // volatility oscillators (bounded)
  volatility_bbp: 0.5, // Bollinger %b: 0=lower, 1=upper; 0.5 is the band midpoint
  volatility_ui: 0, // Ulcer Index 0+, but 0 is the "no drawdown" baseline
  volatility_ttm_squeeze: 0, // TTM Squeeze momentum line, signed
  // volume oscillators
  volume_mfi: 50, // 0-100
  volume_cmf: 0, // Chaikin Money Flow -1..1, midline 0
  volume_fi: 0, // Force Index, signed
  // momentum (overlap/oscillator)
  momentum_kama: 0, // KAMA *delta* — rare as a standalone; left at 0
};

/** The canonical midline for a column, or `null` if the indicator has
 *  no meaningful midpoint (unbounded / asymmetric). */
export function midlineForColumn(column: string): number | null {
  return Object.prototype.hasOwnProperty.call(MIDLINE_BY_COLUMN, column)
    ? MIDLINE_BY_COLUMN[column]
    : null;
}

/** Translate a catalog param name to the registry's param name. */
const PARAM_NAME_OVERRIDES: Record<string, Record<string, string>> = {
  // Most catalog params already match the registry (e.g. 'window',
  // 'smooth1', 'lbp'). Override only when the catalog and the
  // backend registry use different names for the same param.
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
