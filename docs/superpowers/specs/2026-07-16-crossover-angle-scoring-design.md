# Crossover Angle Scoring — Design Spec

## Context

The Custom Screener's composite scoring scheme blends a "base setup" score (general technical health: trend, momentum, volatility, volume) with a "filter match" score (how well a stock satisfies the user's specific filters). The default blend is 60% base setup + 40% filter match.

For crossover filters (e.g., SMA 50 crossed_above SMA 200), the filter match score is **binary**: 100 if the crossover occurred, 0 if not. At 100% filter match (base_weight=0), all passing stocks get the same score — there is no differentiation by *how strong* the crossover is.

This spec adds **angle-based scoring**: the angle between the two lines at the crossover point, computed via backward differencing and normalized by price, becomes the scoring signal. A dedicated slider lets users blend between traditional binary scoring and angle-based scoring.

## Architecture

### Backend

**New function** `compute_cross_angle()` in `backend/app/services/screening/scoring.py`:

```python
def compute_cross_angle(
    fast_series: pd.Series,
    slow_series: pd.Series,
    close_series: pd.Series,
    cross_index: int,
) -> float:
    """
    Compute crossover angle using backward differencing.
    
    gap(t) = fast(t) - slow(t)
    angle = (gap(cross_index) - gap(cross_index - 1)) / close(cross_index) * 100
    
    Returns percentage (e.g., 0.5 = 0.5% gap widening per bar).
    """
    gap_now = fast_series.iloc[cross_index] - slow_series.iloc[cross_index]
    gap_prev = fast_series.iloc[cross_index - 1] - slow_series.iloc[cross_index - 1]
    close_now = close_series.iloc[cross_index]
    return (gap_now - gap_prev) / close_now * 100
```

**Modified** `compute_filter_match_bonus()` — accepts new `angle_weight` param. For cross conditions, stores raw angle on the row as `_raw_angle` alongside the binary pass/fail.

**New function** `apply_angle_scoring()` in `scoring.py`:
- Min-max normalizes `_raw_angle` across all results to 0-100
- Blends: `final_score = (1 - aw) * binary_score + aw * angle_score`
- Called in `run_quant_strategy_screener()` after initial score computation

**Worker changes** in `backend/app/services/agno_screener.py`:
- When a crossover is detected, also compute the angle via `compute_cross_angle()`
- Store as column `cross_angle__{fast_col}__{slow_col}` on the result row

**Router changes** in `backend/app/routers/screener.py`:
- Add `angle_weight: int = 0` to `ScanRequest` model
- Pass through to `run_quant_strategy_screener()`

### Frontend

**New slider** in `frontend/src/pages/app/ScreenerBuilder/ScoringPanel.tsx`:
- Label: "Crossover angle weight"
- Hint: "0 = binary pass/fail, 100 = purely angle-based scoring"
- Only visible when at least one crossover filter is active (`hasCrossFilters` prop)
- Range: 0-100, default 0

**State** in `frontend/src/pages/app/ScreenerBuilder.tsx`:
- New `angleWeight` state (default 0)
- Derive `hasCrossFilters` from filter conditions (any with `crossed_above` or `crossed_below`)
- Pass `angle_weight: angleWeight` in scan request body

## Data Flow

1. User sets up crossover filter + adjusts angle weight slider
2. Frontend sends `angle_weight` in POST `/api/screener/scan`
3. Worker computes cross booleans + cross angles per ticker
4. Aggregator collects all results into DataFrame
5. `compute_quant_score()` runs per-row (binary scoring as before)
6. `apply_angle_scoring()` post-processes: min-max normalizes angles, blends with binary scores
7. Results sorted by final score, returned to frontend

## Files Modified

| File | Change |
|------|--------|
| `backend/app/services/screening/scoring.py` | Add `compute_cross_angle()`, `apply_angle_scoring()`, modify `compute_filter_match_bonus()` |
| `backend/app/services/agno_screener.py` | Compute angle in worker, store as result column |
| `backend/app/routers/screener.py` | Add `angle_weight` to `ScanRequest`, pass through |
| `frontend/src/pages/app/ScreenerBuilder/ScoringPanel.tsx` | Add angle weight slider, `hasCrossFilters` prop |
| `frontend/src/pages/app/ScreenerBuilder.tsx` | Add `angleWeight` state, derive `hasCrossFilters`, pass to backend |

## Verification

1. **Unit test**: Call `compute_cross_angle()` with known series, verify angle matches expected backward-differencing value
2. **Integration test**: Run a scan with SMA 50/200 crossover filter, angle_weight=100, verify scores are non-binary and sorted by angle
3. **Edge case**: angle_weight=0 → scores identical to current binary behavior
4. **Edge case**: no crossover filters active → angle slider hidden, scoring unchanged
5. **Edge case**: all angles identical → min-max returns 50 for all, blending still works
