# Screener Scoring: Tunable Composite + Sub-Score Transparency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Custom Screener "Score" column a user-tunable composite (per-screen base_weight + per-sub-score weights) and surface the 4 sub-scores + their raw indicator inputs in the results table, with inline expand and a drawer breakdown. Fix the momentum sub-score peak from RSI 55 to RSI 65 and add an opt-in alignment diagnostic.

**Architecture:**
- **Backend:** extend `compute_base_setup_breakdown` and `compute_quant_score` in `backend/app/services/screening/scoring.py` to accept `sub_weights` and `include_alignment`. Propagate through `run_quant_strategy_screener` and `run_quant_strategy_screener_with_ai`. Extend `ScanRequest` in `backend/app/routers/screener.py` with `sub_weights` and `include_alignment`. When alignment is on, attach `score_minus_return` to each result record.
- **Frontend:** new `Scoring` panel in the filter sidebar (1 base_weight slider + 4 sub-weight sliders + alignment toggle + reset). New 4 sub-score columns in the results table with `title=` tooltips, inline expand for indicator inputs, and opt-in alignment column. New "Scoring breakdown" section in the TickerDetailDrawer. Persist the new fields in saved screens and the page-state draft.

**Tech Stack:** FastAPI + Pydantic (backend), React + TypeScript + Vite + vitest (frontend), shadcn-style local components (no external shadcn lib), localStorage for persistence.

**Spec:** `docs/superpowers/specs/2026-07-05-screener-scoring-design.md` (commit `ec3ccfe`).

## Global Constraints

- Backend Python interpreter: always use `cd backend && ./venv/bin/python` (per `CLAUDE.md`).
- Frontend tests run with `cd frontend && npm test`.
- All new fields on `ScreenPreset` are **optional**; defaults must apply when missing so old saved screens continue to work unchanged.
- No change to the Return column math, the indicator pipeline (`add_all_ta_features`), filter parsers, or any other tool outside the Custom Screener.
- The momentum peak change (RSI 55 → RSI 65) is intentional and is a one-time behavior shift. All other scoring math is preserved.
- Sort order in the results table stays `score` descending — never re-sort by the alignment diagnostic.
- The alignment diagnostic must be opt-in (off by default) to avoid surprising existing users.
- Do not introduce new npm or pip dependencies.

## File Structure (added or modified)

**Backend**
- Modify: `backend/app/services/screening/scoring.py` — add `sub_weights` and `include_alignment` parameters; rewrite the momentum sub-score.
- Modify: `backend/app/services/agno_screener.py` — propagate the new params; attach `score_minus_return` when requested.
- Modify: `backend/app/routers/screener.py` — add `sub_weights` and `include_alignment` to `ScanRequest`; thread through both the non-AI and AI code paths.
- Create: `backend/tests/screening/test_scoring.py` — unit tests for the new math.

**Frontend**
- Create: `frontend/src/components/ui/Slider.tsx` — minimal shadcn-style range input.
- Create: `frontend/src/components/ui/Toggle.tsx` — minimal shadcn-style switch (used for the alignment diagnostic).
- Create: `frontend/src/lib/subScoreInputs.ts` — mapping from sub-score → raw indicator input keys + legend strings. Pure helpers, fully unit-tested.
- Create: `frontend/src/lib/subScoreInputs.test.ts` — vitest unit tests for the helper.
- Modify: `frontend/src/data/screenerTemplates.ts` — extend `ScreenTemplate` with optional `baseWeight`, `subWeights`, `showAlignment`.
- Modify: `frontend/src/hooks/useScreens.ts` — extend `ScreenPreset` with optional `baseWeight`, `subWeights`, `showAlignment`; apply defaults on save/load.
- Modify: `frontend/src/pages/app/ScreenerBuilder/ScreenLibraryModal.tsx` — copy new fields when loading a template or preset.
- Modify: `frontend/src/pages/app/ScreenerBuilder/ScoringPanel.tsx` — NEW: the collapsible scoring panel (sliders + toggle + reset).
- Modify: `frontend/src/pages/app/ScreenerBuilder/ResultsPanel.tsx` — add 4 sub-score columns, tooltips, inline expand, alignment column.
- Modify: `frontend/src/pages/app/ScreenerBuilder/TickerDetailDrawer.tsx` — add the "Scoring breakdown" section.
- Modify: `frontend/src/pages/app/ScreenerBuilder.tsx` — host the `ScoringPanel`, persist state to the page-state draft and into `savePreset`, send the values on scan requests.

---

## Task 1: Backend — momentum sub-score peak shift + unit tests

**Files:**
- Modify: `backend/app/services/screening/scoring.py:39-46`
- Test: `backend/tests/screening/test_scoring.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: the same `compute_base_setup_breakdown(row)` and `compute_base_setup_score(row)` signatures. The new `momentum_score` formula is documented in §2.3 of the spec.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/screening/test_scoring.py` with this content:

```python
"""Tests for the screener scoring math."""
import math
import pandas as pd
from app.services.screening.scoring import (
    compute_base_setup_breakdown,
    compute_base_setup_score,
    compute_quant_score,
)


def _row(**kwargs):
    """Build a minimal row Series with the indicator columns the scoring needs."""
    base = {
        'close': 100.0,
        'trend_adx': 25.0,
        'trend_sma_fast': 99.0,
        'trend_sma_slow': 95.0,
        'trend_macd_diff': 0.5,
        'momentum_rsi': 55.0,
        'momentum_roc': 2.0,
        'momentum_stoch': 50.0,
        'volatility_atr': 3.0,
        'volatility_bbw': 8.0,
        'volume_ratio': 1.2,
        'volume_mfi': 60.0,
    }
    base.update(kwargs)
    return pd.Series(base)


def test_momentum_score_rsi_peak_is_65():
    """RSI 65 yields the highest rsi_score; RSI 30 and RSI 100 yield zero."""
    r65 = compute_base_setup_breakdown(_row(momentum_rsi=65.0))['momentum_score']
    r30 = compute_base_setup_breakdown(_row(momentum_rsi=30.0))['momentum_score']
    r100 = compute_base_setup_breakdown(_row(momentum_rsi=100.0))['momentum_score']
    assert r65 > r30
    assert r65 > r100
    assert math.isclose(r30, _score_with_rsi(30), abs_tol=0.5)
    assert math.isclose(r100, _score_with_rsi(100), abs_tol=0.5)


def _score_with_rsi(rsi: float) -> float:
    """Reference: rsi_score = 100 - min(abs(rsi-65), 35) * (100/35)."""
    return 100 - min(abs(rsi - 65), 35) * (100 / 35)


def test_momentum_score_roc_negative_lowers_score():
    """Negative ROC drags momentum_score below the no-ROC baseline."""
    neutral = compute_base_setup_breakdown(_row(momentum_roc=0.0))['momentum_score']
    neg = compute_base_setup_breakdown(_row(momentum_roc=-10.0))['momentum_score']
    pos = compute_base_setup_breakdown(_row(momentum_roc=10.0))['momentum_score']
    assert pos > neutral > neg


def test_momentum_score_stoch_peak_is_55():
    """Stoch 55 yields the highest stoch_score within the formula."""
    s55 = compute_base_setup_breakdown(_row(momentum_stoch=55.0))['momentum_score']
    s10 = compute_base_setup_breakdown(_row(momentum_stoch=10.0))['momentum_score']
    assert s55 > s10
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/screening/test_scoring.py -v`
Expected: FAIL — the new RSI peak is 55 today, so `r65 > r100` will fail (RSI 100 is closer to 55 than to 65, so the current formula gives a higher score at RSI 100 than at RSI 65).

- [ ] **Step 3: Rewrite the momentum sub-score**

In `backend/app/services/screening/scoring.py`, replace lines 39-46 with:

```python
    # --- Momentum Quality ---
    # Peak at RSI 65 (strong with room to run), zero at RSI 30 and 100.
    # ROC contributes directionally — negative ROC subtracts, positive adds.
    # Stoch peak at 55, zero at 10 and 100.
    rsi = row.get('momentum_rsi', 50)
    rsi_score = 100 - min(abs(rsi - 65), 35) * (100 / 35)
    roc = row.get('momentum_roc', 0)
    roc_score = 50 + max(-50, min(50, roc * 5))
    stoch = row.get('momentum_stoch', 50)
    stoch_score = 100 - min(abs(stoch - 55), 45) * (100 / 45) if stoch is not None else 50
    momentum_score = round(rsi_score * 0.45 + roc_score * 0.30 + stoch_score * 0.25, 1)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/screening/test_scoring.py -v`
Expected: PASS for all 3 tests.

- [ ] **Step 5: Run the full backend test suite to confirm no regressions**

