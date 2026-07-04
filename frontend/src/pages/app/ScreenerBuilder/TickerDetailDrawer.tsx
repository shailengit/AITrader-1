import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  X,
  TrendingUp,
  ExternalLink,
  Loader2,
  Calendar,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { useTheme } from '../../../context/ThemeContext';
import { CandleStickChart } from '../../../components/quantgen';
import type { IndicatorDescriptor } from '../../../types/indicators';

/** Shape of a single bar from /api/screener/chart-data/{ticker}. */
interface ChartBar {
  time: number | string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  indicators?: Record<string, number | null>;
}

/** TickerDetail shape returned by GET /api/screener/ticker/{ticker}. */
interface TickerDetail {
  ticker: string;
  company_name: string;
  sector: string;
  close: number;
  as_of_date: string;
  fundamentals: {
    market_cap: number | null;
    beta: number | null;
    peg_ratio: number | null;
    eps_growth_qoq: number | null;
    revenue_growth_qoq: number | null;
  };
  indicators: {
    rsi: number | null;
    macd: number | null;
    mfi: number | null;
    bbw: number | null;
    volume_ratio: number | null;
    ath_proximity: number | null;
    volume_cluster_count: number | null;
    rs_vs_sector: number | null;
  };
  earnings_next: {
    date: string | null;
    days_away: number | null;
    eps_estimate: number | null;
  } | null;
}

interface TickerDetailDrawerProps {
  ticker: string | null;
  asOfDate?: string;
  indicators: IndicatorDescriptor[];
  onClose: () => void;
  onExportToLab: (ticker: string) => void;
}

function formatPct(v: number | null | undefined): string {
  if (v == null) return '--';
  return `${v.toFixed(1)}%`;
}

