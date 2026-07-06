# 2026-07-05 — Screener Scoring: Tunable Composite + Sub-Score Transparency

> **Status:** Design (pending user review).
> **Scope:** Custom Screener tab in the AI Stock Screener (`/app/screener` route, served by `backend/app/routers/screener.py` and `backend/app/services/agno_screener.py`).
> **Out of scope:** Dormant Giant tab, QuantGen, Sector Rotation, the AI-agent multi-agent pipeline output formatting, the indicator pipeline (`add_all_ta_features`).

---

## 1. Context

The Custom Screener's results table shows a "Score" column sorted descending. The score is currently:

```python
# backend/app/services/screening/scoring.py:206
def compute_quant_score(row, filters, base_weight=60):
    base  = compute_base_setup_score(row)            # 0–100, 4 sub-scores
    bonus = compute_filter_match_bonus(row, filters) # 0–100, "how far past filters"
    return round(base * 0.60 + bonus * 0.40, 1)
```

`base_setup` is built from 4 sub-scores (`trend`, `momentum`, `volatility`, `volume`) with **hard-coded weights** of 30/25/20/25. Three of the four sub-scores are *peaked at neutral readings* (RSI ≈ 55, ATR% 1–5, volume ratio 1–2×). Only `trend_score` actually rewards directional strength.

The "Return (YYYY-MM-DD)" column next to the score is a **buy-and-hold return from a past cutoff date** — a different point in time. The score says "this stock has a clean current technical setup"; the return says "this stock performed from date X to now." With the current weights, a Golden-Cross or Mean-Reversion screen rewards *pre-breakout quiet stocks*, which is exactly why the user sees the apparent inversion: high score, negative return.

**No one told the user this**, because the column is labeled just "Score" with a green/amber/red color and a `toFixed(0)` number.

**Goals (in priority order):**

1. Make the score **user-controllable** per screen (base_weight is already plumbed; expose it. Add per-sub-score weights.)
2. Show the **4 sub-scores** in the results table so the user can see *why* a stock scored the way it did.
3. Show the **indicator inputs that fed each sub-score** (e.g. ADX, SMA(20), SMA(50), MACD-diff for trend) — first as a hover tooltip, then on row-expand, and full breakdown in the TickerDetailDrawer.
4. **Fix the momentum sub-score** so its peak is in a directional band (RSI ≈ 65) rather than neutral (RSI 55), so a high score correlates with stocks that historically have room to run.
5. Add an opt-in **alignment diagnostic** (`composite - normalized_return`) so the user can verify their weights do what they want.
6. **Persist** the weights in saved screens.

**Non-goals:** No ML model that predicts forward return. No change to the Return column. No change to filter conditions, the indicator pipeline, or any other tool.

---

## 2. Math

### 2.1 Composite (no structural change)

```
composite = base_setup * (base_weight/100) + filter_match_bonus * ((100 - base_weight)/100)
```

- `base_weight` is 0–100. **Default 60** (preserves current behavior).
- `filter_match_bonus` is unchanged.
- Round to 1 decimal place (preserves current behavior).

### 2.2 Base setup (new: per-sub-score weights)

```
base_setup = (trend_score * w_trend + momentum_score * w_momentum
              + volatility_score * w_volatility + volume_score * w_volume)
             / (w_trend + w_momentum + w_volatility + w_volume)
```

- Default sub-weights match today's hard-coded values: **`{trend: 30, momentum: 25, volatility: 20, volume: 25}`**.
- Each weight is a non-negative integer.
- Normalized by their sum, so the user doesn't have to make them sum to 100.
- If all 4 are zero, fall back to equal weights (`{1, 1, 1, 1}`) so we never divide by zero.

### 2.3 The 4 sub-scores

Three of the four sub-scores are **unchanged**. Only `momentum_score` changes.

**`trend_score` (unchanged)** — peaks at a *strong, established* uptrend. Inputs: `trend_adx`, `trend_sma_fast`, `trend_sma_slow`, `close`, `trend_macd_diff`. Weights: ADX 40% / SMA-stack 35% / MACD-sign 25%.

**`volatility_score` (unchanged)** — peaks at "healthy" mid-band vol. Inputs: `volatility_atr`, `close`, `volatility_bbw`. Weights: ATR-score 50% / BBW-score 50%.

**`volume_score` (unchanged)** — peaks at "confirming" volume, not blow-off. Inputs: `volume_ratio`, `volume_mfi`. Weights: vol_ratio_score 50% / MFI-score 50%.

**`momentum_score` (CHANGED)** — peak moves from RSI 55 to RSI 65; ROC contributes directionally.