Run: `cd backend && ./venv/bin/python -m pytest tests/ -v`
Expected: PASS for all existing tests (the momentum change is local and shouldn't break other suites; if any test is brittle to the exact momentum value, it will surface here).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/screening/scoring.py backend/tests/screening/test_scoring.py
git commit -m "feat(screener): shift momentum sub-score peak from RSI 55 to RSI 65

The old formula rewarded neutral readings (RSI 55), which is the
pre-breakout state that goes nowhere in the short term. The new formula
peaks at RSI 65 (the historically most profitable 'strong with room'
zone) and lets a negative ROC subtract, so a high momentum_score now
correlates with stocks that have positive momentum and room to run."
```

---

## Task 2: Backend — `sub_weights` parameter in `compute_base_setup_breakdown`

**Files:**
- Modify: `backend/app/services/screening/scoring.py:13-99, 102-104, 206-211`
- Test: `backend/tests/screening/test_scoring.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `compute_base_setup_breakdown(row, sub_weights: Optional[Dict[str, int]] = None) -> Dict[str, float]`
  - `compute_base_setup_score(row, sub_weights: Optional[Dict[str, int]] = None) -> float`
  - When `sub_weights` is `None` or any key is missing, the missing keys default to the current values: `{trend: 30, momentum: 25, volatility: 20, volume: 25}`.
  - When all 4 weights resolve to 0, fall back to equal weights (`{1, 1, 1, 1}`) to avoid division by zero.

- [ ] **Step 1: Append the failing tests to `backend/tests/screening/test_scoring.py`**

Add at the bottom of the file:

```python
def test_base_setup_default_weights_match_legacy_behavior():
    """When sub_weights is None, the total uses 30/25/20/25 hard-coded."""
    row = _row()
    default = compute_base_setup_breakdown(row)['total']
    explicit = compute_base_setup_breakdown(row, sub_weights={'trend': 30, 'momentum': 25, 'volatility': 20, 'volume': 25})['total']
    assert math.isclose(default, explicit, abs_tol=0.05)


def test_base_setup_user_weights_change_total():
    """Larger weight on trend shifts the total toward the trend sub-score."""
    # Use a row where the sub-scores are not all equal so the weight swap is observable.
    # With close > SMA20 > SMA50 + MACD>0 + high ADX, trend_score ~ 95-100.
    # With RSI 30 (oversold) + ROC -10, momentum_score is depressed.
    row = _row(
        trend_adx=55.0,
        trend_sma_fast=99.0,
        trend_sma_slow=95.0,
        close=101.0,
        trend_macd_diff=1.5,
        momentum_rsi=30.0,
        momentum_roc=-10.0,
    )
    trend_heavy = compute_base_setup_breakdown(row, sub_weights={'trend': 100, 'momentum': 0, 'volatility': 0, 'volume': 0})['total']
    momentum_heavy = compute_base_setup_breakdown(row, sub_weights={'trend': 0, 'momentum': 100, 'volatility': 0, 'volume': 0})['total']
    assert trend_heavy > momentum_heavy


def test_base_setup_all_zero_weights_falls_back_to_equal():
    """All-zero weights must not raise; fallback uses equal weights."""
    row = _row()
    out = compute_base_setup_breakdown(row, sub_weights={'trend': 0, 'momentum': 0, 'volatility': 0, 'volume': 0})
    assert 0 <= out['total'] <= 100
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/screening/test_scoring.py -v`
Expected: FAIL — `compute_base_setup_breakdown` does not yet accept `sub_weights`.

- [ ] **Step 3: Update `compute_base_setup_breakdown` to accept `sub_weights`**

In `backend/app/services/screening/scoring.py`, change the function signature (line 13) from:

```python
def compute_base_setup_breakdown(row: pd.Series) -> Dict[str, float]:
```

to:

```python
def compute_base_setup_breakdown(row: pd.Series, sub_weights: Optional[Dict[str, int]] = None) -> Dict[str, float]:
```

(Add `from typing import Optional` at the top of the file with the other imports.)

Then replace lines 86-91 (the `total = round(...)` block) with:

```python
    # Apply user-supplied sub-weights. Missing keys fall back to legacy
    # hard-coded values; all-zero weights fall back to equal weighting
    # to avoid division by zero.
    default_sub_weights = {'trend': 30, 'momentum': 25, 'volatility': 20, 'volume': 25}
    weights = {**default_sub_weights, **(sub_weights or {})}
    weight_sum = sum(weights.values())
    if weight_sum == 0:
        weights = {k: 1 for k in default_sub_weights}
        weight_sum = sum(weights.values())
    total = round(
        (trend_score * weights['trend']
         + momentum_score * weights['momentum']
         + volatility_score * weights['volatility']
         + volume_score * weights['volume']) / weight_sum,
        1,
    )
```

- [ ] **Step 4: Update `compute_base_setup_score` to forward the parameter**

Replace lines 102-104 with:

```python
def compute_base_setup_score(row: pd.Series, sub_weights: Optional[Dict[str, int]] = None) -> float:
    """Compute a 0-100 base setup score from technical indicators."""
    return compute_base_setup_breakdown(row, sub_weights)['total']
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/screening/test_scoring.py -v`
Expected: PASS for all 6 tests.

- [ ] **Step 6: Run the full suite**

Run: `cd backend && ./venv/bin/python -m pytest tests/ -v`
Expected: PASS for all existing tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/screening/scoring.py backend/tests/screening/test_scoring.py
git commit -m "feat(screener): accept user-supplied sub-weights in base setup score"
```

---

## Task 3: Backend — `include_alignment` in `compute_quant_score` and through the screener

**Files:**
- Modify: `backend/app/services/screening/scoring.py:206-211`
- Modify: `backend/app/services/agno_screener.py:1395-1397, 1400-1422`
- Test: `backend/tests/screening/test_scoring.py` (extend)

**Interfaces:**
- `compute_quant_score(row, filters, base_weight=60, sub_weights=None, include_alignment=False) -> Dict[str, float]`
  - Returns a dict `{score, score_minus_return}` when `include_alignment` is True.
  - Returns a dict `{score}` when False (callers reading `result['score']` keep working).
  - `score_minus_return` is computed from the row's `return_pct` if present; otherwise it's `None` (the row hasn't been enriched yet, which is fine — the caller can recompute it post-enrich).

- [ ] **Step 1: Append the failing test**

Add at the bottom of `backend/tests/screening/test_scoring.py`:

```python
def test_compute_quant_score_returns_dict_with_score_only_by_default():
    filters = {}
    out = compute_quant_score(_row(), filters)
    assert isinstance(out, dict)
    assert 'score' in out
    assert 'score_minus_return' not in out


def test_compute_quant_score_with_alignment_returns_both_keys():
    filters = {}
    row = _row()
    row['return_pct'] = 5.0
    out = compute_quant_score(row, filters, include_alignment=True)
    assert 'score' in out
    assert 'score_minus_return' in out
    # 5% return is normalized to 5; score_minus_return = score - 5
    assert math.isclose(out['score_minus_return'], out['score'] - 5.0, abs_tol=0.5)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/screening/test_scoring.py -v`
Expected: FAIL — `compute_quant_score` currently returns a float.

- [ ] **Step 3: Refactor `compute_quant_score` to return a dict**

Replace `backend/app/services/screening/scoring.py:206-211` with:

```python
def compute_quant_score(
    row: pd.Series,
    filters: Dict[str, Any],
    base_weight: int = 60,
    sub_weights: Optional[Dict[str, int]] = None,
    include_alignment: bool = False,
) -> Dict[str, Any]:
    """Compute the hybrid quant score and optional alignment diagnostic.

    Returns a dict with at least `score`. When `include_alignment` is True
    and the row carries a `return_pct`, also returns `score_minus_return`.
    """
    base = compute_base_setup_score(row, sub_weights)
    bonus = compute_filter_match_bonus(row, filters)
    bw = max(0, min(100, base_weight)) / 100.0
    score = round(base * bw + bonus * (1 - bw), 1)
    out: Dict[str, Any] = {'score': score}
    if include_alignment and row.get('return_pct') is not None:
        normalized_return = max(-100.0, min(100.0, float(row['return_pct'])))
        out['score_minus_return'] = round(score - normalized_return, 1)
    return out
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/screening/test_scoring.py -v`
Expected: PASS for all 8 tests.

- [ ] **Step 5: Update `agno_screener.py` to use the new return shape**

In `backend/app/services/agno_screener.py`, replace lines 1395-1406 (the score computation + first part of the per-row record builder) with:

```python
    # Compute hybrid score (60% base setup + 40% filter match) and sort descending.
    # `include_alignment` propagates from the request; if true, each result row
    # gets a `score_minus_return` field too (computed post-enrich below).
    tech_df['score'] = tech_df.apply(
        lambda row: compute_quant_score(
            row, filters or {}, base_weight, sub_weights, include_alignment
        )['score'],
        axis=1,
    )
    tech_df = tech_df.sort_values(by='score', ascending=False)

    # Map ta column names to frontend-friendly names
    results_records = []
    for _, row in tech_df.iterrows():
        record = {
            'ticker': row.get('ticker', ''),
            'close': row.get('close', None),
            'score': round(float(row.get('score', 0)), 1)
        }
```

- [ ] **Step 6: Add a `sub_weights` and `include_alignment` parameter to `run_quant_strategy_screener`**

Find the signature `def run_quant_strategy_screener(...)` (around line 1340) and add the two new parameters with defaults:

```python
def run_quant_strategy_screener(
    prompt: str = "",
    cutoff_date: Optional[str] = None,
    progress_callback=None,
    log_callback=None,
    filters: Optional[Dict[str, Any]] = None,
    base_weight: int = 60,
    sub_weights: Optional[Dict[str, int]] = None,
    include_alignment: bool = False,
) -> Dict[str, Any]:
```

Pass `sub_weights=sub_weights, include_alignment=include_alignment` into the new `compute_quant_score` call (already done in Step 5).

- [ ] **Step 7: Add the same parameters to `run_quant_strategy_screener_with_ai`**

Find `def run_quant_strategy_screener_with_ai(...)` (around line 1476) and add the two new params with the same defaults. Then find the inner call to `run_quant_strategy_screener` (around line 1514) and pass `sub_weights=sub_weights, include_alignment=include_alignment` through.

- [ ] **Step 8: Compute `score_minus_return` post-enrich (so it sees `return_pct`)**

The `return_pct` is attached during the `enrich_results` step (line 1455). After enrichment, walk `top_records` and if `include_alignment` is True, attach `score_minus_return` to each record:

```python
    if include_alignment:
        for record in top_records:
            return_pct = record.get('return_pct')
            if return_pct is not None:
                normalized = max(-100.0, min(100.0, float(return_pct)))
                record['score_minus_return'] = round(float(record.get('score', 0)) - normalized, 1)
```

Place this block immediately after the `_enrich_with_earnings` and `_apply_earnings_filter` calls (around line 1461, before the return at line 1463).

- [ ] **Step 9: Run the full suite**

Run: `cd backend && ./venv/bin/python -m pytest tests/ -v`
Expected: PASS for all tests.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/screening/scoring.py backend/app/services/agno_screener.py backend/tests/screening/test_scoring.py
git commit -m "feat(screener): add score_minus_return alignment diagnostic"
```

---

## Task 4: Backend — extend `ScanRequest` with the new fields

**Files:**
- Modify: `backend/app/routers/screener.py:68-79` (the `ScanRequest` model)
- Modify: `backend/app/routers/screener.py:840-860` (the two call sites that pass `base_weight`)
- Test: `backend/tests/screening/test_scoring.py` (extend with a route-level test)

**Interfaces:**
- `ScanRequest.sub_weights: Optional[Dict[str, int]] = None` — keys must be a subset of `{trend, momentum, volatility, volume}`, each value must be `int` ≥ 0.
- `ScanRequest.include_alignment: Optional[bool] = False`.
- Both new fields are plumbed through the two call sites that already pass `base_weight`.

- [ ] **Step 1: Append the failing test**

Add at the bottom of `backend/tests/screening/test_scoring.py`:

```python
def test_scan_request_accepts_sub_weights():
    """The ScanRequest model accepts a valid sub_weights dict."""
    from app.routers.screener import ScanRequest
    req = ScanRequest(
        mode='quant_strategy',
        sub_weights={'trend': 50, 'momentum': 25, 'volatility': 10, 'volume': 15},
        include_alignment=True,
    )
    assert req.sub_weights == {'trend': 50, 'momentum': 25, 'volatility': 10, 'volume': 15}
    assert req.include_alignment is True


def test_scan_request_sub_weights_default_to_none():
    from app.routers.screener import ScanRequest
    req = ScanRequest(mode='quant_strategy')
    assert req.sub_weights is None
    assert req.include_alignment is False
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/screening/test_scoring.py::test_scan_request_accepts_sub_weights -v`
Expected: FAIL — `ScanRequest` does not yet have those fields.

- [ ] **Step 3: Add the two fields to `ScanRequest`**

In `backend/app/routers/screener.py:68-79`, add these two lines after the existing `base_weight` line:

```python
    sub_weights: Optional[Dict[str, int]] = None  # Per-sub-score weights: {trend, momentum, volatility, volume}; each >= 0
    include_alignment: Optional[bool] = False  # When true, attach score_minus_return per result row
```

(Check that `Optional` and `Dict` are already imported in the file; if not, add them to the typing import at the top.)

- [ ] **Step 4: Plumb the new fields through both call sites**

The two call sites are around lines 844 and 855 in `backend/app/routers/screener.py`. Find them and add `sub_weights=request.sub_weights, include_alignment=request.include_alignment` to each call.

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/screening/test_scoring.py -v`
Expected: PASS for all 10 tests.

- [ ] **Step 6: Run the full suite**

Run: `cd backend && ./venv/bin/python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/screener.py backend/tests/screening/test_scoring.py
git commit -m "feat(screener): accept sub_weights and include_alignment in ScanRequest"
```

---

## Task 5: Frontend — shadcn-style Slider and Toggle components

**Files:**
- Create: `frontend/src/components/ui/Slider.tsx`
- Create: `frontend/src/components/ui/Toggle.tsx`
- Test: `frontend/src/components/ui/Slider.test.tsx` (small smoke test)
- Test: `frontend/src/components/ui/Toggle.test.tsx` (small smoke test)

**Interfaces:**
- `<Slider value={number} onChange={(v: number) => void} min={number} max={number} step={number} ariaLabel={string} />` — a controlled, accessible range input styled to match the rest of the UI.
- `<Toggle checked={boolean} onChange={(c: boolean) => void} label={string} />` — a labeled switch (label clickable, plus the visual switch).

- [ ] **Step 1: Create `frontend/src/components/ui/Slider.tsx`**

Write this file (preserves the inline-style aesthetic of the rest of the components, per the `Tailwind Spacing Classes Not Applied` lesson in `CLAUDE.md`):

```tsx
import { useId } from 'react';
import { useTheme } from '../../context/ThemeContext';

interface SliderProps {
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  ariaLabel: string;
  disabled?: boolean;
}

export default function Slider({
  value, onChange, min, max, step = 1, ariaLabel, disabled = false,
}: SliderProps) {
  const { isDarkMode } = useTheme();
  const id = useId();
  const colors = {
    track: isDarkMode ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.10)',
    fill: '#10B981',
    thumb: '#10B981',
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
  };
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{ flex: 1, position: 'relative', height: 24, display: 'flex', alignItems: 'center' }}>
        {/* Track */}
        <div
          style={{
            position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 2,
            backgroundColor: colors.track,
          }}
        />
        {/* Fill */}
        <div
          style={{
            position: 'absolute', left: 0, width: `${pct}%`, height: 4, borderRadius: 2,
            backgroundColor: disabled ? colors.muted : colors.fill,
          }}
        />
        {/* Native range input on top for accessibility */}
        <input
          id={id}
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          aria-label={ariaLabel}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{
            position: 'absolute', inset: 0, width: '100%', height: 24,
            opacity: 0, cursor: disabled ? 'not-allowed' : 'pointer', margin: 0,
          }}
        />
        {/* Visible thumb */}
        <div
          aria-hidden
          style={{
            position: 'absolute', left: `calc(${pct}% - 8px)`, width: 16, height: 16,
            borderRadius: 8, backgroundColor: disabled ? colors.muted : colors.thumb,
            boxShadow: '0 1px 3px rgba(0,0,0,0.3)', pointerEvents: 'none',
          }}
        />
      </div>
      <span style={{ minWidth: 56, textAlign: 'right', fontSize: 12, color: colors.muted, fontVariantNumeric: 'tabular-nums' }}>
        {value} / {max}
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/ui/Toggle.tsx`**

```tsx
import { useId } from 'react';
import { useTheme } from '../../context/ThemeContext';

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
}