function formatDollar(v: number | null | undefined): string {
  if (v == null) return '--';
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatMarketCap(v: number | null | undefined): string {
  if (v == null) return '--';
  if (Math.abs(v) >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

const CHART_PALETTE = ['#3B82F6', '#EF4444', '#F59E0B', '#A855F7', '#10B981', '#06B6D4'];

function toEpochSeconds(t: number | string): number {
  if (typeof t === 'number') return t > 1e10 ? Math.floor(t / 1000) : t;
  // ISO yyyy-mm-dd or yyyy-mm-ddThh:mm:ss
  const d = new Date(t);
  return Math.floor(d.getTime() / 1000);
}

function transformBars(bars: ChartBar[]) {
  return bars.map((b) => ({
    time: toEpochSeconds(b.time),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
    volume: b.volume,
  }));
}

function buildChartIndicators(
  bars: ChartBar[],
  activeIds: Set<string>,
  sourceIndicators: IndicatorDescriptor[],
): unknown[] {
  // Map the active source indicator id → series name in the chart payload.
  // The chart endpoint returns `bar.indicators[col]` keyed by the
  // backend column name (the IndicatorDescriptor.id, which is the
  // payloadKey per the screener builder convention).
  const lookup = new Map<string, IndicatorDescriptor>();
  sourceIndicators.forEach((ind) => lookup.set(ind.id, ind));

  const series: Record<string, { time: number; value: number }[]> = {};
  bars.forEach((b) => {
    if (!b.indicators) return;
    const t = toEpochSeconds(b.time);
    Object.entries(b.indicators).forEach(([key, v]) => {
      if (v == null) return;
      if (!activeIds.has(key)) return;
      if (!series[key]) series[key] = [];
      series[key].push({ time: t, value: v });
    });
  });

  return Object.entries(series).map(([key, data], i) => ({
    name: lookup.get(key)?.label ?? key,
    type: 'line',
    data,
    color: CHART_PALETTE[i % CHART_PALETTE.length],
  }));
}

export default function TickerDetailDrawer({
  ticker,
  asOfDate,
  indicators,
  onClose,
  onExportToLab,
}: TickerDetailDrawerProps) {
  const { isDarkMode } = useTheme();
  const [data, setData] = useState<TickerDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [chartBars, setChartBars] = useState<ChartBar[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [activeIndicators, setActiveIndicators] = useState<Set<string>>(
    () => new Set(indicators.map((i) => i.id)),
  );

  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
    subtle: isDarkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)',
    border: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    surface: isDarkMode ? '#0a0a0a' : '#f5f5f7',
    surfaceRaised: isDarkMode ? '#111111' : '#fafafc',
    accent: '#10B981',
    danger: '#EF4444',
    warning: '#F59E0B',
  };

  // Fetch the TickerDetail payload. Aborts in-flight request when ticker
  // changes; we never show stale data from a previous ticker.
  useEffect(() => {
    if (!ticker) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setData(null);

    const params = new URLSearchParams();
    if (asOfDate) params.set('as_of_date', asOfDate);

    fetch(`/api/screener/ticker/${encodeURIComponent(ticker)}?${params}`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json: TickerDetail) => {
        setData(json);
        setLoading(false);
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        setError(err.message);
        setLoading(false);
      });

    return () => controller.abort();
  }, [ticker, asOfDate]);

  // Fetch chart data separately. Same ticker-driven lifecycle.
  useEffect(() => {
    if (!ticker) {
      setChartBars([]);
      return;
    }
    const controller = new AbortController();
    setChartLoading(true);

    const indicatorIds = indicators.map((i) => i.id).join(',');
    const overrides: Record<string, Record<string, number>> = {};
    for (const ind of indicators) {
      if (ind.params && Object.keys(ind.params).length > 0) {
        overrides[ind.id] = ind.params;
      }
    }

    const params = new URLSearchParams();
    if (indicatorIds) params.set('indicators', indicatorIds);
    params.set('days', '120');
    if (Object.keys(overrides).length > 0) {
      params.set('overrides', JSON.stringify(overrides));
    }

    fetch(
      `/api/screener/chart-data/${encodeURIComponent(ticker)}?${params.toString()}`,
      { signal: controller.signal },
    )
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json: ChartBar[]) => {
        setChartBars(Array.isArray(json) ? json : []);
        setChartLoading(false);
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        setChartBars([]);
        setChartLoading(false);
      });

    return () => controller.abort();
  }, [ticker, indicators]);

  // Reset active indicators when the prop list changes (e.g. user picked a
  // different template). New list → all-on by default.
  useEffect(() => {
    setActiveIndicators(new Set(indicators.map((i) => i.id)));
  }, [indicators]);

  const chartIndicatorsPayload = useMemo(
    () => buildChartIndicators(chartBars, activeIndicators, indicators),
    [chartBars, activeIndicators, indicators],
  );

  const toggleIndicator = useCallback((id: string) => {
    setActiveIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  if (!ticker) return null;

  const drawerWidth = expanded ? 800 : 480;
  const chartHeight = expanded ? 260 : 100;

  // Indicator chip row above the chart
  const indicatorChips = indicators.length > 0 && (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 4,
        marginBottom: 6,
      }}
    >
      {indicators.map((ind) => {
        const active = activeIndicators.has(ind.id);
        return (
          <button
            key={ind.id}
            onClick={() => toggleIndicator(ind.id)}
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: '3px 8px',
              borderRadius: 4,
              border: `1px solid ${active ? colors.accent : colors.border}`,
              backgroundColor: active ? 'rgba(16,185,129,0.12)' : 'transparent',
              color: active ? colors.accent : colors.muted,
              cursor: 'pointer',
            }}
          >
            {ind.label}
          </button>
        );
      })}
    </div>
  );

  return (
    <div
      role="dialog"
      aria-label={`Detail for ${ticker}`}
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: drawerWidth,
        backgroundColor: colors.surface,
        borderLeft: `1px solid ${colors.border}`,
        zIndex: 40,
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '-8px 0 24px rgba(0,0,0,0.4)',
        transition: 'width 200ms ease',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          padding: '20px 20px 12px',
          borderBottom: `1px solid ${colors.border}`,
        }}
      >
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 20,
              fontWeight: 700,
              color: colors.text,
            }}
          >
            <TrendingUp size={18} color={colors.accent} />
            {ticker.toUpperCase()}
          </div>
          <div style={{ fontSize: 12, color: colors.muted, marginTop: 2 }}>
            {data?.company_name ?? '—'} · {data?.sector ?? '—'}
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close detail"
          style={{
            background: 'none',
            border: `1px solid ${colors.border}`,
            borderRadius: 6,
            color: colors.muted,
            fontSize: 14,
            width: 28,
            height: 28,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <X size={14} />
        </button>
      </div>

      {/* Scrollable body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        {/* Price + as-of */}
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 12,
            marginBottom: 16,
          }}
        >
          <span style={{ fontSize: 22, fontWeight: 700, color: colors.text }}>
            ${formatDollar(data?.close)}
          </span>
          <span style={{ fontSize: 11, color: colors.subtle, marginLeft: 'auto' }}>
            as of {data?.as_of_date ?? '—'}
          </span>
        </div>

        {/* Chart panel */}
        <div
          style={{
            backgroundColor: colors.surfaceRaised,
            border: `1px solid ${colors.border}`,
            borderRadius: 8,
            padding: 10,
            marginBottom: 16,
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 6,
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                color: colors.muted,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
              }}
            >
              CHART · 120D
            </span>
            <button
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? 'Shrink chart' : 'Expand chart'}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 10,
                fontWeight: 600,
                color: colors.accent,
                background: 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {expanded ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
              {expanded ? 'Shrink' : 'Expand'}
            </button>
          </div>
          {indicatorChips}
          {chartLoading && chartBars.length === 0 ? (
            <div
              style={{
                height: chartHeight,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: colors.subtle,
              }}
            >
              <Loader2
                size={20}
                style={{ animation: 'spin 1s linear infinite', marginRight: 8 }}
              />
              Loading chart...
            </div>
          ) : (
            <CandleStickChart
              data={transformBars(chartBars)}
              height={chartHeight}
              indicators={chartIndicatorsPayload as never}
              cutoffDate={asOfDate}
            />
          )}
        </div>

        {/* Fundamentals */}
        <div style={{ marginBottom: 16 }}>
          <SectionLabel colors={colors}>Fundamentals</SectionLabel>
          {loading && !data ? <SkeletonGrid colors={colors} /> : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 1,
                backgroundColor: colors.border,
                borderRadius: 6,
                overflow: 'hidden',
                border: `1px solid ${colors.border}`,
              }}
            >
              <FundCell label="P/E (TTM)" value={null} colors={colors} hint="Not in this version" />
              <FundCell label="PEG" value={data?.fundamentals.peg_ratio} colors={colors} />
              <FundCell
                label="Mkt Cap"
                value={data ? formatMarketCap(data.fundamentals.market_cap) : null}
                colors={colors}
                asString
              />
              <FundCell
                label="Beta"
                value={data?.fundamentals.beta}
                colors={colors}
                format={(v) => v != null ? v.toFixed(2) : '--'}
              />
              <FundCell
                label="EPS Growth QoQ"
                value={data?.fundamentals.eps_growth_qoq}
                colors={colors}
                format={(v) => v != null ? `${v.toFixed(1)}%` : '--'}
                positiveIsGood
              />
              <FundCell
                label="Rev Growth QoQ"
                value={data?.fundamentals.revenue_growth_qoq}
                colors={colors}
                format={(v) => v != null ? `${v.toFixed(1)}%` : '--'}
                positiveIsGood
              />
            </div>
          )}
        </div>

        {/* Indicators */}
        <div style={{ marginBottom: 16 }}>
          <SectionLabel colors={colors}>Indicators</SectionLabel>
          {loading && !data ? <SkeletonLines colors={colors} /> : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '4px 12px',
                fontSize: 12,
                color: colors.muted,
                lineHeight: 1.8,
              }}
            >
              <IndRow label="RSI (14)" value={data?.indicators.rsi} colors={colors} fmt={(v) => v.toFixed(1)} />
              <IndRow label="MACD" value={data?.indicators.macd} colors={colors} fmt={(v) => v.toFixed(2)} />
              <IndRow label="Vol Ratio" value={data?.indicators.volume_ratio} colors={colors} fmt={(v) => v.toFixed(2)} />
              <IndRow label="ATH Prox" value={data?.indicators.ath_proximity} colors={colors} fmt={(v) => formatPct(v * 100)} />
              <IndRow label="MFI (14)" value={data?.indicators.mfi} colors={colors} fmt={(v) => v.toFixed(1)} />
              <IndRow label="Vol Cluster" value={data?.indicators.volume_cluster_count} colors={colors} fmt={(v) => `${v} / 5`} />
              <IndRow label="RS vs Sector" value={data?.indicators.rs_vs_sector} colors={colors} fmt={(v) => v.toFixed(2)} />
            </div>
          )}
        </div>

        {/* Earnings */}
        {data?.earnings_next && (
          <div
            style={{
              backgroundColor:
                (data.earnings_next.days_away ?? 999) <= 14
                  ? 'rgba(245,158,11,0.08)'
                  : colors.surfaceRaised,
              border: `1px solid ${
                (data.earnings_next.days_away ?? 999) <= 14
                  ? 'rgba(245,158,11,0.3)'
                  : colors.border
              }`,
              borderRadius: 6,
              padding: '8px 10px',
              marginBottom: 16,
              fontSize: 12,
            }}
          >
            <div
              style={{
                color:
                  (data.earnings_next.days_away ?? 999) <= 14
                    ? colors.warning
                    : colors.muted,
                fontWeight: 600,
                marginBottom: 2,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Calendar size={12} />
              {data.earnings_next.days_away != null
                ? `EARNINGS in ${data.earnings_next.days_away} day${data.earnings_next.days_away === 1 ? '' : 's'}`
                : 'EARNINGS upcoming'}
            </div>
            <div style={{ color: colors.text }}>
              {data.earnings_next.date ?? '—'}
              {data.earnings_next.eps_estimate != null &&
                ` · EPS est. $${data.earnings_next.eps_estimate.toFixed(2)}`}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div
            style={{
              padding: '8px 10px',
              border: `1px solid ${colors.danger}50`,
              borderRadius: 6,
              color: colors.danger,
              fontSize: 12,
            }}
          >
            Failed to load detail: {error}
          </div>
        )}
      </div>

      {/* Footer actions */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          padding: '12px 20px',
          borderTop: `1px solid ${colors.border}`,
        }}
      >
        <button
          onClick={() => onExportToLab(ticker)}
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            backgroundColor: colors.accent,
            color: '#000',
            border: 'none',
            padding: '10px 14px',
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <ExternalLink size={13} />
          Export to Lab
        </button>
      </div>
    </div>
  );
}

