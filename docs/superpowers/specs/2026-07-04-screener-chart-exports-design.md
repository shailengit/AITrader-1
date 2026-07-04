# Custom Screener — Chart, Exports & Standalone View — Design

**Date:** 2026-07-04
**Status:** Approved (awaiting implementation plan)
**Author:** brainstorming session

## Context

The Custom Screener page (`/screener/build`) has three open issues and one feature request:

1. **Bug — Export to Lab broken (both row and bulk).** The two `navigate('/app/lab/build?…')` calls land on a URL that does not exist in `App.tsx`. The canonical QuantGen route is `/quantgen/*`. The handlers silently fail to navigate.
2. **Bug — Tunable-window indicators (e.g. SMA 50, SMA 200) do not plot on the drawer's chart for templates that specify them.** The drawer's `chartIndicators` are derived from the active filters with their `params` (`{ window: 50 }`, etc.), but the chart endpoint request sends only `?indicators=...` and never sends the `overrides` JSON. The chart endpoint then falls back to the `ta` library's default window (14), so the lines drawn don't match the values shown in the scan result table.
3. **Feature — A bigger, standalone chart view is needed.** The drawer's 100px / 260px-tall chart is too cramped to actually inspect indicator values around the as-of date. The user wants a full-page view with a dominant chart and a metadata side rail, plus the ability to:
   - **Add any indicator in the catalog** (not just the ones they filtered on), **with any parameter value** (e.g. EMA 200, KAMA 14, MACD with custom fast/slow).
   - **Switch date ranges** between fixed presets (1Y / 2Y / 3Y / 5Y / Max) and a custom start/end pair.

The intended outcome: Export to Lab works for single row and bulk; the drawer's chart shows the indicators the user filtered on at the correct windows; a new full-page chart view at `/screener/build/chart/:ticker` gives the user a real chart canvas with catalog-driven overlays and a date range picker, while keeping the drawer for quick per-row inspection.

## Decisions locked in this session

| # | Decision | Choice |
|---|----------|--------|
| 1 | Where does the big chart live? | New "Open in chart" button on the drawer → full-page view at `/screener/build/chart/:ticker`. Drawer stays. |
| 2 | What does the full-page view show? | Chart + collapsible left rail with fundamentals, indicators, earnings, action buttons. |
| 3 | Source of indicator list in standalone view? | Pull from existing `/api/indicators/catalog` (full universe; includes ta, vectorbt, pandas-ta). |
| 4 | Where does the date range control live? | Pill buttons [1Y / 2Y / 3Y / 5Y / Max / Custom] above the chart. Custom reveals two date inputs. |
| 5 | How are 1Y / 2Y / 3Y / 5Y / Max mapped to dates? | Calendar days: 365 / 730 / 1095 / 1825 / 10000. Max = 10000 (effectively "all available"; the existing endpoint already supports very large `days` values). |
| 6 | Plan scope? | One plan covers all five changes (2 bug fixes + 1 drawer tweak + 1 new full-page view + 1 chart wiring). |

## Architecture

### Routes

```
GET  /screener/build                            →  ScreenerBuilder (today's page)
GET  /screener/build/chart/:ticker              →  ChartView (new full-page)
                                                  (params: ?from=YYYY-MM-DD
                                                          &range=1y|2y|3y|5y|max|custom
                                                          &start=YYYY-MM-DD
                                                          &end=YYYY-MM-DD
                                                          &overlays=ema_20,sma_200
                                                          &params=JSON)
```

The new route is added inside the existing `screener/build` route group in `App.tsx` so the page inherits the same Layout.

### Round-trip navigation

```
ResultsPanel row click
  → setDrawerTicker + URL ?ticker=AAPL         (existing)
  → TickerDetailDrawer opens

TickerDetailDrawer "Open in chart" button
  → closeDrawer()                              (clears ?ticker=)
  → navigate('/screener/build/chart/AAPL?from=cutoff&overlays=...&params=...')

ChartView "Back to results" button
  → navigate('/screener/build')                (returns to builder; no params)
```

