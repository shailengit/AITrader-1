# Markov Scanner Improvements

**Date:** 2026-06-16
**Status:** Approved design

## Summary

Three changes to the Markov Chain Trader page:

1. **Option A convergence logic** — Remove the hard BEAR→SELL gate so stocks in
   BEAR sectors can get BUY signals if the model is confident.
2. **Export BUY signals to QuantGen** — Transfer the list of BUY-signal tickers
   to the QuantGen Builder page for backtesting.
3. **"As of Date" picker** — Let the user scan as of a historical date so they
   can evaluate how past signals would have performed.

---

## 1. Convergence Logic (Option A)

### Current

```python
if is_bull and is_low_vol and pred['signal'] == 'BUY' and is_high_conviction:
    signal = 'BUY'
elif not is_bull or not is_low_vol:
    signal = 'SELL'          # BEAR sectors can NEVER get BUY
else:
    signal = pred['signal']
```

### Proposed

```python
if is_low_vol and pred['signal'] == 'BUY' and is_high_conviction:
    signal = 'BUY'           # Any sector can get BUY if model is confident
elif not is_low_vol:
    signal = 'SELL'          # High vol → SELL (risk gate stays)
else:
    signal = pred['signal']  # Model's prediction otherwise
```

**Changes:**
- Removed `is_bull` from the BUY gate — sector regime no longer blocks BUY.
- Removed `is_bull` from the SELL gate — only high volatility triggers SELL.
- Regime info (BULL/BEAR, bull_probability) stays in the results table for
  context, but doesn't override the model.

**File:** `backend/app/services/markov/signal_generator.py` — `generate_signal()`

---

## 2. Export BUY Signals to QuantGen

### Pattern

Follows the existing Sector Rotation → QuantGen export flow (URL query params):

```
/quantgen/builder?tickers=AAPL,MSFT,ABBV&from_date=2026-06-15
```

### Frontend

- **SignalsTable.tsx**: Add an "Export to QuantGen" button next to the
  Actionable / Full List toggle buttons.
- When clicked, collect all tickers where `signal === "BUY"` and navigate to:
  ```
  /quantgen/builder?tickers=<comma-separated>&from_date=<as-of-date>
  ```
- The `from_date` is the "As of Date" from the scan (or today if not set).
- Opens in a new tab (`window.open`).

### Backend

No backend changes needed — the QuantGen Builder already parses these URL
parameters (`frontend/src/pages/QuantGen/Builder.tsx`).

**Files:**
- `frontend/src/pages/Markov/components/SignalsTable.tsx` — add button
- `frontend/src/pages/Markov/index.tsx` — pass `asOfDate` to SignalsTable

---

## 3. "As of Date" Picker

### Backend

**ScanRequest** (`markov.py`):
- Add optional `end_date: Optional[str] = None` field.
- If provided, use it as the scan's end date instead of `_end_date()`.

**`_do_scan`** (`markov.py`):
- If `end_date` is provided, retrain the regime model with the new end
  date (the regime model is a singleton — for a single-user app this is
  fine; the ~3s retrain happens once per unique end_date).
- Pass `end_date` through to `sg.scan_tickers()`.
- The `end_date` affects three things:
  1. Regime model training (ETF data window)
  2. Feature computation (ticker data window)
  3. Label generation (3-day forward return from end_date)

**`scan_tickers`** (`signal_generator.py`):
- Accept optional `end_date` parameter.
- If provided, use it instead of `datetime.now()` when computing the
  feature date range.

**Minute data fallback** (`feature_engineering.py`):
- Already handled — `compute_ticker_features` checks
  `has_microstructure` and fills microstructure features with 0 if
  minute data isn't available for the date range. No change needed.

### Frontend

**ControlPanel.tsx**:
- Add a date input (`<input type="date">`) labeled "As of Date".
- Default: empty (meaning "today").
- Pass the value through `ScanParams`.

**MarkovPage** (`index.tsx`):
- Pass `asOfDate` to both the scan request and SignalsTable.

**Files:**
- `backend/app/routers/markov.py` — ScanRequest + _do_scan
- `backend/app/services/markov/signal_generator.py` — scan_tickers
- `frontend/src/pages/Markov/components/ControlPanel.tsx` — date input
- `frontend/src/pages/Markov/index.tsx` — pass through

---

## Files Modified

| File | Change |
|------|--------|
| `backend/app/services/markov/signal_generator.py` | Option A logic + `end_date` param |
| `backend/app/routers/markov.py` | `end_date` in ScanRequest + _do_scan |
| `frontend/src/pages/Markov/components/ControlPanel.tsx` | Date picker |
| `frontend/src/pages/Markov/components/SignalsTable.tsx` | Export button |
| `frontend/src/pages/Markov/index.tsx` | Pass through new props |

## Verification

1. Run LSTM scan on all 500 tickers — verify BUY signals appear in BEAR sectors
2. Set "As of Date" to a past date — verify scan uses that date
3. Click "Export to QuantGen" — verify it opens QuantGen Builder with the
   correct tickers and date
4. Verify minute data fallback: set "As of Date" before April 2026 — verify
   scan completes (no minute data, daily only)