export default function Toggle({ checked, onChange, label, disabled = false }: ToggleProps) {
  const { isDarkMode } = useTheme();
  const id = useId();
  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    trackOff: isDarkMode ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.18)',
    trackOn: '#10B981',
    thumb: '#ffffff',
  };
  return (
    <label
      htmlFor={id}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1, userSelect: 'none',
      }}
    >
      <span style={{ fontSize: 13, color: colors.text }}>{label}</span>
      <span style={{ position: 'relative', width: 36, height: 20 }}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          aria-label={label}
          style={{ position: 'absolute', opacity: 0, width: '100%', height: '100%', margin: 0, cursor: disabled ? 'not-allowed' : 'pointer' }}
        />
        <span
          aria-hidden
          style={{
            position: 'absolute', inset: 0, borderRadius: 10,
            backgroundColor: checked ? colors.trackOn : colors.trackOff,
            transition: 'background-color 150ms ease',
          }}
        />
        <span
          aria-hidden
          style={{
            position: 'absolute', top: 2, left: checked ? 18 : 2, width: 16, height: 16,
            borderRadius: 8, backgroundColor: colors.thumb,
            boxShadow: '0 1px 2px rgba(0,0,0,0.3)', transition: 'left 150ms ease',
          }}
        />
      </span>
    </label>
  );
}
```

- [ ] **Step 3: Add the two components to the barrel export**

In `frontend/src/components/ui/index.ts`, add:

```ts
export { default as Slider } from './Slider';
export { default as Toggle } from './Toggle';
```

- [ ] **Step 4: Write the smoke tests**

Create `frontend/src/components/ui/Slider.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Slider from './Slider';

