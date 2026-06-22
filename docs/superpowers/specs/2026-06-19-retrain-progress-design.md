# Retraining Progress Reporting — Markov Chain Trader

**Date:** 2026-06-19
**Status:** Approved

## Problem

When a user retrains XGBoost or LSTM models, the backend spawns a background thread but provides zero progress feedback. The frontend shows a single line ("XGBoost retraining started in background") and the user has no idea how long it will take, what ticker is being processed, or whether the process is still running.

## Solution

Reuse the proven scan progress polling pattern for retraining. The scan flow already has:
- A `/api/markov/scan-status` endpoint returning `{running, progress_pct, current_ticker, tickers_completed/total, elapsed_seconds, estimated_remaining_seconds}`
- Frontend polls every 2s and renders a polished progress bar with shimmer animation
- Thread-safe progress dict with lock

We replicate this same pattern for retraining.

## Backend Changes

### File: `backend/app/routers/markov.py`

**A. Add retrain progress dict:**
```python
_retrain_progress: Dict[str, Any] = {
    "running": False,
    "progress_pct": 0.0,
    "current_ticker": "",
    "current_action": "",
    "tickers_completed": 0,
    "tickers_total": 0,
    "elapsed_seconds": 0.0,
    "estimated_remaining_seconds": 0.0,
    "started_at": None,
    "model": "",
}
_retrain_progress_lock = threading.Lock()
```

**B. Add `_update_retrain_progress()` and `_reset_retrain_progress()` helpers:**
Same pattern as `_update_scan_progress()` and `_reset_scan_progress()`.

**C. Wire `_run()` to update progress:**
- Set `_retrain_progress["started_at"] = time.time()` before regime training
- Pass a progress callback to `tr.train_xgboost()` / `tr.train_lstm()` that calls `_update_retrain_progress()`
- Reset progress when done

**D. Add `GET /api/markov/retrain-status` endpoint:**
```python
@router.get("/retrain-status")
async def retrain_status():
    with _retrain_progress_lock:
        stale = False
        if _retrain_progress["running"] and _retrain_progress["started_at"] is not None:
            elapsed = time.time() - _retrain_progress["started_at"]
            if elapsed > 600 and _retrain_progress["tickers_completed"] == 0:
                stale = True
        result = dict(_retrain_progress)
        result["stale"] = stale
        return result
```

### File: `backend/app/services/markov/trainer.py`

**E. Add optional `progress_callback` parameter to `_train_recognizer()`:**
```python
def _train_recognizer(self, tickers, ..., progress_callback=None):
    for i, ticker in enumerate(tickers):
        # ... feature computation + training ...
        if progress_callback:
            progress_callback(i + 1, len(tickers), ticker)
```

## Frontend Changes

### File: `frontend/src/pages/Markov/components/ControlPanel.tsx`

**A. Add RetrainProgress interface:**
```typescript
interface RetrainProgress {
  running: boolean;
  progress_pct: number;
  current_ticker: string;
  current_action: string;
  tickers_completed: number;
  tickers_total: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number;
  model: string;
  stale?: boolean;
}
```

**B. Add state and polling:**
```typescript
const [retrainProgress, setRetrainProgress] = useState<RetrainProgress | null>(null);
```

Polling `useEffect` (self-contained in ControlPanel, triggered by `retraining` state):

```typescript
useEffect(() => {
  if (!retraining) return;
  const interval = setInterval(async () => {
    try {
      const res = await fetch("/api/markov/retrain-status");
      if (res.ok) {
        const data: RetrainProgress = await res.json();
        setRetrainProgress(data);
        if (!data.running) {
          // Retrain complete — stop polling
          clearInterval(interval);
        }
      }
    } catch { /* ignore */ }
  }, 2000);
  return () => clearInterval(interval);
}, [retraining]);
```

**C. Replace `retrainMsg` with progress bar:** When `retrainProgress && retrainProgress.running`, render the progress bar UI (pulsing dot, action text, progress bar with shimmer, ticker count, elapsed/ETA). When `retrainProgress && !retrainProgress.running`, show a brief "Complete" message for a few seconds.

The progress bar is rendered **inline** below the retrain buttons, keeping it visually anchored to the action.

## No Changes

- `frontend/src/pages/Markov/index.tsx` — No changes needed. Retrain polling is self-contained in ControlPanel.
- `backend/app/services/markov/` — Only `trainer.py` _train_recognizer() gets a callback parameter. No other service files change.