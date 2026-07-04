import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useTheme } from '../../../context/ThemeContext';
import type { TickerDetail } from '../../../components/shared/TickerMetadataPanel';
import {
  catalogEntryToColumn,
  catalogParamsToBackendParams,
} from '../../../data/indicatorMap';
import type { IndicatorDescriptor } from '../../../types/indicators';
import { CandleStickChart } from '../../../components/quantgen';
import MetadataRail from './ChartView/MetadataRail';
import IndicatorPickerPanel from './ChartView/IndicatorPickerPanel';
import DateRangeBar, { type RangeMode } from './ChartView/DateRangeBar';
import OverlaysList from './ChartView/OverlaysList';

interface ChartBar {
  time: number | string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  indicators?: Record<string, number | null>;
}

const RANGE_DAYS: Record<Exclude<RangeMode, 'custom'>, number> = {
  '1y': 365,
  '2y': 730,
  '3y': 1095,
  '5y': 1825,
  max: 10000,
};

const CHART_PALETTE = ['#3B82F6', '#EF4444', '#F59E0B', '#A855F7', '#10B981', '#06B6D4', '#EC4899', '#84CC16'];

function toEpochSeconds(t: number | string): number {
  if (typeof t === 'number') return t > 1e10 ? Math.floor(t / 1000) : t;
  return Math.floor(new Date(t).getTime() / 1000);
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

/**
 * Parse the `overlays` and `params` query params back into
 * IndicatorDescriptors. `params` (if present) is a JSON map from
 * overlay id → params dict, and takes precedence. When the id is a
 * catalog-formatted id (starts with `ta__`), we recover the params
 * from the id; otherwise the id is treated as a payload key (e.g. from
 * the drawer's pass-through) and the params come from the params map.
 */
function parseOverlaysFromUrl(
  overlaysParam: string | null,
  paramsParam: string | null,
): IndicatorDescriptor[] {
  if (!overlaysParam) return [];
  const ids = overlaysParam.split(',').filter(Boolean);
  let paramMap: Record<string, Record<string, number>> = {};
  if (paramsParam) {
    try {
      paramMap = JSON.parse(paramsParam);
    } catch {
      paramMap = {};
    }
  }
  return ids.map((id) => {
    // Prefer the explicit params map. Fall back to a label derived from
    // the id so the chip is at least readable.
    const params = paramMap[id];
    return {
      id,
      label: params ? deriveLabel(id, params) : id,
      params,
    };
  });
}

/** Best-effort label for an id+params pair, e.g. "EMA (200)" or "MACD (12,26,9)". */
function deriveLabel(id: string, params: Record<string, number>): string {
  // The id may be a catalog id (ta__<Name>__<sig>) or a payload key
  // (sma_50__window50). Try to extract the name.
  const m = /^ta__([^_]+(?:_[^_]+?)*?)__/.exec(id);
  if (m) {
    return `${m[1]} (${Object.values(params).join(',')})`;
  }
  // Fallback for payload keys: strip the trailing param sig
  const idx = id.lastIndexOf('__');
  if (idx > 0) return id.slice(0, idx).replace(/_/g, ' ').toUpperCase();
  return id;
}

/**
 * Full-page chart view for a single ticker. Reached from the drawer's
 * "Open in chart" button. URL is the source of truth for overlays and
 * date range; the chart refetches whenever either changes.
 */
export default function ChartView() {
  const { ticker: tickerParam } = useParams<{ ticker: string }>();
  const ticker = (tickerParam ?? '').toUpperCase();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isDarkMode } = useTheme();

  // URL-driven state
  const rangeMode = (searchParams.get('range') ?? '1y') as RangeMode;
  const customStart = searchParams.get('start') ?? '';
  const customEnd = searchParams.get('end') ?? '';
  const fromDate = searchParams.get('from') ?? undefined;

  const overlays: IndicatorDescriptor[] = useMemo(
    () => parseOverlaysFromUrl(searchParams.get('overlays'), searchParams.get('params')),
    [searchParams],
  );

  // Metadata (left rail)
  const [metaData, setMetaData] = useState<TickerDetail | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);

  // Chart
  const [chartBars, setChartBars] = useState<ChartBar[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);

  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
    subtle: isDarkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)',
    border: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    surface: isDarkMode ? '#272729' : '#f5f5f7',
    surfaceRaised: isDarkMode ? '#2a2a2d' : '#fafafc',
    canvas: isDarkMode ? '#050505' : '#f5f5f7',
    accent: '#10B981',
  };

  // Metadata fetch
  useEffect(() => {
    if (!ticker) return;
    const controller = new AbortController();
    setMetaLoading(true);
    setMetaError(null);
    setMetaData(null);
    const params = new URLSearchParams();
    if (fromDate) params.set('as_of_date', fromDate);
    fetch(`/api/screener/ticker/${encodeURIComponent(ticker)}?${params}`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json: TickerDetail) => {
        setMetaData(json);
        setMetaLoading(false);
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        setMetaError(err.message);
        setMetaLoading(false);
      });
    return () => controller.abort();
  }, [ticker, fromDate]);

  // Chart fetch — keyed on ticker, range, and overlays
  useEffect(() => {
    if (!ticker) return;
    const controller = new AbortController();
    setChartLoading(true);
    setChartError(null);

    const cols: string[] = [];
    const overrides: Record<string, Record<string, number>> = {};
    for (const ov of overlays) {
      // Resolve id → column + params
      let column = ov.id;
      let params = ov.params;
      const m = /^ta__(.+)__/.exec(ov.id);
      if (m) {
        const catalogName = m[1];
        column = catalogEntryToColumn(catalogName);
        if (params) {
          params = catalogParamsToBackendParams(catalogName, params);
        }
      }
      cols.push(column);
      if (params && Object.keys(params).length > 0) {
        overrides[column] = params;
      }
    }

    const params = new URLSearchParams();
    if (rangeMode === 'custom' && customStart && customEnd) {
      params.set('start', customStart);
      params.set('end', customEnd);
    } else {
      params.set('days', String(RANGE_DAYS[rangeMode as Exclude<RangeMode, 'custom'>] ?? 365));
    }
    if (cols.length) params.set('indicators', cols.join(','));
    if (Object.keys(overrides).length) params.set('overrides', JSON.stringify(overrides));

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
        setChartError(err.message);
        setChartLoading(false);
      });
    return () => controller.abort();
  }, [ticker, rangeMode, customStart, customEnd, overlays]);

  const updateUrl = useCallback(
    (partial: Record<string, string | null>) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(partial)) {
            if (v == null || v === '') next.delete(k);
            else next.set(k, v);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const handleAddOverlay = useCallback(
    (descriptor: IndicatorDescriptor) => {
      const nextOverlays = [...overlays, descriptor];
      const paramMap: Record<string, Record<string, number>> = {};
      for (const o of nextOverlays) {
        if (o.params && Object.keys(o.params).length > 0) {
          paramMap[o.id] = o.params;
        }
      }
      updateUrl({
        overlays: nextOverlays.map((o) => o.id).join(','),
        params: Object.keys(paramMap).length ? JSON.stringify(paramMap) : null,
      });
    },
    [overlays, updateUrl],
  );

  const handleRemoveOverlay = useCallback(
    (id: string) => {
      const nextOverlays = overlays.filter((o) => o.id !== id);
      const paramMap: Record<string, Record<string, number>> = {};
      for (const o of nextOverlays) {
        if (o.params && Object.keys(o.params).length > 0) {
          paramMap[o.id] = o.params;
        }
      }
      updateUrl({
        overlays: nextOverlays.length ? nextOverlays.map((o) => o.id).join(',') : null,
        params: Object.keys(paramMap).length ? JSON.stringify(paramMap) : null,
      });
    },
    [overlays, updateUrl],
  );

  const handleRangeChange = useCallback(
    (mode: RangeMode, custom?: { start?: string; end?: string }) => {
      if (mode === 'custom') {
        updateUrl({
          range: 'custom',
          start: custom?.start ?? '',
          end: custom?.end ?? '',
        });
      } else {
        updateUrl({
          range: mode,
          start: null,
          end: null,
        });
      }
    },
    [updateUrl],
  );

  // Build the chart's indicator payload from the bars + overlays. Match
  // the chart endpoint's payload key convention: `<column>` for default
  // and `<column>__<sig>` for overrides.
  const chartIndicatorsPayload = useMemo(() => {
    const series: Record<string, { time: number; value: number }[]> = {};
    chartBars.forEach((b) => {
      if (!b.indicators) return;
      const t = toEpochSeconds(b.time);
      Object.entries(b.indicators).forEach(([key, v]) => {
        if (v == null) return;
        if (!series[key]) series[key] = [];
        series[key].push({ time: t, value: v });
      });
    });
    return overlays.map((ov, i) => {
      // Resolve which chart-endpoint payload key holds this overlay's data.
      // For a catalog id (ta__<Name>__<sig>), the column is the catalog
      // translation and the payload key is `<column>__<sig>`. For a
      // payload key id (sma_50__window50), the column AND payload key
      // are the id verbatim.
      let column: string;
      let payloadKey: string;
      const m = /^ta__(.+)__/.exec(ov.id);
      if (m) {
        const catalogName = m[1];
        column = catalogEntryToColumn(catalogName);
        const sig = ov.params
          ? Object.entries(ov.params)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([k, v]) => `${k}${v}`)
              .join('_')
          : '';
        payloadKey = sig ? `${column}__${sig}` : column;
      } else {
        column = ov.id;
        payloadKey = ov.id;
      }
      return {
        name: ov.label,
        type: 'line',
        data: series[payloadKey] ?? [],
        color: CHART_PALETTE[i % CHART_PALETTE.length],
      };
    });
  }, [chartBars, overlays]);

  if (!ticker) {
    return (
      <div style={{ padding: 64, color: colors.muted, textAlign: 'center' }}>
        No ticker specified.
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: colors.canvas, display: 'flex', flexDirection: 'column' }}>
      {/* Header strip */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '20px 32px',
          borderBottom: `1px solid ${colors.border}`,
          backgroundColor: colors.surface,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            onClick={() => navigate('/screener/build')}
            aria-label="Back to results"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 12px',
              borderRadius: 6,
              border: `1px solid ${colors.border}`,
              background: 'none',
              color: colors.muted,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            <ArrowLeft size={14} />
            Back to results
          </button>
          <span style={{ fontSize: 12, color: colors.subtle }}>Custom Screener ›</span>
          <span style={{ fontSize: 18, fontWeight: 700, color: colors.text }}>{ticker}</span>
          {metaData?.company_name && (
            <span style={{ fontSize: 13, color: colors.muted }}>{metaData.company_name}</span>
          )}
        </div>
      </div>

      {/* Two-column grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '320px 1fr',
          flex: 1,
          minHeight: 0,
        }}
      >
        {/* Left rail */}
        <div
          style={{
            borderRight: `1px solid ${colors.border}`,
            backgroundColor: colors.surface,
            padding: 20,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
          }}
        >
          <MetadataRail
            ticker={ticker}
            data={metaData}
            loading={metaLoading}
            error={metaError}
            fromDate={fromDate}
          />
          <div style={{ height: 1, backgroundColor: colors.border }} />
          <div>
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
              Overlays
            </div>
            <OverlaysList overlays={overlays} onRemove={handleRemoveOverlay} colors={colors} />
          </div>
          <div style={{ height: 1, backgroundColor: colors.border }} />
          <div>
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
              Add indicator
            </div>
            <IndicatorPickerPanel onAdd={handleAddOverlay} alreadyAdded={overlays.map((o) => o.id)} />
          </div>
        </div>

        {/* Chart panel */}
        <div
          style={{
            padding: 24,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
          }}
        >
          <DateRangeBar
            mode={rangeMode}
            customStart={customStart}
            customEnd={customEnd}
            onChange={handleRangeChange}
            colors={colors}
          />
          <div
            style={{
              backgroundColor: colors.surfaceRaised,
              border: `1px solid ${colors.border}`,
              borderRadius: 12,
              padding: 16,
              flex: 1,
              minHeight: 400,
              position: 'relative',
            }}
          >
            {chartError ? (
              <div style={{ color: colors.muted, textAlign: 'center', padding: 40 }}>
                Failed to load chart: {chartError}
                <button
                  onClick={() => setChartError(null)}
                  style={{
                    marginLeft: 12,
                    padding: '4px 10px',
                    borderRadius: 4,
                    border: `1px solid ${colors.border}`,
                    background: 'none',
                    color: colors.muted,
                    cursor: 'pointer',
                  }}
                >
                  Retry
                </button>
              </div>
            ) : chartLoading && chartBars.length === 0 ? (
              <div style={{ color: colors.muted, textAlign: 'center', padding: 40 }}>
                Loading chart...
              </div>
            ) : chartBars.length === 0 ? (
              <div style={{ color: colors.muted, textAlign: 'center', padding: 40 }}>
                No data for {ticker} on this range. Try Max or a wider Custom range.
              </div>
            ) : (
              <CandleStickChart
                data={transformBars(chartBars)}
                height={500}
                indicators={chartIndicatorsPayload as never}
                cutoffDate={fromDate}
              />
            )}
            {chartLoading && chartBars.length > 0 && (
              <div
                style={{
                  position: 'absolute',
                  top: 12,
                  right: 12,
                  fontSize: 10,
                  fontWeight: 600,
                  color: colors.muted,
                  backgroundColor: colors.surface,
                  padding: '4px 8px',
                  borderRadius: 4,
                  border: `1px solid ${colors.border}`,
                }}
              >
                Loading...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
