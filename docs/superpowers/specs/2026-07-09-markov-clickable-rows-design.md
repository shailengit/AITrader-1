# Markov Chain Trader — Clickable Rows + Stock Detail Drawer

**Date:** 2026-07-09
**Status:** Approved design

## Context

The Markov Chain Trader page (`/markov`) runs a scan and displays results in a static table. Users want the same interactive row-click behavior as the Custom Screener: clicking a stock row opens a right-side drawer with a candlestick chart, toggleable indicator overlays, ticker metadata, and export actions.

Additionally, navigating away from the Markov page and back currently causes a full remount, losing all scan results. State persistence is needed.

## Goals

1. Make Markov results table rows clickable → open stock detail drawer
2. Reuse the exact `TickerDetailDrawer` component from the Custom Screener
3. Default chart overlays: EMA20 and EMA50 (toggleable)
4. Full indicator picker capability in the full-page chart view (~30 indicators)
5. State persistence: scan results survive navigation within the same tab
6. New route: `/markov/chart/:ticker` for full-page chart view

## Non-Goals

- No backend changes — existing `/api/screener/chart-data/{ticker}` and `/api/screener/ticker/{ticker}` endpoints are reused
- No scoring breakdown in the drawer (Markov has no scores — `TickerDetailDrawer` already hides this when `scoreRow` is null)
- No changes to the Custom Screener's `TickerDetailDrawer` component

## Design

### 1. State Persistence

**URL search params for scan configuration:**
- `model` — model type (xgboost/lstm)
- `threshold` — buy/sell threshold
- `minConviction` — minimum conviction filter
- `maxResults` — max results limit
- `asOfDate` — scan end date
- `ticker` — currently open drawer ticker

**sessionStorage for scan results:**
- Key: `markov:scan:results`
- Stores: `{ signals, sectors, totalScanned, timestamp }`
- On mount: check URL params → pre-fill ControlPanel; check sessionStorage → restore results if less than 5 minutes old
- On new scan: clear sessionStorage, run scan, save fresh results
- On unmount: results remain in sessionStorage for restore on return

### 2. Clickable Rows

**`SignalsTable.tsx` changes:**
- Add `onTickerClick: (ticker: string) => void` prop
- Each `<tr>` gets: `role="button"`, `tabIndex={0}`, `onClick`, `onKeyDown` (Enter/Space)
- Hover effect: background color change on mouse enter/leave
- Cursor: pointer

**`MarkovPage/index.tsx` changes:**
- Add `drawerTicker` state, synced to `?ticker=` URL param
- Import and render `TickerDetailDrawer` at the page level
- Pass `onTickerClick` to `SignalsTable`

### 3. TickerDetailDrawer

Reused directly from `ScreenerBuilder/TickerDetailDrawer.tsx` with:

| Prop | Value |
|------|-------|
| `ticker` | `drawerTicker` (from state) |
| `asOfDate` | `lastAsOfDate` (from scan params) |
| `indicators` | Default: `[{ id: 'ema_20', label: 'EMA 20' }, { id: 'ema_50', label: 'EMA 50' }]` |
| `scoreRow` | `null` (hides scoring breakdown) |
| `onClose` | Clear `drawerTicker` and remove `?ticker=` from URL |
| `onOpenInChart` | Navigate to `/markov/chart/:ticker` |
| `onExportToLab` | Navigate to `/quantgen/build?tickers=:ticker&from_date=:date` |

The drawer includes:
- Header with ticker name, company, sector
- Candlestick chart with volume histogram (auto-rendered by `CandleStickChart`)
- Toggleable indicator chips (EMA20, EMA50, plus any added via full-page chart)
- Expand/shrink button for chart size
- "Open in chart" button → full-page chart view
- Ticker metadata panel (company info, sector, market cap, etc.)
- "Export to Lab" button → QuantGen builder

### 4. Full-Page Chart View (`/markov/chart/:ticker`)

**New route** renders a thin `MarkovChartView` wrapper around the existing `ChartView` component.

**`MarkovChartView.tsx`** (new file):
- Renders `ChartView` with Markov-specific props
- Back button label: "Back to Markov Chain Trader"
- Referrer: `/markov` (for the Layout's back-navigation)

**`ChartView.tsx` refactor:**
- Make back-button label and referrer configurable via props
- Default values remain "Back to Custom Screener" and `/screener/build` for backward compatibility

The full-page chart includes:
- Indicator picker with ~30 indicators (searchable, filterable by category)
- Per-indicator parameter tuning (window, signal, etc.)
- Overlays list with toggle (eye/eye-off) and delete (X) buttons
- Date range bar (1y/2y/3y/5y/max/custom)
- Metadata rail (left side)
- Multiple param combos for the same indicator

### 5. Files to Modify

| File | Change |
|------|--------|
| `frontend/src/pages/Markov/index.tsx` | Add `drawerTicker` state, URL params sync, sessionStorage restore/write, render `TickerDetailDrawer` |
| `frontend/src/pages/Markov/components/SignalsTable.tsx` | Add `onTickerClick` prop, clickable rows with hover effects |
| `frontend/src/pages/Markov/components/ControlPanel.tsx` | Accept initial values from URL params for pre-fill |
| `frontend/src/pages/Markov/MarkovChartView.tsx` | **New** — thin wrapper around ChartView |
| `frontend/src/App.tsx` | Add route `/markov/chart/:ticker` |
| `frontend/src/pages/app/ScreenerBuilder/ChartView.tsx` | Minor refactor: configurable back-button label and referrer |

### 6. No Backend Changes

The existing endpoints serve all needed data:
- `GET /api/screener/chart-data/{ticker}?indicators=ema_20,ema_50&days=250` → OHLCV + EMA20/EMA50 values
- `GET /api/screener/ticker/{ticker}` → company metadata
- `GET /api/indicators/catalog` → full indicator catalog for the picker

## Verification

1. Run a Markov scan → verify results table appears with clickable rows
2. Click a row → verify right-side drawer opens with candlestick chart + volume + EMA20/EMA50 overlays
3. Toggle EMA20/EMA50 chips → verify overlays appear/disappear on chart
4. Click "Open in chart" → verify full-page chart at `/markov/chart/:ticker` with full indicator picker
5. Add a new indicator in the full-page chart → verify it renders
6. Navigate to home and back → verify scan results and drawer state are restored
7. Click "Export to Lab" → verify opens QuantGen builder with the ticker pre-filled
8. Refresh the page → verify scan config is preserved in URL params (results may be lost — acceptable)
