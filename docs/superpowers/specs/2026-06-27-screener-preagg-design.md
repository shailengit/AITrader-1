# Screener / Scanner Pre-Aggregation Layer — Design Spec

**Date:** 2026-06-27
**Status:** Brainstorming → Spec (draft)
**Owner:** TradeCraft backend
**Related:** `backend/app/services/agno_screener.py`, `backend/app/routers/sectors.py`, `backend/app/services/data_service.py`

## Context

TradeCraft's screener (`backend/app/services/agno_screener.py`) and sector scanner (`backend/app/routers/sectors.py`) both pay the same per-ticker tax on every scan. The user asked whether postgres MCP / CLI tools would help; after exploration we concluded they cannot accelerate the runtime hot path (TA indicators run in pandas in workers, not as interactive LLM queries). The real win is a backend refactor: stop doing per-ticker SQL round-trips and per-worker engine spin-ups, and replace them with a single pre-aggregation query per scan.

### Current behaviour

**Screener** (`_worker_ta_analysis` in `backend/app/services/agno_screener.py`):
- Each worker process opens its own SQLAlchemy engine + `QueuePool` (`create_engine(DB_URL, poolclass=QueuePool, pool_size=1)`) on every invocation.
- Fetches the last 250 rows of OHLCV via `pd.read_sql(... LIMIT 250)`.
- Calls `add_all_ta_features` (the `ta` library) — 30+ indicators computed in pandas.
- Re-computes `sma_20`, `ema_9`, `high_52w`, `low_52w`, `volume_ma_50`, `volume_ratio`, `all_time_high`, `all_time_low`, `ath_proximity` per worker.
- Runs in `ProcessPoolExecutor(max_workers=os.cpu_count())` — 8-10 worker processes per scan.

**Sector scanner** (`get_sector_stocks` and `_get_stock_full_metrics_sync` in `backend/app/routers/sectors.py`):
- For each stock in the sector (capped at 50), runs ~5-7 separate `with engine.connect()` blocks.
- Top-20 momentum leaders uses a two-pass: lightweight summary → top-20 → full metrics. The full-metrics pass re-fetches data the lightweight pass already touched.

### Why it matters

A full S&P 1500 scan touches **~3,000+ raw SQL operations** per scan, **~1,500 engine spin-ups**, and **duplicate Bollinger/SMA/SD math** across the screener and sector scanner. The screener in particular can't be cached aggressively because users pick arbitrary cutoffs and indicator parameters.

## Approach