### Frontend file layout

```
frontend/src/pages/app/ScreenerBuilder/
├── ChartView.tsx                 # NEW — full-page chart + left rail
└── ChartView/                    # NEW
    ├── IndicatorPickerPanel.tsx  # NEW — search, category chips, param editor
    ├── DateRangeBar.tsx          # NEW — pill buttons + Custom date inputs
    ├── MetadataRail.tsx          # NEW — left rail content (fundamentals + earnings + actions)
    └── OverlaysList.tsx          # NEW — current overlays with color swatch + remove

frontend/src/data/
└── indicatorMap.ts               # NEW — pure helpers: catalog→backend column, param
                                   #       translation, label formatting, id codec

frontend/src/components/shared/   # NEW dir
└── TickerMetadataPanel.tsx       # NEW — shared fundamentals/indicators/earnings panel,
                                   #       used by both drawer and ChartView
```

### Backend

**Modified:** `backend/app/routers/screener.py` — `/api/screener/chart-data/{ticker}` gains two optional query params:

```python
async def chart_data(
    ticker: str,
    indicators: str = "",
    days: int = 250,                       # existing
    start: str | None = None,              # NEW — yyyy-mm-dd
    end: str | None = None,                # NEW — yyyy-mm-dd
    overrides: str = "",                   # existing
):
```

**Modified:** `backend/app/services/screening/chart_data.py` — `get_chart_data()` gains two optional kwargs. When both `start` and `end` are provided, SQL is `SELECT * FROM "<table>" WHERE "Date" BETWEEN :start AND :end ORDER BY "Date"`. When only `start` is provided, upper bound is `start + days` calendar days (or `MAX("Date")` if that's earlier). When only `end` is provided, lower bound is `end - days`. When neither is provided, use `days` (today's behavior, fully backward compatible).

