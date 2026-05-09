# Dormant Giant Screener v2 Design

## Context

The Dormant Giant screener identifies stocks in a Bollinger Band squeeze with hidden accumulation, or already breaking out with volume. The current implementation has several weak signals that produce false positives and misses genuinely explosive setups.

## Goals

1. Sharpen the technical criteria to reduce false positives
2. Add market context (relative strength, sector momentum) so we only find setups in rising water
3. Replace noisy signals (OBV slope) with more robust ones (MFI)
4. Add composite scoring so results are ranked by "explosiveness" rather than pass/fail
5. Improve the frontend to surface scores, new filters, and richer context

## Architecture

The screener is a two-phase pipeline:
- Phase 1: Technical scan (parallel, per-ticker)
- Phase 2: Fundamental verification + enrichment (sequential, batched)

We add a Phase 1.5: Sector/momentum context (single query, cached) and modify Phase 1 to compute composite scores per ticker.

## Changes

### 1. Bollinger Bandwidth Squeeze Fix

**Current:** `current_bandwidth <= min_120d * threshold` — weak, just means "not much wider than recent minimum"

**New:** Require bandwidth in the bottom 20% of its 120-day range AND absolute bandwidth < 6%
```python
bandwidth_pct = (current_bw - min_120d) / (max_120d - min_120d + 1e-9)
is_squeezing = (bandwidth_pct < 0.20) and (current_bw < 0.06)
```

This detects genuine volatility contraction, not just "slightly narrower."

### 2. Consolidation Tightness Filter

**New signal:** Price must be within ±3% of its 20-day SMA for at least 15 of the last 20 days.
```python
sma_20 = df['Close'].rolling(20).mean()
within_band = (abs(df['Close'].tail(20) - sma_20.tail(20)) / sma_20.tail(20)) < 0.03
tight_consolidation = within_band.sum() >= 15
```

This defines "coiling" far better than a single linear slope check. A stock drifting 4% over 20 days but only spending 10 days near its SMA is NOT coiling.

### 3. Replace OBV with MFI Accumulation

**Current:** OBV slope > 0 with flat price — noisy, easily distorted by one big volume day

**New:** Money Flow Index (MFI) on the last 20 days. MFI > 55 indicates accumulation pressure.
```python
typical_price = (High + Low + Close) / 3
raw_money_flow = typical_price * Volume
positive_flow = sum(raw_money_flow where TP > prev_TP)
negative_flow = sum(raw_money_flow where TP < prev_TP)
money_ratio = positive_flow / negative_flow
mfi = 100 - (100 / (1 + money_ratio))
```

MFI is volume-weighted RSI. > 55 = accumulation, > 65 = strong accumulation. We use 55 as the threshold.

### 4. Volume Cluster Detection

**New signal:** At least 3 of the last 5 days had volume > 1.2x the 50-day average. This is what institutional accumulation actually looks like — not one spike day.
```python
vol_spike_days = (df['Volume'].tail(5) > (avg_vol_50 * 1.2)).sum()
has_volume_cluster = vol_spike_days >= 3
```

### 5. Relative Strength vs SPY

**New signal:** Stock's 20-day return vs SPY's 20-day return. Require RS > 0.8 (stock isn't severely lagging the market).
```python
stock_20d_return = (close / close_20d_ago) - 1
spy_20d_return = (spy_close / spy_close_20d_ago) - 1
rs_ratio = stock_20d_return / spy_20d_return if spy_20d_return != 0 else 1
is_strong_rs = rs_ratio > 0.8
```

SPY data is fetched once at scan start, shared across all workers.

### 6. Sector Momentum Gate

**New signal:** Only include tickers whose sector ETF is above its 50-day SMA. We fetch all 11 sector ETFs once at scan start, compute their 50-day SMA, and build a ticker→sector→is_above_sma mapping.

This dramatically reduces false breakouts into weak sectors.

### 7. Composite Scoring

Each passing ticker gets a score 0-100 based on:

| Factor | Weight | Scoring Logic |
|---|---|---|
| Squeeze quality | 20% | 100 - (bandwidth_pct * 100) |
| Consolidation tightness | 20% | (days_near_sma / 20) * 100 |
| MFI accumulation | 15% | min(mfi, 100) |
| Volume cluster | 15% | (vol_spike_days / 5) * 100 |
| RS vs SPY | 15% | min(max(rs_ratio * 100, 0), 100) |
| Sector momentum | 15% | 100 if sector_above_sma else 0 |

Results are sorted by score descending. The frontend shows the score and a visual "Explosiveness" bar.

### 8. Frontend Filter Controls (Replaced)

**Removed (obsolete with new logic):**
- ~~squeeze_threshold~~ — replaced by fixed bottom-20% bandwidth rule
- ~~accumulation_threshold~~ — replaced by MFI and consolidation tightness
- ~~volume_threshold~~ — replaced by volume cluster detection

**New filter controls:**
- Consolidation tightness slider: 10-20 days (default 15)
- MFI threshold slider: 45-70 (default 55)
- Volume cluster days slider: 2-5 (default 3)
- RS minimum slider: 0.5-1.2 (default 0.8)
- Sector momentum toggle: on/off (default on)

**Results card updates:**
- Show composite score (0-100) with color coding: green ≥70, yellow 50-69, red <50
- Show MFI value, volume cluster status, RS ratio
- Show sector and whether sector is in momentum

**Empty state:** Already implemented ("No stocks matched" with "Try relaxing filters")

### 9. Help Button & Explanation Modal

**New "How it works" button** on the screener card (top-right, next to mode selector).

**Modal content** explains the screener in plain language:
- What "Dormant Giant" means
- How each signal works (squeeze, consolidation, MFI, volume cluster, RS, sector momentum)
- How the composite score is calculated
- What to look for in results
- Tips for adjusting filters

Styled with the app's dark theme, using the same card/panel styling.

## Data Flow

```
Scan Start
  └─> Fetch SPY 200-day history
  └─> Fetch all 11 sector ETF 200-day histories
  └─> Compute sector_above_sma_50 mapping
  └─> Parallel workers (per ticker)
        └─> Fetch ticker 200-day OHLCV
        └─> Compute all signals + score
        └─> Return result with score if passes all gates
  └─> Sort results by score descending
  └─> Fundamental verification (EPS/revenue)
  └─> Enrich with metadata
  └─> Return top N
```

## Files Modified

- `backend/app/services/agno_screener.py` — core logic changes
- `backend/app/routers/screener.py` — possibly extend endpoint if needed
- `frontend/src/pages/StockScreener.tsx` — new filter controls, results display

## Verification Plan

1. Run screener with default filters → expect 5-20 results with scores
2. Tighten consolidation to 20 days → expect fewer results
3. Disable sector momentum → expect more results, potentially weaker
4. Verify score sorting: highest score first
5. Verify no errors in logs
6. Frontend: verify new controls render and update correctly
7. Frontend: verify score display and color coding

## Risks

- **SPY/ETF data missing:** If `spy` or sector ETF tables don't exist, scan fails. Mitigation: make context filters optional with graceful fallback.
- **Performance:** Fetching SPY + 11 ETFs adds ~1s to scan. Acceptable.
- **False negatives:** Tighter criteria may reduce results. That's the point — quality over quantity.
