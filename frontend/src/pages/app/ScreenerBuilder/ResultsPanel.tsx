import { useMemo, useState } from 'react';
import {
  Loader2,
  Search,
  BarChart3,
  TrendingUp,
  FileDown,
  Eye,
  EyeOff,
} from 'lucide-react';
import { useTheme } from '../../../context/ThemeContext';
import {
  getColumnsForFilters,
  type ResultsColumn,
} from '../../../data/filterCatalog';
import type { FilterCondition, FilterGroup } from '../../../hooks/useScreens';

// Buy-and-hold return is only meaningful if at least 2 trading days have elapsed
// since the as-of-date. Otherwise the buy/sell prices collapse to the same bar.
const MIN_DAYS_HELD = 2;

function isCutoffEligible(cutoff: string | null | undefined): boolean {
  if (!cutoff) return false;
  const cutoffMs = new Date(cutoff + 'T00:00:00').getTime();
  if (Number.isNaN(cutoffMs)) return false;
  const todayMs = Date.now();
  return (todayMs - cutoffMs) / 86_400_000 >= MIN_DAYS_HELD;
}

interface ScanResult {
  ticker: string;
  company_name?: string;
  sector?: string;
  close?: number;
  score?: number;
  rsi?: number;
  volume_ratio?: number;
  ath_proximity?: number;
  eps_growth_qoq?: number;
  momentum_rsi?: number;
  [key: string]: any;
}

interface ResultsPanelProps {
  results: ScanResult[];
  loading: boolean;
  error?: string;
  returnData?: Record<string, number> | null;
  returnLoading?: boolean;
  cutoffDate?: string;
  /** Active filters from the builder. Used to derive table columns and
   *  chart overlays so the results table is meaningful for what was actually
   *  filtered on. */
  filters?: FilterGroup;
  onExport: () => void;
  onShowBacktest: () => void;
  /** Called when the user clicks anywhere on a results row. */
  onTickerClick: (ticker: string) => void;
}

