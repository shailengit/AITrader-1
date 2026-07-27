# Golden Cross Rotation — Alpaca Deployment Design

## Overview
Automate the Golden Cross Rotation strategy to run daily on Alpaca paper trading.
The strategy scans 1500 stocks daily, holds top 5 with dynamic sizing, and exits
on death cross, ATR-based trailing stop, or rotation.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Daily Pipeline (6 PM ET)              │
│                                                          │
│  1. Fetch Data ──→ 2. Scan 1500 stocks ──→ 3. Rank Top 5 │
│       │                  │                    │           │
│       ▼                  ▼                    ▼           │
│  PostgreSQL         Strategy Engine       Score + Sort    │
│                                                          │
│  4. Compare with Current Positions ──→ 5. Generate Orders  │
│       │                                      │           │
│       ▼                                      ▼           │
│  Alpaca Portfolio API                   Alpaca Orders API │
└─────────────────────────────────────────────────────────┘
```

## Components

### 1. Alpaca Client (`backend/app/services/alpaca_client.py`)
- Wraps `alpaca-trade-api` REST client
- Methods: `get_account()`, `get_positions()`, `submit_order()`, `cancel_orders()`, `get_bars()`
- Supports paper/live mode via `ALPACA_PAPER` env var

### 2. Strategy Engine (`strategies/golden_cross_ultimate.py`)
- The proven strategy (v5 + crisis override, 60/40 blend)
- Already built and validated

### 3. Daily Runner (`backend/app/services/alpaca_runner.py`)
- Orchestrates the daily pipeline
- Fetches data → runs scan → compares positions → generates orders

### 4. Cron Script (`scripts/run_alpaca_strategy.sh`)
- Triggered by cron at 6 PM ET daily
- Activates venv, runs the daily runner, logs output

## Daily Flow

1. **6:00 PM ET** — Cron triggers the script
2. **Fetch Data** — Query PostgreSQL for latest daily bars of all 1500 stocks
3. **Run Scan** — Compute EMA20/200 crossovers, Entry B signals, score by 60% angle + 40% market cap
4. **Rank** — Sort by score, keep top 5 with dynamic sizing (30/25/20/15/10%)
5. **Compare** — Fetch current Alpaca positions, determine which to sell and which to buy
6. **Execute** — Submit bracket orders to Alpaca:
   - BUY: market-on-open with attached OCO (take profit 20% + trailing stop ATR-based)
   - SELL: market-on-open for positions to close
7. **Log** — Save results, send summary

## Order Types

For each new position, Alpaca bracket orders handle exits automatically:
- BUY @ market-on-open
- Take Profit: 20% limit (GTC)
- Stop Loss: ATR-based trailing stop (GTC)

## Configuration

Add to `.env`:
```
ALPACA_API_KEY=pk_xxx
ALPACA_SECRET_KEY=xxx
ALPACA_PAPER=true
```

## Files to Create

| File | Description |
|------|-------------|
| `backend/app/services/alpaca_client.py` | Alpaca API wrapper |
| `backend/app/services/alpaca_runner.py` | Daily strategy runner |
| `scripts/run_alpaca_strategy.sh` | Cron trigger script |

## Risk Management

- Strategy's built-in exits: death cross, ATR trailing stop, crisis override
- Alpaca bracket orders handle intra-day exits automatically
- No additional safety guards needed per user preference
