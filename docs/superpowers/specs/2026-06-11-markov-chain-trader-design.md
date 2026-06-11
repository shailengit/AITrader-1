# Design Document: Markov Chain Trader

**Date:** 2026-06-11  
**Status:** Draft  
**Author:** Shailendra Kaushik + Claude Code

---

## 1. Overview

### 1.1 Problem

The existing TradeCraft platform provides sector rotation scanning, AI stock screening (Dormant Giant, Quant Strategy), and QuantGen strategy building/backtesting — but none of these tools incorporate **regime-aware trading signals**. Strategies run the same logic regardless of whether the market is in a bull trend, bear trend, or high-volatility distress. A system that adapts to the current market regime can produce higher risk-adjusted returns.

### 1.2 Solution

Build a **Persistence-Driven Dual-Model Trading System** as a new standalone tab in TradeCraft. The system combines:

1. **Statistical Jump Model** — Detects persistent Bull/Bear regimes per sector ETF, with a GJR-GARCH volatility overlay to gate signals during high-volatility periods
2. **Pattern Recognizer** (XGBoost or LSTM) — Predicts 3-day forward returns per ticker, outputting BUY/HOLD/SELL with conviction probability

A **convergent signal** fires only when both models agree, and the conviction score determines position sizing.

### 1.3 Integration Approach (Hybrid — C)

The system has two modes:

1. **Screener Mode:** A new REST API (`/api/markov/*`) and frontend tab that produces ranked daily actionable lists. Independent service.
2. **Backtest Mode:** A `MarkovSignalProvider` object injected into the existing QuantGen `exec()` sandbox (same way `DataService` is injected). No code generation needed — signals are served from a pre-computed cache.