describe('Slider', () => {
  it('renders with the current value visible', () => {
    render(<Slider value={30} onChange={() => {}} min={0} max={100} ariaLabel="Test" />);
    expect(screen.getByLabelText('Test')).toBeInTheDocument();
    expect(screen.getByText('30 / 100')).toBeInTheDocument();
  });

  it('calls onChange when the user moves it', () => {
    const onChange = vi.fn();
    render(<Slider value={0} onChange={onChange} min={0} max={100} ariaLabel="Test" />);
    fireEvent.change(screen.getByLabelText('Test'), { target: { value: '42' } });
    expect(onChange).toHaveBeenCalledWith(42);
  });
});
```

Create `frontend/src/components/ui/Toggle.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Toggle from './Toggle';

describe('Toggle', () => {
  it('renders the label and reflects the checked state', () => {
    render(<Toggle checked={true} onChange={() => {}} label="Show" />);
    const input = screen.getByLabelText('Show') as HTMLInputElement;
    expect(input.checked).toBe(true);
  });

  it('flips state on click', () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} label="Show" />);
    fireEvent.click(screen.getByLabelText('Show'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});
```

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm test`
Expected: PASS for all tests (existing + 4 new).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/Slider.tsx frontend/src/components/ui/Toggle.tsx \
        frontend/src/components/ui/index.ts \
        frontend/src/components/ui/Slider.test.tsx frontend/src/components/ui/Toggle.test.tsx
git commit -m "feat(ui): add Slider and Toggle components for the scoring panel"
```

---

## Task 6: Frontend — `subScoreInputs` helper and unit tests

**Files:**
- Create: `frontend/src/lib/subScoreInputs.ts`
- Create: `frontend/src/lib/subScoreInputs.test.ts`

**Interfaces:**
- `type SubScoreKey = 'trend_score' | 'momentum_score' | 'volatility_score' | 'volume_score';`
- `type IndicatorInput = { label: string; value: number | string | null; note?: string };`
- `getSubScoreInputs(subScore: SubScoreKey, row: Record<string, any>): IndicatorInput[]` — returns the list of inputs in display order.
- `getSubScoreTooltip(subScore: SubScoreKey, row: Record<string, any>): string` — returns the one-line `title=` tooltip string.
- `SUB_SCORE_KEYS: readonly SubScoreKey[]` — the four keys in display order.

- [ ] **Step 1: Create `frontend/src/lib/subScoreInputs.ts`**

```ts
/**
 * Maps each sub-score to the raw indicator values that fed it, plus a
 * one-line tooltip summary. Pure helpers — no React, no I/O.
 *
 * The mapping is documented in the spec (2026-07-05-screener-scoring-design.md
 * §2.3 and §4). Backend already returns the raw indicator values on each
 * result row; the frontend just maps them.
 *
 * Some indicators are exposed under two names because the backend's
 * `ta_to_friendly` map renames known columns but leaves the rest as the
 * raw `ta` names. We try both keys.
 */

export type SubScoreKey = 'trend_score' | 'momentum_score' | 'volatility_score' | 'volume_score';

export const SUB_SCORE_KEYS: readonly SubScoreKey[] = [
  'trend_score', 'momentum_score', 'volatility_score', 'volume_score',
] as const;

export interface IndicatorInput {
  label: string;
  value: number | string | null;
  note?: string;
}

function pick(row: Record<string, any>, ...keys: string[]): number | string | null {
  for (const k of keys) {
    if (row[k] !== undefined && row[k] !== null && !Number.isNaN(row[k])) {
      return row[k];
    }
  }
  return null;
}

function fmt(v: number | string | null, digits = 2): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string') return v;
  return v.toFixed(digits);
}

export function getSubScoreInputs(subScore: SubScoreKey, row: Record<string, any>): IndicatorInput[] {
  switch (subScore) {
    case 'trend_score':
      return [
        { label: 'ADX',          value: pick(row, 'trend_adx'),                note: 'peak at 50' },
        { label: 'SMA(20)',      value: pick(row, 'trend_sma_fast', 'sma_20'), note: 'close > fast > slow = 100' },
        { label: 'SMA(50)',      value: pick(row, 'trend_sma_slow', 'sma_50') },
        { label: 'Close',        value: pick(row, 'close') },
        { label: 'MACD diff',    value: pick(row, 'trend_macd_diff'),          note: 'positive = 100' },
      ];
    case 'momentum_score':
      return [
        { label: 'RSI(14)',      value: pick(row, 'momentum_rsi', 'rsi'),     note: 'peak at 65' },
        { label: 'ROC',          value: pick(row, 'momentum_roc'),             note: 'positive adds, negative subtracts' },
        { label: 'Stoch %K',     value: pick(row, 'momentum_stoch'),          note: 'peak at 55' },
      ];
    case 'volatility_score':
      return [
        { label: 'ATR',          value: pick(row, 'volatility_atr') },
        { label: 'ATR %',        value: (() => {
          const atr = pick(row, 'volatility_atr');
          const close = pick(row, 'close');
          if (typeof atr === 'number' && typeof close === 'number' && close > 0) {
            return (atr / close) * 100;
          }
          return null;
        })(), note: 'peak band 1–5%' },
        { label: 'BBW',          value: pick(row, 'volatility_bbw'),           note: 'peak band 2–15' },
      ];
    case 'volume_score':
      return [
        { label: 'Vol ratio',    value: pick(row, 'volume_ratio'),             note: 'peak 1–2x' },
        { label: 'MFI',          value: pick(row, 'volume_mfi'),               note: 'peak at 100' },
      ];
  }
}

export function getSubScoreTooltip(subScore: SubScoreKey, row: Record<string, any>): string {
  const inputs = getSubScoreInputs(subScore, row);
  return inputs
    .filter((i) => i.value !== null)
    .map((i) => `${i.label} ${fmt(i.value)}${i.note ? ` (${i.note})` : ''}`)
    .join(' · ');
}
```

- [ ] **Step 2: Create `frontend/src/lib/subScoreInputs.test.ts`**

```ts
import { describe, it, expect } from 'vitest';
import { getSubScoreInputs, getSubScoreTooltip, SUB_SCORE_KEYS } from './subScoreInputs';

const SAMPLE_ROW = {
  trend_adx: 22.4,
  trend_sma_fast: 198.3,
  trend_sma_slow: 192.1,
  close: 201.45,
  trend_macd_diff: 0.42,
  momentum_rsi: 65.0,
  momentum_roc: 2.0,
  momentum_stoch: 50.0,
  volatility_atr: 3.0,
  volatility_bbw: 8.0,
  volume_ratio: 1.2,
  volume_mfi: 60.0,
};

describe('SUB_SCORE_KEYS', () => {
  it('has the four sub-scores in display order', () => {
    expect(SUB_SCORE_KEYS).toEqual(['trend_score', 'momentum_score', 'volatility_score', 'volume_score']);
  });
});

describe('getSubScoreInputs', () => {
  it('returns trend inputs in order with the right labels', () => {
    const inputs = getSubScoreInputs('trend_score', SAMPLE_ROW);
    expect(inputs.map((i) => i.label)).toEqual(['ADX', 'SMA(20)', 'SMA(50)', 'Close', 'MACD diff']);
    expect(inputs[0].value).toBe(22.4);
  });

  it('returns momentum inputs in order', () => {
    const inputs = getSubScoreInputs('momentum_score', SAMPLE_ROW);
    expect(inputs.map((i) => i.label)).toEqual(['RSI(14)', 'ROC', 'Stoch %K']);
  });

  it('computes ATR% from ATR and close when both are present', () => {
    const inputs = getSubScoreInputs('volatility_score', SAMPLE_ROW);
    const atrPct = inputs.find((i) => i.label === 'ATR %');
    expect(atrPct).toBeDefined();
    expect(atrPct!.value).toBeCloseTo(3.0 / 201.45 * 100, 4);
  });

  it('returns volume inputs in order', () => {
    const inputs = getSubScoreInputs('volume_score', SAMPLE_ROW);
    expect(inputs.map((i) => i.label)).toEqual(['Vol ratio', 'MFI']);
  });

  it('handles missing columns gracefully (returns null values, no throw)', () => {
    const inputs = getSubScoreInputs('trend_score', { close: 100 });
    expect(inputs[0].value).toBeNull();
    expect(inputs[1].value).toBeNull();
  });

  it('falls back to the friendly name when the ta name is missing', () => {
    // Backend sometimes renames `trend_sma_fast` to `sma_20`. Verify fallback.
    const inputs = getSubScoreInputs('trend_score', { sma_20: 100, sma_50: 95 });
    expect(inputs[1].value).toBe(100);
    expect(inputs[2].value).toBe(95);
  });
});

