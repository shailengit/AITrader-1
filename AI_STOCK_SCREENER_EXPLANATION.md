# AI Stock Screener — Comprehensive Explanation

## Overview

The **AI Stock Screener** is one of three tools inside the TradeCraft platform. It lives at the route `/screener` and is powered by a React frontend (`StockScreener.tsx`) that talks to a FastAPI backend (`screener.py` and `agno_screener.py`).

The page offers **two distinct screening strategies** that users can choose between:

1. **Dormant Giant Screener**
2. **Quant Strategy Screener**

Both strategies can be run **with or without AI**. When AI is enabled, a multi-agent team built with the Agno framework collaborates to produce a natural-language analysis report on top of the raw stock results.

---

## Shared User Experience (Both Screeners)

### 1. Mode Selection
The top of the page presents two large cards side-by-side. Each card shows:
- The screener name
- A short description of what it looks for
- **Agent chips** listing which AI specialists are involved (e.g., Technical Specialist, Fundamental Specialist, Risk Manager)

### 2. AI Analysis Toggle
- A prominent switch labeled **"AI Analysis"** lets the user turn multi-agent intelligence on or off.
- When **ON**, a **Custom Instructions** textarea appears. The user can type a custom prompt that guides the AI team. If left blank, a sensible default prompt is used.
- When **OFF**, the scan runs as fast pure-Python logic against the PostgreSQL database with no LLM calls.

### 3. Real-Time Progress
After clicking **Start Scan**, the frontend polls the backend every second (`/api/screener/status/{scan_id}`). A progress bar animates from 0% to 100% as the scan moves through its phases.

### 4. Results Display
Once complete, the page shows:
- A grid of **stock cards** (ticker, price, signal name, catalyst, SMA/RSI values)
- A collapsible **AI Analysis Report** section (only if `use_ai=true`) containing the natural-language summary written by the agent team

### 5. API Flow
1. `POST /api/screener/scan` — kicks off the scan and returns a `scan_id`
2. `GET /api/screener/status/{scan_id}` — polled every second for progress
3. `GET /api/screener/results/{scan_id}` — fetches the final list of stocks
4. `GET /api/screener/ai-report/{scan_id}` — fetches the Markdown AI report

---

## Strategy 1: Dormant Giant Screener

### What It Does
The **Dormant Giant** strategy hunts for stocks that are quietly building energy before a potential explosive move. It looks for three technical signatures:

1. **Bollinger Bandwidth Squeeze** — volatility is contracting to a very tight range
2. **OBV Hidden Accumulation** — On-Balance Volume is rising even though price is barely moving (sign of quiet institutional buying)
3. **Active Breakout** — price has just punched through a 120-day resistance level on a volume spike

After finding candidates with one of those three signals, it runs a **fundamental verification** step: it checks whether the company has **EPS acceleration** over the last three quarters. The idea is that the technical setup must be backed by real earnings momentum acting as the catalyst.

### The Multi-Agent Team (AI mode)
| Agent | Role |
|-------|------|
| **Technical Specialist** | Scans the entire S&P 1500 universe for squeeze, accumulation, or breakout patterns |
| **Fundamental Specialist** | Verifies that each candidate shows confirmed EPS acceleration (current quarter growth > 1.5x previous quarter growth) |
| **Risk Manager** | Evaluates downside risk and recommends stop-loss placement below the breakout zone or lower Bollinger Band |
| **Team Lead** | Orchestrates the workflow and writes the final comprehensive report |

### User-Configurable Filters
Because the technical criteria involve thresholds, the UI exposes three sensitivity sliders **only for this mode**:

| Filter | Default | Range | What It Controls |
|--------|---------|-------|------------------|
| **Squeeze** | 1.15 | 1.0 – 2.0 | How close the current Bollinger bandwidth must be to the 120-day minimum. Lower = tighter squeeze required. |
| **Accumulation** | 0.005 | 0.001 – 0.02 | How flat price must be while OBV rises. Lower = stricter accumulation. |
| **Volume** | 1.5 | 1.0 – 3.0 | How far above the 50-day average volume the breakout must occur. Higher = requires bigger volume surge. |

> **Note:** This mode does **not** support backtesting.

### Technical Details
- Reads the last **200 days** of price/volume data per ticker from PostgreSQL
- Uses parallel processing (`ProcessPoolExecutor`, 8 workers) to scan the full universe quickly
- Bollinger Bandwidth = `(upper_band - lower_band) / SMA`
- OBV calculated manually from close differences and volume
- EPS acceleration query pulls the most recent 3 quarterly EPS values from `stock_financials_quarterly`

---

## Strategy 2: Quant Strategy Screener

