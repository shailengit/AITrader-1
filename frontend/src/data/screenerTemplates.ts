import type { FilterCategory } from './filterCatalog';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FilterCondition {
  id: string;
  filterKey: string;
  operator: string;
  value: unknown;
  referenceFilterKey?: string;
  lookbackDays?: number;
  params?: Record<string, number>;
  referenceParams?: Record<string, number>;
  compareToIndicator?: boolean;
}

export interface FilterGroup {
  match: 'all' | 'any';
  conditions: FilterCondition[];
}

export interface ScreenTemplate {
  isTemplate: true;
  id: string;
  name: string;
  description: string;
  category: FilterCategory;
  filters: FilterGroup;
  sort?: { by: string; order: 'asc' | 'desc' };
  maxResults: number;
  useAi: boolean;
  // Scoring tunables (added 2026-07-05). All optional — defaults applied on load.
  baseWeight?: number;
  subWeights?: {
    trend: number;
    momentum: number;
    volatility: number;
    volume: number;
  };
  showAlignment?: boolean;
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

export const SCREENER_TEMPLATES: ScreenTemplate[] = [
  // ── 1. Dormant Giant ─────────────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-dormant-giant',
    name: 'Dormant Giant',
    description:
      'Bollinger squeeze + OBV accumulation + EPS acceleration. Identifies stocks in tight consolidation with institutional accumulation and strong sector tailwinds.',
    category: 'momentum',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-dg-1',
          filterKey: 'volatility_bbw_pct',
          operator: 'lt',
          value: 20,
          params: { window: 20, window_dev: 2 },
        },
        {
          id: 'tpl-dg-2',
          filterKey: 'consolidation_tightness',
          operator: 'gte',
          value: 75,
        },
        {
          id: 'tpl-dg-3',
          filterKey: 'mfi',
          operator: 'gt',
          value: 55,
          params: { window: 14 },
        },
        {
          id: 'tpl-dg-4',
          filterKey: 'volume_cluster_count',
          operator: 'gte',
          value: 3,
        },
        {
          id: 'tpl-dg-5',
          filterKey: 'rs_vs_sector',
          operator: 'gte',
          value: 0.8,
        },
        {
          id: 'tpl-dg-6',
          filterKey: 'sector_above_sma50',
          operator: 'eq',
          value: true,
        },
      ],
    },
    sort: { by: 'score', order: 'desc' },
    maxResults: 50,
    useAi: true,
  },

  // ── 2. Quant Strategy ───────────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-quant-strategy',
    name: 'Quant Strategy',
    description:
      'General technical analysis screener. Filters for reasonable RSI range and minimum volume activity across the full universe.',
    category: 'momentum',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-qs-1',
          filterKey: 'rsi',
          operator: 'gte',
          value: 30,
          params: { window: 14 },
        },
        {
          id: 'tpl-qs-2',
          filterKey: 'rsi',
          operator: 'lte',
          value: 70,
          params: { window: 14 },
        },
        {
          id: 'tpl-qs-3',
          filterKey: 'volume_ratio',
          operator: 'gte',
          value: 0.7,
        },
      ],
    },
    sort: { by: 'ticker', order: 'asc' },
    maxResults: 50,
    useAi: false,
  },

  // ── 3. Golden Cross ─────────────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-golden-cross',
    name: 'Golden Cross',
    description:
      'SMA 50 crosses above SMA 200 — a classic long-term bullish signal. Captures stocks entering a new uptrend.',
    category: 'trend',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-gc-1',
          filterKey: 'sma_50',
          operator: 'crossed_above',
          value: null,
          referenceFilterKey: 'sma_200',
          lookbackDays: 1,
          params: { window: 50 },
        },
      ],
    },
    sort: { by: 'ticker', order: 'asc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 4. RSI Oversold Bounce ──────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-rsi-oversold',
    name: 'RSI Oversold Bounce',
    description:
      'RSI below 30 with above-average volume. Identifies potential reversal candidates from oversold conditions.',
    category: 'momentum',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-ro-1',
          filterKey: 'rsi',
          operator: 'lt',
          value: 30,
          params: { window: 14 },
        },
        {
          id: 'tpl-ro-2',
          filterKey: 'volume_ratio',
          operator: 'gte',
          value: 0.8,
        },
      ],
    },
    sort: { by: 'rsi', order: 'asc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 5. EPS Growth > 20% ────────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-eps-growth',
    name: 'EPS Growth > 20%',
    description:
      'Strong earnings growth with double-digit revenue growth. Finds companies with accelerating fundamental performance.',
    category: 'growth_quality',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-eg-1',
          filterKey: 'eps_growth_qoq',
          operator: 'gt',
          value: 20,
        },
        {
          id: 'tpl-eg-2',
          filterKey: 'revenue_growth_qoq',
          operator: 'gt',
          value: 10,
        },
      ],
    },
    sort: { by: 'eps_growth_qoq', order: 'desc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 6. Value + GARP ────────────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-value-garp',
    name: 'Value + GARP',
    description:
      'Reasonable valuation with growth. P/E under 25, PEG under 2, and positive EPS growth. Growth at a reasonable price.',
    category: 'valuation',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-vg-1',
          filterKey: 'pe_ttm',
          operator: 'lt',
          value: 25,
        },
        {
          id: 'tpl-vg-2',
          filterKey: 'peg_ratio',
          operator: 'lt',
          value: 2,
        },
        {
          id: 'tpl-vg-3',
          filterKey: 'eps_growth_qoq',
          operator: 'gt',
          value: 10,
        },
      ],
    },
    sort: { by: 'peg_ratio', order: 'asc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 7. CANSLIM-lite ─────────────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-canslim-lite',
    name: 'CANSLIM-lite',
    description:
      'Momentum + growth inspired by William O\'Neil\'s CANSLIM system. Strong EPS and revenue growth, near highs, with heavy volume.',
    category: 'growth_quality',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-cl-1',
          filterKey: 'eps_growth_qoq',
          operator: 'gt',
          value: 20,
        },
        {
          id: 'tpl-cl-2',
          filterKey: 'revenue_growth_qoq',
          operator: 'gt',
          value: 15,
        },
        {
          id: 'tpl-cl-3',
          filterKey: 'ath_proximity',
          operator: 'gte',
          value: 90,
        },
        {
          id: 'tpl-cl-4',
          filterKey: 'volume_ratio',
          operator: 'gte',
          value: 1.0,
        },
      ],
    },
    sort: { by: 'eps_growth_qoq', order: 'desc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 8. Low-Float Squeeze Watch ──────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-squeeze-watch',
    name: 'Low-Float Squeeze Watch',
    description:
      'Tight consolidation with low volume. Stocks coiling up with decreasing interest — potential breakout candidates.',
    category: 'volatility',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-sw-1',
          filterKey: 'volatility_bbw_pct',
          operator: 'lt',
          value: 20,
          params: { window: 20, window_dev: 2 },
        },
        {
          id: 'tpl-sw-2',
          filterKey: 'consolidation_tightness',
          operator: 'gte',
          value: 80,
        },
        {
          id: 'tpl-sw-3',
          filterKey: 'volume_ratio',
          operator: 'lt',
          value: 0.8,
        },
      ],
    },
    sort: { by: 'consolidation_tightness', order: 'desc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 9. Post-Earnings Drift ──────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-post-earnings-drift',
    name: 'Post-Earnings Drift',
    description:
      'Strong earnings surprise with price near highs and heavy volume. Captures post-earnings momentum drift.',
    category: 'momentum',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-ped-1',
          filterKey: 'eps_growth_qoq',
          operator: 'gt',
          value: 30,
        },
        {
          id: 'tpl-ped-2',
          filterKey: 'ath_proximity',
          operator: 'gte',
          value: 95,
        },
        {
          id: 'tpl-ped-3',
          filterKey: 'volume_ratio',
          operator: 'gte',
          value: 1.2,
        },
      ],
    },
    sort: { by: 'eps_growth_qoq', order: 'desc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 10. Volatility Squeeze Breakout ─────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-squeeze-breakout',
    name: 'Volatility Squeeze Breakout',
    description:
      'Bollinger squeeze with volume cluster and strong relative strength. High-probability breakout setup.',
    category: 'volatility',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-sb-1',
          filterKey: 'volatility_bbw_pct',
          operator: 'lt',
          value: 20,
          params: { window: 20, window_dev: 2 },
        },
        {
          id: 'tpl-sb-2',
          filterKey: 'volume_cluster_count',
          operator: 'gte',
          value: 3,
        },
        {
          id: 'tpl-sb-3',
          filterKey: 'rs_vs_sector',
          operator: 'gte',
          value: 1.0,
        },
      ],
    },
    sort: { by: 'rs_vs_sector', order: 'desc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 11. Sector Leaders ──────────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-sector-leaders',
    name: 'Sector Leaders',
    description:
      'Strong relative strength vs sector with bullish RSI and above-average volume. Leading stocks in their sectors.',
    category: 'momentum',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-sl-1',
          filterKey: 'rs_vs_sector',
          operator: 'gte',
          value: 1.2,
        },
        {
          id: 'tpl-sl-2',
          filterKey: 'rsi',
          operator: 'gte',
          value: 50,
          params: { window: 14 },
        },
        {
          id: 'tpl-sl-3',
          filterKey: 'volume_ratio',
          operator: 'gte',
          value: 1.0,
        },
      ],
    },
    sort: { by: 'rs_vs_sector', order: 'desc' },
    maxResults: 20,
    useAi: false,
  },

  // ── 12. Mean Reversion Long ────────────────────────────────────────────
  {
    isTemplate: true,
    id: 'tpl-mean-reversion',
    name: 'Mean Reversion Long',
    description:
      'Oversold bounce candidates. RSI below 35, still within 80% of ATH, with reasonable volume. Potential mean reversion setups.',
    category: 'momentum',
    filters: {
      match: 'all',
      conditions: [
        {
          id: 'tpl-mr-1',
          filterKey: 'rsi',
          operator: 'lt',
          value: 35,
          params: { window: 14 },
        },
        {
          id: 'tpl-mr-2',
          filterKey: 'ath_proximity',
          operator: 'gte',
          value: 80,
        },
        {
          id: 'tpl-mr-3',
          filterKey: 'volume_ratio',
          operator: 'gte',
          value: 0.7,
        },
      ],
    },
    sort: { by: 'rsi', order: 'asc' },
    maxResults: 20,
    useAi: false,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Look up a template by its id. */
export function getTemplateById(id: string): ScreenTemplate | undefined {
  return SCREENER_TEMPLATES.find((t) => t.id === id);
}

/** Get all templates for a given category. */
export function getTemplatesByCategory(
  category: FilterCategory,
): ScreenTemplate[] {
  return SCREENER_TEMPLATES.filter((t) => t.category === category);
}