Introduce a single pre-aggregation query that, per scan, returns every requested ticker in one row carrying all the **windowed OHLCV primitives** the downstream code needs. pandas-ta still runs in Python on the 250-row window per ticker (that's the math layer we keep), but **all raw OHLCV fetching, window selection, and lookback math moves to one SQL round-trip per scan**.

### Constraints

- **TA indicators stay in Python.** `pandas-ta` / `ta` already does this efficiently on per-series data. Pushing 30+ indicators into SQL window functions is a separate, larger effort and out of scope.
- **No schema change.** Pure Python-side refactor; no migrations, no new tables, no cron jobs.
- **No API change.** Response shape of `/api/screener/scan`, `/api/stocks/{sector}`, `/api/top-momentum-leaders` is byte-identical.
- **Preserve mock-data fallbacks.** Existing branches that return mock data when the DB is unavailable stay in place.

## Architecture

Three layers, each with a single responsibility:

### 1. `app/services/data_service.py:fetch_windowed_ohlcv_batch(tickers, cutoff_date)` (new function)

- Takes a list of tickers + optional cutoff date.
- Issues **one SQL query** using `unnest($1::text[])` with a CTE that returns one row per ticker containing every windowed primitive the screener/scanner need.
- Returns a list of dicts (one per ticker) that downstream code consumes directly.
- Reuses the existing engine from `app/db/database.py` (no new pool).
- Per-ticker table sanitization via existing `get_safe_table_name()`.

### 2. `app/services/agno_screener.py:_worker_ta_analysis` (refactor)

- Stop opening its own engine per worker.
- Accept the pre-aggregated row dict as input.
- Keep `add_all_ta_features` and `custom_ema_pct_change` as-is (the 30-indicator pandas compute we explicitly preserve).
- Stop computing `sma_20`, `high_52w`, `avg_vol_50`, `ath`, `atl` separately — these come from the pre-aggregated row.
- Keep the 250-row `pd.read_sql` for the TA math, **but reuse the shared engine** instead of spinning up a new one.

### 3. `backend/app/routers/sectors.py:_get_stock_full_metrics_sync` and `get_sector_stocks` (refactor)

- Replace the 5-7 per-ticker `engine.connect()` blocks with one call to `fetch_windowed_ohlcv_batch`.
- Top-20's two-pass structure collapses into one pass — the lightweight summary and full-metrics queries become the same call.

## SQL CTE shape (concrete)

One query, one row per ticker, with these columns:

```
latest_date          DATE        — most recent trading day on or before cutoff
latest_close         NUMERIC     — close on latest_date
latest_volume        BIGINT      — volume on latest_date
ref_date             DATE        — actual anchor used (may differ from cutoff if no trading day on cutoff)
ref_close            NUMERIC     — close on ref_date (= latest when cutoff is null)
ref_volume           BIGINT      — volume on ref_date
sma_20               NUMERIC     — 20-day SMA of close ending on ref_date
sd_20                NUMERIC     — 20-day sample stdev of close (for Bollinger)
sma_50               NUMERIC     — 50-day SMA of close ending on ref_date
sma_200              NUMERIC     — 200-day SMA of close ending on ref_date (NULL if insufficient history)
high_10d             NUMERIC     — max("High") over the 10 days ending on ref_date
avg_vol_20d          NUMERIC     — avg("Volume") over the 20 days ending on ref_date
close_3m_ago         NUMERIC     — close on the closest trading day ~90 days before ref_date
close_6m_ago         NUMERIC     — close on the closest trading day ~180 days before ref_date
sector               TEXT        — from stock_metadata
name                 TEXT        — from stock_metadata
```

### Two design points worth flagging

- **`unnest($1::text[]) WITH ORDINALITY`** preserves caller-supplied order, so response rows match input list order — important for the two-pass screener that pairs summary rows with full-metrics rows.
- **`LATERAL` joins** let us dynamically reference the per-row ticker table. The function builds one parameterized SQL string per call: the ticker table names are inlined via `format()` after `get_safe_table_name()` validates them, and every other value (`cutoff_date`, the ticker array itself) goes through SQLAlchemy bound parameters via `text()`. This matches the existing pattern in `sectors.py` (e.g., `get_ticker_performance`) and reuses the same sanitizer gate against SQL injection.

### Missing-table tolerance

`fetch_windowed_ohlcv_batch` uses `LEFT JOIN ... ON TRUE` semantics for each per-ticker lookup. If a ticker's table doesn't exist (delisted ticker), its row returns with NULL columns. The downstream `_worker_ta_analysis` already filters `df.empty or len(df) < 50`, so it gracefully drops them. No exceptions raised for missing tables.

## Worker refactor

`_worker_ta_analysis` signature becomes:

```python
def _worker_ta_analysis(
    ticker: str,
    preagg: Dict[str, Any],         # NEW: row from fetch_windowed_ohlcv_batch
    df: pd.DataFrame,               # EXISTING: 250-row OHLCV window for TA math
    requested_indicators: List[str],
    cutoff_date: Optional[str],
    custom_params: ...
) -> Optional[Dict]:
```

- Stop spawning a per-worker SQLAlchemy engine.
- Stop computing `sma_20`, `high_52w`, `avg_vol_50`, `ath`, `atl` separately.
- Keep `add_all_ta_features` and `custom_ema_pct_change` as-is.
- Reuse the shared engine from `data_service.py` for the 250-row pandas-ta fetch (passed in or imported as a module-level singleton).

**Net win per scan:**
- ~1,500 fewer engine spin-ups + disposals.
- ~1,500 × ~6 fewer DB round-trips.
- No duplicate SMA/SD/avg-volume math.

## Data flow

### Screener

```
POST /api/screener/scan
  └─ agno_screener.technical_screener()
       ├─ 1) fetch_windowed_ohlcv_batch(all_tickers, cutoff_date)         ← NEW: 1 SQL query
       │       → [{ticker, latest_close, sma_20, sd_20, ref_close, ...}, ...]
       │
       ├─ 2) ProcessPoolExecutor distributes per-ticker TA compute        ← unchanged math layer
       │       └─ _worker_ta_analysis(preagg_row, df_250, ...)
       │
       └─ 3) Merge + score (compute_filter_match_bonus, base_setup_breakdown)
              → results (unchanged shape)
```

### Sector scanner

```
GET /api/stocks/XLK
  └─ get_sector_stocks()
       ├─ 1) fetch_windowed_ohlcv_batch(sector_tickers, cutoff_date)      ← NEW: 1 SQL query
       │
       ├─ 2) For each stock: derive Bollinger from CTE's sma_20/sd_20     ← no second query
       │   (outperformance check uses CTE's perf_3m columns directly)
       │
       └─ 3) For stocks that pass filter: forward_return + hold_since_as_of
              (these still need targeted SQL — short windows, optional follow-up)
```

### Top-20 momentum leaders

```
GET /api/top-momentum-leaders
  └─ get_top_momentum_leaders()
       ├─ 1) fetch_windowed_ohlcv_batch(all_tickers, cutoff_date)        ← NEW: 1 SQL query
       │
       ├─ 2) Sort by perf_3m desc, take top 20                            ← in-memory
       │
       └─ 3) For each top-20: forward_return + hold_since_as_of
              (these still need targeted SQL — single-stock queries)
```

The two-pass structure collapses because the lightweight summary and full-metrics queries become the same call.

## Error handling

- **Empty ticker list:** `fetch_windowed_ohlcv_batch` returns `[]`.
- **Invalid ticker:** existing `get_safe_table_name()` raises `ValueError` for malformed tickers — propagated to caller.
- **Missing table for a ticker (delisted):** row with NULL columns returned; no exception raised.
- **Database unavailable:** all callers fall back to mock-data branches that already exist in `screener.py` and `sectors.py`.
- **Cutoff date is None:** CTE falls back to "latest available close" for both `latest_*` and `ref_*` columns; downstream code already tolerates this.
- **Worker crash mid-scan:** existing `ProcessPoolExecutor` already swallows per-task exceptions and returns None for that ticker.

## Testing

### New unit tests (`backend/tests/services/test_preagg.py`)

- Empty ticker list returns `[]`.
- Single ticker returns correct row with all 17+ columns populated.
- Invalid ticker (sanitizer-rejected) raises `ValueError`.
- Missing table for a delisted ticker → row with NULL columns (no exception).
- Cutoff date honored: ref_* columns point to closest trading day on or before cutoff.
- Result order matches input order (ORDINALITY preserved).

### Existing tests

- `backend/tests/test_sectors.py` shape assertions continue to pass — response shape doesn't change, only the internals.
- Existing screener tests (if any) continue to pass for the same reason.

### Optional manual performance regression

Time a screener scan against the 1,500-ticker universe before and after; target:
- **≥ 4× wall-clock improvement** on the same hardware.
- **≥ 80% reduction in DB round-trips** (measured via SQLAlchemy event listener).

This is a manual check, not a CI gate — included as a way to validate the refactor landed the intended win.

## Backward compatibility

- No API shape change.
- No schema change.
- Pure Python-side refactor; deployable as a normal commit.
- Roll-back: revert the PR.
- Existing cache (`backend/app/services/cache.py`) untouched — pre-aggregation is orthogonal to caching.

## Out of scope (called out for honesty)

- **Precomputed `daily_indicators` table** populated by cron or trigger. Bigger, longer spec — separate effort.
- **Async SQLAlchemy (asyncpg)** across FastAPI handlers. Separate effort.
- **Pushing TA indicators into SQL window functions.** Would require rewriting ~30 indicators as window functions and maintaining them in two places.
- **Markov and QuantGen optimizer refactor.** They have similar patterns but are not called from screener/scanner; separate effort if you want them.

## Critical files

- `backend/app/services/data_service.py` — add `fetch_windowed_ohlcv_batch`.
- `backend/app/services/agno_screener.py` — refactor `_worker_ta_analysis`, update call site in `technical_screener`.
- `backend/app/routers/sectors.py` — refactor `get_sector_stocks` and `_get_stock_full_metrics_sync`; collapse top-20 two-pass.
- `backend/tests/services/test_preagg.py` — new test file (~50 lines).
- `backend/tests/test_sectors.py` — confirm existing shape assertions still pass.

## Verification

1. Restart backend (`cd backend && ./venv/bin/python -m app.main`).
2. Run `cd backend && ./venv/bin/python -m pytest tests/ -q` — all existing tests pass.
3. Run new `backend/tests/services/test_preagg.py` — all pass.
4. Time a full screener scan (manually trigger via the frontend or `curl POST /api/screener/scan` with a saved screen). Compare to baseline. Target ≥ 4× improvement.
5. Trigger `/api/stocks/XLK` and `/api/top-momentum-leaders` — response shapes unchanged; latencies improved.
6. SQLAlchemy event listener log shows ~80% fewer queries per scan.

## Implementation plan

This spec will be handed to the writing-plans skill to produce a detailed implementation plan with task breakdowns and dependencies.