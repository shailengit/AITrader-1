# Screener / Scanner Pre-Aggregation Layer — Design Spec

**Date:** 2026-06-27
**Status:** Shelved / back-burner
**Owner:** TradeCraft backend
**Related:** `backend/app/services/agno_screener.py`, `backend/app/routers/sectors.py`, `backend/app/services/data_service.py`

> **Status note (2026-06-27):** The user asked to shelve this work for now. No code changes are planned against this spec. It is kept on disk as a reference for the "80% benefit, 20% risk" approach — a much smaller, evidence-based refactor than what was originally drafted. The original three-router fan-out (screener + sector scanner + top-20) with worker signature changes was deemed too aggressive. The reduced form below is what would actually be done if/when this is picked back up. **Do not start work on this without first running the profiling step in [Pre-flight: profile before optimizing](#pre-flight-profile-before-optimizing).**

## Context

TradeCraft's screener (`backend/app/services/agno_screener.py`) and sector scanner (`backend/app/routers/sectors.py`) both pay the same per-ticker tax on every scan. A user asked whether postgres MCP / CLI tools would help; after exploration we concluded they cannot accelerate the runtime hot path (TA indicators run in pandas in workers, not as interactive LLM queries). The real win is a backend refactor.

The original brainstorm produced an aggressive plan: a single wide-CTE query per scan, plus a worker signature change in `agno_screener._worker_ta_analysis`, plus a refactor of all three sector scanner entry points. On review, that approach is **too much moving parts in one change** for unverified gains. It optimizes a presumed bottleneck ("~3,000+ raw SQL operations") that hasn't been measured. The TA math itself (pandas-ta) is untouched, so if pandas-ta is the actual bottleneck, none of this helps.

This spec documents a much smaller alternative: **start with the cheapest, highest-confidence wins; gate everything else on real measurements.**

## The 80/20 plan

Three changes, in this order. **Each step is independent and shippable on its own.** Stop after any step if the next isn't justified by data.

1. **Step 1 — Shared connection pool for screener workers.** The current code creates a new SQLAlchemy engine with `QueuePool(pool_size=1)` per worker invocation. Fix that to reuse a single shared pool. Five-line change, no new SQL, no new test surface beyond "scan still works." If the bottleneck is connection setup, this alone may be the whole win.
2. **Step 2 — `fetch_windowed_ohlcv_batch` for the sector scanner only.** A new utility in `data_service.py` that issues one SQL round-trip per scan, returning the windowed primitives the sector scanner needs. Refactor `get_sector_stocks` and `_get_stock_full_metrics_sync` to use it. **Do not touch the screener.** This keeps the highest-stakes code path (`agno_screener._worker_ta_analysis`) unchanged.
3. **Step 3 — Measurement only.** Add a small `bench/` script that times the screener and sector scanner before and after Step 2. If the gain is < 2×, **stop**. The pre-aggregation complexity is not justified by < 2×.

The original spec's wider scope (worker signature change, screener refactor, top-20 two-pass collapse) is **explicitly not in this version** and should be reconsidered only if a future profile shows it is needed.

## Pre-flight: profile before optimizing

**Required before Step 1.** We currently have no baseline. Without it, "this is faster" is a feeling, not a measurement.

Add temporary timing logs (or a one-shot script) to capture:

- Wall-clock for a full S&P 1500 screener scan (one sample run)
- Wall-clock for `/api/stocks/XLK` and `/api/top-momentum-leaders`
- SQLAlchemy event listener counting `engine.connect()` and query executions per scan
- Time spent in `_worker_ta_analysis` per ticker (process spawn + setup + ta math)

If the screener scan completes in < 10s and the sector scanner in < 2s, **the whole spec is unnecessary** — work on something else.

## Step 1 — Shared connection pool

**Goal:** Remove per-worker engine spin-up cost.

**File:** `backend/app/services/agno_screener.py`

**Current behaviour** (in `_worker_ta_analysis` or wherever the engine is created per-worker): `create_engine(DB_URL, poolclass=QueuePool, pool_size=1)`.

**Proposed change:** Import a shared engine from `app.db.database` (which already exists, used by the rest of the backend). Delete the per-worker `create_engine` call. That's it.

**Why this works:** `QueuePool` already supports concurrent connections across processes when the URL points to the same DB. The `pool_size=1` per worker is artificial; the real issue (if any) is that the engine is being *created* per task rather than *reused* per process.

**Risk:** Very low. SQLAlchemy engines are designed to be long-lived. The only failure mode is if there's hidden global state in the existing engine — quick to check by running the existing test suite.

**Verification:**

- Run the existing screener tests.
- Run one screener scan; confirm it still returns the same ticker set with the same numbers.
- If we have timing logs from the pre-flight step, compare wall-clock.

## Step 2 — `fetch_windowed_ohlcv_batch` (sector scanner only)

**Goal:** Replace the 5–7 per-ticker `engine.connect()` blocks in the sector scanner with a single SQL round-trip per scan.

### Constraints

- **No schema change.** Pure Python-side refactor.
- **No API change.** Response shape of `/api/stocks/{sector}` and `/api/top-momentum-leaders` is byte-identical.
- **Screener is out of scope.** This PR does not touch `agno_screener.py`.
- **Preserve mock-data fallbacks.** Existing branches that return mock data when the DB is unavailable stay in place.

### What this is

A single new function in `backend/app/services/data_service.py`:

```python
def fetch_windowed_ohlcv_batch(
    tickers: List[str],
    cutoff_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """One SQL round-trip returning one row per ticker with windowed OHLCV primitives.

    Returns a list of dicts (one per ticker, in input order via ORDINALITY).
    Missing-table tickers return a row with NULL columns — no exception raised.
    """
```

It uses `unnest($1::text[]) WITH ORDINALITY` plus `LATERAL` joins to a per-ticker table query, returning columns the sector scanner already needs:

```
latest_date, latest_close, latest_volume,
ref_date, ref_close, ref_volume,
sma_20, sd_20, sma_50, sma_200,
high_10d, avg_vol_20d,
close_3m_ago, close_6m_ago,
sector, name
```

### Why LATERAL + format() on table names is acceptable here

The ticker table names are inlined via `format()` **after** `get_safe_table_name()` validates them. Every other value (`cutoff_date`, the ticker array itself) goes through SQLAlchemy bound parameters via `text()`. This matches the existing pattern in `sectors.py` (e.g., `get_ticker_performance`) and reuses the same sanitizer gate against SQL injection. It is not a new pattern; it is the existing one consolidated into one query.

### Missing-table tolerance

`LEFT JOIN ... ON TRUE` semantics for each per-ticker lookup. If a ticker's table doesn't exist (delisted ticker), its row returns with NULL columns. The downstream code already tolerates NULL/short data — no exceptions raised.

### What changes in `sectors.py`

**Refactor these two functions:**

- `get_sector_stocks` — replace per-stock loops with one `fetch_windowed_ohlcv_batch` call.
- `_get_stock_full_metrics_sync` — same treatment in the top-20 second pass.

**Do not refactor:** `_get_stock_perf_summary_sync` (the top-20 lightweight first pass) **unless** the two-pass structure can be collapsed without risk. If it can, the win is real (one round-trip per scan instead of two). If it can't, leave it alone.

The two-pass collapse is the only design call worth a second look. Default is "do it, it's strictly better"; revisit if tests fail.

### What does NOT change

- `_worker_ta_analysis` — untouched. Worker signature stays exactly as it is today.
- Screener response shape — untouched.
- The top-20 lightweight first pass — untouched (unless two-pass collapse is safe; see above).
- `get_forward_return`, `get_buy_and_hold_since`, `get_ticker_performance` — untouched. These are short-window targeted queries; the pre-aggregation layer doesn't help them.

### Forward return and hold-since are still separate

The pre-aggregation is for windowed primitives (sma_20, sd_20, close_3m_ago, etc.). `get_forward_return` and `get_buy_and_hold_since` remain targeted per-stock queries because they need very specific date windows (e.g., close on `ref_date + 30d`). Trying to fold them into the same CTE complicates the SQL for marginal gain.

## Step 3 — Measure

After Step 2 lands:

- Re-run the timing logs from the pre-flight step.
- Compare sector scanner wall-clock and SQLAlchemy event counts.
- **If improvement is < 2×:** document the result in this spec file under a "Results" section, declare done, and move on.
- **If improvement is ≥ 2×:** the approach is validated. The screener refactor (original spec, Section 5 of the first draft) is now evidence-justified and can be considered for a separate PR.

## What this spec is NOT

To be explicit about what is **out of scope** for this reduced plan:

- **Screener refactor.** `agno_screener._worker_ta_analysis` and the ProcessPoolExecutor fan-out are unchanged. The original spec proposed changing the worker signature to take a pre-aggregated row; that change is not in this version.
- **Top-20 two-pass collapse.** Only attempted if it can be done without touching the lightweight pass's return contract.
- **Precomputed `daily_indicators` table** populated by cron or trigger. Bigger, longer spec — separate effort if ever needed.
- **Async SQLAlchemy (asyncpg)** across FastAPI handlers. Separate effort.
- **Pushing TA indicators into SQL window functions.** Would require rewriting ~30 indicators as window functions and maintaining them in two places.
- **Markov and QuantGen refactor.** They have similar patterns but are not called from the screener/scanner; separate effort if ever needed.

## Testing

### Step 1

- Existing screener tests pass.
- One manual screener scan returns the same ticker set + numbers as before.

### Step 2

- New `backend/tests/services/test_preagg.py` (~50 lines):
  - Empty ticker list returns `[]`.
  - Single ticker returns correct row with all 17+ columns populated.
  - Invalid ticker (sanitizer-rejected) raises `ValueError`.
  - Missing table for a delisted ticker → row with NULL columns (no exception).
  - Cutoff date honored: `ref_*` columns point to closest trading day on or before cutoff.
  - Result order matches input order (ORDINALITY preserved).
- Existing `backend/tests/test_sectors.py` shape assertions continue to pass — response shape doesn't change, only the internals.

### Step 3

- Manual `bench/` script captures before/after wall-clock and SQLAlchemy event counts. Documented in this spec's "Results" section.

## Backward compatibility

- No API shape change (screener or sector scanner).
- No schema change.
- Step 1 is a single-line import swap in `agno_screener.py`.
- Step 2 changes internals only; response shape preserved.
- Roll-back: revert the commit.

## Critical files

- `backend/app/services/agno_screener.py` — Step 1: swap per-worker engine for shared engine.
- `backend/app/services/data_service.py` — Step 2: add `fetch_windowed_ohlcv_batch`.
- `backend/app/routers/sectors.py` — Step 2: refactor `get_sector_stocks` and `_get_stock_full_metrics_sync`.
- `backend/tests/services/test_preagg.py` — Step 2: new test file.
- `backend/tests/test_sectors.py` — confirm existing shape assertions still pass.
- `bench/screener_timing.py` (new) — Step 3: timing script.

## Verification

1. **Pre-flight (required):** Add timing logs / run a one-shot timing script. Capture wall-clock for screener scan, sector scan, top-20. If screener < 10s and sector < 2s, stop and delete this spec.
2. **Step 1:**
   - Restart backend; run screener tests.
   - Time one scan before and after; record the delta.
3. **Step 2:**
   - Restart backend; run `pytest tests/ -q`.
   - Run new `test_preagg.py`; all pass.
   - Time one `/api/stocks/XLK` and one `/api/top-momentum-leaders` before and after; record the delta.
   - SQLAlchemy event listener log shows fewer round-trips.
4. **Step 3:** Write the timing results into a "Results" section in this file. If < 2× gain, declare done. If ≥ 2×, the approach is validated and the screener can be considered in a future PR.

## Implementation plan

When this is picked up, the writing-plans skill will produce a task-by-task plan with dependencies. The plan should respect the three-step ordering: each step lands on its own commit, with tests + measurement, before the next step starts.