This maximizes reuse of the battle-tested True WFO pipeline, portfolio tracker, and results display.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Markov Chain Trader                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐   │
│  │   FEATURE     │    │   11 SECTOR       │    │  PATTERN      │   │
│  │   ENGINE      │───▶│   REGIME MODELS   │    │  RECOGNIZER   │   │
│  │ (daily+1min)  │    │  (Jump Model)     │    │  (XGB/LSTM)   │   │
│  └──────────────┘    └────────┬─────────┘    └───────┬───────┘   │
│                               │                      │           │
│                               ▼                      ▼           │
│                      ┌──────────────────────────────────┐        │
│                      │     CONVERGENT SIGNAL ENGINE      │        │
│                      │  (BUY if both agree + conviction) │        │
│                      └──────────┬───────────────┬───────┘        │
│                                 │               │                │
│               ┌─────────────────▼───┐   ┌───────▼──────────┐    │
│               │  Screener API       │   │ MarkovSignal      │    │
│               │  /api/markov/*      │   │ Provider          │    │
│               │  (daily ranked list)│   │ (for exec globals)│    │
│               └─────────────────────┘   └───────────────────┘    │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
   React Markov Tab            QuantGen strategies
   /markov                      via exec sandbox
```

### 2.1 New Files to Create

```
backend/app/
  ├── services/markov/
  │   ├── __init__.py
  │   ├── regime_model.py         # Statistical Jump Model per ETF
  │   ├── feature_engineering.py  # Daily + intraday features + label binning
  │   ├── pattern_recognizer.py   # XGBoost / LSTM training & inference
  │   ├── signal_generator.py     # Convergent BUY/HOLD/SELL + conviction
  │   ├── signal_provider.py      # MarkovSignalProvider for exec sandbox
  │   └── trainer.py              # Orchestrates scheduled retraining
  ├── routers/markov.py           # FastAPI endpoints for new tab
  └── __init__.py

frontend/
  └── pages/Markov/
      ├── index.tsx               # Main tab page
      └── components/             # To be detailed during UI implementation
```

### 2.2 New Dependencies

Add to `backend/requirements.txt`:

```
statsmodels>=0.14.0       # Markov switching models
arch>=6.0.0               # GJR-GARCH with Student-t
scikit-learn>=1.3.0       # Train/test splitting, metrics
xgboost>=2.0.0            # Pattern recognizer (fast track)
torch>=2.0.0              # Pattern recognizer (deep track) — optional, only if LSTM used
```

---

## 3. Data Sources

| Database | Schema | Coverage | History | Used For |
|---|---|---|---|---|
| `sp1500_1d` | OHLCV daily | Full S&P 1500 + 11 ETFs | Years | Feature A, C, D; regime model training |
| `sp1500_1m` | OHLCV 1-min | Full S&P 1500 | Rolling 60 days | Feature B (microstructure) |
| `stock_metadata` | ticker, sector | Full S&P 1500 | Static | Sector-to-ETF mapping |

### 3.1 Existing Infrastructure

- `DataService.get_ohlcv_data()` supports both `frequency="daily"` and `frequency="minute"` with resampling to 5m, 15m, 30m, 1h
- `SECTOR_ETFS` in `database.py` maps 11 ETFs to sectors
- `stock_metadata` table provides ticker-to-sector mapping

---

## 4. Feature Engineering

### 4.1 Feature Groups

**Feature A — Returns & Risk** (daily, from `sp1500_1d`):
- 20-day rolling log returns
- EWM downside deviation (half-life 10, 20)
- Sortino ratio (half-life 20, 60)
- Used by: Jump Model (ETF) + Pattern Recognizer (ticker)

**Feature B — Microstructure** (from `sp1500_1m`, recent 60 days):
- Realized variance (5-min returns, daily aggregation)
- Realized quarticity
- Signed jump variation
- **Required** — tickers without 1m data are skipped (not degraded)
- Used by: Pattern Recognizer only

**Feature C — Technical** (from `sp1500_1d`):
- RSI(14), MACD, Bollinger Band position
- Volume ratio (current / 50-day avg)
- ATH proximity (close / 52-week high)
- Used by: Pattern Recognizer (ticker-level)

**Feature D — Labels** (for pattern recognizer training):
- 3-day forward return
- Binned into 3 buckets: BUY (>+threshold), HOLD (between ±threshold), SELL (< -threshold)
- Threshold default: 2%, user-configurable in UI
- Conviction = model's softmax/logistic probability for the predicted class

### 4.2 Key Design Decisions

- Features computed lazily per-request, cached until next trading day
- Microstructure features are **required** (not degraded) — tickers without 1m data are excluded from screener output
- The 3-day forward window aligns with True WFO's daily trading cadence while giving the signal time to play out

---

## 5. Regime Model — Statistical Jump Model

### 5.1 Algorithm

Each of the 11 sector ETFs (XLK, XLE, XLF, XLV, XLY, XLI, XLC, XLP, XLB, XLRE, XLU) gets its own Jump Model:

1. Compute 20-day rolling log returns on ETF close prices
2. Initialize 2-state model (Bull / Bear)
3. Run coordinate descent to minimize:
   ```
   min Σ Loss(features_t, θ_s_t) + λ · Σ 𝟙(s_t ≠ s_{t-1})
   ```
   where λ is the **jump penalty** that prevents "chattering"
4. Extract filtered probabilities p_t = P(state = Bull | data up to t)

### 5.2 Hyperparameter Tuning

- λ is tuned monthly via rolling walk-forward validation
- Selection criterion: max Sharpe ratio over an 8-year validation window
- Implementation: `statsmodels.tsa.regime_switching.markov_regression` with custom jump penalty

### 5.3 GJR-GARCH Volatility Overlay

- Applied to residuals of the mean model
- GJR-GARCH with Student-t distribution (via `arch` library)
- Extracts filtered probability p_t of being in "Distress/High-Vol" regime
- All buy signals are suppressed when p_t > 0.5

### 5.4 Per-ETF Output (daily)

| Field | Type | Description |
|---|---|---|
| `regime` | `BULL` / `BEAR` | Hard state assignment |
| `bull_probability` | float 0.0–1.0 | Smoothed probability of being in Bull |
| `vol_regime` | `LOW` / `HIGH` | GJR-GARCH filtered volatility state |
| `vol_probability` | float 0.0–1.0 | P(Distress/High-Vol) — gates buy signals if > 0.5 |

---

## 6. Pattern Recognizer — XGBoost / LSTM

### 6.1 Training Data (per ticker)

- Historical daily OHLCV from `sp1500_1d`
- Recent 1m microstructure from `sp1500_1m`
- Sector regime state (from Jump Model) as an input feature
- 3-day forward return → label buckets (3 classes)

Feature vector = [Returns, Risk, Microstructure, Technical, Sector_Regime_State]

### 6.2 Two Tracks

| Aspect | XGBoost | LSTM |
|---|---|---|
| Library | `xgboost` | `torch` (PyTorch) |
| Retrain schedule | Daily (lightweight) | Every 3 months (heavy) |
| Data window | Rolling 1 year | 3+ years of daily |
| Min data required | 252 trading days | 756 trading days (3 years) |
| Tickers below min | Use XGBoost only | Skipped from LSTM screener |
| Sequence awareness | No (features handle it) | Yes (temporal patterns) |
| Frontend label | "Fast" mode | "Deep" mode |
| Training cost | ~seconds/ticker | ~minutes/sector group |

### 6.3 Inference

- Output: 3-class probabilities: [P(SELL), P(HOLD), P(BUY)]
- Conviction = P(BUY)
- BUY signal suppressed to HOLD if conviction < user-configurable minimum (default 0.6)

---

## 7. Convergent Signal Engine

### 7.1 Rules

```
BUY   ← regime == BULL AND vol_probability < 0.5 AND conviction >= min_conviction
SELL  ← regime == BEAR OR vol_probability >= 0.5
HOLD  ← everything else
```

### 7.2 1-Day Trading Delay

All signals carry a mandatory 1-day delay (per the spec). A signal generated from today's data trades at tomorrow's open. This prevents lookahead bias and matches the True WFO pipeline's execution model.

**Implementation distinction:**
- **Screener mode (live):** The `signal_generator.py` automatically shifts signals forward by 1 day. Today's scan tells you what to do tomorrow.
- **Backtest mode (historical):** The `MarkovSignalProvider` does NOT apply the delay — the delay is inherent in the True WFO pipeline structure (train on past N days, trade the next day). The provider serves aligned (date → signal) pairs, and the pipeline's window mechanics handle the temporal separation naturally.

This dual approach ensures neither mode suffers from lookahead bias.

---

## 8. Screener API

### 8.1 Endpoints

```
POST /api/markov/scan
  Body: {
    tickers: string[] | null,     // null = all tickers with data
    model: "xgboost" | "lstm",
    threshold: 0.02,              // BUY/SELL threshold, default 2%
    min_conviction: 0.6,          // minimum probability to act
    sort_by: "conviction" | "ticker",
    max_results: 50
  }
  Returns: {
    signals: [
      {
        ticker: "AAPL",
        sector: "Technology",
        regime: "BULL",
        bull_probability: 0.87,
        vol_regime: "LOW",
        signal: "BUY",
        conviction: 0.73,
        model: "xgboost",
        etf: "XLK",
        price: 198.45
      }
    ],
    sector_status: [               // 11 sector regimes
      { etf: "XLK", sector: "Technology", regime: "BULL", ... }
    ],
    model_health: {
      xgboost_last_trained: "2026-06-11",
      lstm_last_trained: "2026-03-15",
      regimes_as_of: "2026-06-11"
    }
  }

GET /api/markov/status
  Returns model health, cache freshness, coverage stats

POST /api/markov/retrain
  Query: model=xgboost|lstm|all
  Forces retraining on demand
```

### 8.2 Caching (Two Scopes)

**Live cache (screener):**
- ETF regime states: cached until next trading day (in-memory dict keyed by ETF)
- XGBoost models: retrained daily, model files cached per ticker on disk
- LSTM models: retrained quarterly, model files cached per ticker on disk
- Next-day signal cache: pre-computed daily for all tickers, invalidated after market close

**Backtest cache (on-demand):**
- Built when a QuantGen strategy requests `MarkovSignalProvider` with a date range
- Pre-computes ETF regimes for the full historical range + ticker predictions
- Written to a pickle/parquet file keyed by (model, threshold, date_range_hash)
- Subsequent same-parameter runs hit the cache (O(1) per lookup)
- Invalidated when models retrain (cache key includes model version timestamp)

---

## 9. MarkovSignalProvider (Backtest Bridge)

### 9.1 Interface

```python
class MarkovSignalProvider:
    """Injected into QuantGen exec() sandbox. Serves cached signals."""

    def __init__(self, model: str = "xgboost"):
        """Load pre-computed signal cache for the model type."""

    def get_signal(self, ticker: str, date: str) -> str:
        """Returns 'BUY', 'HOLD', or 'SELL'"""

    def get_conviction(self, ticker: str, date: str) -> float:
        """Returns 0.0–1.0"""

    def get_regime(self, ticker: str, date: str) -> dict:
        """Returns sector regime context for this ticker"""
```

### 9.2 Strategy Usage

```python
# A QuantGen strategy using Markov signals
markov = MarkovSignalProvider(model="xgboost")
min_conviction = 0.6

entries = pd.Series(False, index=close.index)
exits = pd.Series(False, index=close.index)

for date in close.index:
    signal = markov.get_signal(ticker, date.strftime('%Y-%m-%d'))
    conviction = markov.get_conviction(ticker, date.strftime('%Y-%m-%d'))
    if signal == 'BUY' and conviction >= min_conviction:
        entries.loc[date] = True
    elif signal == 'SELL':
        exits.loc[date] = True
```

### 9.3 Cache Build

When a QuantGen strategy requests `MarkovSignalProvider`:

1. System detects the date range needed from the strategy code's date parameters
2. Pre-computes ETF regimes for the full range
3. Pre-computes ticker predictions for the full range using the selected model
4. Writes to cache file → `MarkovSignalProvider` reads from cache
5. Subsequent runs with same params hit the cache (O(1) per lookup)

---

## 10. Frontend

### 10.1 Tab

New sidebar item: **Markov Chain Trader** → `/markov`

### 10.2 Page Layout (1440px–1728px primary)

```
┌─ Header ───────────────────────────────────────────────────────┐
│ "Markov Chain Trader" + status badges [Regime ✓] [XGBoost ✓]  │
├─ Control Panel (max-width 480px) ──────────────────────────────┤
│ Model: [XGBoost ● / LSTM ○]                                    │
│ Threshold: [━━━━━━━●───────] 2.0%                              │
│ Min Conviction: [━━━●───────────] 0.6                          │
│ Universe: [▼ All Tickers]  Max Results: [50]                   │
│ [Run Scan] [Backtest Selected]                                 │
├─ Sector Regime Dashboard ──────────────────────────────────────┤
│ Grid of 11 sector badges showing regime + vol status           │
├─ Signals Table ─────────────────────────────────────────────────┤
│ Rank │ Ticker │ Sector │ Signal │ Conviction │ Price │ ETF    │
│ Toggle: [Actionable (≥min)] [Full List]                       │
│ Click row → expands with CandleStickChart + conviction history │
└────────────────────────────────────────────────────────────────┘
```

### 10.3 Component Reuse

- `CandleStickChart` — already handles OHLCV with volume histogram
- Sidebar navigation — same pattern as other pages
- shadcn/ui: Table, Slider, Select, Badge, Button
- Max-width 1280px centered, 12-column grid

### 10.4 "Backtest Selected" Flow

Clicking "Backtest Selected" navigates to `/quantgen?tickers=NVDA,AMZN,JPM&mode=markov&model=xgboost&threshold=0.02`. The QuantGen Builder pre-populates with a Markov-aware strategy template and these params. User can then run/optimize via the existing WFO pipeline.

---

## 11. Scheduler & Retraining Cadence

| Trigger | Action |
|---|---|
| Every trading day (market close + 1hr) | Update ETF regimes (fetch latest bar, recompute Jump Model + GJR-GARCH) |
| Every trading day | Retrain XGBoost on rolling 1yr window, pre-compute next-day signals |
| Every 3 months (Jan/Apr/Jul/Oct 1st) | Retrain LSTM on full historical data, tune λ, re-estimate GARCH params |
| On demand (`/api/markov/retrain`) | Force retrain for specified model |

Implementation: `trainer.py` runs as a background thread in the FastAPI process.

---

## 12. Testing & Verification Strategy

### 12.1 Unit Tests

| Component | What We Test |
|---|---|
| `regime_model.py` | Jump Model converges, λ reduces chattering, 2 states detected |
| `feature_engineering.py` | Features match expected shapes, microstructure required check, label binning |
| `pattern_recognizer.py` | XGBoost trains without error, LSTM trains without error, predictions in [0,1] |
| `signal_generator.py` | Convergence rules produce correct BUY/HOLD/SELL for known inputs |
| `signal_provider.py` | Lookup returns cached values, raises on missing ticker |

### 12.2 Integration Tests

- **Regime training:** Synthetic 2-year data with known bull/bear periods → Jump Model finds them
- **Pattern training:** Synthetic data with known 3-day forward returns → model learns pattern
- **Convergent signals:** Pre-set regime + NN output → BUY only when both agree

### 12.3 End-to-End Tests

- **Screener API:** Call `/api/markov/scan` with real ticker → valid JSON with expected fields
- **QuantGen bridge:** Strategy using `MarkovSignalProvider` → run via `/api/optimize` → trades match expected pattern
- **Frontend:** Markov tab renders, scan populates table, backtest navigates correctly

### 12.4 Validation Pipeline

```
Step 1: Generate synthetic OHLCV with known regime shifts
Step 2: Train Jump Model → verify correct regimes
Step 3: Train XGBoost → verify prediction > random
Step 4: Run convergent signal generator → BUY precision > 40%
Step 5: Full backtest on 10 tickers → compare vs buy-and-hold
Step 6: True WFO on Markov strategy → verify no lookahead
```

Each step must pass before the next begins.

---

## 13. Implementation Phases

| Phase | What | Depends On |
|---|---|---|
| **P1** | Add dependencies (`statsmodels`, `arch`, `scikit-learn`, `xgboost`, `torch`) | — |
| **P2** | Feature engineering module + tests | P1 |
| **P3** | Regime model (Jump Model + GJR-GARCH) + tests | P2 |
| **P4** | Pattern recognizer (XGBoost track) + tests | P2 |
| **P5** | Pattern recognizer (LSTM track) + tests | P4 |
| **P6** | Convergent signal generator + screener API | P3, P5 |
| **P7** | MarkovSignalProvider + QuantGen exec sandbox integration | P6 |
| **P8** | Scheduler / retraining orchestration | P7 |
| **P9** | Frontend Markov tab | P6 |
| **P10** | Frontend backtest bridge (QuantGen pre-population) | P7, P9 |
| **P11** | E2E validation pipeline + documentation | P10 |

---

## 14. Open Questions (Resolved)

| Question | Decision |
|---|---|
| Single index vs per-sector regime? | 11 sector ETFs, ticker inherits from its sector |
| Simple signal vs score? | Signal (BUY/HOLD/SELL) + conviction score (0–1) |
| Forward window length? | 3 days |
| Label buckets? | 3 (BUY/HOLD/SELL) with conviction for strength |
| Threshold user-configurable? | Yes, ±2% default, adjustable in UI |
| Microstructure data required or optional? | Required |
| XGBoost vs LSTM? | Both, frontend toggle (XGBoost: Fast, LSTM: Deep) |