```python
# New:
rsi_score   = 100 - min(abs(rsi - 65), 35) * (100 / 35)   # triangle: peak 65, zero at 30 or 100
roc_score   = 50 + max(-50, min(50, roc * 5))             # +/- 50 around 0 roc
stoch_score = 100 - min(abs(stoch - 55), 45) * (100 / 45) # triangle: peak 55, zero at 10 or 100
momentum_score = rsi_score*0.45 + roc_score*0.30 + stoch_score*0.25
```

Why: the old formula *rewards quiet, neutral readings* — exactly the pre-breakout state that goes nowhere in the short term. Moving the RSI peak to 65 (the historically most profitable "strong with room" zone) and letting a negative ROC subtract makes a high momentum_score correlate with stocks that have positive momentum *and* room to run.

### 2.4 Sub-score color thresholds (frontend only)

- green ≥ 70, amber 50–69, red < 50.
- Applied to the composite **and** to each of the 4 sub-scores in the table.

### 2.5 Alignment diagnostic (new, opt-in)

When the request sets `include_alignment: true`, the backend adds a per-row field:

```python
score_minus_return = round(composite - normalize_return(return_pct), 1)
# normalize_return = clip(return_pct, -100, 100)
```

**Sort key is still composite** — the diagnostic is a *measurement*, not a replacement. A user can eyeball whether the top of the table has small `score_minus_return` values (good alignment) or large positive ones (high score, low return — current behavior).

The diagnostic is opt-in (off by default) because it adds a column to the table and most users won't care.

---

## 3. UI & API surface

### 3.1 New request fields on `ScanRequest` (`backend/app/routers/screener.py:68`)

```python
class ScanRequest(BaseModel):
    # ... existing fields ...
    base_weight: Optional[int] = 60                # already exists
    sub_weights: Optional[Dict[str, int]] = None   # NEW. Keys: trend, momentum, volatility, volume
    include_alignment: Optional[bool] = False      # NEW. Adds score_minus_return per row.
```

`sub_weights` is validated server-side:
- Each of the 4 keys is an int ≥ 0.
- Missing keys default to the current values (`{30, 25, 20, 25}`).
- If all 4 resolve to 0, the service falls back to equal weights (no user error).

### 3.2 New per-row fields in the response

The backend already attaches `trend_score`, `momentum_score`, `volatility_score`, `volume_score` to each row (`agno_screener.py:1408-1412`). The `ta_to_friendly` map already exposes the raw indicator values. **No backend change is required to surface the sub-scores and the raw inputs in the UI** — they are already in the response payload. The frontend just needs to render them.

New field: `score_minus_return` (only present when `include_alignment: true`).

### 3.3 New "Scoring" panel in the filter sidebar (frontend)

A new collapsible section at the bottom of `ScreenerBuilder/FilterPicker.tsx`, titled **"Scoring"**. Contains:

- **1 slider** for `base_weight` (0–100, default 60, label "Base setup vs filter match"). Tooltip: "Weight of the technical setup quality score vs the filter match bonus. 0 = pure filter match, 100 = pure setup, 60 = balanced (default)."
- **4 sliders** for sub-weights (`trend`, `momentum`, `volatility`, `volume`, each 0–100, defaults 30/25/20/25). Tooltip: "How much each sub-score contributes to the base setup score. Normalized to sum, so you can move them freely. Set one to 100 to ignore the other three."
- **1 toggle** for "Show alignment diagnostic" (off by default). When on, the table adds a small "Δ vs return" column.
- **A "Reset to defaults" link** that snaps everything back to current values.

Sliders use the same component as the existing filter-picker controls (shadcn `Slider`). Each slider has a label and a numeric value to the right (`30 / 50`).

When a slider moves, the next `/api/screener/scan` request sends the new values. There is no live re-score (that would be too expensive); scores recompute on Scan.

### 3.4 Sub-score columns in the results table (frontend)

`ResultsPanel.tsx:438-494` is where the composite Score cell is currently rendered. We add 4 new columns immediately after it:

| header | key | format | color |
|---|---|---|---|
| Trend | `trend_score` | `toFixed(0)` | green ≥ 70, amber 50–69, red < 50 |
| Momentum | `momentum_score` | `toFixed(0)` | same |
| Volatility | `volatility_score` | `toFixed(0)` | same |
| Volume | `volume_score` | `toFixed(0)` | same |

Each sub-score cell has a `title=` (native browser tooltip) with a one-line summary, e.g. for trend: *"ADX 22.4 (peak 50) · close > SMA20 > SMA50 · MACD-hist +0.4"*. The summary is built in the frontend from the row's raw indicator values (which are already in the response payload — no new backend work).

### 3.5 Inline expand for sub-score components (α + γ)

Clicking a sub-score cell toggles an expanded sub-row *underneath* the stock's row. The sub-row is a 2-column key/value list of the raw indicator inputs that fed that sub-score, plus a one-line legend explaining the peak.

