# Crossover Angle Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add angle-based scoring for crossover filters (e.g., SMA 50 crossed_above SMA 200) so stocks are ranked by crossover strength, not just binary pass/fail.

**Architecture:** A new `compute_cross_angle()` function computes the angle via backward differencing of the gap between two lines, normalized by price. A new `apply_angle_scoring()` function min-max normalizes angles across all results and blends with binary scores. A dedicated slider in the ScoringPanel controls the blend weight.

**Tech Stack:** Python (pandas, numpy), FastAPI, React/TypeScript

## Global Constraints

- All new functions go in `backend/app/services/screening/scoring.py`
- Worker changes in `backend/app/services/agno_screener.py` — the per-ticker `_worker_ta_analysis()` function
- Router changes in `backend/app/routers/screener.py` — `ScanRequest` model + call sites
- Frontend changes in `ScoringPanel.tsx` and `ScreenerBuilder.tsx`
- `angle_weight` defaults to 0 (backward compatible — no behavior change for existing users)
- Angle column naming: `cross_angle__{fast_col}__{slow_col}`

---

### Task 1: Add `compute_cross_angle()` to scoring.py

**Files:**
- Modify: `backend/app/services/screening/scoring.py` (add function at end of file)

**Interfaces:**
- Produces: `compute_cross_angle(fast_series: pd.Series, slow_series: pd.Series, close_series: pd.Series, cross_index: int) -> float`

- [ ] **Step 1: Add the function**

Append to `backend/app/services/screening/scoring.py`:

```python
def compute_cross_angle(
    fast_series: pd.Series,
    slow_series: pd.Series,
    close_series: pd.Series,
    cross_index: int,
) -> float:
    """Compute crossover angle using backward differencing.

    gap(t) = fast(t) - slow(t)
    angle = (gap(cross_index) - gap(cross_index - 1)) / close(cross_index) * 100

    Returns percentage (e.g., 0.5 = 0.5% gap widening per bar).
    """
    if cross_index < 1 or cross_index >= len(fast_series):
        return 0.0
    gap_now = fast_series.iloc[cross_index] - slow_series.iloc[cross_index]
    gap_prev = fast_series.iloc[cross_index - 1] - slow_series.iloc[cross_index - 1]
    close_now = close_series.iloc[cross_index]
    if close_now == 0 or pd.isna(close_now):
        return 0.0
    return float((gap_now - gap_prev) / close_now * 100)
```

- [ ] **Step 2: Verify import**

Check that `compute_cross_angle` is importable from `screening.scoring`:

```bash
cd backend && ./venv/bin/python -c "from app.services.screening.scoring import compute_cross_angle; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/screening/scoring.py
git commit -m "feat: add compute_cross_angle() for crossover angle scoring"
```

---

### Task 2: Modify `compute_filter_match_bonus()` to accept `angle_weight` and tag raw angles

**Files:**
- Modify: `backend/app/services/screening/scoring.py`

**Interfaces:**
- Consumes: `compute_cross_angle()` from Task 1
- Produces: Modified `compute_filter_match_bonus(row, filters, angle_weight=0) -> float` that stores `_raw_angle` on the row when angle data is available

- [ ] **Step 1: Modify the function signature**

Change line 126 from:
```python
def compute_filter_match_bonus(row: pd.Series, filters: Dict[str, Any]) -> float:
```
to:
```python
def compute_filter_match_bonus(row: pd.Series, filters: Dict[str, Any], angle_weight: int = 0) -> float:
```

- [ ] **Step 2: Add angle detection in the cross-condition branch**

Find the cross-condition block (around line 169-183). After the existing `bonuses.append(100.0 if bool(val) else 0.0)` line, add:

```python
                # If angle_weight > 0, also capture the raw angle for
                # post-processing in apply_angle_scoring().
                if angle_weight > 0:
                    angle_col = f"cross_angle__{col}__{ref_col}"
                    if angle_col in row.index:
                        angle_val = row[angle_col]
                        if pd.notna(angle_val):
                            row['_raw_angle'] = angle_val
```

The full block should look like:

```python
            cross_col = _CROSS_COLUMN_NAME(item)
            if cross_col in row.index:
                val = row[cross_col]
                if pd.isna(val):
                    continue
                bonuses.append(100.0 if bool(val) else 0.0)
                # If angle_weight > 0, also capture the raw angle for
                # post-processing in apply_angle_scoring().
                if angle_weight > 0:
                    angle_col = f"cross_angle__{col}__{ref_col}"
                    if angle_col in row.index:
                        angle_val = row[angle_col]
                        if pd.notna(angle_val):
                            row['_raw_angle'] = angle_val
                continue
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/screening/scoring.py
git commit -m "feat: add angle_weight param to compute_filter_match_bonus()"
```

---

### Task 3: Add `apply_angle_scoring()` to scoring.py

**Files:**
- Modify: `backend/app/services/screening/scoring.py`

**Interfaces:**
- Consumes: `_raw_angle` column on DataFrame (set by Task 2)
- Produces: `apply_angle_scoring(df: pd.DataFrame, angle_weight: int) -> pd.DataFrame` — modifies `score` column in-place

- [ ] **Step 1: Add the function**

Append to `backend/app/services/screening/scoring.py`:

```python
def apply_angle_scoring(
    df: pd.DataFrame,
    angle_weight: int,
) -> pd.DataFrame:
    """Post-process scores: replace binary cross scores with angle-based scores.

    Min-max normalizes _raw_angle across all results to 0-100, then blends:
        final_score = (1 - aw) * binary_score + aw * angle_score

    When angle_weight <= 0 or no _raw_angle column exists, returns df unchanged.
    """
    if angle_weight <= 0 or '_raw_angle' not in df.columns:
        return df

    angles = df['_raw_angle'].dropna()
    if angles.empty:
        return df

    min_a, max_a = angles.min(), angles.max()
    if max_a == min_a:
        # All angles identical — assign midpoint score
        df['_angle_score'] = 50.0
    else:
        df['_angle_score'] = (df['_raw_angle'] - min_a) / (max_a - min_a) * 100.0

    aw = max(0, min(100, angle_weight)) / 100.0
    df['score'] = df.apply(
        lambda row: round(
            row['score'] * (1 - aw) + row.get('_angle_score', row['score']) * aw,
            1,
        ) if pd.notna(row.get('_angle_score')) else row['score'],
        axis=1,
    )
    return df
```

- [ ] **Step 2: Verify import**

```bash
cd backend && ./venv/bin/python -c "from app.services.screening.scoring import apply_angle_scoring; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/screening/scoring.py
git commit -m "feat: add apply_angle_scoring() for min-max normalization of crossover angles"
```

---

### Task 4: Compute angle in the worker (`_worker_ta_analysis`)

**Files:**
- Modify: `backend/app/services/agno_screener.py` (around lines 768-800)

**Interfaces:**
- Consumes: `compute_cross_angle()` from scoring.py, `_cross_column_name()` from agno_screener.py
- Produces: `cross_angle__{col}__{ref}` columns on the result dict

- [ ] **Step 1: Add import at top of file**

Find the existing import block and add:
```python
from app.services.screening.scoring import compute_cross_angle
```

- [ ] **Step 2: Add angle computation in the cross-evaluation block**

In `_worker_ta_analysis()`, after the cross boolean is set (around line 788), add angle computation:

```python
            cross_booleans[_cross_column_name(cf)] = bool(last) if pd.notna(last) else False

            # NEW: Compute crossover angle for scoring
            if bool(last) if pd.notna(last) else False:
                # Find the exact bar where the crossover occurred
                if op == 'crossed_above':
                    cross_mask = (col_s > ref_s) & (col_s.shift(1) <= ref_s.shift(1))
                else:
                    cross_mask = (col_s < ref_s) & (col_s.shift(1) >= ref_s.shift(1))
                cross_indices = cross_mask[cross_mask].index
                if len(cross_indices) > 0:
                    cross_idx = df.index.get_loc(cross_indices[-1])
                    angle = compute_cross_angle(col_s, ref_s, df['Close'], cross_idx)
                    angle_col = f"cross_angle__{col}__{ref}"
                    cross_booleans[angle_col] = round(angle, 4)
```

The full block should look like:

```python
        cross_booleans: Dict[str, bool] = {}
        for cf in (cross_filters or []):
            if not isinstance(cf, dict):
                continue
            col = cf.get('column')
            ref = cf.get('reference_column')
            op = cf.get('condition')
            if not (col and ref and op in ('crossed_above', 'crossed_below')):
                continue
            lookback = max(1, int(cf.get('lookback_days', 1)))
            col_s = _ensure_series_on_df(df, col, (custom_params or {}).get(col))
            ref_s = _ensure_series_on_df(df, ref, (custom_params or {}).get(ref))
            if col_s is None or ref_s is None or len(df) <= lookback:
                cross_booleans[_cross_column_name(cf)] = False
                continue
            if op == 'crossed_above':
                crossed = (col_s > ref_s) & (col_s.shift(lookback) <= ref_s.shift(lookback))
            else:  # crossed_below
                crossed = (col_s < ref_s) & (col_s.shift(lookback) >= ref_s.shift(lookback))
            last = crossed.iloc[-1]
            cross_booleans[_cross_column_name(cf)] = bool(last) if pd.notna(last) else False

            # Compute crossover angle for scoring (use 1-bar lookback for angle)
            if bool(last) if pd.notna(last) else False:
                if op == 'crossed_above':
                    cross_mask = (col_s > ref_s) & (col_s.shift(1) <= ref_s.shift(1))
                else:
                    cross_mask = (col_s < ref_s) & (col_s.shift(1) >= ref_s.shift(1))
                cross_indices = cross_mask[cross_mask].index
                if len(cross_indices) > 0:
                    cross_idx = df.index.get_loc(cross_indices[-1])
                    angle = compute_cross_angle(col_s, ref_s, df['Close'], cross_idx)
                    angle_col = f"cross_angle__{col}__{ref}"
                    cross_booleans[angle_col] = round(angle, 4)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agno_screener.py
git commit -m "feat: compute crossover angle in worker for angle-based scoring"
```

---

### Task 5: Add `angle_weight` to router and pass through

**Files:**
- Modify: `backend/app/routers/screener.py`

- [ ] **Step 1: Add `angle_weight` to `ScanRequest`**

Find the `ScanRequest` class (around line 68) and add:
```python
    angle_weight: Optional[int] = 0  # 0-100, how much crossover angle matters vs binary pass/fail
```

- [ ] **Step 2: Pass `angle_weight` to `run_quant_strategy_screener`**

Find the non-AI call (around line 852-864) and add `angle_weight=request.angle_weight`:

```python
                result = await run_in_threadpool(
                    lambda: run_quant_strategy_screener(
                        prompt=request.prompt or "...",
                        cutoff_date=request.cutoff_date,
                        progress_callback=update_progress,
                        log_callback=update_logs,
                        filters=request.filters,
                        base_weight=request.base_weight,
                        sub_weights=request.sub_weights,
                        include_alignment=request.include_alignment,
                        angle_weight=request.angle_weight,  # NEW
                        result_columns=[c.model_dump(exclude_none=True) for c in (request.result_columns or [])],
                    )
                )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/screener.py
git commit -m "feat: add angle_weight to ScanRequest and pass to screener"
```

---

### Task 6: Accept `angle_weight` in `run_quant_strategy_screener` and call `apply_angle_scoring()`

**Files:**
- Modify: `backend/app/services/agno_screener.py`

- [ ] **Step 1: Add `angle_weight` parameter to function signature**

Change line 1533-1538 from:
```python
def run_quant_strategy_screener(prompt: str, cutoff_date: Optional[str] = None, progress_callback=None,
                                log_callback=None, filters: Optional[Dict[str, Any]] = None,
                                base_weight: int = 60,
                                sub_weights: Optional[Dict[str, int]] = None,
                                include_alignment: bool = False,
                                result_columns: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
```
to:
```python
def run_quant_strategy_screener(prompt: str, cutoff_date: Optional[str] = None, progress_callback=None,
                                log_callback=None, filters: Optional[Dict[str, Any]] = None,
                                base_weight: int = 60,
                                sub_weights: Optional[Dict[str, int]] = None,
                                include_alignment: bool = False,
                                angle_weight: int = 0,
                                result_columns: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
```

- [ ] **Step 2: Add import for `apply_angle_scoring`**

Find the existing import block and add:
```python
from app.services.screening.scoring import (
    compute_base_setup_score,
    compute_filter_match_bonus,
    compute_quant_score,
    compute_cross_angle,       # already added in Task 4
    apply_angle_scoring,        # NEW
)
```

