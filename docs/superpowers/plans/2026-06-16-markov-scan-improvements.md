# Markov Scanner Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three improvements to the Markov Chain Trader page: (1) remove the BEAR→SELL hard gate so stocks in BEAR sectors can get BUY signals, (2) add an "As of Date" picker to scan historically, (3) add an "Export to QuantGen" button for BUY signals.

**Architecture:** Backend changes in `signal_generator.py` (convergence logic + end_date param) and `markov.py` (ScanRequest + _do_scan). Frontend changes in `ControlPanel.tsx` (date picker), `SignalsTable.tsx` (export button), and `index.tsx` (wire props).

**Tech Stack:** Python/FastAPI backend, React/TypeScript frontend

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/services/markov/signal_generator.py` | Option A convergence logic, `end_date` param on `scan_tickers` |
| `backend/app/routers/markov.py` | `end_date` field on `ScanRequest`, pass through `_do_scan` |
| `frontend/src/pages/Markov/components/ControlPanel.tsx` | "As of Date" date input |
| `frontend/src/pages/Markov/components/SignalsTable.tsx` | "Export to QuantGen" button |
| `frontend/src/pages/Markov/index.tsx` | Wire `asOfDate` through scan request + SignalsTable |

---

### Task 1: Option A Convergence Logic

**Files:**
- Modify: `backend/app/services/markov/signal_generator.py:84-94`

- [ ] **Step 1: Modify `generate_signal()` convergence rules**

Replace the current 4-gate BUY logic with Option A:

```python
# Convergence rules — Option A: sector regime no longer blocks BUY
is_low_vol = regime_info['vol_probability'] < VOL_GATE_THRESHOLD
is_high_conviction = pred['conviction'] >= min_conviction

if is_low_vol and pred['signal'] == 'BUY' and is_high_conviction:
    signal = 'BUY'
elif not is_low_vol:
    signal = 'SELL'
else:
    signal = pred['signal']
```

The `is_bull` variable is no longer used. Remove it.

- [ ] **Step 2: Verify the change compiles**

Run: `cd backend && ./venv/bin/python -c "from app.services.markov.signal_generator import SignalGenerator; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/markov/signal_generator.py
git commit -m "feat(markov): Option A convergence logic — remove BEAR→SELL hard gate"
```

---

### Task 2: As of Date — Backend

**Files:**
- Modify: `backend/app/routers/markov.py:109-114` (ScanRequest)
- Modify: `backend/app/routers/markov.py:151-197` (_do_scan)
- Modify: `backend/app/services/markov/signal_generator.py:109-114` (scan_tickers signature)
- Modify: `backend/app/services/markov/signal_generator.py:156-162` (date computation in loop)

- [ ] **Step 1: Add `end_date` to ScanRequest**

```python
class ScanRequest(BaseModel):
    tickers: Optional[List[str]] = None  # None = all available
    model: str = "xgboost"
    threshold: float = DEFAULT_BUY_THRESHOLD
    min_conviction: float = 0.6
    max_results: int = 50
    end_date: Optional[str] = None  # YYYY-MM-DD; None = today
```

- [ ] **Step 2: Update `_do_scan` to use `end_date`**

In `_do_scan`, replace the hardcoded `end = _end_date()` with:

```python
end = request.end_date if request.end_date else _end_date()
```

Then, after the regime training check, add a retrain-if-end-date-changed block:

```python
# Train regimes if not done yet, or if end_date changed
if rm.last_updated is None or (request.end_date and rm.last_updated != request.end_date):
    _update_scan_progress(0, action="Training regime models...")
    start_3y = (datetime.now() - timedelta(days=int(365.25 * 3 + 35))).strftime('%Y-%m-%d')
    rm.train_all(start_3y, end)
```

And pass `end_date` to `sg.scan_tickers()`:

```python
result = sg.scan_tickers(
    ticker_list,
    model=request.model,
    threshold=request.threshold,
    min_conviction=request.min_conviction,
    max_results=request.max_results,
    max_tickers=request.max_results,
    end_date=request.end_date,
    progress_callback=_progress,
)
```

- [ ] **Step 3: Add `end_date` parameter to `scan_tickers`**

```python
def scan_tickers(self, tickers: List[Dict[str, str]], model: str = "xgboost",
                threshold: float = DEFAULT_BUY_THRESHOLD,
                min_conviction: float = 0.6,
                max_results: int = 50,
                max_tickers: int = 50,
                end_date: Optional[str] = None,
                progress_callback=None) -> Dict[str, Any]:
```

Add to the docstring: `end_date: Optional scan end date (YYYY-MM-DD). Defaults to today.`

- [ ] **Step 4: Use `end_date` in the scan loop**

Replace the date computation inside the loop (lines 156-157):

```python
end = end_date if end_date else datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
```

Note: `start` is always 400 days before today (the lookback window), regardless of `end_date`. Only `end` changes.

- [ ] **Step 5: Verify backend changes**

Run: `cd backend && ./venv/bin/python -c "from app.routers.markov import ScanRequest; r=ScanRequest(end_date='2026-01-15'); print(r.end_date)"`
Expected: `2026-01-15`

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/markov.py backend/app/services/markov/signal_generator.py
git commit -m "feat(markov): add end_date param for As-of-Date scanning"
```

