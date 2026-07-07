# 2026-07-06 — Trade Coach Agent (Approach A: Journal + On-Demand Critique)

> **Status:** Approved by user 2026-07-06. Implementation plan: `docs/superpowers/plans/2026-07-06-trade-coach-agent.md`.
> **Scope:** A new "Coach" tab in TradeCraft, a new trade-journal persistence layer, a deterministic analytics module over the journal, and an LLM-driven on-demand critique engine. Paper-trading only. Single user.
> **Out of scope:** Broker integration, auto-trading, live critique hooks on every screen run, auto-generating new strategies, multi-user/auth, real-time alerts, news/sentiment ingestion, ML on trade history.

---

## 1. Context

### 1.1 Problem

TradeCraft has accumulated a powerful, opinionated set of tools — sector rotation scanning, AI screener (Dormant Giant + Quant Strategy), QuantGen strategy builder with True WFO, Markov regime trader, earnings calendar, and an Alorse strategy catalog. But none of them **close the loop**:

- When the user runs a screen or WFO, the result is returned and **forgotten**. There's no persistent record of "what did the screener say on date X, for what tickers, with what parameters, in what regime".
- When the user takes a paper trade, it is **not recorded** anywhere in TradeCraft (no `journal_trade` table exists today).
- There is no concept of "what is working for me, in what regimes, with what win rate, with what drawdown." The user can answer "what did Golden Cross return last year?" via WFO, but cannot answer "what is my *win rate* on Golden Cross trades that *I* took?"
- The existing LLM (`kimi-k2.5:cloud` via Ollama, wired in `backend/app/services/llm_engine.py`) is used only to generate strategy code. It is **not** used to interpret the user's own trading history.

The user's stated goal is: "a trading agent that uses these tools but also learns from past performance and keeps getting better with time." The platform is mature enough to support that goal, but needs a journal + critique layer to do it.

### 1.2 Solution

Build a **Trade Coach Agent** that:

1. **Writes** every screen run, WFO result, Markov signal, and (manually-entered) paper trade into a structured trade-journal schema (new PostgreSQL tables, all names prefixed `journal_`).
2. **Computes** deterministic analytics over the journal — win rate, expectancy, P&L by regime, MAE/MFE distribution, entry-timing lag, strategy correlation, drawdown curve, regime attribution. No LLM. Pure SQL + pandas.
3. **Critiques** on demand: when the user clicks "Generate Report", the analytics bundle + recent journal entries are passed to the same local LLM the rest of the app uses, with a strict system prompt that forbids financial advice and forbids inventing numbers. A post-processor validates every number in the output against the input bundle. Retry once on failure.
4. **Displays** a Coach tab with: a metrics dashboard (KPIs + small charts), the latest report (markdown), a regenerate button, a date-range picker, and a list of past reports.

The agent is **read-only on the user's portfolio**. It does not place trades. It does not generate new strategies. It does not run continuously. Reports are generated **on demand only** (the user clicks "Regenerate"). A weekly cron is a follow-up — see Section 12. It is the foundation that future "live critique loop" (Approach B) and "auto strategy factory" (Approach C) features will sit on.

### 1.3 Decisions confirmed with the user

