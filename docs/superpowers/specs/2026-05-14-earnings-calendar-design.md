# Design: Earnings Calendar & AI Screener Integration

**Date:** 2026-05-14
**Status:** Draft

## Context

TradeCraft currently has no visibility into upcoming earnings dates. The PostgreSQL database contains historical OHLCV, metadata, and quarterly/yearly financials, but no earnings calendar or corporate events data. The AI Screener evaluates technical and fundamental signals but cannot account for earnings as a catalyst or risk factor. This feature adds earnings calendar awareness to the platform, starting with earnings announcements and leaving room for dividends, splits, and macro events.

## Goals

1. Provide a browsable **Earnings Calendar** page showing upcoming earnings dates with EPS estimates and times.
2. Enrich the **AI Screener** with `days_until_next_earnings` as a signal/filter.
3. Cache earnings data locally for fast screener queries, using Finnhub as the primary source.
4. Keep the architecture extensible for dividends, splits, and macro events later.

## Non-Goals

- Real-time earnings alerts (push notifications, websockets) — out of scope for this pass.
- Historical earnings backtesting engine — we store history, but deep analysis is future work.
- International stock coverage beyond what Finnhub free tier supports.

## Architecture

```
Finnhub API (free tier)
    |
    v
backend/app/services/earnings_sync.py  -- bulk sync job
    |
    v
PostgreSQL: earnings_calendar table
    |
    +---> backend/app/services/earnings_service.py  -- query helpers
    |           |
    |           +---> backend/app/routers/earnings.py  -- API endpoints
    |                   |
    |                   +---> frontend/src/pages/EarningsCalendar.tsx
    |
    +---> backend/app/services/agno_screener.py  -- enrich scan results
            |
            +---> frontend/src/pages/StockScreener.tsx  -- new column + filter
```

## Database Schema

### New Table: `earnings_calendar`

| Column           | Type         | Notes                                      |
|------------------|--------------|--------------------------------------------|
| ticker           | VARCHAR(10)  | Primary key part                           |
| report_date      | DATE         | Primary key part                           |
| fiscal_year      | INT          | Optional                                   |
| fiscal_quarter   | INT          | Q1=1, Q2=2, etc.                           |
| eps_estimate     | NUMERIC      | Analyst consensus EPS estimate             |
| revenue_estimate | NUMERIC      | Analyst consensus revenue estimate         |
| eps_actual       | NUMERIC      | Filled after report                        |
| revenue_actual   | NUMERIC      | Filled after report                        |
| time_of_day      | VARCHAR(10)  | `bmo` (before market open), `amc` (after), `dmh` (during), `tns` (time not supplied) |
| source           | VARCHAR(20)  | `finnhub`, `yfinance`                      |
| updated_at       | TIMESTAMP    | Auto-updated                               |

**Constraints:**
- `PRIMARY KEY (ticker, report_date)`
- `INDEX idx_report_date` for fast calendar queries
- `INDEX idx_ticker` for fast per-stock lookups

**Migration:** Add via Alembic or raw SQL in a new migration file. For this project (no Alembic yet), provide a SQL snippet in the backend startup or a manual migration file.

## Backend

### New Service: `backend/app/services/earnings_sync.py`

Responsible for syncing earnings data from Finnhub into the local database.

**Function: `sync_earnings_calendar(start_date: str, end_date: str)`**
- Calls Finnhub `earningsCalendar` bulk endpoint for the date range.
- Upserts results into `earnings_calendar` table (ON CONFLICT (ticker, report_date) DO UPDATE).
- Logs progress and counts.
- Returns a summary dict: `{"inserted": N, "updated": M, "failed": P}`.

**Function: `sync_tickers(tickers: List[str])`**
- Uses yfinance as fallback for individual tickers missing from the cache.
- Called on-demand when a specific ticker is requested and not found in the cache.

**Configuration:**
- `FINNHUB_API_KEY` environment variable (required for sync).
- Sync schedule: daily at market close (can be triggered manually or via cron).

### New Service: `backend/app/services/earnings_service.py`

Query helpers for the rest of the backend.

**Function: `get_next_earnings(ticker: str) -> Optional[Dict]`**
- Returns the single next upcoming earnings row for a ticker.
- Computes `days_until = (report_date - today).days`.

**Function: `get_earnings_window(days: int = 7, tickers: Optional[List[str]] = None) -> List[Dict]`**
- Returns all earnings in the next N days, optionally filtered to a ticker list.
- Used by the calendar page and the screener batch enrichment.

**Function: `enrich_scan_results(results: List[Dict]) -> List[Dict]`**
- Takes a list of screener result dicts (each has a `ticker`).
- Batches a query to get `days_until_next_earnings` for all tickers.
- Mutates each result dict in-place to add `next_earnings_date` and `days_until_earnings` fields.

### New Router: `backend/app/routers/earnings.py`

FastAPI endpoints.