describe('getSubScoreTooltip', () => {
  it('produces a one-line summary for trend', () => {
    const s = getSubScoreTooltip('trend_score', SAMPLE_ROW);
    expect(s).toContain('ADX');
    expect(s).toContain('SMA(20)');
    expect(s).toContain('MACD diff');
    expect(s).not.toContain('null');
  });
});
```

- [ ] **Step 3: Run the tests**

Run: `cd frontend && npm test`
Expected: PASS for all tests.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/subScoreInputs.ts frontend/src/lib/subScoreInputs.test.ts
git commit -m "feat(screener): sub-score input mapping helper for tooltip/expand/drawer"
```

---

## Task 7: Frontend — extend `ScreenPreset` and `ScreenTemplate` types + persistence

**Files:**
- Modify: `frontend/src/hooks/useScreens.ts` (extend `ScreenPreset`)
- Modify: `frontend/src/data/screenerTemplates.ts` (extend `ScreenTemplate`)
- Modify: `frontend/src/pages/app/ScreenerBuilder/ScreenLibraryModal.tsx` (copy new fields on load)

**Interfaces:**
- `ScreenPreset.baseWeight?: number` (0–100, default 60).
- `ScreenPreset.subWeights?: { trend, momentum, volatility, volume }` (each 0–100, default 30/25/20/25).
- `ScreenPreset.showAlignment?: boolean` (default false).
- `ScreenTemplate` gets the same three optional fields.

- [ ] **Step 1: Extend `ScreenPreset` in `useScreens.ts`**

In `frontend/src/hooks/useScreens.ts:27-44`, add three optional fields:

```ts
  baseWeight?: number;
  subWeights?: {
    trend: number;
    momentum: number;
    volatility: number;
    volume: number;
  };
  showAlignment?: boolean;
```

- [ ] **Step 2: Extend `ScreenTemplate` in `screenerTemplates.ts`**

In `frontend/src/data/screenerTemplates.ts:24-34`, add the same three optional fields to the `ScreenTemplate` interface (after `useAi`):

```ts
  baseWeight?: number;
  subWeights?: {
    trend: number;
    momentum: number;
    volatility: number;
    volume: number;
  };
  showAlignment?: boolean;
```

- [ ] **Step 3: Copy the new fields when loading a template**

In `frontend/src/pages/app/ScreenerBuilder/ScreenLibraryModal.tsx:42-57`, the `handleLoadTemplate` function builds a `preset` from a `template`. Add three lines after the existing `useAi` line (currently line 53):

```ts
      baseWeight: template.baseWeight,
      subWeights: template.subWeights,
      showAlignment: template.showAlignment,
```

In `handleLoadPreset` (lines 59-62), the preset is loaded as-is; no change needed.

- [ ] **Step 4: Apply defaults when loading an old preset that lacks the fields**

In `frontend/src/pages/app/ScreenerBuilder.tsx` find the function that maps a loaded `ScreenPreset` into the local state (search for `loadPreset` calls; the conversion happens around the `handleLoadPreset` callback or inline in the load handler). Add this helper near the top of the file (after the existing imports):

```ts
function presetScoring(preset: ScreenPreset | undefined): {
  baseWeight: number;
  subWeights: { trend: number; momentum: number; volatility: number; volume: number };
  showAlignment: boolean;
} {
  return {
    baseWeight: preset?.baseWeight ?? 60,
    subWeights: preset?.subWeights ?? { trend: 30, momentum: 25, volatility: 20, volume: 25 },
    showAlignment: preset?.showAlignment ?? false,
  };
}
```

Then, at each call site that consumes a loaded preset (template load and preset load), merge the result into local state.

- [ ] **Step 5: Run typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: PASS (no type errors from the optional fields).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useScreens.ts \
        frontend/src/data/screenerTemplates.ts \
        frontend/src/pages/app/ScreenerBuilder/ScreenLibraryModal.tsx \
        frontend/src/pages/app/ScreenerBuilder.tsx
git commit -m "feat(screener): persist scoring weights and alignment flag in screens"
```

---

## Task 8: Frontend — `ScoringPanel` component

**Files:**
- Create: `frontend/src/pages/app/ScreenerBuilder/ScoringPanel.tsx`
- Test: `frontend/src/pages/app/ScreenerBuilder/ScoringPanel.test.tsx`

**Interfaces:**
- Props:
  ```ts
  interface ScoringPanelProps {
    baseWeight: number;
    subWeights: { trend: number; momentum: number; volatility: number; volume: number };
    showAlignment: boolean;
    onBaseWeightChange: (v: number) => void;
    onSubWeightChange: (key: 'trend' | 'momentum' | 'volatility' | 'volume', v: number) => void;
    onShowAlignmentChange: (v: boolean) => void;
    onReset: () => void;
  }
  ```
- Component is a collapsible card with the 5 sliders + 1 toggle + reset link.

- [ ] **Step 1: Create `ScoringPanel.tsx`**

```tsx
import { useState } from 'react';
import { ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';
import { useTheme } from '../../../context/ThemeContext';
import { Slider, Toggle } from '../../../components/ui';

export interface SubWeights {
  trend: number;
  momentum: number;
  volatility: number;
  volume: number;
}

export const DEFAULT_BASE_WEIGHT = 60;
export const DEFAULT_SUB_WEIGHTS: SubWeights = { trend: 30, momentum: 25, volatility: 20, volume: 25 };
export const DEFAULT_SHOW_ALIGNMENT = false;

interface ScoringPanelProps {
  baseWeight: number;
  subWeights: SubWeights;
  showAlignment: boolean;
  onBaseWeightChange: (v: number) => void;
  onSubWeightChange: (key: keyof SubWeights, v: number) => void;
  onShowAlignmentChange: (v: boolean) => void;
  onReset: () => void;
}

export default function ScoringPanel({
  baseWeight, subWeights, showAlignment,
  onBaseWeightChange, onSubWeightChange, onShowAlignmentChange, onReset,
}: ScoringPanelProps) {
  const { isDarkMode } = useTheme();
  const [open, setOpen] = useState(true);
  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
    border: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    surface: isDarkMode ? '#272729' : '#f5f5f7',
    accent: '#10B981',
  };

  return (
    <div
      style={{
        backgroundColor: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: 10,
        padding: '12px 14px',
        marginTop: 12,
      }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: '100%', background: 'none', border: 'none', padding: 0,
          cursor: 'pointer', color: colors.text, fontSize: 13, fontWeight: 600,
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Scoring
        </span>
        <span
          role="button"
          tabIndex={0}
          onClick={(e) => { e.stopPropagation(); onReset(); }}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onReset(); } }}
          style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: colors.muted, cursor: 'pointer' }}
        >
          <RotateCcw size={11} /> Reset
        </span>
      </button>
      {open && (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Base setup vs filter match" hint="0 = pure filter match, 100 = pure setup">
            <Slider value={baseWeight} onChange={onBaseWeightChange} min={0} max={100} ariaLabel="Base setup vs filter match" />
          </Field>
          <Field label="Trend weight" hint="How much the trend sub-score contributes">
            <Slider value={subWeights.trend} onChange={(v) => onSubWeightChange('trend', v)} min={0} max={100} ariaLabel="Trend weight" />
          </Field>
          <Field label="Momentum weight" hint="How much the momentum sub-score contributes">
            <Slider value={subWeights.momentum} onChange={(v) => onSubWeightChange('momentum', v)} min={0} max={100} ariaLabel="Momentum weight" />
          </Field>
          <Field label="Volatility weight" hint="How much the volatility sub-score contributes">
            <Slider value={subWeights.volatility} onChange={(v) => onSubWeightChange('volatility', v)} min={0} max={100} ariaLabel="Volatility weight" />
          </Field>
          <Field label="Volume weight" hint="How much the volume sub-score contributes">
            <Slider value={subWeights.volume} onChange={(v) => onSubWeightChange('volume', v)} min={0} max={100} ariaLabel="Volume weight" />
          </Field>
          <div style={{ borderTop: `1px solid ${colors.border}`, paddingTop: 10 }}>
            <Toggle
              checked={showAlignment}
              onChange={onShowAlignmentChange}
              label="Show alignment diagnostic (Δ vs return)"
            />
            <div style={{ fontSize: 11, color: colors.muted, marginTop: 4, lineHeight: 1.4 }}>
              Adds a small column showing score − return. Use it to verify that the
              top of the table by score is also near the top by return.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  const { isDarkMode } = useTheme();
  const muted = isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)';
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: isDarkMode ? '#FAFAFA' : '#1d1d1f' }}>{label}</div>
      <div style={{ fontSize: 11, color: muted, marginBottom: 6, lineHeight: 1.3 }}>{hint}</div>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Write the smoke test**

