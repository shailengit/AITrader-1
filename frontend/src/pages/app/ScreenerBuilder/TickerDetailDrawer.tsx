import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  X,
  TrendingUp,
  ExternalLink,
  Loader2,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { useTheme } from '../../../context/ThemeContext';
import { CandleStickChart } from '../../../components/quantgen';
import type { IndicatorDescriptor } from '../../../types/indicators';
import TickerMetadataPanel, { type TickerDetail } from '../../../components/shared/TickerMetadataPanel';

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

interface TickerDetailDrawerProps {
  ticker: string | null;
  asOfDate?: string;
  indicators: IndicatorDescriptor[];
  onClose: () => void;
  onExportToLab: (ticker: string) => void;
  onOpenInChart: (ticker: string) => void;
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
  onOpenInChart,
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                onClick={() => onOpenInChart(ticker)}
                aria-label="Open in full-page chart"
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
                <ExternalLink size={11} />
                Open in chart
              </button>
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

        {/* Metadata — extracted to TickerMetadataPanel so ChartView can share it. */}
        <TickerMetadataPanel data={data} loading={loading} error={error} variant="drawer" />
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