// ── Sub-components (small, in-file) ───────────────────────

function SectionLabel({ children, colors }: { children: React.ReactNode; colors: any }) {
  return (
    <div
      style={{
        fontSize: 10,
        fontWeight: 600,
        color: colors.accent,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        marginBottom: 8,
      }}
    >
      {children}
    </div>
  );
}

function FundCell({
  label,
  value,
  colors,
  format,
  positiveIsGood,
  asString,
  hint,
}: {
  label: string;
  value: number | string | null | undefined;
  colors: any;
  format?: (v: number) => string;
  positiveIsGood?: boolean;
  asString?: boolean;
  hint?: string;
}) {
  let display = '--';
  let textColor = colors.text;
  if (value != null) {
    if (asString) {
      display = String(value);
    } else if (typeof value === 'string') {
      display = value;
    } else if (format) {
      display = format(value);
    } else {
      display = String(value);
    }
    if (!asString && typeof value === 'number' && positiveIsGood) {
      if (value < 0) textColor = colors.danger;
      else if (value > 0) textColor = colors.accent;
    }
  }
  return (
    <div
      style={{ backgroundColor: colors.surfaceRaised, padding: '8px 10px' }}
      title={hint}
    >
      <div style={{ fontSize: 10, color: colors.muted, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: textColor }}>{display}</div>
    </div>
  );
}

function IndRow({
  label,
  value,
  colors,
  fmt,
}: {
  label: string;
  value: number | null | undefined;
  colors: any;
  fmt: (v: number) => string;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span>{label}:</span>
      <span style={{ color: colors.text, fontWeight: 500 }}>
        {value != null ? fmt(value) : '--'}
      </span>
    </div>
  );
}

function SkeletonGrid({ colors: _colors }: { colors: any }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 1,
        borderRadius: 6,
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.08)',
      }}
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          style={{
            backgroundColor: 'rgba(255,255,255,0.04)',
            padding: '8px 10px',
            height: 50,
          }}
        />
      ))}
    </div>
  );
}

function SkeletonLines({ colors: _colors }: { colors: any }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {Array.from({ length: 7 }).map((_, i) => (
        <div
          key={i}
          style={{
            backgroundColor: 'rgba(255,255,255,0.04)',
            height: 14,
            borderRadius: 3,
            width: i % 2 === 0 ? '90%' : '70%',
          }}
        />
      ))}
    </div>
  );
}
