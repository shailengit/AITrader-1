# Auto-Computed Parameter Ranges with Source-Value Tracking

## Problem

In the QuantGen Builder, users switch to **Optimize** mode and must manually set `start`, `stop`, and `step` for every parameter. When the strategy code is regenerated or edited, these ranges are either preserved from stale values or recalculated blindly, leading to a poor UX. Users want ranges to **auto-populate** based on the current parameter values in code, with a ±50% exploration window, and to **reset intelligently** when a parameter value changes.

## Goal

1. Automatically compute `start`, `stop`, and `step` from each parameter's value in the strategy code.
2. Reset a parameter's range **only** when that specific parameter's value changes in code.
3. Preserve manually-edited ranges for parameters whose code values haven't changed.

## Design

### 1. Data Model

Extend `ParamRange` with a hidden `sourceValue` field:

```ts
interface ParamRange {
  name: string;
  start: number;
  stop: number;
  step: number;
  sourceValue?: number; // The code value that last generated this range
}
```

`sourceValue` is used only in the frontend state machine. It is **not** sent to the backend API.

### 2. Parameter Parsing & Range Computation

When parsing the `# Parameters` section from code, for each `name = value` pair:

| Condition | Action |
|---|---|
| New parameter (not in existing `optParams`) | Compute auto range, store `sourceValue = value` |
| Existing parameter, `sourceValue === value` | Keep existing range (preserves manual edits) |
| Existing parameter, `sourceValue !== value` or missing | Recompute auto range, update `sourceValue = value` |

**Auto-range formula** for parameter value `v`:

- **Integer literal** (e.g., `sma_window = 20`):
  - `start = max(1, round(v * 0.5))`
  - `stop  = max(1, round(v * 1.5))`
  - `step  = max(1, round(v * 0.1))`

- **Float literal** (e.g., `threshold = 1.5`):
  - `start = max(0.1, round(v * 0.5, 2))`
  - `stop  = max(0.1, round(v * 1.5, 2))`
  - `step  = max(0.1, round(v * 0.1, 2))`

Rounding to 2 decimal places for floats. Minimum floors prevent degenerate ranges (e.g., `0` or negative).

### 3. UI Behavior

- The **Optimization Config** panel (`OptimizationConfig.tsx`) remains visually unchanged.
- Parameters are listed as editable rows; users can still override any field.
- If the user edits a range, the `sourceValue` remains unchanged. On the next code parse, if the parameter value in code hasn't changed, the manual edit is preserved.
- When a parameter value changes in the code editor (e.g., `sma_window = 20` → `sma_window = 30`), that parameter's range recalculates to ±50% of 30. Other parameters are unaffected.

### 4. Edge Cases

| Scenario | Handling |
|---|---|
| Value = 0 (integer) | `start=1`, `stop=1`, `step=1` (minimum floor) |
| Value = 0.0 (float) | `start=0.1`, `stop=0.1`, `step=0.1` |
| Very small value (e.g., 2) | Integer: `start=1`, `stop=3`, `step=1` |
| Legacy saved state (no `sourceValue`) | Treated as stale; recomputed on next parse |
| Parameter removed from code | Parameter row disappears from panel; state drops naturally via filtering |

### 5. Files to Modify

1. **`frontend/src/pages/QuantGen/Builder.tsx`**
   - Update `ParamRange` interface to add `sourceValue?: number`.
   - Rewrite the `useEffect` that parses parameters (lines 689–732) to use source-value tracking and the new ±50% formulas.
   - Ensure `sourceValue` is stripped from the payload before sending to `/api/optimize`.

2. **`frontend/src/components/quantgen/OptimizationConfig.tsx`**
   - Update `ParamRange` interface to add `sourceValue?: number` (shared type).

### 6. Verification

1. Generate a strategy with `# Parameters` section containing `sma_window = 20` and `rsi_threshold = 30.0`.
2. Switch to **Optimize** mode.
3. Confirm `sma_window` range is `10–30` with step `2`.
4. Confirm `rsi_threshold` range is `15.0–45.0` with step `3.0`.
5. Manually change `sma_window` stop to `50`.
6. Edit code to `sma_window = 25`.
7. Confirm `sma_window` resets to `13–38` step `3`, and `rsi_threshold` remains at its previous value.
8. Run optimization and confirm the API payload contains only `name`, `start`, `stop`, `step` (no `sourceValue`).