- [ ] **Step 3: Call `apply_angle_scoring()` after score computation**

Find the score computation block (around line 1599-1605):

```python
    # Compute hybrid score (60% base setup + 40% filter match) and sort descending.
    tech_df['score'] = tech_df.apply(
        lambda row: compute_quant_score(
            row, filters or {}, base_weight, sub_weights, include_alignment
        )['score'],
        axis=1,
    )
    tech_df = tech_df.sort_values(by='score', ascending=False)
```

Change to:

```python
    # Compute hybrid score (60% base setup + 40% filter match) and sort descending.
    tech_df['score'] = tech_df.apply(
        lambda row: compute_quant_score(
            row, filters or {}, base_weight, sub_weights, include_alignment
        )['score'],
        axis=1,
    )

    # Apply angle-based scoring post-processing (blends binary cross scores
    # with angle-based scores when angle_weight > 0 and angle data exists).
    tech_df = apply_angle_scoring(tech_df, angle_weight)

    tech_df = tech_df.sort_values(by='score', ascending=False)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/agno_screener.py
git commit -m "feat: integrate apply_angle_scoring() into quant strategy screener"
```

---

### Task 7: Frontend — Add angle weight slider to ScoringPanel

**Files:**
- Modify: `frontend/src/pages/app/ScreenerBuilder/ScoringPanel.tsx`

- [ ] **Step 1: Add `angleWeight`, `onAngleWeightChange`, and `hasCrossFilters` props**

Update the `ScoringPanelProps` interface:

```tsx
interface ScoringPanelProps {
  baseWeight: number;
  subWeights: SubWeights;
  showAlignment: boolean;
  angleWeight: number;          // NEW
  hasCrossFilters: boolean;     // NEW
  onBaseWeightChange: (v: number) => void;
  onSubWeightChange: (key: keyof SubWeights, v: number) => void;
  onShowAlignmentChange: (v: boolean) => void;
  onAngleWeightChange: (v: number) => void;  // NEW
  onReset: () => void;
}
```

- [ ] **Step 2: Destructure new props**

In the component function, add to destructuring:
```tsx
  angleWeight, hasCrossFilters,
  onAngleWeightChange,
```

- [ ] **Step 3: Add the new slider after the Volume weight slider**

After the Volume weight `<Field>` block (around line 93), add:

```tsx
          {hasCrossFilters && (
            <Field label="Crossover angle weight" hint="0 = binary pass/fail, 100 = purely angle-based scoring">
              <Slider value={angleWeight} onChange={onAngleWeightChange} min={0} max={100} ariaLabel="Crossover angle weight" />
            </Field>
          )}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/app/ScreenerBuilder/ScoringPanel.tsx
git commit -m "feat: add crossover angle weight slider to ScoringPanel"
```

---

### Task 8: Frontend — Add angleWeight state and hasCrossFilters derivation to ScreenerBuilder

**Files:**
- Modify: `frontend/src/pages/app/ScreenerBuilder.tsx`

- [ ] **Step 1: Add `angleWeight` state**

Find the scoring tunables section (around line 257-261) and add:
```tsx
  const [angleWeight, setAngleWeight] = useState(0);
```

- [ ] **Step 2: Derive `hasCrossFilters`**

Add after the state declarations:
```tsx
  const hasCrossFilters = useMemo(
    () => filters.conditions.some(
      (c) => c.operator === 'crossed_above' || c.operator === 'crossed_below'
    ),
    [filters.conditions],
  );
```

- [ ] **Step 3: Pass new props to ScoringPanel**

Find the `<ScoringPanel>` usage (around line 1340-1352) and add:
```tsx
        <ScoringPanel
          baseWeight={baseWeight}
          subWeights={subWeights}
          showAlignment={showAlignment}
          angleWeight={angleWeight}
          hasCrossFilters={hasCrossFilters}
          onBaseWeightChange={setBaseWeight}
          onSubWeightChange={(key, v) => setSubWeights((prev) => ({ ...prev, [key]: v }))}
          onShowAlignmentChange={setShowAlignment}
          onAngleWeightChange={setAngleWeight}
          onReset={() => {
            setBaseWeight(DEFAULT_BASE_WEIGHT);
            setSubWeights(DEFAULT_SUB_WEIGHTS);
            setShowAlignment(DEFAULT_SHOW_ALIGNMENT);
            setAngleWeight(0);
          }}
        />
```