---

### Task 3: As of Date — Frontend Date Picker

**Files:**
- Modify: `frontend/src/pages/Markov/components/ControlPanel.tsx`

- [ ] **Step 1: Add `asOfDate` to `ScanParams` interface**

```typescript
export interface ScanParams {
  model: "xgboost" | "lstm";
  threshold: number;
  minConviction: number;
  maxResults: number;
  asOfDate: string;  // YYYY-MM-DD, empty string = today
}
```

- [ ] **Step 2: Add date input state and UI**

Add state: `const [asOfDate, setAsOfDate] = useState("");`

Add the date input after the Max Tickers field:

```tsx
{/* As of Date */}
<div style={{ marginBottom: 24 }}>
  <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
    As of Date
  </label>
  <input
    type="date"
    value={asOfDate}
    onChange={(e) => setAsOfDate(e.target.value)}
    style={{
      padding: "8px 12px",
      borderRadius: 8,
      border: "1px solid #d2d2d7",
      width: 180,
    }}
  />
  <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
    Scan as of this date (leave empty for today). Affects regime model, features, and labels.
  </div>
</div>
```

- [ ] **Step 3: Pass `asOfDate` in the scan call**

Update the `onScan` call:

```tsx
onClick={() => onScan({ model, threshold: threshold / 100, minConviction, maxResults, asOfDate })}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Markov/components/ControlPanel.tsx
git commit -m "feat(markov): add As-of-Date date picker to ControlPanel"
```

---

### Task 4: Export BUY Signals to QuantGen

**Files:**
- Modify: `frontend/src/pages/Markov/components/SignalsTable.tsx`

- [ ] **Step 1: Add `asOfDate` prop to SignalsTable**

```typescript
interface SignalsTableProps {
  signals: Signal[];
  totalScanned: number;
  loading: boolean;
  isDarkMode: boolean;
  minConviction?: number;
  asOfDate?: string;
}
```

- [ ] **Step 2: Add "Export to QuantGen" button**

Add a button next to the Actionable/Full List toggle. It collects all BUY tickers and navigates to the QuantGen Builder:

```tsx
const buyTickers = signals.filter((s) => s.signal === "BUY").map((s) => s.ticker);
const exportUrl = buyTickers.length > 0
  ? `/quantgen/builder?tickers=${buyTickers.join(",")}&from_date=${asOfDate || new Date().toISOString().split("T")[0]}`
  : null;
```

Add the button after the Full List button:

```tsx
{exportUrl && (
  <button
    onClick={() => window.open(exportUrl, "_blank")}
    style={{
      marginLeft: "auto",
      padding: "6px 16px",
      borderRadius: 6,
      border: `1px solid #10B981`,
      background: "rgba(16, 185, 129, 0.1)",
      cursor: "pointer",
      fontSize: 13,
      color: "inherit",
    }}
    title="Open these BUY signals in QuantGen Builder for backtesting"
  >
    Export {buyTickers.length} BUY → QuantGen
  </button>
)}
```

The button should be right-aligned (using `marginLeft: "auto"` in a flex container).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Markov/components/SignalsTable.tsx
git commit -m "feat(markov): add Export-to-QuantGen button for BUY signals"
```

---

### Task 5: Wire Everything Together in MarkovPage

**Files:**
- Modify: `frontend/src/pages/Markov/index.tsx`

- [ ] **Step 1: Add `lastAsOfDate` state**

```typescript
const [lastAsOfDate, setLastAsOfDate] = useState("");
```

- [ ] **Step 2: Update `handleScan` to store and send `asOfDate`**

```typescript
const handleScan = useCallback(async (params: ScanParams) => {
    setLoading(true);
    setError(null);
    setSignals([]);
    setSectors([]);
    setProgress(null);
    setLastMinConviction(params.minConviction);
    setLastAsOfDate(params.asOfDate);
    try {
      const res = await fetch("/api/markov/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: params.model,
          threshold: params.threshold,
          min_conviction: params.minConviction,
          max_results: params.maxResults,
          end_date: params.asOfDate || undefined,
        }),
      });
      // ... rest unchanged
```

- [ ] **Step 3: Pass `asOfDate` to SignalsTable**

```tsx
<SignalsTable
  signals={signals}
  totalScanned={totalScanned}
  loading={loading}
  isDarkMode={isDarkMode}
  minConviction={lastMinConviction}
  asOfDate={lastAsOfDate}
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Markov/index.tsx
git commit -m "feat(markov): wire asOfDate through MarkovPage scan + SignalsTable"
```

---

## Verification

1. **Option A**: Run LSTM scan — verify BUY signals appear in BEAR sectors (e.g., AAPL in XLK/BEAR should be able to get BUY if model predicts it)
2. **As of Date**: Set date to 2026-01-15, run scan — verify the scan uses that date (check logs for "Fetched N rows for A (daily) from ... to 2026-01-15")
3. **Export**: Click "Export to QuantGen" — verify it opens a new tab with the QuantGen Builder URL containing the BUY tickers and from_date
4. **Minute fallback**: Set As of Date to 2025-06-01 (before minute DB exists) — verify scan completes with daily-only features