export default function ResultsPanel({
  results,
  loading,
  error,
  returnData,
  returnLoading,
  cutoffDate,
  filters,
  onExport,
  onShowBacktest,
  onTickerClick,
}: ResultsPanelProps) {
  const { isDarkMode } = useTheme();

  const [showAllMetrics, setShowAllMetrics] = useState(false);

  // Derive one column per indicator referenced by the active filters.
  // Falls back to empty array when no filters were applied yet (load/empty states).
  const filterColumns: ResultsColumn[] = useMemo(
    () => getColumnsForFilters((filters?.conditions ?? []) as FilterCondition[]),
    [filters],
  );

  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
    subtle: isDarkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)',
    border: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    surface: isDarkMode ? '#272729' : '#f5f5f7',
    surfaceRaised: isDarkMode ? '#2a2a2d' : '#fafafc',
    accent: '#10B981',
    danger: '#EF4444',
    warning: '#F59E0B',
    bg: isDarkMode ? '#0a0a0a' : '#ffffff',
  };

  // ── Chart overlay set ────────────────────────────────────────
  // The chart always shows the indicators the user filtered on, so a click on
  // the row is a "let me see what I just filtered on, in context" affordance.
  // ── Loading state ──────────────────────────────────────
  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '64px 32px',
          borderRadius: 12,
          border: `1px solid ${colors.border}`,
          backgroundColor: colors.surface,
        }}
      >
        <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', color: colors.accent }} />
        <span style={{ marginTop: 16, fontSize: 15, color: colors.muted }}>
          Scanning...
        </span>
      </div>
    );
  }

  // ── Error state ─────────────────────────────────────────
  if (error) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '48px 32px',
          borderRadius: 12,
          border: `1px solid ${colors.danger}30`,
          backgroundColor: colors.surface,
        }}
      >
        <span style={{ fontSize: 14, color: colors.danger, textAlign: 'center' }}>
          {error}
        </span>
      </div>
    );
  }

  // ── Empty state ─────────────────────────────────────────
  if (results.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '64px 32px',
          borderRadius: 12,
          border: `1px solid ${colors.border}`,
          backgroundColor: colors.surface,
        }}
      >
        <Search size={32} style={{ color: colors.subtle, marginBottom: 12 }} />
        <span style={{ fontSize: 15, fontWeight: 600, color: colors.text, marginBottom: 4 }}>
          No results yet
        </span>
        <span style={{ fontSize: 13, color: colors.muted, textAlign: 'center' }}>
          Configure your filters and click "Scan" to find matching stocks.
        </span>
      </div>
    );
  }

  // ── Results table ───────────────────────────────────────
  const formatScore = (score: number | undefined): { label: string; color: string } => {
    if (score == null) return { label: '--', color: colors.subtle };
    if (score >= 70) return { label: score.toFixed(0), color: colors.accent };
    if (score >= 50) return { label: score.toFixed(0), color: colors.warning };
    return { label: score.toFixed(0), color: colors.danger };
  };

  const formatPrice = (val: number | undefined): string => {
    if (val == null) return '--';
    return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const formatPct = (val: number | undefined): string => {
    if (val == null) return '--';
    return `${(val * 100).toFixed(1)}%`;
  };

  const formatReturn = (val: number | undefined): string => {
    if (val == null) return '--';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${val.toFixed(1)}%`;
  };

  const hasReturnCol = isCutoffEligible(cutoffDate);
  const returnLabel = cutoffDate
    ? `Return (${cutoffDate})`
    : 'Return';

  // When "Show all metrics" is off, hide the legacy fixed columns (RSI,
  // Vol Ratio, ATH %, EPS Growth). They were always-on and unrelated to the
  // active filters, which is exactly the UX problem we're fixing.
  const legacyColumns = [
    { header: 'RSI', key: 'momentum_rsi', fallbackKey: 'rsi', format: (v: any) => (v != null ? v.toFixed(1) : '--') },
    { header: 'Vol Ratio', key: 'volume_ratio', format: (v: any) => (v != null ? v.toFixed(2) + 'x' : '--') },
    { header: 'ATH %', key: 'ath_proximity', format: (v: any) => (v != null ? formatPct(v) : '--') },
    { header: 'EPS Growth', key: 'eps_growth_qoq', format: (v: any) => (v != null ? `${v.toFixed(1)}%` : '--') },
  ];

  return (
    <div>
      {/* Results header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: colors.text }}>
            Results
          </span>
          <span
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: colors.accent,
              padding: '2px 8px',
              borderRadius: 6,
              backgroundColor: 'rgba(16,185,129,0.1)',
            }}
          >
            {results.length} stock{results.length !== 1 ? 's' : ''}
          </span>
          {filterColumns.length > 0 && (
            <span style={{ fontSize: 11, color: colors.muted }}>
              showing {filterColumns.length} filter column
              {filterColumns.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={() => setShowAllMetrics((v) => !v)}
            title={
              showAllMetrics
                ? 'Hide RSI / Vol Ratio / ATH% / EPS Growth'
                : 'Show RSI / Vol Ratio / ATH% / EPS Growth'
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 14px',
              borderRadius: 8,
              border: `1px solid ${colors.border}`,
              backgroundColor: 'transparent',
              color: colors.muted,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 150ms ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = colors.accent;
              e.currentTarget.style.color = colors.accent;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = colors.border;
              e.currentTarget.style.color = colors.muted;
            }}
          >
            {showAllMetrics ? <EyeOff size={15} /> : <Eye size={15} />}
            {showAllMetrics ? 'Focused view' : 'All metrics'}
          </button>
          <button
            onClick={onExport}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 14px',
              borderRadius: 8,
              border: `1px solid ${colors.border}`,
              backgroundColor: 'transparent',
              color: colors.muted,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 150ms ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = colors.accent;
              e.currentTarget.style.color = colors.accent;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = colors.border;
              e.currentTarget.style.color = colors.muted;
            }}
          >
            <FileDown size={15} />
            Export to Lab
          </button>
          <button
            onClick={onShowBacktest}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 14px',
              borderRadius: 8,
              border: 'none',
              backgroundColor: 'rgba(16,185,129,0.1)',
              color: colors.accent,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'opacity 150ms ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.opacity = '0.9';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = '1';
            }}
          >
            <BarChart3 size={15} />
            Show Backtest
          </button>
        </div>
      </div>

      {/* Table */}
      <div
        style={{
          borderRadius: 12,
          border: `1px solid ${colors.border}`,
          overflow: 'hidden',
        }}
      >
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            {/* Table head */}
            <thead>
              <tr
                style={{
                  borderBottom: `1px solid ${colors.border}`,
                  backgroundColor: colors.surface,
                }}
              >
                {/* Always-on: Ticker, Close, Score */}
                {['Ticker', 'Close', 'Score'].map((header) => (
                  <th
                    key={header}
                    style={{
                      padding: '10px 14px',
                      fontSize: 11,
                      fontWeight: 600,
                      color: colors.muted,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      textAlign: 'left',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {header}
                  </th>
                ))}
                {/* Filter-derived columns — what's actually being tested. */}
                {filterColumns.map((col) => (
                  <th
                    key={col.dataKey}
                    style={{
                      padding: '10px 14px',
                      fontSize: 11,
                      fontWeight: 600,
                      color: colors.accent,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      textAlign: 'left',
                      whiteSpace: 'nowrap',
                    }}
                    title={
                      col.isCrossoverSide === 'reference'
                        ? `Reference indicator for crossover filter`
                        : undefined
                    }
                  >
                    {col.header}
                  </th>
                ))}
                {/* Legacy fixed columns — hidden by default. */}
                {showAllMetrics &&
                  legacyColumns.map((col) => (
                    <th
                      key={col.header}
                      style={{
                        padding: '10px 14px',
                        fontSize: 11,
                        fontWeight: 600,
                        color: colors.muted,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        textAlign: 'left',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {col.header}
                    </th>
                  ))}
                {hasReturnCol && (
                  <th
                    style={{
                      padding: '10px 14px',
                      fontSize: 11,
                      fontWeight: 600,
                      color: colors.accent,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      textAlign: 'right',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {returnLoading ? 'Loading...' : returnLabel}
                  </th>
                )}
              </tr>
            </thead>

            {/* Table body */}
            <tbody>
              {results.map((row, idx) => {
                const score = formatScore(row.score);
                const retVal = returnData?.[row.ticker.toUpperCase()];
                const retPositive = retVal != null && retVal >= 0;
                return (
                  <tr
                    key={row.ticker}
                    role="button"
                    tabIndex={0}
                    aria-label={`Open detail for ${row.ticker.toUpperCase()}`}
                    onClick={() => onTickerClick(row.ticker)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onTickerClick(row.ticker);
                      }
                    }}
                    style={{
                      borderBottom:
                        idx < results.length - 1 ? `1px solid ${colors.border}` : 'none',
                      backgroundColor: colors.bg,
                      cursor: 'pointer',
                      transition: 'background-color 150ms ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = colors.surfaceRaised;
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = colors.bg;
                    }}
                  >
                    <td
                      style={{
                        padding: '10px 14px',
                        fontSize: 14,
                        fontWeight: 600,
                        color: colors.text,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <TrendingUp size={14} color={colors.accent} />
                        {row.ticker.toUpperCase()}
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px', fontSize: 13, color: colors.text }}>
                      ${formatPrice(row.close)}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span
                        style={{
                          fontSize: 13,
                          fontWeight: 700,
                          color: score.color,
                        }}
                      >
                        {score.label}
                      </span>
                    </td>
                    {/* Filter-derived values */}
                    {filterColumns.map((col) => {
                      // Prefer the canonical column, but fall back to a
                      // snake_case variant — backend sometimes returns
                      // `momentum_rsi`, frontend filter key says `rsi`.
                      const raw =
                        row[col.dataKey] ??
                        row[col.dataKey.replace(/^trend_/, '')] ??
                        row[col.dataKey.replace(/^momentum_/, '')] ??
                        row[col.dataKey.replace(/^volatility_/, '')] ??
                        row[col.dataKey.replace(/^volume_/, '')];
                      const formatted =
                        raw == null
                          ? '--'
                          : typeof raw === 'number'
                            ? raw.toFixed(2)
                            : String(raw);
                      return (
                        <td
                          key={col.dataKey}
                          style={{
                            padding: '10px 14px',
                            fontSize: 13,
                            color: colors.text,
                            fontVariantNumeric: 'tabular-nums',
                          }}
                        >
                          {formatted}
                        </td>
                      );
                    })}
                    {/* Legacy fixed columns */}
                    {showAllMetrics &&
                      legacyColumns.map((col) => {
                        const v =
                          row[col.key] ?? (col.fallbackKey ? row[col.fallbackKey] : undefined);
                        return (
                          <td
                            key={col.header}
                            style={{
                              padding: '10px 14px',
                              fontSize: 13,
                              color: colors.text,
                              fontVariantNumeric: 'tabular-nums',
                            }}
                          >
                            {col.format(v)}
                          </td>
                        );
                      })}
                    {hasReturnCol && (
                      <td
                        style={{
                          padding: '10px 14px',
                          fontSize: 13,
                          fontWeight: 600,
                          color: retPositive ? colors.accent : colors.danger,
                          textAlign: 'right',
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {returnLoading ? '...' : formatReturn(retVal)}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