Example for the Trend sub-score:

```
ADX          22.4    (peak at 50)
SMA(20)     198.30   (close > fast > slow = 100)
SMA(50)     192.10
Close       201.45
MACD diff   +0.42    (positive = 100)
```

The sub-row also shows the legend from §2.3, e.g. *"Trend 60: weak ADX, price above both SMAs, MACD positive."*

Each of the 4 sub-scores expands its own set of inputs. The expanded state is per-row per-sub-score (so a user can have 2 trend cells expanded at once). State is local component state — no need to persist across reloads.

### 3.6 TickerDetailDrawer "Scoring breakdown" (γ)

`TickerDetailDrawer.tsx` opens on row click. We add a **"Scoring breakdown"** section above the existing chart:

- A small 4-row mini-table: `Trend 60 · Momentum 95 · Volatility 50 · Volume 80` (each colored, each is a `Button` that copies that sub-score to clipboard as a quick reference).
- Below each, a 2-column input/legend list (same data as the inline expand, but in a less space-constrained layout).
- A "Composite: 78" header at the top, with the `base_weight` shown in small grey text ("60% base + 40% filter match").

### 3.7 Alignment diagnostic column (when enabled)

One extra column, header `"Δ vs return"`, value formatted as `±N.N` with the same green/red coloring as the Return column. Width: ~80px, right-aligned.

### 3.8 Saved-screen persistence

`useScreens.ts` defines `ScreenPreset`. We extend it (additive, no breaking change):

```ts
interface ScreenPreset {
  // ... existing fields ...
  baseWeight?: number;                        // 0–100, default 60
  subWeights?: {                              // 0–100 each, defaults 30/25/20/25
    trend: number;
    momentum: number;
    volatility: number;
    volume: number;
  };
  showAlignment?: boolean;                    // default false
}
```

`useScreens.ts:107-112 savePreset` and `:170-171` (template load path) need to default these fields when not set, so old saved screens continue to work.

`ScreenLibraryModal.tsx:42-57 handleLoadTemplate` and `:59-62 handleLoadPreset` already copy filter/sort/maxResults/useAi; we extend them to also copy `baseWeight`, `subWeights`, `showAlignment`.

`ScreenerBuilder.tsx:198 savePreset` is the call site that hands the preset to the hook; we extend the call to include the new fields.