### What It Does
The **Quant Strategy** screener is a broader, more flexible technical-analysis-driven scan. Instead of looking for a single pattern like the Dormant Giant, it performs a **systematic technical indicator sweep** across the S&P 1500, then layers on fundamental health, risk metadata, and optionally historical forward performance.

It is designed to answer requests like:
> *"Find me 5 Small or Mid Cap stocks in an uptrend with consistent yearly revenue growth."*

### The Multi-Agent Team (AI mode)
| Agent | Role |
|-------|------|
| **Technical Specialist** | Screens all stocks for SMA, RSI, MACD, and volume patterns |
| **Fundamental Specialist** | Vets candidates using quarterly/yearly revenue and income trends |
| **Risk Manager** | Flags small-cap (< $2B) and high-volatility (Beta > 1.5) stocks; checks sector concentration |
| **Performance Analyst** | If a cutoff date is provided, calculates how the screened stocks performed from that date to today |
| **Team Lead** | Synthesizes everything into a final Markdown table with Technical, Fundamental, Risk, and Performance columns |

### User-Configurable Options
Unlike the Dormant Giant, this mode has **no sensitivity sliders**. Instead, it offers:

- **Custom Prompt** — guides the AI team on what kind of stocks to look for (e.g., small cap, uptrend, revenue growth)
- **Backtest Cutoff Date** (optional) — if the user selects a date, the Performance Analyst will calculate the price change from that date to the present day. This lets users evaluate whether the screening criteria would have historically picked winners.

> **Note:** The cutoff date filters **both** the technical data and the fundamental data, so the simulation truly runs as if the user were standing on that historical date.

### Technical Details
- Reads up to **250 days** of OHLCV data per ticker
- Calculates indicators manually in pure Python (no `ta` library dependency):
  - **SMA(20)** and **SMA(50)**
  - **RSI(14)**
  - **MACD** (12/26 EMA difference with 9-signal EMA)
- Fundamental query uses a window function (`LAG`) to compute quarter-over-quarter revenue growth
- Metadata query fetches `sector`, `market_cap`, and `beta` from `stock_metadata`
- Performance calculation looks up the exact price at or before the cutoff date, then compares to the latest price

---

## Comparison at a Glance

| Feature | Dormant Giant | Quant Strategy |
|---------|---------------|----------------|
| **Primary Goal** | Find coiling / breakout setups before they explode | Broad TA + fundamental screening with flexible criteria |
| **Core Signals** | Bollinger Squeeze, OBV Accumulation, Resistance Breakout | SMA, RSI, MACD, Volume |
| **Fundamental Check** | EPS acceleration only | Revenue, net income, sector, market cap, beta |
| **AI Agents** | 3 (Tech, Fund, Risk) | 4 (Tech, Fund, Risk, Performance) |
| **Backtesting** | Not supported | Supported via cutoff date |
| **User Filters** | 3 sensitivity sliders (Squeeze, Accumulation, Volume) | Custom prompt + cutoff date only |
| **Default Prompt** | "Begin the daily Dormant Giant screening workflow..." | "Find me 5 Small or Mid Cap stocks in an uptrend..." |
| **Parallelism** | 8 workers | All available CPU cores |
| **Speed** | Very fast (pure Python, targeted logic) | Fast (pure Python, broad indicator sweep) |

---

## What the User Can Actually Do in the UI

1. **Pick a strategy** by clicking one of the two large mode cards.
2. **Toggle AI on/off** with the switch. If on, type custom instructions to steer the agent team.
3. **Adjust sensitivity** (Dormant Giant only) with three sliders to make the scan stricter or looser.
4. **Set a backtest date** (Quant Strategy only) to see how the screened stocks performed since a past date.
5. **Click Start Scan** and watch a real-time progress bar fill up.
6. **Browse results** as animated cards showing ticker, signal, price, catalyst, SMA, and RSI.
7. **Read the AI Report** (if enabled) by expanding the collapsible report panel at the top of the results section.
8. **Retry with different settings** if no stocks are found — the backend will suggest relaxing filters or changing the prompt.

---

## Architecture Recap

| Layer | Files |
|-------|-------|
| **Frontend** | `frontend/src/pages/StockScreener.tsx` |
| **API Router** | `backend/app/routers/screener.py` |
| **Screener Logic** | `backend/app/services/agno_screener.py` |
| **Database** | PostgreSQL `sp1500_1d` (individual stock tables + `stock_financials_quarterly` + `stock_metadata`) |
| **AI Framework** | Agno with Ollama models (`glm-5:cloud` / `minimax-m2.5:cloud`) |

The entire pipeline is asynchronous: the FastAPI endpoint queues a background task, the frontend polls for status, and results stream back as soon as the parallel workers finish.
