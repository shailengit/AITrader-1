# TradeCraft CLI Redesign: Natural Language Strategy Lab

**Date:** 2026-07-08
**Status:** Design (approved for implementation)

## Overview

Rebuild the TradeCraft CLI from scratch to serve as the primary interface for Claude Code to create, backtest, analyze, and learn from trading strategies using natural language. The CLI replaces the outdated `cli-anything-tradecraft` with a clean `tradecraft` command that reflects the current state of the repo.

## Architecture

```
Claude Code Session
  │
  ├── tradecraft CLI tool (--json) ── called by Claude as a structured tool
  │
  └── tradecraft skill ── orchestrates the multi-step conversation flow
          │
          ▼
  tradecraft CLI (Python, Click-based)
    │
    ├── strategy   (create, review, backtest, test-on, save, list, show)
    ├── coach      (kpis, report, trades)
    ├── markov     (status, train, signal)
    ├── sectors    (list, stocks, ohlcv)
    ├── screener   (scan, results, modes, ...)
    ├── quantgen   (generate, run, optimize, ...)
    ├── strategies (list, show, delete)
    ├── projects   (create, show, notes, ...)
    ├── config     (get, set, show)
    ├── repl       (interactive shell)
    └── mcp        (start MCP stdio server — future)
          │
          ▼
  FastAPI Backend (port 8000)
    ├── /api/sectors/*       — Sector rotation
    ├── /api/screener/*      — AI stock screener
    ├── /api/generate, /api/run, /api/optimize  — QuantGen
    ├── /api/strategies/*    — Strategy persistence
    ├── /coach/*             — Coach analytics & reports
    └── /api/ohlcv/*         — OHLCV data
          │
          ▼
  PostgreSQL (sp1500_1d)
    ├── stock data tables
    ├── trade journal tables (JournalTrade, JournalStrategy, etc.)
    └── lessons_learned (new)
```

## CLI Command Structure

### `tradecraft strategy` — Natural Language Strategy Lab

```
strategy create <prompt> --tickers <list> [--start-date <date>] [--end-date <date>]
  Generate strategy code from natural language. Calls QuantGen /api/generate.
  Returns: strategy_id, summary, generated code, tickers, date range.

strategy review <id>
  Show the summary and generated code for a strategy. Reads from local session cache
  (~/.config/tradecraft/session.json) — no API call needed.

strategy backtest <id> [--tickers <list>]
  Run backtest. Calls /api/run. Returns full metrics:
  - total_return, win_rate, expectancy, sharpe_ratio, max_drawdown
  - n_trades, n_open, equity_curve (list of {date, equity})
  - drawdown_curve (list of {date, drawdown})

strategy test-on <id> --tickers <list>
  Run backtest on multiple tickers. Returns comparison table:
  - Per ticker: return, win_rate, sharpe, max_dd
  - Summary row: average across tickers

strategy save <id> --name <name>
  Persist strategy to database. Logs to trade journal.

strategy list [--kind <kind>]
  List saved strategies.

strategy show <id>
  Show saved strategy details.
```

### `tradecraft coach` — Performance Analytics

```
coach kpis [--period <days>] [--strategy-id <id>]
  Deterministic KPIs from trade journal. Returns: total_pnl, win_rate, expectancy,
  n_trades, n_open, max_dd, current_dd, sharpe_proxy.

coach report [--period <days>] [--strategy-id <id>]
  LLM-generated critique report. Returns markdown report with analysis and recommendations.

coach trades list [--period <days>] [--strategy-id <id>]
  List trades from journal.

coach trades add --ticker <t> --side <long|short> --qty <n> --entry-px <p>
  Add a trade to the journal.

coach trades close <trade-id> [--exit-px <p>]
  Close a trade.
```

### `tradecraft markov` — Learning Agent Status

```
markov status
  Model health: last trained dates, model accuracy, number of tickers covered.

markov train [--model <xgboost|lstm>]
  Trigger retraining. Returns training progress.

markov signal <ticker> [--date <date>]
  Get current conviction signal for a ticker.
```

### `tradecraft mcp` — MCP Server (future)

```
mcp start
  Start MCP stdio server. Exposes structured tools that delegate to CLI internals.
  Registered in .claude/settings.json for automatic discovery.
```

## Strategy Workflow (End-to-End)

```
1. CREATE:   tradecraft strategy create "RSI mean reversion" --tickers AAPL
             → Returns strategy_id, summary, generated code

2. REVIEW:   Claude presents summary + code to user
             → User approves or requests changes

3. BACKTEST: tradecraft strategy backtest <id>
             → Returns full metrics

4. ANALYZE:  Claude presents metrics conversationally
             → User may request multi-asset testing

5. MULTI:    tradecraft strategy test-on <id> --tickers MSFT,GOOG
             → Returns comparison table

6. SAVE:     tradecraft strategy save <id> --name "rsi-reversion-v1"
             → Persists to DB + trade journal
```

