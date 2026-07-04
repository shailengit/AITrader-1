import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Search,
  Save,
  Share2,
  BookTemplate,
  Plus,
  Loader2,
  SlidersHorizontal,
  Sparkles,
  FunctionSquare,
  Layers,
} from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { useScreens, type FilterCondition, type FilterGroup, type ScreenPreset } from '../../hooks/useScreens';
import { useComposites } from '../../hooks/useComposites';
import { useMacros } from '../../hooks/useMacros';
import { decodeShareUrl } from '../../lib/shareCodec';
import { getFilterByKey, type FilterSpec } from '../../data/filterCatalog';
import {
  getColumnsForFilters,
  type ResultsColumn,
} from '../../data/filterCatalog';
import type { IndicatorDescriptor } from '../../types/indicators';
import TickerDetailDrawer from './ScreenerBuilder/TickerDetailDrawer';
import TemplateChips from './ScreenerBuilder/TemplateChips';
import GroupHeader from './ScreenerBuilder/GroupHeader';
import FilterRow from './ScreenerBuilder/FilterRow';
import FilterPicker from './ScreenerBuilder/FilterPicker';
import ScreenLibraryModal from './ScreenerBuilder/ScreenLibraryModal';
import SaveScreenDialog from './ScreenerBuilder/SaveScreenDialog';
import ShareDialog from './ScreenerBuilder/ShareDialog';
import ResultsPanel from './ScreenerBuilder/ResultsPanel';
import BacktestPanel from './ScreenerBuilder/BacktestPanel';
import CompositeBuilder from './ScreenerBuilder/CompositeBuilder';

// ── Types ─────────────────────────────────────────────────

interface ScanResult {
  ticker: string;
  company_name?: string;
  sector?: string;
  close?: number;
  score?: number;
  rsi?: number;
  momentum_rsi?: number;
  volume_ratio?: number;
  ath_proximity?: number;
  eps_growth_qoq?: number;
  [key: string]: any;
}

const DRAFT_KEY = 'screener:builder:draft';

// ── Helpers ───────────────────────────────────────────────

let _condCounter = 0;
function newConditionId(): string {
  _condCounter += 1;
  return `cond_${Date.now()}_${_condCounter}`;
}

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

function createEmptyCondition(): FilterCondition {
  return {
    id: newConditionId(),
    filterKey: '',
    operator: 'gte',
    value: null,
  };
}

function convertFiltersToBackend(filters: FilterGroup): Record<string, any> {
  const indicatorFilters: Record<string, any>[] = [];

  for (const cond of filters.conditions) {
    const spec = getFilterByKey(cond.filterKey);
    if (!spec) continue;

    // Translate frontend catalog `key` → backend column name produced by
    // `add_all_ta_features` (e.g. `sma_50` → `trend_sma_slow`, `rsi` → `momentum_rsi`).
    // Without this, the backend filters out conditions whose column doesn't
    // exist in the DataFrame, causing identical results across all parameter
    // combinations. (See parsers.apply_quant_filters: missing-column skip.)
    const column = spec.backendColumn || cond.filterKey;
    const refSpec = cond.referenceFilterKey
      ? getFilterByKey(cond.referenceFilterKey)
      : undefined;
    const referenceColumn = refSpec
      ? (refSpec.backendColumn || cond.referenceFilterKey)
      : cond.referenceFilterKey;

    if (spec.type === 'number') {
      // ── Crossover mode (Crossed Above / Crossed Below) ──────────
      if (cond.operator === 'crossed_above' || cond.operator === 'crossed_below') {
        if (cond.referenceFilterKey) {
          const item: Record<string, any> = {
            column,
            condition: cond.operator === 'crossed_above' ? 'crossed_above' : 'crossed_below',
            reference_column: referenceColumn,
            lookback_days: cond.lookbackDays ?? 5,
          };
          if (cond.params) item.params = cond.params;
          if (cond.referenceParams) item.reference_params = cond.referenceParams;
          indicatorFilters.push(item);
        }
        continue;
      }

      // ── Indicator comparison mode (e.g. SMA20 > SMA200) ────────
      if (cond.compareToIndicator && cond.referenceFilterKey) {
        const conditionMap: Record<string, string> = {
          gt: 'above',
          gte: 'above',
          lt: 'below',
          lte: 'below',
          eq: 'equals',
        };
        const mapped = conditionMap[cond.operator];
        if (mapped) {
          const item: Record<string, any> = {
            column,
            condition: mapped,
            reference_column: referenceColumn,
          };
          if (cond.params) item.params = cond.params;
          if (cond.referenceParams) item.reference_params = cond.referenceParams;
          indicatorFilters.push(item);
        }
        continue;
      }

      // ── Value comparison mode (default) ────────────────────────
      const item: Record<string, any> = { column };
      if (cond.params) item.params = cond.params;
      switch (cond.operator) {
        case 'gte':
          item.min = cond.value;
          break;
        case 'gt':
          item.min = cond.value;
          item.exclusive_min = true;
          break;
        case 'lte':
          item.max = cond.value;
          break;
        case 'lt':
          item.max = cond.value;
          item.exclusive_max = true;
          break;
        case 'eq':
          item.min = cond.value;
          item.max = cond.value;
          break;
        case 'neq':
          item.min_exclude = cond.value;
          item.max_exclude = cond.value;
          break;
      }
      indicatorFilters.push(item);
    } else if (spec.type === 'cross' && cond.referenceFilterKey) {
      indicatorFilters.push({
        column,
        condition: cond.operator === 'crossed_above' ? 'above' : 'below',
        reference_column: referenceColumn,
        lookback_days: cond.lookbackDays ?? 5,
      });
    }
  }

  return {
    indicator_filters: indicatorFilters,
    sort_by: 'score',
    sort_order: 'desc',
    max_results: 50,
  };
}