**`GET /api/earnings/calendar`**
- Query params: `from` (date), `to` (date), `tickers` (comma-separated, optional).
- Returns a list of earnings events matching the range.

**`GET /api/earnings/next/{ticker}`**
- Returns the next earnings event for a single ticker.

**`POST /api/earnings/sync`**
- Admin/manual endpoint to trigger a sync for a date range.
- Body: `{ "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }`.

### Screener Integration

Both `run_dormant_giant_screener` and `run_quant_strategy_screener` in `backend/app/services/agno_screener.py` will:
1. After computing the initial scan results, call `earnings_service.enrich_scan_results(results)`.
2. Add `days_until_earnings` to the `ScanResult` Pydantic model in `backend/app/routers/screener.py`.
3. The AI screener prompt will be updated to mention that `days_until_earnings` is available as a signal (if `use_ai=True`).

### Existing File Modifications

- `backend/app/routers/screener.py`: Add `days_until_earnings` to `ScanResult` model.
- `backend/app/services/agno_screener.py`: Call `earnings_service.enrich_scan_results()` after generating results.
- `backend/app/main.py`: Register the new `earnings` router.

## Frontend

### New Page: `frontend/src/pages/EarningsCalendar.tsx`

A weekly/monthly calendar view of upcoming earnings.

**Layout:**
- Header: Date range picker (default: today to today+14 days), sector filter.
- Grid: A horizontal date strip. Each date cell shows a list of tickers reporting that day.
- Ticker card: Ticker, company name (from metadata), time of day badge (BMO/AMC), EPS estimate (if available), revenue estimate.
- Clicking a ticker opens the existing CandleStickChart modal with an earnings annotation line on the chart.

**Data:**
- Fetches from `GET /api/earnings/calendar`.

### Screener Enhancements

**`frontend/src/pages/StockScreener.tsx`:**
- Add `days_until_earnings` and `next_earnings_date` to the `ScanResult` interface.
- New column in the results table: "Next Earnings" — shows "Tomorrow", "3 days", "2 weeks", or the date.
- New optional filter in the filter panel: "Earnings within N days" (number input, default off).

### New Components

- `frontend/src/components/earnings/EarningsDayCard.tsx` — a single day cell in the calendar.
- `frontend/src/components/earnings/EarningsTickerRow.tsx` — a single ticker row inside a day card.

### Existing File Modifications

- `frontend/src/App.tsx`: Add `/earnings` route and sidebar nav item.
- `frontend/src/components/layout/Layout.tsx`: Add "Earnings Calendar" to the sidebar.

## Data Flow

1. **Sync:** A background sync job (or manual trigger) calls Finnhub for a date range and upserts into `earnings_calendar`.
2. **Screener Run:** When a scan is triggered, the backend queries `earnings_calendar` for all result tickers, computes `days_until`, and appends to each result.
3. **Calendar View:** The frontend fetches the calendar range from the backend, which reads from the local cache table.
4. **Fallback:** If a ticker is missing from the cache, `earnings_sync.sync_tickers([ticker])` is called on-demand using yfinance.

## Error Handling

- **Finnhub API failure:** Log error, skip sync, return 503 on manual trigger. The screener continues with whatever cached data exists.
- **Missing `FINNHUB_API_KEY`:** Log a clear warning at startup. The sync endpoint returns 400. The screener falls back to yfinance for individual lookups.
- **yfinance fallback failure:** If both sources fail, `days_until_earnings` is omitted from the result (not a fatal error).

## Testing Plan

1. **Backend:**
   - Unit test `earnings_service.get_next_earnings` with mocked DB rows.
   - Unit test `earnings_sync.sync_earnings_calendar` with mocked Finnhub response.
   - Integration test: Run a screener scan and verify `days_until_earnings` appears in results for tickers with cached data.

2. **Frontend:**
   - Verify the Earnings Calendar page loads and displays data.
   - Verify the Screener results table shows the new column.
   - Verify the filter panel has the new "Earnings within N days" control.

3. **End-to-End:**
   - Trigger a manual sync for a past date range (e.g., last week) to verify the sync endpoint.
   - Run a screener scan and confirm earnings data is present.
   - Open the Earnings Calendar and click a ticker to open the chart modal.

## Rollout Plan

1. Add `earnings_calendar` table and `earnings_sync.py` / `earnings_service.py`.
2. Add `/api/earnings/*` endpoints.
3. Integrate into the screener (backend + frontend column/filter).
4. Build the `EarningsCalendar` page and route.
5. Trigger initial backfill sync for the next 90 days.
6. (Future) Add dividends and splits to the same table with a `type` column, or a separate table.

## Open Questions / Future Work

- Should we store historical earnings for trend analysis (e.g., "beats 80% of the time")? Not for this pass.
- Should the screener have a *negative* filter ("exclude stocks reporting within 3 days")? Yes, the filter can be generalized to "within N days" where N=0 means "no earnings soon."
- Macro events (CPI, Fed) will need a separate table and likely a different data source (e.g., tradingeconomics.com or a macro API).