Create `frontend/src/pages/app/ScreenerBuilder/ScoringPanel.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ScoringPanel, { DEFAULT_BASE_WEIGHT, DEFAULT_SUB_WEIGHTS } from './ScoringPanel';

// Mock the theme to keep test output predictable.
vi.mock('../../../context/ThemeContext', () => ({
  useTheme: () => ({ isDarkMode: true }),
}));

describe('ScoringPanel', () => {
  it('renders the sliders and toggle with the provided values', () => {
    render(
      <ScoringPanel
        baseWeight={DEFAULT_BASE_WEIGHT}
        subWeights={DEFAULT_SUB_WEIGHTS}
        showAlignment={false}
        onBaseWeightChange={() => {}}
        onSubWeightChange={() => {}}
        onShowAlignmentChange={() => {}}
        onReset={() => {}}
      />,
    );
    expect(screen.getByLabelText('Base setup vs filter match')).toBeInTheDocument();
    expect(screen.getByLabelText('Trend weight')).toBeInTheDocument();
    expect(screen.getByLabelText('Momentum weight')).toBeInTheDocument();
    expect(screen.getByLabelText('Volatility weight')).toBeInTheDocument();
    expect(screen.getByLabelText('Volume weight')).toBeInTheDocument();
    expect(screen.getByLabelText(/alignment diagnostic/i)).toBeInTheDocument();
  });

  it('calls onReset when the Reset chip is clicked', () => {
    const onReset = vi.fn();
    render(
      <ScoringPanel
        baseWeight={60}
        subWeights={DEFAULT_SUB_WEIGHTS}
        showAlignment={false}
        onBaseWeightChange={() => {}}
        onSubWeightChange={() => {}}
        onShowAlignmentChange={() => {}}
        onReset={onReset}
      />,
    );
    fireEvent.click(screen.getByText(/Reset/));
    expect(onReset).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 3: Run the tests**

Run: `cd frontend && npm test`
Expected: PASS for all tests (existing + 2 new).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/app/ScreenerBuilder/ScoringPanel.tsx \
        frontend/src/pages/app/ScreenerBuilder/ScoringPanel.test.tsx
git commit -m "feat(screener): ScoringPanel with base_weight + sub-weight sliders + alignment toggle"
```

---

## Task 9: Frontend — wire `ScoringPanel` into `ScreenerBuilder.tsx`

**Files:**
- Modify: `frontend/src/pages/app/ScreenerBuilder.tsx` (import, host, state, draft persistence, savePreset, scan request)

**Interfaces added on the page:**
- State: `baseWeight`, `subWeights`, `showAlignment`.
- Draft key: `screener:builder:draft` (already used in this file; extend the persisted object).
- Scan request body: now also sends `base_weight`, `sub_weights`, `include_alignment`.
- `savePreset` call: now also sends `baseWeight`, `subWeights`, `showAlignment`.

- [ ] **Step 1: Add state for the three values**

In `ScreenerBuilder.tsx` near the other `useState` calls (around line 248, where `cutoffDate` is set), add:

```tsx
  const [baseWeight, setBaseWeight] = useState(60);
  const [subWeights, setSubWeights] = useState({ trend: 30, momentum: 25, volatility: 20, volume: 25 });
  const [showAlignment, setShowAlignment] = useState(false);
```

- [ ] **Step 2: Add the import for `ScoringPanel`**

At the top of `ScreenerBuilder.tsx`, alongside the other `import` statements, add:

```tsx
import ScoringPanel, { DEFAULT_BASE_WEIGHT, DEFAULT_SUB_WEIGHTS, DEFAULT_SHOW_ALIGNMENT } from './ScreenerBuilder/ScoringPanel';
```

- [ ] **Step 3: Mount the panel in the filter sidebar**

Find the JSX block that renders the filter sidebar (around line 1518 where `<FilterPicker />` is mounted). Add the panel immediately after `<FilterPicker />`:

```tsx
            <ScoringPanel
              baseWeight={baseWeight}
              subWeights={subWeights}
              showAlignment={showAlignment}
              onBaseWeightChange={setBaseWeight}
              onSubWeightChange={(key, v) => setSubWeights((prev) => ({ ...prev, [key]: v }))}
              onShowAlignmentChange={setShowAlignment}
              onReset={() => {
                setBaseWeight(DEFAULT_BASE_WEIGHT);
                setSubWeights(DEFAULT_SUB_WEIGHTS);
                setShowAlignment(DEFAULT_SHOW_ALIGNMENT);
              }}
            />
```

- [ ] **Step 4: Persist the values in the page-state draft**

Find the `useEffect` that builds and writes the page-state draft (the one with `DRAFT_KEY` around line 327). Extend the `draft` object to include the three new fields:

```tsx
      const draft = {
        // ... existing fields ...
        baseWeight,
        subWeights,
        showAlignment,
      };
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
```

Also extend the restore effect (around line 430) to read them back:

```tsx
          if (typeof draft.baseWeight === 'number') setBaseWeight(draft.baseWeight);
          if (draft.subWeights) setSubWeights(draft.subWeights);
          if (typeof draft.showAlignment === 'boolean') setShowAlignment(draft.showAlignment);
```

(Place these reads after the existing `if (draft.cutoffDate) setCutoffDate(draft.cutoffDate);` line.)

- [ ] **Step 5: Send the values on the scan request**

Find the `fetch('/api/screener/scan', ...)` calls (there are at least two: one in the "live refetch" effect around line 486, one in the "scan" handler around line 680, and possibly one more in the AI path). For each one, add three lines inside the `body: JSON.stringify({...})` object:

```tsx
                  base_weight: baseWeight,
                  sub_weights: subWeights,
                  include_alignment: showAlignment,
```