// ── Component ────────────────────────────────────────────

export default function ScreenerBuilder() {
  const { isDarkMode } = useTheme();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { savePreset } = useScreens();
  const { composites } = useComposites();
  const { macros, saveMacro } = useMacros();

  // Drawer state — ticker detail card. Synced to ?ticker= URL param.
  const [drawerTicker, setDrawerTicker] = useState<string | null>(null);

  // URL → drawer sync on mount / external nav.
  useEffect(() => {
    const fromUrl = searchParams.get('ticker');
    if (fromUrl && fromUrl.toUpperCase() !== drawerTicker) {
      setDrawerTicker(fromUrl.toUpperCase());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const openTicker = useCallback(
    (t: string) => {
      const upper = t.toUpperCase();
      setDrawerTicker(upper);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('ticker', upper);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const closeDrawer = useCallback(() => {
    setDrawerTicker(null);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('ticker');
        return next;
      },
      { replace: true },
    );
  }, [setSearchParams]);

  // ── State ──────────────────────────────────────────────
  const [filters, setFilters] = useState<FilterGroup>({
    match: 'all',
    conditions: [],
  });
  const [screenName, setScreenName] = useState('Untitled Screener');
  const [cutoffDate, setCutoffDate] = useState('');
  const [sortBy, setSortBy] = useState('score');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [maxResults, setMaxResults] = useState(50);
  const [useAi, setUseAi] = useState(false);

  // Scan state
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [scanError, setScanError] = useState<string | undefined>();
  const [scanResults, setScanResults] = useState<ScanResult[]>([]);

  // Buy-and-hold return data (ticker -> return_pct)
  const [returnData, setReturnData] = useState<Record<string, number> | null>(null);
  const [returnLoading, setReturnLoading] = useState(false);

  // Inline backtest panel (Buy & Hold + With Exit Rules)
  const [backtestExpanded, setBacktestExpanded] = useState(false);

  // Dialog state
  const [pickerOpen, setPickerOpen] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveMode, setSaveMode] = useState<'save' | 'save-as'>('save');
  const [shareOpen, setShareOpen] = useState(false);
  const [compositeOpen, setCompositeOpen] = useState(false);
  const [macroName, setMacroName] = useState('');
  const [showMacroSave, setShowMacroSave] = useState(false);

  // Refs
  const eventSourceRef = useRef<EventSource | null>(null);

  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
    subtle: isDarkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)',
    border: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    surface: isDarkMode ? '#272729' : '#f5f5f7',
    surfaceRaised: isDarkMode ? '#2a2a2d' : '#fafafc',
    inputBg: isDarkMode ? '#000000' : '#ffffff',
    canvas: isDarkMode ? '#050505' : '#f5f5f7',
    accent: '#10B981',
  };

  // ── URL param handling ─────────────────────────────────
  useEffect(() => {
    const shared = searchParams.get('s');
    if (shared) {
      const decoded = decodeShareUrl(shared);
      if (decoded) {
        setFilters(decoded.filters as FilterGroup);
        if (decoded.sort?.by) setSortBy(decoded.sort?.by);
        if (decoded.sort?.order) setSortOrder(decoded.sort?.order);
        if (decoded.maxResults) setMaxResults(decoded.maxResults);
        if (decoded.cutoffDate) setCutoffDate(decoded.cutoffDate);
      }
    }

    const loadId = searchParams.get('load');
    if (loadId) {
      // Template loading is handled via the library modal
      // URL param is for direct preset loading
    }
  }, [searchParams]);

  // ── Draft persistence ──────────────────────────────────
  useEffect(() => {
    try {
      const draft = {
        filters,
        screenName,
        cutoffDate,
        sortBy,
        sortOrder,
        maxResults,
        useAi,
        timestamp: Date.now(),
      };
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      // ignore
    }
  }, [filters, screenName, cutoffDate, sortBy, sortOrder, maxResults, useAi]);

  // Restore draft on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) {
        const draft = JSON.parse(raw);
        const isFresh = draft.timestamp && Date.now() - draft.timestamp < 24 * 60 * 60 * 1000;
        if (isFresh) {
          if (draft.filters) setFilters(draft.filters);
          if (draft.screenName) setScreenName(draft.screenName);
          if (draft.cutoffDate) setCutoffDate(draft.cutoffDate);
          if (draft.sort?.by) setSortBy(draft.sort?.by);
          if (draft.sort?.order) setSortOrder(draft.sort?.order);
          if (draft.maxResults) setMaxResults(draft.maxResults);
          if (draft.useAi !== undefined) setUseAi(draft.useAi);
        }
      }
    } catch {
      // ignore
    }
  }, []);

  // Cleanup event source on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // ── Custom filters from composites & macros ────────────
  const customFilters = useMemo(() => {
    const filters: FilterSpec[] = [];

    // User-defined math composites
    for (const comp of composites) {
      filters.push({
        key: comp.name,
        label: comp.name,
        category: 'composite',
        type: 'number',
        backendColumn: comp.name,
        operators: [
          { operator: 'gt', label: '>', valueType: 'number' },
          { operator: 'gte', label: '>=', valueType: 'number' },
          { operator: 'lt', label: '<', valueType: 'number' },
          { operator: 'lte', label: '<=', valueType: 'number' },
        ],
        unit: 'pts',
        description: comp.description || `Custom: ${comp.leftIndicator} ${comp.operation} ${comp.rightIndicator}`,
      });
    }

    // Macro filter groups
    for (const macro of macros) {
      filters.push({
        key: `__macro__${macro.id}`,
        label: `📁 ${macro.name}`,
        category: 'composite',
        type: 'categorical',
        backendColumn: '',
        operators: [],
        description: macro.description || `${macro.filters.conditions.length} condition macro`,
      });
    }

    return filters;
  }, [composites, macros]);

  // Indicator list for the drawer's chart overlay set. Mirrors the
  // filterColumns derivation in ResultsPanel so the drawer's chart shows
  // the same overlays the user filtered on.
  const filterColumns: ResultsColumn[] = useMemo(
    () => getColumnsForFilters(filters.conditions as unknown as FilterCondition[]),
    [filters.conditions],
  );
  const chartIndicators: IndicatorDescriptor[] = useMemo(
    () =>
      filterColumns.map((col) => ({
        id: col.payloadKey,
        label: col.header,
        params: col.params,
      })),
    [filterColumns],
  );

  // ── Filter operations ──────────────────────────────────
  const addCondition = () => {
    setFilters((prev) => ({
      ...prev,
      conditions: [...prev.conditions, createEmptyCondition()],
    }));
  };

  const updateCondition = (index: number, updated: FilterCondition) => {
    setFilters((prev) => {
      const conditions = [...prev.conditions];
      conditions[index] = updated;
      return { ...prev, conditions };
    });
  };

  const removeCondition = (index: number) => {
    setFilters((prev) => ({
      ...prev,
      conditions: prev.conditions.filter((_, i) => i !== index),
    }));
  };

  const setGroupMatch = (match: 'all' | 'any') => {
    setFilters((prev) => ({ ...prev, match }));
  };

  // ── Load preset ────────────────────────────────────────
  const handleLoadPreset = (preset: ScreenPreset) => {
    setFilters(preset.filters);
    setScreenName(preset.name);
    if (preset.sort?.by) setSortBy(preset.sort?.by);
    if (preset.sort?.order) setSortOrder(preset.sort?.order);
    if (preset.maxResults) setMaxResults(preset.maxResults);
    if (preset.cutoffDate) setCutoffDate(preset.cutoffDate);
    if (preset.useAi !== undefined) setUseAi(preset.useAi);
  };

  // ── Save ───────────────────────────────────────────────
  const handleSave = (name: string, description?: string, category?: string) => {
    savePreset({
      name,
      filters,
      description,
      category,
      sort: sortBy ? { by: sortBy, order: sortOrder } : undefined,
      maxResults,
      cutoffDate: cutoffDate || undefined,
      useAi,
    });
    setScreenName(name);
  };

  // ── Share data ─────────────────────────────────────────
  const shareData = {
    schemaVersion: 1 as const,
    name: screenName || 'Untitled',
    filters,
    sort: sortBy ? { by: sortBy, order: sortOrder } : undefined,
    maxResults,
    cutoffDate: cutoffDate || undefined,
    useAi,
  };

  // ── Scan pipeline ───────────────────────────────────────
  const startScan = useCallback(async () => {
    if (filters.conditions.length === 0) return;

    setIsScanning(true);
    setScanError(undefined);
    setScanResults([]);
    setScanProgress(0);
    setReturnData(null);

    const backendFilters = convertFiltersToBackend(filters);

    // Build custom composites list for the backend
    const customCompositesList = composites
      .filter((comp) => {
        // Only include composites that are referenced in the current filters
        return filters.conditions.some((c) => c.filterKey === comp.name);
      })
      .map((comp) => ({
        name: comp.name,
        left_indicator: comp.leftIndicator,
        right_indicator: comp.rightIndicator,
        operation: comp.operation,
      }));

    try {
      const res = await fetch('/api/screener/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'quant_strategy',
          use_ai: useAi,
          cutoff_date: cutoffDate || undefined,
          max_results: maxResults,
          filters: backendFilters,
          // Tell the backend which result-row keys the UI needs values for
          // (e.g. the user's chosen SMA 200 with window=200). The worker
          // computes each column at the requested params and includes the
          // value in the scan result row.
          result_columns: filterColumns
            .filter((c) => c.dataKey)
            .map((c) => ({ dataKey: c.dataKey, params: c.params })),
          custom_composites: customCompositesList.length > 0 ? customCompositesList : undefined,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to start scan');
      }

      const data = await res.json();
      const id = data.scan_id;

      // SSE stream
      const es = new EventSource(`/api/screener/stream/${id}`);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          const { type, data: eventData } = payload;

          if (type === 'progress') {
            setScanProgress(eventData.progress);
          } else if (type === 'status') {
            if (eventData.status === 'completed') {
              setIsScanning(false);
              setScanProgress(100);
              fetchResults(id);
              es.close();
              // Fetch buy-and-hold returns after results come in
              if (isCutoffEligible(cutoffDate)) {
                (async () => {
                  try {
                    const r = await fetch(`/api/screener/results/${id}`);
                    const d = await r.json();
                    const tickers = (d.results || []).map((x: any) => x.ticker);
                    if (tickers.length > 0) {
                      setReturnLoading(true);
                      const br = await fetch('/api/screener/backtest-hold', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers, as_of_date: cutoffDate }),
                      });
                      if (br.ok) {
                        const bd = await br.json();
                        const returns: Record<string, number> = {};
                        for (const tr of bd.ticker_results || []) {
                          returns[tr.ticker] = tr.return_pct;
                        }
                        setReturnData(returns);
                      }
                    }
                  } catch { /* ignore */ }
                  finally { setReturnLoading(false); }
                })();
              }
            } else if (eventData.status === 'failed') {
              setIsScanning(false);
              setScanError(eventData.error || 'Scan failed');
              es.close();
            }
          }
        } catch {
          // ignore parse errors
        }
      };

      es.onerror = () => {
        es.close();
        pollFallback(id);
      };
    } catch (err) {
      setIsScanning(false);
      setScanError(err instanceof Error ? err.message : 'Unknown error');
    }
  }, [filters, useAi, cutoffDate, maxResults]);

  const fetchResults = async (id: string) => {
    try {
      const res = await fetch(`/api/screener/results/${id}`);
      const data = await res.json();
      setScanResults(data.results || []);
    } catch {
      // ignore
    }
  };

  const pollFallback = async (id: string) => {
    const poll = async () => {
      try {
        const res = await fetch(`/api/screener/status/${id}`);
        const data = await res.json();

        setScanProgress(data.progress);

        if (data.status === 'running') {
          setTimeout(poll, 1000);
        } else if (data.status === 'completed') {
          setIsScanning(false);
          setScanProgress(100);
          fetchResults(id);
          // Fetch buy-and-hold returns
          if (isCutoffEligible(cutoffDate)) {
            (async () => {
              try {
                const r = await fetch(`/api/screener/results/${id}`);
                const d = await r.json();
                const tickers = (d.results || []).map((x: any) => x.ticker);
                if (tickers.length > 0) {
                  setReturnLoading(true);
                  const br = await fetch('/api/screener/backtest-hold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tickers, as_of_date: cutoffDate }),
                  });
                  if (br.ok) {
                    const bd = await br.json();
                    const returns: Record<string, number> = {};
                    for (const tr of bd.ticker_results || []) {
                      returns[tr.ticker] = tr.return_pct;
                    }
                    setReturnData(returns);
                  }
                }
              } catch { /* ignore */ }
              finally { setReturnLoading(false); }
            })();
          }
        } else if (data.status === 'failed') {
          setIsScanning(false);
          setScanError(data.error || 'Scan failed');
        }
      } catch {
        setIsScanning(false);
        setScanError('Failed to get scan status');
      }
    };
    poll();
  };

  // ── Export to Lab ──────────────────────────────────────
  const exportToLab = () => {
    const tickers = scanResults.map((r) => r.ticker).join(',');
    const fromDate = cutoffDate || new Date().toISOString().split('T')[0];
    navigate(`/app/lab/build?tickers=${encodeURIComponent(tickers)}&from_date=${fromDate}`);
  };

  // ── Render ──────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', backgroundColor: colors.canvas }}>
      <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px' }}>
        {/* ── Header ──────────────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingTop: 32,
            paddingBottom: 24,
          }}
        >
          <div>
            <h1
              style={{
                fontSize: 28,
                fontWeight: 600,
                letterSpacing: '-0.02em',
                color: colors.text,
                margin: 0,
              }}
            >
              Custom Screener
            </h1>
            <p style={{ fontSize: 14, color: colors.muted, margin: '4px 0 0' }}>
              Build your own stock screener from a library of filters
            </p>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => {
                setSaveMode('save');
                setSaveOpen(true);
              }}
              style={headerButtonStyle(colors)}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = colors.accent;
                e.currentTarget.style.color = colors.accent;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = colors.border;
                e.currentTarget.style.color = colors.muted;
              }}
            >
              <Save size={15} />
              Save
            </button>
            <button
              onClick={() => {
                setSaveMode('save-as');
                setSaveOpen(true);
              }}
              style={headerButtonStyle(colors)}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = colors.accent;
                e.currentTarget.style.color = colors.accent;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = colors.border;
                e.currentTarget.style.color = colors.muted;
              }}
            >
              Save As
            </button>
            <button
              onClick={() => setLibraryOpen(true)}
              style={headerButtonStyle(colors)}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = colors.accent;
                e.currentTarget.style.color = colors.accent;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = colors.border;
                e.currentTarget.style.color = colors.muted;
              }}
            >
              <BookTemplate size={15} />
              Templates
            </button>
            <button
              onClick={() => setShareOpen(true)}
              style={{
                ...headerButtonStyle(colors),
                backgroundColor: 'rgba(16,185,129,0.1)',
                color: colors.accent,
                borderColor: 'rgba(16,185,129,0.2)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'rgba(16,185,129,0.2)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'rgba(16,185,129,0.1)';
              }}
            >
              <Share2 size={15} />
              Share
            </button>
          </div>
        </div>

        {/* ── Config row ─────────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            marginBottom: 24,
            padding: '16px 20px',
            borderRadius: 12,
            border: `1px solid ${colors.border}`,
            backgroundColor: colors.surface,
          }}
        >
          <div style={{ flex: 1 }}>
            <label
              style={{
                display: 'block',
                fontSize: 11,
                fontWeight: 600,
                color: colors.muted,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 4,
              }}
            >
              Screen Name
            </label>
            <input
              type="text"
              value={screenName}
              onChange={(e) => setScreenName(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: `1px solid ${colors.border}`,
                backgroundColor: colors.inputBg,
                color: colors.text,
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>

          <div style={{ width: 180 }}>
            <label
              style={{
                display: 'block',
                fontSize: 11,
                fontWeight: 600,
                color: colors.muted,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 4,
              }}
            >
              As-Of Date
            </label>
            <input
              type="date"
              value={cutoffDate}
              onChange={(e) => setCutoffDate(e.target.value)}
              max={new Date().toISOString().split('T')[0]}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: `1px solid ${colors.border}`,
                backgroundColor: colors.inputBg,
                color: colors.text,
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 16 }}>
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: colors.muted,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              AI
            </span>
            <button
              onClick={() => setUseAi(!useAi)}
              style={{
                width: 36,
                height: 20,
                borderRadius: 10,
                border: 'none',
                backgroundColor: useAi ? colors.accent : colors.subtle,
                cursor: 'pointer',
                position: 'relative',
                transition: 'background-color 150ms ease',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  top: 2,
                  width: 16,
                  height: 16,
                  borderRadius: '50%',
                  backgroundColor: '#fff',
                  transition: 'transform 150ms ease',
                  transform: useAi ? 'translateX(16px)' : 'translateX(2px)',
                }}
              />
            </button>
          </div>
        </div>

        {/* ── Template chips strip ──────────────────────── */}
        <TemplateChips
          onLoad={(tpl) => {
            setFilters(tpl.filters);
            setScreenName(tpl.name);
            if (tpl.sort?.by) setSortBy(tpl.sort.by);
            if (tpl.sort?.order) setSortOrder(tpl.sort.order);
            if (tpl.maxResults) setMaxResults(tpl.maxResults);
            if (tpl.useAi !== undefined) setUseAi(tpl.useAi);
          }}
          activeFilters={filters}
        />

        {/* ── Filter builder ──────────────────────────────── */}
        <div
          style={{
            marginBottom: 24,
            padding: 20,
            borderRadius: 12,
            border: `1px solid ${colors.border}`,
            backgroundColor: colors.surface,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <SlidersHorizontal size={18} color={colors.text} />
            <span style={{ fontSize: 15, fontWeight: 600, color: colors.text }}>
              Filters
            </span>
            {filters.conditions.length > 0 && (
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
                {filters.conditions.length} condition
                {filters.conditions.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          {filters.conditions.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <GroupHeader
                match={filters.match}
                onMatchChange={setGroupMatch}
                conditionCount={filters.conditions.length}
              />
              {filters.conditions.map((cond, idx) => (
                <FilterRow
                  key={cond.id}
                  condition={cond}
                  index={idx}
                  total={filters.conditions.length}
                  groupMatch={filters.match}
                  onChange={(updated) => updateCondition(idx, updated)}
                  onRemove={() => removeCondition(idx)}
                  onGroupMatchChange={setGroupMatch}
                />
              ))}
            </div>
          ) : (
            <div
              style={{
                textAlign: 'center',
                padding: '32px 16px',
                color: colors.muted,
              }}
            >
              <Search size={28} style={{ margin: '0 auto 8px', display: 'block', opacity: 0.4 }} />
              <span style={{ fontSize: 14, display: 'block', marginBottom: 12 }}>
                No filters yet. Add a filter to start building your screener.
              </span>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button
              onClick={addCondition}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '8px 16px',
                borderRadius: 8,
                border: `1px dashed ${colors.border}`,
                backgroundColor: 'transparent',
                color: colors.accent,
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 150ms ease',
                flex: 1,
                justifyContent: 'center',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = colors.accent;
                e.currentTarget.style.backgroundColor = 'rgba(16,185,129,0.05)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = colors.border;
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
            >
              <Plus size={16} />
              Add Filter
            </button>
            <button
              onClick={() => setCompositeOpen(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '8px 16px',
                borderRadius: 8,
                border: `1px dashed ${colors.border}`,
                backgroundColor: 'transparent',
                color: colors.accent,
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = colors.accent;
                e.currentTarget.style.backgroundColor = 'rgba(16,185,129,0.05)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = colors.border;
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
            >
              <FunctionSquare size={16} />
              Create Composite
            </button>
            {filters.conditions.length > 0 && (
              <button
                onClick={() => {
                  const name = `Macro (${filters.conditions.length} conditions)`;
                  saveMacro(name, filters);
                  setShowMacroSave(true);
                  setMacroName(name);
                  setTimeout(() => setShowMacroSave(false), 2000);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '8px 16px',
                  borderRadius: 8,
                  border: `1px dashed ${colors.border}`,
                  backgroundColor: 'transparent',
                  color: colors.accent,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = colors.accent;
                  e.currentTarget.style.backgroundColor = 'rgba(16,185,129,0.05)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = colors.border;
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <Layers size={16} />
                Save as Macro
              </button>
            )}
          </div>
          {showMacroSave && (
            <div
              style={{
                marginTop: 8,
                padding: '6px 12px',
                borderRadius: 6,
                backgroundColor: 'rgba(16,185,129,0.1)',
                color: colors.accent,
                fontSize: 12,
                fontWeight: 500,
                textAlign: 'center',
              }}
            >
              Saved as macro "{macroName}" — find it in the filter picker under Composites
            </div>
          )}
        </div>

        {/* ── Sort & Config ──────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            marginBottom: 24,
            padding: '16px 20px',
            borderRadius: 12,
            border: `1px solid ${colors.border}`,
            backgroundColor: colors.surface,
          }}
        >
          <div>
            <label
              style={{
                display: 'block',
                fontSize: 11,
                fontWeight: 600,
                color: colors.muted,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 4,
              }}
            >
              Sort By
            </label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              style={{
                padding: '8px 10px',
                borderRadius: 6,
                border: `1px solid ${colors.border}`,
                backgroundColor: colors.inputBg,
                color: colors.text,
                fontSize: 13,
                outline: 'none',
              }}
            >
              <option value="score">Score</option>
              <option value="close">Close Price</option>
              <option value="momentum_rsi">RSI</option>
              <option value="volume_ratio">Volume Ratio</option>
              <option value="ath_proximity">ATH Proximity</option>
              <option value="eps_growth_qoq">EPS Growth</option>
              <option value="ticker">Ticker</option>
            </select>
          </div>

          <div>
            <label
              style={{
                display: 'block',
                fontSize: 11,
                fontWeight: 600,
                color: colors.muted,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 4,
              }}
            >
              Order
            </label>
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
              style={{
                padding: '8px 10px',
                borderRadius: 6,
                border: `1px solid ${colors.border}`,
                backgroundColor: colors.inputBg,
                color: colors.text,
                fontSize: 13,
                outline: 'none',
              }}
            >
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
          </div>

          <div style={{ width: 100 }}>
            <label
              style={{
                display: 'block',
                fontSize: 11,
                fontWeight: 600,
                color: colors.muted,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 4,
              }}
            >
              Max Results
            </label>
            <input
              type="number"
              min={1}
              max={200}
              value={maxResults}
              onChange={(e) => setMaxResults(parseInt(e.target.value, 10) || 50)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 6,
                border: `1px solid ${colors.border}`,
                backgroundColor: colors.inputBg,
                color: colors.text,
                fontSize: 13,
                outline: 'none',
              }}
            />
          </div>

          <div style={{ flex: 1 }} />

          {/* Scan button */}
          <button
            onClick={startScan}
            disabled={isScanning || filters.conditions.length === 0}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 24px',
              borderRadius: 8,
              border: 'none',
              backgroundColor:
                isScanning || filters.conditions.length === 0 ? colors.subtle : colors.accent,
              color:
                isScanning || filters.conditions.length === 0 ? colors.muted : '#000',
              fontSize: 14,
              fontWeight: 600,
              cursor:
                isScanning || filters.conditions.length === 0
                  ? 'not-allowed'
                  : 'pointer',
              transition: 'all 150ms ease',
              marginTop: 16,
            }}
            onMouseEnter={(e) => {
              if (!isScanning && filters.conditions.length > 0) {
                e.currentTarget.style.opacity = '0.9';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = '1';
            }}
          >
            {isScanning ? (
              <>
                <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                Scanning... {scanProgress}%
              </>
            ) : (
              <>
                <Sparkles size={16} />
                Scan
              </>
            )}
          </button>
        </div>

        {/* ── Progress bar ────────────────────────────────── */}
        {isScanning && (
          <div
            style={{
              marginBottom: 24,
              height: 4,
              borderRadius: 2,
              backgroundColor: colors.border,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${scanProgress}%`,
                height: '100%',
                backgroundColor: colors.accent,
                borderRadius: 2,
                transition: 'width 300ms ease',
              }}
            />
          </div>
        )}

        {/* ── Results ──────────────────────────────────────── */}
        {(scanResults.length > 0 || isScanning || scanError) && (
          <div style={{ marginBottom: 48 }}>
            <ResultsPanel
              results={scanResults}
              loading={isScanning}
              error={scanError}
              returnData={returnData}
              returnLoading={returnLoading}
              cutoffDate={cutoffDate}
              filters={filters}
              onExport={exportToLab}
              onShowBacktest={() => {
                // Toggle the inline backtest panel (Buy & Hold + With Exit Rules)
                setBacktestExpanded((v) => !v);
              }}
              onTickerClick={openTicker}
            />
            {backtestExpanded && cutoffDate && (
              <div style={{ marginTop: 16 }}>
                <BacktestPanel
                  tickers={scanResults.map((r) => r.ticker)}
                  asOfDate={cutoffDate}
                  customFilters={convertFiltersToBackend(filters)}
                />
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Dialogs ────────────────────────────────────────── */}
      <FilterPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(filterKey) => {
          // Check if this is a macro (starts with __macro__)
          if (filterKey.startsWith('__macro__')) {
            const macro = macros.find((m) => `__macro__${m.id}` === filterKey);
            if (macro) {
              // Expand macro conditions into the builder
              setFilters((prev) => ({
                ...prev,
                conditions: [
                  ...prev.conditions,
                  ...macro.filters.conditions.map((c) => ({ ...c, id: `cond_${Date.now()}_${Math.random()}` })),
                ],
              }));
            }
            return;
          }

          if (filters.conditions.length === 0) {
            addCondition();
          }
          // Update the last condition with the selected filter
          setFilters((prev) => {
            if (prev.conditions.length === 0) return prev;
            const conditions = [...prev.conditions];
            const last = { ...conditions[conditions.length - 1] };
            last.filterKey = filterKey;
            // Reset cross-condition fields when switching filters
            last.referenceFilterKey = undefined;
            last.lookbackDays = undefined;
            last.compareToIndicator = false;
            // Check custom filters first (composites)
            const customFilter = customFilters.find((f: FilterSpec) => f.key === filterKey);
            const spec = customFilter || getFilterByKey(filterKey);
            if (spec) {
              last.operator =
                spec.type === 'number'
                  ? 'gte'
                  : spec.type === 'cross'
                    ? 'crossed_above'
                    : 'is_true';
              last.value = spec.type === 'number' ? 0 : spec.type === 'boolean' ? true : null;
            }
            conditions[conditions.length - 1] = last;
            return { ...prev, conditions };
          });
        }}
        customFilters={customFilters}
      />

      <ScreenLibraryModal
        open={libraryOpen}
        onOpenChange={setLibraryOpen}
        onLoad={handleLoadPreset}
      />

      <SaveScreenDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        onSave={handleSave}
        initialName={screenName}
        mode={saveMode}
      />

      <ShareDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        screenData={shareData}
      />

      <CompositeBuilder
        open={compositeOpen}
        onOpenChange={setCompositeOpen}
      />

      <TickerDetailDrawer
        ticker={drawerTicker}
        asOfDate={cutoffDate}
        indicators={chartIndicators}
        onClose={closeDrawer}
        onExportToLab={(t) => {
          // Pre-fill Lab with just this ticker and the current as-of date.
          const fromDate = cutoffDate || new Date().toISOString().split('T')[0];
          navigate(`/app/lab/build?tickers=${encodeURIComponent(t)}&from_date=${fromDate}`);
          closeDrawer();
        }}
      />
    </div>
  );
}

// ── Style helpers ─────────────────────────────────────────

function headerButtonStyle(colors: Record<string, string>): React.CSSProperties {
  return {
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
  };
}