The `overrides` JSON plumbing is already complete from a prior fix; the only bug was on the client side (the drawer's request never sent `params` as `overrides`).

### Indicator spec format

The catalog returns `{ name, source, category, params: [{name, default, min, max}], ... }`. The picker converts to `IndicatorDescriptor` whose `id` is `{source}__{name}__{paramsSig}`. Examples:

- `ta__RSI__window14` → RSI 14
- `ta__RSI__window21` → RSI 21 (same indicator, different window)
- `ta__EMA__window200` → 200-period EMA
- `ta__MACD__window_fast12_window_slow26_window_sign9` → MACD with explicit params

`indicatorMap.ts` exposes pure helpers:

- `catalogEntryToColumn(catalogName)` — `RSI → momentum_rsi`, `EMA → trend_ema_fast`, `MACD → trend_macd`, etc. Hand-curated for the ~25 catalog entries.
- `catalogParamsToBackendParams(catalogName, values)` — translates ta-library param names to registry names (`lbp` → `window`, etc.).
- `formatOverlayLabel(catalogName, params)` — `RSI (21)`, `EMA (200)`, `MACD (12,26,9)`.
- `idFromCatalog(catalogName, params)` / `paramsFromId(id)` — URL codec.

### Connector to chart endpoint

When the standalone view sends its request, the picker maps each `IndicatorDescriptor.id` back to a backend column + params and constructs:

```
GET /api/screener/chart-data/AAPL
  ?indicators=ema_20,sma_200,sma_50
  &overrides={"ema_20":{"window":200},"sma_50":{"window":50}}
  &days=1825
```

The `overrides` map is JSON-encoded (the existing endpoint already parses it).

## Data flow

```
URL changes (any source: back/forward, "Open in chart" pass-through, picker edits)
  → ChartView parses URL → setPickerOverlays, setRangeMode, setCustomRange
  → useEffect on (ticker, rangeMode, customRange, pickerOverlays) fires
  → AbortController for old request, new request built
  → chart endpoint returns bars
  → state: { kind: 'data', bars, loading: false }
  → chart re-renders

User picks a new range
  → setRangeMode(...) → setSearchParams({ range }, { replace: true })
  → URL updates → useEffect fires → chart refetches

User adds an overlay via the picker
  → updateOverlays(arr => [...arr, newOne])
  → setSearchParams with new overlays + params
  → URL updates → useEffect fires → chart refetches

User clicks "Back to results"
  → navigate('/screener/build') → results table re-renders
```

## State (ChartView)

```ts
const [pickerOverlays, setPickerOverlays] = useState<IndicatorDescriptor[]>([]);
const [rangeMode, setRangeMode] = useState<'1y' | '2y' | '3y' | '5y' | 'max' | 'custom'>('1y');
const [customRange, setCustomRange] = useState<{ start?: string; end?: string }>({});
const [chartState, setChartState] = useState<
  | { kind: 'idle' }
  | { kind: 'loading-first' }
  | { kind: 'data'; bars: ChartBar[]; loading: boolean }
  | { kind: 'error'; message: string }
>({ kind: 'idle' });
```

`pickerOverlays`, `rangeMode`, `customRange` are all derived from the URL via `useMemo` and mutated via a single `updateUrl(partial)` helper that calls `setSearchParams(..., { replace: true })`. Replace, not push, so back-button history doesn't bloat.

## Error handling

| Failure | UI |
|---|---|
| Chart endpoint returns 400 (bad range, malformed overrides) | Inline error pill in the chart panel with "Retry" button. |
| Chart endpoint returns 404 (`DATA_NOT_FOUND` for the ticker) | "No data for AAPL on this date" with hint to try a different date/range. |
| Chart endpoint times out (5s) | "Chart is taking longer than expected" with "Retry" button. |
| Metadata endpoint fails | Skeleton stays visible (never showed data, no flicker). |
| Catalog endpoint fails (indicator picker) | Empty state in the picker: "Couldn't load indicators. Refresh the page." |
| User navigates to `/screener/build/chart/INVALID` | Page shows "Ticker not found" full-page state; no crash. |
| Network offline | "You're offline. Chart will reload when you reconnect." |

**Loading states:**

- First paint: skeleton for everything until BOTH the chart and metadata have returned (or one has errored). Avoids flicker.
- Subsequent re-fetches: chart panel keeps the previous chart visible with a small "Loading..." badge in the corner.
- State machine: `idle → loading-first → data → data(loading=true) → data(loading=false)`. Errors from a re-fetch fall back to the previous data with a "Retry" affordance.

## Testing

### Backend (`backend/tests/routers/test_chart_data.py`, new)

Five tests, each uses `monkeypatch.setattr` on the chart module's engine to inject a small fixture of synthetic OHLCV rows:

1. `test_chart_data_with_start_and_end_returns_bars_in_range` — both params → bars between (inclusive) the dates, oldest first.
2. `test_chart_data_with_start_only_returns_bars_from_start_forward` — start only → all bars from `start` to latest, no end filter.
3. `test_chart_data_without_range_falls_back_to_days` — neither present → respects `days` (backward-compat regression).
4. `test_chart_data_with_overrides_still_works_after_date_range_addition` — regression: `overrides={"ema_20":{"window":200}}` still produces a separate `ema_20__w200` series.
5. `test_chart_data_with_malformed_start_returns_400` — `start=not-a-date` → 400 with `{"detail": "Invalid start date: ..."}`.

Run: `cd backend && ./venv/bin/python -m pytest tests/ -x -q` — all green.

### Frontend

- `cd frontend && npx tsc --noEmit` — clean.
- `cd frontend && npm run lint` — clean.
- `cd frontend && npm run build` — succeeds.
- `cd frontend && ./node_modules/.bin/vitest run src/data/indicatorMap.test.ts` — 6 unit tests pass.

### End-to-end smoke (manual, follows the recent `2a9d7b3` commit pattern)

1. Visit `/screener/build`. Click "Golden Cross" template chip. Click "Scan". Verify SMA 50 and SMA 200 columns are populated in the results table (regression check).
2. Click "Export to Lab" in the results header. Verify the URL is `/quantgen/build?tickers=...&from_date=...` and the QuantGen page loads (bug fix).
3. Click a result row. Verify the drawer opens. Verify SMA 50 and SMA 200 lines are visible in the drawer's chart (bug fix).
4. Click "Open in chart" in the drawer's chart header. Verify the URL becomes `/screener/build/chart/AAPL?from=...&range=1y&overlays=sma_50__window50,sma_200__window200` and the full-page chart loads.
5. Click "Add indicator" in the left rail. Pick "EMA", set window=200, click "Add overlay". Verify the URL updates and the chart re-fetches with the new line.
6. Click "5Y" in the date range bar. Verify the chart refetches with `?days=1825` and shows more bars.
7. Click "Custom" in the date range bar. Enter start `2024-01-01` and end `2024-06-30`. Verify the chart refetches with `?start=2024-01-01&end=2024-06-30` and only shows that range.
8. Click "Back to results". Verify the URL returns to `/screener/build` and the drawer/scan state is preserved.
9. Click "Export to Lab" in the left rail of ChartView. Verify the URL is `/quantgen/build?tickers=AAPL&from_date=...` (single-ticker path).
10. Open a new tab to `/screener/build/chart/INVALID`. Verify the page shows "Ticker not found" gracefully.
11. Resize the browser to 1024px wide. Verify the left rail collapses gracefully.

## Files

**New:**
- `frontend/src/pages/app/ScreenerBuilder/ChartView.tsx`
- `frontend/src/pages/app/ScreenerBuilder/ChartView/IndicatorPickerPanel.tsx`
- `frontend/src/pages/app/ScreenerBuilder/ChartView/DateRangeBar.tsx`
- `frontend/src/pages/app/ScreenerBuilder/ChartView/MetadataRail.tsx`
- `frontend/src/pages/app/ScreenerBuilder/ChartView/OverlaysList.tsx`
- `frontend/src/data/indicatorMap.ts`
- `frontend/src/data/indicatorMap.test.ts`
- `frontend/src/components/shared/TickerMetadataPanel.tsx`
- `backend/tests/routers/test_chart_data.py`

**Modified:**
- `frontend/src/App.tsx` — add new route
- `frontend/src/pages/app/ScreenerBuilder/TickerDetailDrawer.tsx` — add `onOpenInChart` prop + button
- `frontend/src/pages/app/ScreenerBuilder.tsx` — add `openChartView` handler, pass to drawer
- `backend/app/routers/screener.py` — add `start` / `end` query params
- `backend/app/services/screening/chart_data.py` — add `start` / `end` kwargs, branched SQL

**Unchanged (explicit non-goals):**
- `agno_screener.py` (backtest-orchestrator still depends on it)
- `TickerDetailDrawer` body (only one prop + one button change)
- `CandleStickChart` (reused as-is)
- `/api/indicators/catalog` (already provides everything the picker needs)
- The existing `screenerTemplates.ts` (12 templates are correct)
- The `paramsSignature` and `payloadKey` plumbing in `filterCatalog.ts` (already supports arbitrary params)

## Out of scope

- Comparing overlays across multiple tickers in one chart.
- Saving chart configurations (overlay set + range) to the user's library.
- AI narrative on the chart view.
- Mobile-first layout polish beyond what already exists (the page is desktop-first per CLAUDE.md).
- Indicator picker with per-row `params` editor beyond what the catalog provides (e.g. a "free-form" param input that the catalog doesn't list).
- Sharing the standalone chart via URL (the URL is already shareable; no "Share" button is added).