(Verify that the call sites use `baseWeight`, `subWeights`, `showAlignment` from the closure — they will, because they're top-level `useState`.)

- [ ] **Step 6: Send the values to `savePreset`**

Find the `savePreset` call (around line 625). Extend the object literal:

```tsx
    savePreset({
      // ... existing fields ...
      baseWeight,
      subWeights,
      showAlignment,
    });
```

- [ ] **Step 7: Run typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: PASS.

- [ ] **Step 8: Run all frontend tests**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/app/ScreenerBuilder.tsx
git commit -m "feat(screener): host ScoringPanel, persist weights, send on scan + save"
```

---

## Task 10: Frontend — `ResultsPanel` sub-score columns + tooltips + inline expand + alignment

**Files:**
- Modify: `frontend/src/pages/app/ScreenerBuilder/ResultsPanel.tsx`

**Interfaces added:**
- `ResultsPanelProps.showAlignment: boolean` (new optional, default false) — when true, an extra column is rendered.
- `ResultsPanelProps.baseWeight: number` (new optional, default 60) — used in the score tooltip and the drawer.

- [ ] **Step 1: Add the two new props to `ResultsPanelProps`**

In `ResultsPanel.tsx:44-59`, add:

```ts
  showAlignment?: boolean;
  baseWeight?: number;
```

- [ ] **Step 2: Add the imports**

At the top of the file, add:

```ts
import { SUB_SCORE_KEYS, getSubScoreTooltip, getSubScoreInputs, type SubScoreKey } from '../../../lib/subScoreInputs';
import { ChevronDown, ChevronRight } from 'lucide-react';
```

(If `ChevronDown`/`ChevronRight` are already imported from `lucide-react`, skip those two names. The current import block imports `Loader2, Search, BarChart3, TrendingUp, FileDown, Eye, EyeOff`. Add the missing ones.)

- [ ] **Step 3: Add per-row expand state**

Inside `ResultsPanel`, before the early returns, add:

```tsx
  const [expanded, setExpanded] = useState<Record<string, Set<SubScoreKey>>>({});
  const toggleExpand = (ticker: string, key: SubScoreKey) => {
    setExpanded((prev) => {
      const next = { ...prev };
      const set = new Set(next[ticker] ?? []);
      if (set.has(key)) set.delete(key); else set.add(key);
      next[ticker] = set;
      return next;
    });
  };
```

- [ ] **Step 4: Render the 4 sub-score columns in the table header**

In the table header `<tr>` (around line 396, after the existing Score cell), add 4 `<th>` cells:

```tsx
                  {SUB_SCORE_KEYS.map((key) => (
                    <th
                      key={key}
                      style={{
                        padding: '10px 14px',
                        fontSize: 11,
                        fontWeight: 600,
                        color: colors.muted,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        textAlign: 'left',
                        whiteSpace: 'nowrap',
                        cursor: 'help',
                      }}
                      title={key === 'trend_score' ? 'Trend strength (ADX, SMA stack, MACD)'
                        : key === 'momentum_score' ? 'Momentum (RSI, ROC, Stoch)'
                        : key === 'volatility_score' ? 'Volatility regime (ATR%, BBW)'
                        : 'Volume confirmation (Vol ratio, MFI)'}
                    >
                      {key === 'trend_score' ? 'Trend' : key === 'momentum_score' ? 'Momentum' : key === 'volatility_score' ? 'Volatility' : 'Volume'}
                    </th>
                  ))}
```

- [ ] **Step 5: Render the 4 sub-score cells in each row body**

In the row body (around line 484, immediately after the existing composite Score cell), add 4 `<td>` cells:

```tsx
                    {SUB_SCORE_KEYS.map((key) => {
                      const value = row[key];
                      const formatted = value == null ? '--' : Number(value).toFixed(0);
                      const color = value == null ? colors.subtle
                        : Number(value) >= 70 ? colors.accent
                        : Number(value) >= 50 ? colors.warning
                        : colors.danger;
                      const tooltip = getSubScoreTooltip(key, row);
                      const isOpen = expanded[row.ticker]?.has(key) ?? false;
                      return (
                        <td
                          key={key}
                          title={tooltip}
                          onClick={(e) => { e.stopPropagation(); toggleExpand(row.ticker, key); }}
                          style={{
                            padding: '10px 14px',
                            fontSize: 13,
                            fontWeight: 700,
                            color,
                            cursor: 'pointer',
                            fontVariantNumeric: 'tabular-nums',
                          }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            {isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                            {formatted}
                          </span>
                        </td>
                      );
                    })}
```

- [ ] **Step 6: Render the inline expand sub-row**

Still inside the `<tr>`'s `return`, after the sub-score cells (and before the `hasReturnCol` block), add a `<td colSpan={...}>` sub-row. To keep the implementation simple, render the expand content as a second `<tr>` that is inserted conditionally. Replace the start of the row mapping (around line 437, the `results.map((row, idx) => {` line) with a version that also returns a follow-up `<tr>` when any sub-score for that ticker is expanded:

```tsx
              {results.flatMap((row, idx) => {
                const openSet = expanded[row.ticker] ?? new Set<SubScoreKey>();
                const cells = [
                  <tr
                    key={row.ticker}
                    role="button"
                    tabIndex={0}
                    aria-label={`Open detail for ${row.ticker.toUpperCase()}`}
                    onClick={() => onTickerClick(row.ticker)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onTickerClick(row.ticker);
                      }
                    }}
                    style={{
                      borderBottom: idx < results.length - 1 || openSet.size > 0 ? `1px solid ${colors.border}` : 'none',
                      backgroundColor: colors.bg,
                      cursor: 'pointer',
                      transition: 'background-color 150ms ease',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = colors.surfaceRaised; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = colors.bg; }}
                  >
                    <td style={{ padding: '10px 14px', fontSize: 14, fontWeight: 600, color: colors.text }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <TrendingUp size={14} color={colors.accent} />
                        {row.ticker.toUpperCase()}
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px', fontSize: 13, color: colors.text }}>
                      ${formatPrice(row.close)}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span
                        style={{
                          fontSize: 13, fontWeight: 700,
                          color: row.score == null ? colors.subtle
                            : Number(row.score) >= 70 ? colors.accent
                            : Number(row.score) >= 50 ? colors.warning
                            : colors.danger,
                        }}
                        title={`Composite = base setup (${baseWeight ?? 60}%) + filter match (${100 - (baseWeight ?? 60)}%)`}
                      >
                        {row.score == null ? '--' : Number(row.score).toFixed(0)}
                      </span>
                    </td>
                    {SUB_SCORE_KEYS.map((key) => {
                      const value = row[key];
                      const formatted = value == null ? '--' : Number(value).toFixed(0);
                      const color = value == null ? colors.subtle
                        : Number(value) >= 70 ? colors.accent
                        : Number(value) >= 50 ? colors.warning
                        : colors.danger;
                      const tooltip = getSubScoreTooltip(key, row);
                      const isOpen = openSet.has(key);
                      return (
                        <td
                          key={key}
                          title={tooltip}
                          onClick={(e) => { e.stopPropagation(); toggleExpand(row.ticker, key); }}
                          style={{
                            padding: '10px 14px', fontSize: 13, fontWeight: 700,
                            color, cursor: 'pointer', fontVariantNumeric: 'tabular-nums',
                          }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            {isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                            {formatted}
                          </span>
                        </td>
                      );
                    })}
                    {showAllMetrics && legacyColumns.map((col) => { /* ... unchanged ... */ })}
                    {hasReturnCol && ( /* ... unchanged ... */ )}
                  </tr>,
                ];
                if (openSet.size > 0) {
                  const inputsByKey: Record<SubScoreKey, ReturnType<typeof getSubScoreInputs>> = {
                    trend_score: getSubScoreInputs('trend_score', row),
                    momentum_score: getSubScoreInputs('momentum_score', row),
                    volatility_score: getSubScoreInputs('volatility_score', row),
                    volume_score: getSubScoreInputs('volume_score', row),
                  };
                  cells.push(
                    <tr key={`${row.ticker}-expand`} style={{ backgroundColor: colors.surface }}>
                      <td colSpan={99} style={{ padding: '8px 14px 14px 36px', borderBottom: idx < results.length - 1 ? `1px solid ${colors.border}` : 'none' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
                          {Array.from(openSet).map((key) => (
                            <div key={key}>
                              <div style={{ fontSize: 11, fontWeight: 600, color: colors.muted, textTransform: 'uppercase', marginBottom: 6 }}>
                                {key === 'trend_score' ? 'Trend inputs' : key === 'momentum_score' ? 'Momentum inputs' : key === 'volatility_score' ? 'Volatility inputs' : 'Volume inputs'}
                              </div>
                              {inputsByKey[key].map((inp) => (
                                <div key={inp.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: colors.text, padding: '2px 0' }}>
                                  <span style={{ color: colors.muted }}>{inp.label}</span>
                                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                                    {inp.value == null ? '—' : typeof inp.value === 'number' ? inp.value.toFixed(2) : inp.value}
                                    {inp.note ? <span style={{ color: colors.subtle, marginLeft: 6 }}>({inp.note})</span> : null}
                                  </span>
                                </div>
                              ))}
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>,
                  );
                }
                return cells;
              })}
```

(Replace the `results.map((row, idx) => { ... })` body with the above `flatMap`.)

- [ ] **Step 7: Render the alignment column when `showAlignment` is true**

In the table header (after the 4 sub-score headers), add:

```tsx
                  {showAlignment && (
                    <th style={{ padding: '10px 14px', fontSize: 11, fontWeight: 600, color: colors.accent, textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'right', whiteSpace: 'nowrap' }}>
                      Δ vs return
                    </th>
                  )}
```

In the row body (after the 4 sub-score cells), add:

```tsx
                    {showAlignment && (
                      <td
                        style={{
                          padding: '10px 14px', fontSize: 13, fontWeight: 600,
                          color: row.score_minus_return == null ? colors.subtle
                            : Number(row.score_minus_return) >= 0 ? colors.accent
                            : colors.danger,
                          textAlign: 'right', fontVariantNumeric: 'tabular-nums',
                        }}
                        title="Score − normalized return. Small values = score aligns with return."
                      >
                        {row.score_minus_return == null ? '--'
                          : `${Number(row.score_minus_return) >= 0 ? '+' : ''}${Number(row.score_minus_return).toFixed(1)}`}
                      </td>
                    )}
```

- [ ] **Step 8: Add `showAlignment` and `baseWeight` to the destructure**

In the `ResultsPanel` props destructure (around line 62), add `showAlignment = false, baseWeight = 60` to the function signature. Pass `showAlignment` from `ScreenerBuilder.tsx` (Task 11).

- [ ] **Step 9: Run typecheck and tests**

Run: `cd frontend && npx tsc -b --noEmit && cd frontend && npm test`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/app/ScreenerBuilder/ResultsPanel.tsx
git commit -m "feat(screener): sub-score columns, tooltips, inline expand, alignment column"
```

---

## Task 11: Frontend — `TickerDetailDrawer` "Scoring breakdown" section

**Files:**
- Modify: `frontend/src/pages/app/ScreenerBuilder/TickerDetailDrawer.tsx`

**Interfaces added:**
- `TickerDetailDrawerProps.baseWeight?: number` (new optional, default 60) — used in the breakdown header.

- [ ] **Step 1: Add the `baseWeight` prop**

In `TickerDetailDrawer.tsx`, find the props interface and add:

```ts
  baseWeight?: number;
```

Add it to the destructure with a default of 60.

- [ ] **Step 2: Add the imports**

At the top of the file, add:

```ts
import { SUB_SCORE_KEYS, getSubScoreInputs, type SubScoreKey } from '../../../lib/subScoreInputs';
```

(If the file already imports from that path, skip this step.)

- [ ] **Step 3: Add the "Scoring breakdown" section above the chart**

Find the JSX block that renders the chart (search for `<CandleStickChart` or whatever chart component is used in the drawer). Immediately before that chart, insert:

```tsx
      <div
        style={{
          padding: '12px 16px',
          borderBottom: `1px solid ${colors.border}`,
          backgroundColor: colors.surface,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>Scoring breakdown</span>
          <span style={{ fontSize: 11, color: colors.muted }}>
            Composite: <strong style={{ color: colors.text }}>{row.score == null ? '—' : Number(row.score).toFixed(0)}</strong>
            {' · '}{baseWeight ?? 60}% base + {100 - (baseWeight ?? 60)}% filter match
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          {SUB_SCORE_KEYS.map((key) => {
            const value = row[key];
            const color = value == null ? colors.subtle
              : Number(value) >= 70 ? colors.accent
              : Number(value) >= 50 ? colors.warning
              : colors.danger;
            const inputs = getSubScoreInputs(key, row);
            return (
              <div
                key={key}
                style={{
                  backgroundColor: colors.bg,
                  border: `1px solid ${colors.border}`,
                  borderRadius: 8,
                  padding: '8px 10px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: colors.muted, textTransform: 'uppercase' }}>
                    {key === 'trend_score' ? 'Trend' : key === 'momentum_score' ? 'Momentum' : key === 'volatility_score' ? 'Volatility' : 'Volume'}
                  </span>
                  <span style={{ fontSize: 16, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>
                    {value == null ? '—' : Number(value).toFixed(0)}
                  </span>
                </div>
                {inputs.map((inp) => (
                  <div key={inp.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '1px 0' }}>
                    <span style={{ color: colors.muted }}>{inp.label}</span>
                    <span style={{ color: colors.text, fontVariantNumeric: 'tabular-nums' }}>
                      {inp.value == null ? '—' : typeof inp.value === 'number' ? inp.value.toFixed(2) : inp.value}
                    </span>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
```

- [ ] **Step 4: Pass `baseWeight` from `ScreenerBuilder.tsx`**

In `ScreenerBuilder.tsx`, find the `<TickerDetailDrawer ... />` mount (search for `TickerDetailDrawer`). Add the prop:

```tsx
              baseWeight={baseWeight}
```

- [ ] **Step 5: Run typecheck and tests**

Run: `cd frontend && npx tsc -b --noEmit && cd frontend && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/app/ScreenerBuilder/TickerDetailDrawer.tsx \
        frontend/src/pages/app/ScreenerBuilder.tsx
git commit -m "feat(screener): Scoring breakdown section in TickerDetailDrawer"
```

---

## Task 12: End-to-end manual verification

**Files:** none. This task runs the dev stack and exercises the feature in a browser.

- [ ] **Step 1: Start the backend**

Run: `cd backend && ./venv/bin/python -m app.main`
Expected: Uvicorn running on http://127.0.0.1:8000.

- [ ] **Step 2: Start the frontend**

In a separate terminal: `cd frontend && npm run dev`
Expected: Vite running on http://localhost:5173.

- [ ] **Step 3: Open the Custom Screener**

Open http://localhost:5173/app/screener. Confirm the page loads with no console errors.

- [ ] **Step 4: Run a baseline scan**

Click "Scan" with default filters. Confirm the results table now shows columns in this order:
**Ticker · Price · Score · Trend · Momentum · Volatility · Volume · Return (if cutoff eligible)**.

- [ ] **Step 5: Hover a sub-score cell**

Hover the "Trend" cell of the top row. Confirm the tooltip shows values like *"ADX 22.40 · SMA(20) 198.30 · SMA(50) 192.10 · Close 201.45 · MACD diff 0.42"*.

- [ ] **Step 6: Click a sub-score cell**

Click the "Trend" cell. Confirm an expanded sub-row appears under the row, showing the trend inputs and their notes (e.g. "ADX 22.40 (peak at 50)"). Click the cell again to collapse.

- [ ] **Step 7: Click a ticker row**

Click anywhere on the row except a sub-score cell. Confirm the `TickerDetailDrawer` opens and contains a "Scoring breakdown" section with 4 sub-score cards (Trend, Momentum, Volatility, Volume) and their inputs.

- [ ] **Step 8: Move sliders and re-scan**

In the Scoring panel:
- Set Trend weight to 100, all others to 0. Re-scan.
- Confirm the sort order changes — stocks with high Trend scores bubble up, stocks with low Trend scores bubble down.

- [ ] **Step 9: Save and reload**

Click "Save" to save the screen as "Test Scoring". Open the Screen Library, find "Test Scoring" under My Screens, load it. Confirm the sliders snap back to 100/0/0/0 (the saved values). Re-scan and confirm the same results.

- [ ] **Step 10: Toggle the alignment diagnostic**

In the Scoring panel, toggle "Show alignment diagnostic". Re-scan. Confirm a new "Δ vs return" column appears at the right of the table. With default weights, the top of the table should have some large positive Δ values (the original inversion). With Trend=100/others=0, the Δ values on the top should shrink.

- [ ] **Step 11: Open a built-in template**

Open the Quant Strategy and Golden Cross templates. Confirm both still scan and the new columns appear. (The "Δ vs return" column should be hidden unless you toggle it on.)

- [ ] **Step 12: Test regression on an old saved screen**

If you have any existing saved screen from before this change, load it. Confirm the sliders default to 60/30/25/20/25 and the scan runs without errors.

- [ ] **Step 13: Stop the dev servers and run the final test pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/ -v && cd frontend && npm test`
Expected: PASS for all tests.

- [ ] **Step 14: Commit (no code changes, but tag a checkpoint)**

```bash
git commit --allow-empty -m "chore(screener): end-to-end verification passed"
```

---

## Self-Review

**Spec coverage:**
- §1 goals 1–6: Tasks 7, 8, 9 (weights exposed + persisted); Task 10 (sub-score columns + tooltips + expand); Task 11 (drawer breakdown); Task 1 (momentum peak shift); Task 10 alignment column + Task 3 backend plumbing (alignment diagnostic); Task 7 (persistence).
- §2.1 composite: Task 2 (no structural change; only adds `sub_weights` to base setup).
- §2.2 base setup: Task 2.
- §2.3 sub-scores: Task 1 (momentum); other sub-scores unchanged.
- §2.4 color thresholds: Tasks 10, 11 (color helpers applied identically in both views).
- §2.5 alignment diagnostic: Task 3 backend, Task 10 frontend.
- §3.1 ScanRequest fields: Task 4.
- §3.2 response fields: already in response; Task 10 surfaces them.
- §3.3 Scoring panel: Tasks 5, 8, 9.
- §3.4 sub-score columns: Task 10.
- §3.5 inline expand: Task 10.
- §3.6 drawer breakdown: Task 11.
- §3.7 alignment column: Task 10.
- §3.8 persistence: Task 7.
- §4 data flow: Tasks 1–4 backend, 5–11 frontend.
- §5.1 backend unit tests: Tasks 1, 2, 3, 4.
- §5.2 frontend unit tests: Tasks 5, 6, 8.
- §5.3 manual e2e: Task 12.
- §5.4 regression: Task 12 step 12.

**Placeholder scan:** none.

**Type consistency:**
- `SubWeights` type is defined in Task 8 and re-imported in Task 9 (named import `DEFAULT_SUB_WEIGHTS`).
- `SubScoreKey` is defined in Task 6 and re-imported in Tasks 8, 10, 11.
- `getSubScoreInputs` is defined in Task 6 and used in Tasks 10 and 11. `getSubScoreTooltip` is defined in Task 6 and used in Task 10.
- `ScreenPreset.baseWeight`, `subWeights`, `showAlignment` are defined in Task 7 and used in Task 9's `savePreset` call and Task 7's load handler.
- Backend `sub_weights` is a `Dict[str, int]` with keys `trend, momentum, volatility, volume`; frontend `SubWeights` matches (Task 6).
- `scanResults` shape: each row carries `score`, `trend_score`, `momentum_score`, `volatility_score`, `volume_score`, all raw indicator columns. `score_minus_return` is present only when `include_alignment=true` (Task 3).

No type mismatches found.