- [ ] **Step 4: Pass `angle_weight` in scan request body**

Find the scan request body (around line 716-733) and add:
```python
          angle_weight: angleWeight,
```

- [ ] **Step 5: Persist `angleWeight` in draft state**

Find the draft persistence effect (around line 368-397) and add `angleWeight` to the draft object:
```tsx
      const draft = {
        filters,
        screenName,
        cutoffDate,
        sortBy,
        sortOrder,
        maxResults,
        useAi,
        baseWeight,
        subWeights,
        showAlignment,
        angleWeight,        // NEW
        scanId,
        drawerTicker,
        timestamp: Date.now(),
      };
```

Find the restore effect (around line 441-549) and add:
```tsx
          if (typeof draft.angleWeight === 'number') setAngleWeight(draft.angleWeight);
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/app/ScreenerBuilder.tsx
git commit -m "feat: add angleWeight state and hasCrossFilters to ScreenerBuilder"
```

---

### Task 9: Verification

- [ ] **Step 1: Verify backend imports**

```bash
cd backend && ./venv/bin/python -c "
from app.services.screening.scoring import compute_cross_angle, apply_angle_scoring
print('scoring imports OK')
from app.services.agno_screener import run_quant_strategy_screener
print('screener imports OK')
"
```

Expected: both print OK

- [ ] **Step 2: Unit test `compute_cross_angle()`**

```bash
cd backend && ./venv/bin/python -c "
import pandas as pd
from app.services.screening.scoring import compute_cross_angle

# Simulate: fast line at 102, slow at 100, close=101
# gap_now=2, gap_prev=1, angle=(2-1)/101*100 = 0.99%
fast = pd.Series([99, 100, 102])
slow = pd.Series([99, 99, 100])
close = pd.Series([99, 100, 101])
angle = compute_cross_angle(fast, slow, close, 2)
print(f'Angle: {angle:.4f}%')
assert abs(angle - 0.9901) < 0.01, f'Expected ~0.99, got {angle}'
print('PASS')
"
```

Expected: `Angle: 0.9901%` then `PASS`

- [ ] **Step 3: Unit test `apply_angle_scoring()`**

```bash
cd backend && ./venv/bin/python -c "
import pandas as pd
from app.services.screening.scoring import apply_angle_scoring

df = pd.DataFrame({
    'ticker': ['A', 'B', 'C'],
    'score': [100.0, 100.0, 100.0],
    '_raw_angle': [0.5, 1.0, 2.0],
})
result = apply_angle_scoring(df.copy(), 100)
# With angle_weight=100, scores should be min-max normalized angles:
# A: (0.5-0.5)/(2.0-0.5)*100 = 0, B: (1.0-0.5)/(2.0-0.5)*100 = 33.3, C: 100
scores = result['score'].values
assert scores[0] < scores[1] < scores[2], f'Expected ascending, got {scores}'
assert abs(scores[0] - 0.0) < 0.1, f'Expected 0, got {scores[0]}'
assert abs(scores[2] - 100.0) < 0.1, f'Expected 100, got {scores[2]}'
print(f'Scores: {scores}')
print('PASS')

# With angle_weight=0, scores should be unchanged
result2 = apply_angle_scoring(df.copy(), 0)
assert (result2['score'] == 100.0).all()
print('PASS (angle_weight=0 unchanged)')
"
```

Expected: `Scores: [0.0 33.3 100.0]` then `PASS` then `PASS (angle_weight=0 unchanged)`

- [ ] **Step 4: Verify frontend compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30
```

Expected: No type errors

- [ ] **Step 5: Full integration test**

1. Start backend: `cd backend && ./venv/bin/python -m app.main`
2. Start frontend: `cd frontend && npm run dev`
3. Open Custom Screener page
4. Click "Golden Cross" template (SMA 50 crossed_above SMA 200)
5. Verify "Crossover angle weight" slider appears
6. Set slider to 100, set "Base setup vs filter match" to 0
7. Click Scan
8. Verify results are sorted by crossover angle (not all 100s)
9. Set slider back to 0, re-scan
10. Verify results show binary scoring (all passing stocks have same score)