When a saved screen is loaded, the slider values are populated from the preset. When the user clicks "Scan", the request carries the current slider values (not the preset's), so the user can re-tune and re-save.

---

## 4. Data flow & boundaries

- **Backend:**
  - `screening/scoring.py`: add `sub_weights: Dict[str, int] | None = None` parameter to `compute_base_setup_breakdown` (default None = use current weights). Replace the hard-coded sub-weights in the `total =` line with the normalized user-supplied weights.
  - `screening/scoring.py`: add `include_alignment: bool = False` parameter to `compute_quant_score` and propagate it up to `run_quant_strategy_screener` and `run_quant_strategy_screener_with_ai` so the response can include `score_minus_return`.
  - `agno_screener.py:1395-1397`: pass `sub_weights` and `include_alignment` through to `compute_quant_score`; when `include_alignment` is true, attach `score_minus_return` to each result record using the row's `return_pct` (which the enrich step already produces).
  - `routers/screener.py:68`: add `sub_weights` and `include_alignment` to `ScanRequest`. Validate sub_weights is `Dict[str, int] | None` with keys in `{trend, momentum, volatility, volume}` and each value ≥ 0.
- **Frontend:**
  - `ScreenerBuilder/FilterPicker.tsx`: add the Scoring panel (1 + 4 sliders + 1 toggle + reset).
  - `ScreenerBuilder.tsx`: state for the 6 controls; pass them into the scan request body; pass them into `savePreset`; read them back from a loaded preset.
  - `ScreenerBuilder/ResultsPanel.tsx`: add 4 sub-score columns, the `title=` tooltips, the inline expand, the alignment column (when enabled), the per-row expand state.
  - `ScreenerBuilder/TickerDetailDrawer.tsx`: add the Scoring breakdown section.
  - `hooks/useScreens.ts` and `pages/app/ScreenerBuilder/ScreenLibraryModal.tsx`: extend the types and load/save paths for the new fields.
  - `data/screenerTemplates.ts`: add the new optional fields to `ScreenTemplate` and set them on the existing built-in templates (defaults: baseWeight 60, subWeights default, showAlignment false; some templates can set showAlignment true to be useful out of the box — TBD with user).

**Boundaries:**
- The backend never sends the "raw inputs that fed the sub-score" — it already sends the raw indicator values (e.g. `trend_adx`, `trend_sma_fast`) as part of the response. The frontend is responsible for knowing which inputs feed which sub-score and building the tooltip / expand / drawer from them. The mapping is documented in §2.3 and lives in a small frontend helper module (`screener/subScoreInputs.ts`).
- The alignment diagnostic is purely a frontend-visible column; the backend just attaches `score_minus_return` and the frontend renders it.

---

## 5. Verification (end-to-end)

### 5.1 Unit tests (backend)

- `tests/test_scoring.py` (NEW, or add to existing if it exists):
  - `test_compute_base_setup_breakdown_default_weights` — current behavior preserved when `sub_weights=None`.
  - `test_compute_base_setup_breakdown_with_user_weights` — confirms the sub-weights change the result.
  - `test_compute_base_setup_breakdown_all_zero_weights` — falls back to equal weights, no division by zero.
  - `test_momentum_score_rsi_peak_at_65` — RSI 65 returns max; RSI 30 or 100 returns 0; RSI 50 returns ~43.
  - `test_momentum_score_roc_negative_lowers_score` — negative ROC drags momentum_score down; positive ROC raises it.
  - `test_compute_quant_score_alignment_diagnostic` — when `include_alignment=True`, the returned value carries the alignment.

### 5.2 Unit tests (frontend)

- `ResultsPanel.test.tsx` (if it exists, else new): renders 4 sub-score columns.
- `subScoreInputs.test.ts` (NEW): the helper that maps sub-score → inputs returns the right keys for a sample row.
- `TickerDetailDrawer.test.tsx` (if it exists): the Scoring breakdown section renders.

### 5.3 Manual end-to-end (with the dev stack)

1. Run the backend (`cd backend && ./venv/bin/python -m app.main`) and frontend (`cd frontend && npm run dev`).
2. Open the Custom Screener. Run a scan with no filters. Confirm the table has columns: Ticker / Price / Score / Trend / Momentum / Volatility / Volume / Return (if cutoff eligible).
3. Hover the Trend sub-score cell — confirm the tooltip shows "ADX … · SMA(20) … · SMA(50) … · MACD-diff …".
4. Click the Trend sub-score cell — confirm the inline expand appears with the raw inputs and the legend.
5. Click the ticker row — confirm the TickerDetailDrawer shows the Scoring breakdown section with all 4 sub-scores and their inputs.
6. Open the Scoring panel in the filter sidebar. Move the `momentum` weight from 25 → 0 and `trend` from 30 → 100. Re-scan. Confirm: stocks with high Trend scores bubble up; stocks with low Trend scores bubble down.
7. Save the screen. Reload. Open it from My Screens. Confirm the sliders snap back to the saved values.
8. Toggle "Show alignment diagnostic". Re-scan. Confirm the "Δ vs return" column appears. Confirm: with default weights, some Δ values are large and positive (the inversion the user observed). With `momentum=0, trend=100`, the Δ values should shrink on the top of the table.
9. Open the Quant Strategy and Golden Cross built-in templates — confirm they still scan and the new columns appear.

### 5.4 Regression checks

- A user with an old saved screen that has *no* `baseWeight` / `subWeights` / `showAlignment` continues to work. Defaults: baseWeight 60, subWeights {30,25,20,25}, showAlignment false. The composite score and sort order for an old screen should match what the user sees today (modulo the momentum peak change, which is a one-time intentional shift).
- The AI path (`run_quant_strategy_screener_with_ai`) gets the new `sub_weights` and `include_alignment` plumbed the same way as the non-AI path. The AI agent's narrative report is not changed.
- No change to the Return column math, the indicator pipeline, the filter parsers, or the Dormant Giant / Sector Rotation tools.

---

## 6. Out-of-scope follow-ups (for the next brainstorm)

- Display the indicator inputs *on the chart* (e.g. overlay the SMA(20)/SMA(50) the trend score is using) so the user can see the inputs in context. Useful but a separate piece of work.
- Backtest that picks sub-weights that maximize forward return on historical data. Useful for default tuning but requires a labeling campaign and is a separate piece of work.
- "Compare 2 stocks" side-by-side panel with both scoring breakdowns. Useful but separate.

---

## 7. Spec self-review

- **Placeholders:** None. Each section is concrete.
- **Internal consistency:** §2 math matches §3.2 ("no backend change to surface sub-scores and raw inputs") and §3.3 ("sliders trigger a new scan"). §3.8 (persistence) matches §3.2 (the new fields are just optional request fields). §5 verification covers the user-visible behaviors promised in §1 goals.
- **Scope:** Single coherent feature. No decomposition needed.
- **Ambiguity:** The "raw inputs" mapping is documented in §4 and pinned to a frontend helper module. The `score_minus_return` formula is pinned in §2.5. The fallback when all sub-weights are zero is pinned in §2.2.