- Scope: **Approach A** (Journal + On-Demand Critique). Not B, not C.
- Trading reality: **paper only, for now**. The journal is the source of truth; broker integration is a separate future spec.
- Time horizon: **swing (days–weeks)**. Position sizing, MAE/MFE, regime attribution matter most. Intraday/minute-bar analysis is out of scope.
- Memory model: **PostgreSQL tables**, not JSON files, not vector embeddings. Real persistence, real queries.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  TradeCraft (existing)                                              │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │  Screener    │  │  QuantGen    │  │   Markov     │  │ Earnings │  │
│  │  (DG, QS)    │  │  (WFO, bt)   │  │  (regime)    │  │ Calendar │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────┬─────┘  │
│         │                 │                 │              │        │
│         │ existing routers return JSON      │              │        │
│         │                 │                 │              │        │
│         └─────────────────┴────────┬────────┴──────────────┘        │
│                                   │ post-run journal.record(...)   │
│                                   ▼                                  │
│                          ┌──────────────────┐                        │
│                          │  Trade Journal   │  ◀── NEW               │
│                          │  (PG tables)     │      journal_*          │
│                          └────────┬─────────┘                        │
│                                   │                                  │
│                          ┌────────┴─────────┐                        │
│                          │                  │                        │
│                          ▼                  ▼                        │
│                ┌──────────────────┐  ┌──────────────────┐            │
│                │   Coach          │  │   Coach          │            │
│                │   Analytics      │  │   LLM            │            │
│                │   (deterministic)│  │   (Ollama)       │            │
│                │   NO LLM         │  │   same model     │            │
│                │   SQL + pandas   │  │   as llm_engine  │            │
│                └────────┬─────────┘  └────────┬─────────┘            │
│                         │                     │                      │
│                         └──────────┬──────────┘                      │
│                                    ▼                                 │
│                          ┌──────────────────┐                        │
│                          │   Coach API      │  ◀── NEW router        │
│                          │   /api/coach/*   │                        │
│                          └────────┬─────────┘                        │
│                                   │                                  │
│                                   ▼                                  │
│                          ┌──────────────────┐                        │
│                          │  React Coach     │  ◀── NEW page          │
│                          │  Tab             │                        │
│                          └──────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 New files

```
backend/app/
  ├── services/coach/
  │   ├── __init__.py
  │   ├── journal.py           # write-side: record signals, trades, runs
  │   ├── analytics.py         # read-side: deterministic SQL/pandas queries
  │   ├── llm.py               # LLM critique: prompt + validate + retry
  │   ├── bundle.py            # builds the "data bundle" the LLM sees
  │   ├── prompts.py           # system + user prompt templates
  │   └── types.py             # Pydantic models for reports & metrics
  ├── routers/coach.py         # FastAPI endpoints
  ├── models/journal.py        # SQLAlchemy ORM models for journal_* tables
  └── db/migrations/003_trade_journal.py   # Alembic migration (new revision)

frontend/src/
  ├── pages/Coach/
  │   ├── index.tsx            # main Coach tab
  │   ├── KPICards.tsx
  │   ├── EquityCurve.tsx
  │   ├── RegimeAttribution.tsx
  │   ├── MAEvsMFE.tsx
  │   ├── WinRateByStrategy.tsx
  │   ├── ReportView.tsx
  │   ├── DateRangePicker.tsx
  │   ├── trades.tsx           # sub-route for the trade log
  │   ├── TradeTable.tsx
  │   ├── TradeForm.tsx
  │   └── CloseTradeDialog.tsx
  └── lib/
      └── coach.ts             # typed client for /api/coach/*

backend/tests/coach/
  ├── conftest.py
  └── test_analytics.py
```

### 2.2 Touched (existing) files

- `backend/app/routers/screener.py` — add `journal.record_strategy_run(...)` after each scan completes
- `backend/app/routers/quantgen.py` — same, after `/api/run`, `/api/optimize`, `/api/true-wfo`
- `backend/app/routers/markov.py` — same, after daily scan + retrain
- `backend/app/main.py` — register the `coach` router
- `backend/app/db/database.py` — expose `Base = declarative_base()` (if not already)
- `backend/app/models/__init__.py` — import the new `journal` module
- `backend/app/services/llm_engine.py` — export a `get_llm_client()` helper the coach can reuse (no duplication of retry/timeout logic)
- `frontend/src/App.tsx` — add `/coach` and `/coach/trades` routes
- `frontend/src/components/layout/Layout.tsx` — add "Coach" nav entry
- `frontend/package.json` — add `react-markdown` and `remark-gfm`

---

## 3. Trade Journal Schema

All tables in PostgreSQL, names prefixed `journal_`. Schema-only — no data backfill is required. Empty journals are explicitly supported and produce an empty-state UI.

### 3.1 `journal_strategy`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `kind` | text NOT NULL | enum: `screener`, `quantgen`, `markov`, `manual` |
| `name` | text NOT NULL | human label, e.g. "Golden Cross 50/200", "Markov Daily" |
| `params` | jsonb NOT NULL DEFAULT '{}' | strategy parameters (sma windows, etc.) |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |
| `retired_at` | timestamptz NULL | set when user explicitly retires a strategy |
| `notes` | text NULL | free-form |
| UNIQUE | `(kind, name)` | upsert natural key |

### 3.2 `journal_strategy_run`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `strategy_id` | UUID FK → journal_strategy.id | ON DELETE CASCADE |
| `started_at` | timestamptz NOT NULL | |
| `finished_at` | timestamptz NULL | null while running |
| `result_summary` | jsonb NOT NULL DEFAULT '{}' | top-level metrics (return, sharpe, max_dd, n_trades) |
| `as_of_date` | date NULL | for as-of runs |
| `regime_at_run` | text NULL | bull/bear/sideways/high_vol, sourced from Markov if available |

A single WFO or screener run writes one row. We keep the full result summary in JSONB so we can re-derive analytics even if the journal_trade rows are partial.

### 3.3 `journal_signal`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `strategy_run_id` | UUID FK → journal_strategy_run.id | ON DELETE CASCADE |
| `ticker` | text NOT NULL | |
| `signal_type` | text NOT NULL | `entry`, `exit`, `buy`, `sell`, `hold` |
| `signal_strength` | numeric NULL | 0..1, optional |
| `as_of_date` | date NOT NULL | |
| `payload` | jsonb NOT NULL DEFAULT '{}' | per-ticker details (screener score, indicator values, etc.) |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

Indexes: `(ticker, as_of_date)`, `(strategy_run_id)`.

### 3.4 `journal_trade`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `strategy_id` | UUID FK → journal_strategy.id NULL | ON DELETE SET NULL; null for fully-manual trades |
| `signal_id` | UUID FK → journal_signal.id NULL | ON DELETE SET NULL; the signal that *triggered* the entry |
| `ticker` | text NOT NULL | |
| `side` | text NOT NULL | `long`, `short` (swing trader → long only in v1) |
| `qty` | numeric NOT NULL | |
| `entry_px` | numeric NOT NULL | |
| `exit_px` | numeric NULL | null while open |
| `entry_at` | timestamptz NOT NULL | |
| `exit_at` | timestamptz NULL | null while open |
| `stop_px` | numeric NULL | optional stop-loss level |
| `target_px` | numeric NULL | optional target |
| `pnl` | numeric NULL | computed on close |
| `pnl_pct` | numeric NULL | computed on close |
| `mae` | numeric NULL | max adverse excursion, computed on close (low − entry) |
| `mfe` | numeric NULL | max favorable excursion, computed on close (high − entry) |
| `regime_at_entry` | text NULL | |
| `regime_at_exit` | text NULL | |
| `notes` | text NULL | user free-form |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |
| `updated_at` | timestamptz NOT NULL DEFAULT now() | |

Indexes: `(ticker)`, `(strategy_id, entry_at)`, partial on `(exit_at) WHERE exit_at IS NULL` for open-trade queries.

### 3.5 `journal_market_regime`

| Column | Type | Notes |
|---|---|---|
| `date` | date PK | |
| `regime` | text NOT NULL | bull/bear/sideways/high_vol |
| `confidence` | numeric NULL | 0..1 |
| `by_sector` | jsonb NOT NULL DEFAULT '{}' | optional per-sector regime |

Written by the Markov pipeline (existing). The Coach reads it; it doesn't write it.

### 3.6 `journal_coach_report`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `generated_at` | timestamptz NOT NULL DEFAULT now() | |
| `period_start` | date NOT NULL | |
| `period_end` | date NOT NULL | |
| `strategy_id` | UUID FK → journal_strategy.id NULL | null = all strategies |
| `bundle` | jsonb NOT NULL | the full data bundle passed to the LLM (so reports are auditable) |
| `report_md` | text NOT NULL | the markdown report |
| `metrics` | jsonb NOT NULL | structured metrics that go with the report |
| `model_id` | text NOT NULL | e.g. `kimi-k2.5:cloud` |
| `prompt_tokens` | int NULL | |
| `completion_tokens` | int NULL | |
| `duration_ms` | int NULL | |

### 3.7 Migration

`backend/app/db/migrations/003_trade_journal.py` — Alembic `revision="003"`, `down_revision="002"`, creates all six tables + indexes in `upgrade()`. `downgrade()` drops them in reverse FK order. Matches the existing pattern (`001_create_earnings_calendar.sql` was a raw-SQL file, but `002_add_stock_indexes.py` is an Alembic Python migration — we follow the latter, since we need UUID extensions and `server_default` text).

---

## 4. Coach Analytics Module

`backend/app/services/coach/analytics.py` — pure functions over the journal. No LLM. No side effects on data. Each function takes a `Session` and named date/strategy filters.

| Function | Returns | Notes |
|---|---|---|
| `overview(period, strategy_id?)` | `{period, kpis, equity_curve, drawdown_curve, pnl_by_regime, win_rate_by_strategy, entry_timing_lag}` | main dashboard payload |
| `kpis(period, strategy_id?)` | `{total_pnl, win_rate, expectancy, n_trades, n_open, max_dd, current_dd, sharpe_proxy}` | single numbers |
| `equity_curve(period, strategy_id?)` | `[{date, equity}, ...]` | cumulative P&L |
| `drawdown_curve(period, strategy_id?)` | `[{date, dd}, ...]` | underwater curve |
| `pnl_by_regime(period, strategy_id?)` | `{regime: {n, pnl, pnl_pct}}` | |
| `mae_mfe_scatter(strategy_id?)` | `[{mae, mfe, pnl, ticker, entry_at}, ...]` | for the scatter plot |
| `win_rate_by_strategy(period)` | `[{strategy_id, name, n, win_rate}, ...]` | |
| `entry_timing_lag(strategy_id, period)` | `{p25, p50, p75, mean, n}` | how late you enter after the signal |
| `strategy_correlation_matrix(period)` | `{strategies, matrix}` | daily P&L per strategy, then `.corr()` |
| `recent_trades(strategy_id?, n=20)` | `[Trade.to_dict()]` | for the LLM bundle |
| `regime_timeline(period)` | `[{date, regime, confidence}, ...]` | for the LLM bundle |

**Implementation notes**

- All functions use a single read-only DB session passed in by the caller (the FastAPI dependency). No global session state.
- Pure functions where possible. Side effects only for query execution.
- Tests live in `backend/tests/coach/test_analytics.py`. Fixture journal: 50 trades across 3 strategies and 2 regimes, deterministic seeds, fixed expectations.
- Performance: with a journal of 10k trades the dashboard should render in < 1s. If not, pre-aggregate a `journal_strategy_daily` rollup table populated by a nightly job (out of scope for v1).

---

## 5. Coach LLM Module

`backend/app/services/coach/llm.py` — three pieces.

### 5.1 `bundle.build(...)`

Assembles the data bundle the LLM sees. Pure function, fully deterministic, no hidden state. Returns a JSON-serializable dict:

```python
{
  "period": {"start": "2026-06-01", "end": "2026-07-06"},
  "strategy_id": null,
  "kpis": {...},
  "pnl_by_regime": {...},
  "win_rate_by_strategy": [...],
  "entry_timing_lag": {...},
  "mae_mfe_summary": {"n": 50, "mae_mean": ..., "mfe_mean": ...},
  "equity_curve_summary": {"n": 50, "start": ..., "end": ..., "peak": ..., "trough": ...},
  "drawdown_summary": {"n": 50, "max_dd": ...},
  "strategy_correlation": {"strategies": [...], "matrix": [[...]]},
  "recent_trades": [...],            # max 20
  "regime_timeline": [...],          # max 90 days
  "warnings": [],                    # populated if either is truncated
}
```

The bundle is the **only** thing the LLM sees. The raw journal tables, the raw SQL, the user prompts, and any other context are not in the prompt.

### 5.2 Prompt templates (`prompts.py`)

**System prompt** (locked, not user-editable):

```
You are Trade Coach, an AI that reviews a trader's journal and produces a
written critique. You are NOT a financial advisor. You do not give buy/sell
recommendations. You only describe what the data in the JSON bundle shows.

Hard rules:
- Use only numbers that appear in the JSON bundle. If a number is not in the
  bundle, do not state it.
- Cite specific trade IDs and strategy names when making claims.
- Be concise. Use these section headers in this order:
  ## Top Performers
  ## Underperformers
  ## Regime Mismatch
  ## Behavioral Notes
  ## Concrete Suggestions
- Under "Concrete Suggestions", propose at most 3 testable changes. Each
  suggestion must be implementable as a single A/B WFO test.
- Never recommend taking or avoiding any specific real trade.
- Output valid markdown, no preamble.
```

**User prompt**: a single string containing the JSON bundle, pretty-printed.

### 5.3 `llm.generate_report(bundle, model=None) -> ReportResult`

Pipeline:
1. Call `llm_engine.get_llm_client()` (reuses the Ollama client + retry/timeout; **no duplication**)
2. Send the system + user prompts
3. Receive the markdown
4. **Validate numbers** — regex-extract every number from the markdown, check each against the serialized bundle. If any fail, retry once with a stricter user prompt: "Your previous output contained numbers not in the bundle. Re-issue the report using only bundle values."
5. If the retry also fails, return `ReportResult(markdown=None, error="llm_invented_numbers", bundle=bundle)`. The router will return the metrics dashboard with a "Coach critique unavailable" banner.
6. If valid, parse the markdown into the five sections (lightweight, regex-based).
7. Persist to `journal_coach_report` (the full bundle + report_md + metrics + model_id + token counts + duration).
8. Return the report to the caller.

**Token budget**: bundle is capped at ~30k tokens by truncating `recent_trades` to 20 and `regime_timeline` to 90 days. We surface a warning in the UI if the bundle is truncated.

---

## 6. Coach API

`backend/app/routers/coach.py` — new router, mounted at `/api/coach`.

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/coach/metrics/overview` | the dashboard data (no LLM) — KPIs + equity + drawdown + regime attribution in one payload |
| GET  | `/api/coach/metrics/mae-mfe` | MAE/MFE scatter data |
| GET  | `/api/coach/metrics/win-rate-by-strategy` | win-rate bar chart data |
| GET  | `/api/coach/trades` | list trades, paginated, filterable |
| POST | `/api/coach/trades` | create a paper trade |
| PATCH | `/api/coach/trades/{id}` | update notes, stop, target |
| DELETE | `/api/coach/trades/{id}` | delete a trade |
| POST | `/api/coach/trades/{id}/close` | close a paper trade (computes pnl, pnl_pct, mae, mfe from OHLCV) |
| GET  | `/api/coach/strategies` | list registered strategies |
| POST | `/api/coach/strategies` | manually register a strategy |
| PATCH | `/api/coach/strategies/{id}` | update name/notes/retire |
| POST | `/api/coach/report` | generate a new critique (calls LLM) |
| GET  | `/api/coach/reports` | list past reports |
| GET  | `/api/coach/reports/{id}` | fetch a specific report (markdown + bundle + metrics) |
| DELETE | `/api/coach/reports/{id}` | delete a report |

The router uses the same `SessionLocal` dependency pattern as the rest of the app. The **paper-trade close** endpoint is the only piece of business logic that's not pure CRUD — it takes a trade id + close price (or "use today's close"), and computes:

- `pnl = (close_px − entry_px) × qty × sign(side)`
- `pnl_pct = (close_px − entry_px) / entry_px × sign(side)`
- `mae` = `min(low_during_trade) − entry_px` (worst adverse move, signed by side)
- `mfe` = `max(high_during_trade) − entry_px` (best favorable move, signed by side)

It pulls the OHLCV series for `[entry_at, exit_at]` from `DataService.get_ohlcv_data(ticker, start, end)` (in `backend/app/services/data_service.py:80`) and walks it.

---

## 7. Coach UI

`frontend/src/pages/Coach/index.tsx` — a new tab in the existing Layout, sibling to Markov / Screener / QuantGen.

**Layout** (desktop, 1440px+, matches the design system rules in CLAUDE.md):

```
┌──────────────────────────────────────────────────────────────────────┐
│  Trade Coach                                          [7d][30d]…  ▾  │
├──────────────────────────────────────────────────────────────────────┤
│  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐                    │
│  │PnL │  │Win%│  │Exp.│  │#Tr │  │Open│  │ DD │   ← KPI cards       │
│  └────┘  └────┘  └────┘  └────┘  └────┘  └────┘                    │
├──────────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────┐  ┌─────────────────────────────────┐ │
│  │  Equity Curve              │  │  P&L by Regime                  │ │
│  │  (Recharts line)           │  │  (Recharts bar)                 │ │
│  └────────────────────────────┘  └─────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────┐  ┌─────────────────────────────────┐ │
│  │  MAE vs MFE                │  │  Win Rate by Strategy           │ │
│  │  (Recharts scatter)        │  │  (Recharts horizontal bar)      │ │
│  └────────────────────────────┘  └─────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Latest Coach Report                       [Regenerate ↻]    │   │
│  │  ─────────────────────────────────────────────────────────   │   │
│  │  ## Top Performers                                            │   │
│  │  ...markdown rendered...                                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────┤
│  Past Reports                                                       │
│  • 2026-07-05  Period 7d  … [view]                                  │
└──────────────────────────────────────────────────────────────────────┘
```

**Trade log** is a separate sub-route `/coach/trades` — a table with add/edit/close actions. Linked from a "Trades" button in the Coach header.

**Components** (all use shadcn/ui per CLAUDE.md):

- `KPICards.tsx` — 6 cards in a 6-column grid, value + label, color-coded P&L and DD
- `EquityCurve.tsx` — Recharts line, dollar values
- `RegimeAttribution.tsx` — Recharts bar, 4 categories (bull/bear/sideways/high_vol)
- `MAEvsMFE.tsx` — Recharts scatter, x=MAE y=MFE, color by P&L sign
- `WinRateByStrategy.tsx` — Recharts horizontal bar
- `ReportView.tsx` — renders the markdown via `react-markdown` + `remark-gfm` (new deps). Section anchors for the 5 headers. "Regenerate" button confirms and POSTs to `/api/coach/report`. Shows a spinner + elapsed time during generation.
- `DateRangePicker.tsx` — presets (7d/30d/90d/YTD/All) + custom range
- `TradeTable.tsx` — paginated, sortable, with inline edit for stop/target/notes, "Close" action that calls `/api/coach/trades/{id}/close`
- `TradeForm.tsx` — create new trade (ticker, side, qty, entry_px, entry_at, notes)
- `CloseTradeDialog.tsx` — small dialog for explicit close price

**Empty state**: when `journal_trade` is empty, the dashboard shows a single card: "Run a screener, take a paper trade, and your Coach will start learning from your activity."

**LLM failure banner**: when the LLM is unavailable, the report card shows a rose-bordered banner: "Critique unavailable, metrics are up-to-date" (per CLAUDE.md troubleshooting note on null guards: use `!= null` for numeric fields from the API).

---

## 8. Trade Journal Recording Hooks

Each existing router gets a small post-run recorder. The recorder is **failure-isolated**: if `record_strategy_run(...)` raises (DB down, schema mismatch), we log a WARNING and the user's primary flow continues. This is **explicitly acceptable** for v1 — the user's primary flow must not be blocked by the journal.

**Pattern** (pseudocode, applied to each router):

```python
from app.services.coach.journal import upsert_strategy, record_strategy_run, record_signal

@router.post("/api/screener/scan")
async def run_scan(req: ScanRequest):
    result = await run_dormant_giant_or_quant_strategy(req)
    # record (no await — fire-and-forget into the same request)
    try:
        strat = upsert_strategy(kind="screener", name=f"screener:{req.mode}")
        if strat is not None:
            run = record_strategy_run(strategy_id=strat.id, started_at=..., result_summary=..., as_of_date=...)
            if run is not None:
                for hit in result.hits:
                    record_signal(run_id=run.id, ticker=hit.ticker, signal_type="entry", as_of_date=..., payload=hit.to_dict())
    except Exception as e:
        logger.warning("Coach screener hook failed: %s", e)
    return result
```

**Recording events**:

| Event | Source router | What gets recorded |
|---|---|---|
| Screener scan finishes | `screener.py` | `journal_strategy_run` + one `journal_signal` per hit |
| WFO run finishes | `quantgen.py` (True WFO endpoint) | `journal_strategy_run` + one `journal_signal` per trade the WFO produced |
| Backtest run finishes | `quantgen.py` (`/api/run`) | `journal_strategy_run` + signals if present |
| Markov daily scan | `markov.py` | `journal_strategy_run` + signals |
| Markov retrain | `markov.py` | `journal_strategy_run` with `result_summary.metrics = {model_version, train_score, ...}` |
| Earnings calendar refresh | `earnings.py` | out of scope for v1 (low priority) |

Total code: ~80 lines added across 3 files.

---

## 9. Failure Modes

| Failure | Detection | Response |
|---|---|---|
| LLM timeout / Ollama down | `httpx.TimeoutException` (handled by `llm_engine.py` retry) | `ReportResult(error="llm_unavailable")` → router returns 503 + body has the metrics bundle; UI shows "Critique unavailable, metrics are up-to-date" banner |
| LLM invents a number | Post-processor in `llm.generate_report` | Retry once with stricter prompt; on second failure return `{error: "llm_invented_numbers", metrics: <full bundle>}`; UI shows the bundle metrics as a fallback |
| Journal DB is unreachable | DB health check at boot | `GET /api/coach/*` returns 503; the rest of the app still works (journal hooks no-op with a warning log) |
| Journal is empty | `SELECT COUNT(*) FROM journal_trade` returns 0 | UI empty state; LLM not called |
| User closes browser mid-report-generation | `POST /api/coach/report` already wrote to `journal_coach_report` | They can revisit `/coach` and see the report in the list |
| `mae`/`mfe` calculation fails (missing price data) | caught exception in the close endpoint | Trade is closed but `mae`/`mfe` left null; a warning surfaces in the trade's row |
| Bundle exceeds 30k tokens | `bundle.build(...)` checks size | Truncate `recent_trades` and `regime_timeline`; log a warning; UI shows "Note: report uses a truncated view" |
| 10k+ trades slow the dashboard | `EXPLAIN ANALYZE` on the queries | Add the `journal_strategy_daily` rollup; nightly job populates it; queries switch to it when present (out of v1, flag for follow-up) |
| User deletes a report/trade | `DELETE /api/coach/reports/{id}` works; deleting a trade sets `strategy_id`/`signal_id` to NULL on the trade (we set `ON DELETE SET NULL` for those FKs) | standard CRUD |
| User changes strategy params but keeps the same name | `journal_strategy.params` is a JSONB that gets overwritten | We keep the *latest* params; if the user wants history they can retire + re-create |

---

## 10. What we explicitly will NOT do

- ❌ **Auto-place trades** (paper or live). Coach is read-only.
- ❌ **Connect to a broker.** No Schwab/Alpaca/IBKR integration. Future spec.
- ❌ **Auto-generate strategies** (Approach C). Coach critiques what's there.
- ❌ **Real-time alerts / push notifications** (Approach B's live hooks). Coach runs on demand only.
- ❌ **Multi-user / auth / sharing.** Single-user, paper-only.
- ❌ **Ingest news / sentiment / fundamentals.** Coach uses price + regime data only.
- ❌ **Train an ML model on trade history.** Coach is deterministic metrics + LLM prose. ML-on-trades needs more data than one user will generate in months and risks overfitting.
- ❌ **Auto-import broker fills.** Same as broker integration — out of scope.

---

## 11. Verification

End-to-end (manual, ~30 min):

1. **Schema**: `psql -d sp1500_1d -c "\dt journal_*"` lists 6 new tables. `SELECT * FROM journal_trade LIMIT 0;` returns the expected columns.
2. **Hook smoke**: run a screener, then `SELECT * FROM journal_strategy_run` shows one new row, `SELECT * FROM journal_signal` shows N rows where N = the hit count.
3. **Hook smoke for QuantGen**: run a backtest, verify a row appears.
4. **Hook smoke for Markov**: trigger a Markov scan, verify a row appears.
5. **Trade CRUD**: POST a paper trade, PATCH notes, POST close — verify pnl/mae/mfe are populated.
6. **Analytics**: GET `/api/coach/metrics/overview` returns a non-empty payload with realistic numbers (sanity check: win_rate is in [0,1], pnl sums match a manual `SUM(journal_trade.pnl)`).
7. **Analytics unit tests**: `pytest backend/tests/coach/test_analytics.py` passes — fixture journal of 50 trades, fixed expectations on win_rate, expectancy, pnl_by_regime, etc.
8. **LLM critique**: POST `/api/coach/report` with a populated journal. Within 30s a report appears, all numbers in the markdown appear in the bundle, and a row is written to `journal_coach_report`.
9. **LLM failure path**: simulate Ollama down — verify the router returns 503 with metrics in the body, and the UI shows the right banner.
10. **Empty state**: on a clean DB, GET `/api/coach/metrics/overview` returns the empty-state payload; UI renders the "Run a screener first" card.
11. **UI**: load `/coach` in the browser, change the date range, click Regenerate, view a past report, add a paper trade, close it. Screenshot the result.
12. **History**: regenerate the same report twice — verify two rows in `journal_coach_report`, both visible in the "Past Reports" list.

Performance checks (manual, not strict):

- Dashboard renders in < 1s with 1k trades.
- Dashboard renders in < 3s with 10k trades (if not, the rollup is needed — flag for follow-up).
- LLM report returns in < 30s for a 7-day window with 20+ trades.

---

## 12. Open questions (parking lot, not blockers)

These are explicitly out of scope for this spec, recorded so we don't lose them:

- **Live critique hook on every screen run** (Approach B) — add a 1-paragraph insight in the screener results view, sourced from the same LLM call but with a tighter prompt.
- **Weekly cron for the Coach** — a scheduled job that generates a digest on Sunday evening and posts a notification.
- **Auto strategy factory** (Approach C) — agent proposes variants, runs WFO, surfaces winners.
- **Broker integration** — Schwab/Alpaca/IBKR, fill import, position sync.
- **Multi-user / auth / sharing** — turn the app into a real product.
- **News/sentiment ingestion** — a separate data pipeline, separate spec.
- **Push notifications** — weekly coach digest via email or push.
- **Trade journal mobile view** — read-only mobile-friendly Coach view.
- **Strategy correlation back into the screener** — "tickers that historically correlate with your open positions" as a risk overlay.