## Learning Loops

### Loop 1: Code Generation Quality (Lessons Learned)

When a strategy backtest fails due to a code error:

1. Capture the error message and the generated code
2. Extract a lesson: pattern description, error signature, fix instructions
3. Store in `~/.config/tradecraft/lessons.json` (JSON file — no DB migration needed)
4. Before future code generation, inject relevant lessons into the LLM prompt
5. Increment `count` on repeat occurrences to track frequency

**Lessons schema:**
```json
{
  "pattern": "vbt_comparison_operators",
  "error_sig": "cannot join with no overlapping index names",
  "fix": "Use .vbt.gt() / .vbt.lt() instead of > / <, and vbt.combine_logic instead of &",
  "trigger_hint": "VBT optimization",
  "count": 3,
  "first_seen": "2026-03-15",
  "last_seen": "2026-07-01"
}
```

### Loop 2: Trading Performance (Coach + Journal)

Every saved strategy run is logged to the trade journal. The Coach queries the journal to:
- Calculate KPIs (win rate, Sharpe, drawdown, etc.)
- Generate LLM critique reports with specific recommendations
- Identify which strategy types, sectors, or market conditions perform best

### Loop 3: Signal Improvement (Markov Retraining)

The Markov models (XGBoost daily, LSTM quarterly) retrain on a schedule:
- Incorporate new market data
- Improve pattern recognition accuracy
- Signal provider serves better conviction scores over time

## Claude Code Integration

### Tool Registration (.claude/settings.json)

```json
{
  "tools": {
    "tradecraft": {
      "command": "tradecraft",
      "args": ["--json"],
      "description": "TradeCraft CLI — strategy creation, backtesting, coach analytics, Markov learning"
    }
  }
}
```

The `--json` flag ensures machine-readable output that Claude can parse and present conversationally.

### Skill (.claude/skills/tradecraft/SKILL.md)

A Claude Code skill that defines the conversation protocol:
- When user says "create a strategy" → call `tradecraft strategy create`
- Present summary + code → ask for approval
- On approval → call `tradecraft strategy backtest`
- Present metrics → offer multi-asset testing, saving, iteration
- Before code generation → check lessons learned
- After a failure → extract and store the lesson

## Files to Create/Modify

| File | Action | Purpose |
|---|---|---|
| `agent-harness/setup.py` | Modify | New entry point `tradecraft`, update deps |
| `agent-harness/cli_anything/tradecraft/tradecraft_cli.py` | Rewrite | Fresh CLI with all command groups |
| `agent-harness/cli_anything/tradecraft/core/lessons.py` | Create | Lessons learned store |
| `agent-harness/cli_anything/tradecraft/commands/strategy.py` | Create | Strategy command group |
| `agent-harness/cli_anything/tradecraft/commands/coach.py` | Create | Coach command group |
| `agent-harness/cli_anything/tradecraft/commands/markov.py` | Create | Markov command group |
| `agent-harness/cli_anything/tradecraft/commands/mcp.py` | Create | MCP server (future) |
| `.claude/settings.json` | Create/Update | Tool registration |
| `.claude/skills/tradecraft/SKILL.md` | Create | Conversation orchestrator skill |
| `backend/app/services/coach/journal.py` | Extend | Log strategy runs with full metrics |

## Implementation Phasing

This project is large and should be implemented in phases:

| Phase | Focus | Key Files |
|---|---|---|
| 1 | **CLI Foundation** — setup.py, main CLI entry point, config, API client, port existing commands (sectors, screener, quantgen, strategies, projects) | `setup.py`, `tradecraft_cli.py`, `core/config.py`, `core/session.py`, `utils/api_client.py` |
| 2 | **Strategy Lab** — strategy create/review/backtest/test-on/save/list/show commands | `commands/strategy.py` |
| 3 | **Lessons Learned** — capture, store, match, and inject lessons into code generation | `core/lessons.py` |
| 4 | **Coach Commands** — kpis, report, trades CRUD | `commands/coach.py` |
| 5 | **Markov Commands** — status, train, signal | `commands/markov.py` |
| 6 | **Claude Code Integration** — .claude/settings.json tool registration, skill | `.claude/settings.json`, `.claude/skills/tradecraft/SKILL.md` |

Each phase is independently shippable and testable.

## Success Criteria

1. User can say "create a mean reversion strategy for AAPL" and get a working backtest in under 2 minutes
2. Failed backtests due to code errors are captured and never repeated
3. Coach can answer "how am I doing?" with real KPIs from the trade journal
4. Markov models report training status and serve signals
5. All commands work with `--json` for Claude Code consumption
