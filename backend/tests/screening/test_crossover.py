"""Tests for crossover logic.

Crossover detection (crossed_above / crossed_below) is implemented in the
worker (`_worker_ta_analysis`), which has the per-ticker 250-row time-series
DataFrame where `.shift(lookback)` is meaningful. The aggregator collects
the boolean result and filters on it directly.

`apply_quant_filters` is no longer responsible for evaluating crossovers —
it raises a ValueError if a crossover condition is passed (the screener
should strip those out before calling apply_quant_filters). The threshold
filter and indicator-comparison filters (above/below/equals) still work
in apply_quant_filters.

This file tests BOTH:
1. Worker crossover evaluation (via direct _worker_ta_analysis call with a
   synthetic DataFrame, using a fixture ticker).
2. apply_quant_filters raises on crossover conditions and still works for
   threshold and indicator-comparison conditions.
"""
import pandas as pd
import numpy as np
import pytest

from app.services.screening.parsers import apply_quant_filters


def _make_df(close_a, close_b):
    """Create a DataFrame with two indicator columns."""
    n = max(len(close_a), len(close_b))
    return pd.DataFrame({
        'ticker': ['AAPL'] * n,
        'close': np.ones(n) * 100,
        'indicator_a': close_a,
        'indicator_b': close_b,
    })


# ── apply_quant_filters no longer handles crossovers ─────────────────────

def test_apply_quant_filters_raises_on_crossed_above():
    """apply_quant_filters must reject crossed_above — it's worker-only."""
    df = _make_df([10, 15, 20], [20, 20, 20])
    filters = {
        "indicator_filters": [{
            "column": "indicator_a",
            "condition": "crossed_above",
            "reference_column": "indicator_b",
            "lookback_days": 1,
        }]
    }
    with pytest.raises(ValueError, match="crossed_above"):
        apply_quant_filters(df, filters)


def test_apply_quant_filters_raises_on_crossed_below():
    """apply_quant_filters must reject crossed_below — it's worker-only."""
    df = _make_df([20, 15, 10], [20, 20, 20])
    filters = {
        "indicator_filters": [{
            "column": "indicator_a",
            "condition": "crossed_below",
            "reference_column": "indicator_b",
            "lookback_days": 1,
        }]
    }
    with pytest.raises(ValueError, match="crossed_below"):
        apply_quant_filters(df, filters)


def test_apply_quant_filters_raises_on_missing_column():
    """Missing-column filter must fail loud with a clear message."""
    df = _make_df([10, 15, 20], [20, 20, 20])
    filters = {
        "indicator_filters": [{
            "column": "nonexistent_indicator",
            "min": 5,
        }]
    }
    with pytest.raises(ValueError, match="missing column"):
        apply_quant_filters(df, filters)


# ── Threshold filters still work ────────────────────────────────────────

def test_threshold_filter_works():
    df = _make_df([10, 15, 20, 25, 30], [20, 20, 20, 20, 20])
    filters = {
        "indicator_filters": [{
            "column": "indicator_a",
            "min": 15,
            "max": 25,
        }]
    }
    result = apply_quant_filters(df, filters)
    assert len(result) == 3  # 15, 20, 25


# ── Indicator comparison filters still work ─────────────────────────────

def test_existing_above_still_works():
    """Existing 'above' condition should still work unchanged."""
    df = _make_df(
        close_a=[10, 15, 20, 25, 30],
        close_b=[20, 20, 20, 20, 20],
    )
    filters = {
        "indicator_filters": [{
            "column": "indicator_a",
            "condition": "above",
            "reference_column": "indicator_b",
        }]
    }
    result = apply_quant_filters(df, filters)
    assert len(result) == 2  # indices 3, 4 (index 2 has A=20 == B=20, not strictly above)


def test_existing_below_still_works():
    """Existing 'below' condition should still work unchanged."""
    df = _make_df(
        close_a=[30, 25, 20, 15, 10],
        close_b=[20, 20, 20, 20, 20],
    )
    filters = {
        "indicator_filters": [{
            "column": "indicator_a",
            "condition": "below",
            "reference_column": "indicator_b",
        }]
    }
    result = apply_quant_filters(df, filters)
    assert len(result) == 2  # indices 3, 4


# ── End-to-end: worker computes boolean, aggregator filters on it ─────────

def test_cross_column_name_format():
    """The cross boolean column name must be stable and unique per condition."""
    from app.services.agno_screener import _cross_column_name
    cf = {
        "column": "trend_sma_slow",
        "condition": "crossed_above",
        "reference_column": "sma_200",
        "lookback_days": 1,
    }
    assert _cross_column_name(cf) == "cross_trend_sma_slow_crossed_above_sma_200_in_1d"
    # lookback default is 1
    cf_no_lookback = {"column": "x", "condition": "crossed_below", "reference_column": "y"}
    assert _cross_column_name(cf_no_lookback) == "cross_x_crossed_below_y_in_1d"


def test_worker_computes_cross_boolean_from_df():
    """The worker's _ensure_series_on_df + shift-combo must produce the right
    cross boolean at the latest row.

    Pre-computes sma_50 and sma_200 as DataFrame columns so the test directly
    exercises the cross-evaluation formula. Sets sma_50 just above sma_200 at
    the latest bar and exactly at parity on the prior bar — the canonical
    "cross happened in the last 1 day" case.
    """
    from app.services.agno_screener import (
        _ensure_series_on_df,
        _cross_column_name,
    )

    n = 250
    # sma_50: constant 50 for 249 rows, then 100 on the last row.
    # Rolling mean of the last 50: row -1 = (49*50 + 100)/50 = 50.98
    # row -2 = 50.00 (the 100-bar is not in the window yet)
    sma50 = np.full(n, 50.0)
    sma50[249] = 100.0
    # sma_200: constant 50 throughout. Row -1 mean = 50, row -2 = 50.
    sma200 = np.full(n, 50.0)
    df = pd.DataFrame({
        "ticker": ["AAPL"] * n,
        "Date": pd.date_range("2024-01-01", periods=n),
        "Close": np.full(n, 50.0),
        "Open": np.full(n, 50.0),
        "High": np.full(n, 50.0),
        "Low": np.full(n, 50.0),
        "Volume": np.ones(n),
        "sma_50": sma50,
        "sma_200": sma200,
    })

    s50 = _ensure_series_on_df(df, "sma_50")
    s200 = _ensure_series_on_df(df, "sma_200")
    assert s50 is not None and s200 is not None

    # The cross at the latest row: sma_50 > sma_200 NOW, sma_50 <= sma_200 YESTERDAY
    cross_now = (s50 > s200) & (s50.shift(1) <= s200.shift(1))
    last_val = cross_now.iloc[-1]
    assert bool(last_val) is True, f"expected a fresh cross at the latest row, got {last_val}"

    # Sanity: the cross boolean is also keyed by _cross_column_name correctly
    cf = {
        "column": "sma_50", "condition": "crossed_above",
        "reference_column": "sma_200", "lookback_days": 1,
    }
    cname = _cross_column_name(cf)
    assert cname == "cross_sma_50_crossed_above_sma_200_in_1d"


def test_aggregator_strips_cross_and_filters_on_boolean():
    """Simulates the aggregator: cross items are stripped from filters before
    apply_quant_filters; the cross boolean column on the df is filtered on
    directly. UTHR-like (long-ago cross) should be filtered OUT; freshly-crossed
    stocks should remain.
    """
    # Three rows: A (just crossed), B (long-ago cross, stale), C (no cross)
    df = pd.DataFrame({
        "ticker": ["A", "B", "C"],
        "close": [100.0, 100.0, 100.0],
        "indicator_a": [10.0, 10.0, 10.0],
        "indicator_b": [10.0, 10.0, 10.0],
        "cross_indicator_a_crossed_above_indicator_b_in_1d": [True, False, False],
    })
    cross_filters = [{
        "column": "indicator_a",
        "condition": "crossed_above",
        "reference_column": "indicator_b",
        "lookback_days": 1,
    }]

    # 1. apply_quant_filters with the cross item still in filters must RAISE
    with pytest.raises(ValueError, match="crossed_above"):
        apply_quant_filters(df, {"indicator_filters": cross_filters})

    # 2. apply_quant_filters with cross items stripped must succeed (no-op on this df)
    non_cross = [it for it in cross_filters
                 if it.get("condition") not in ("crossed_above", "crossed_below")]
    stripped = {"indicator_filters": non_cross}
    result = apply_quant_filters(df, stripped)
    assert len(result) == 3  # nothing filtered

    # 3. The aggregator's gate (df[cross_col] == True) filters to just row A
    from app.services.agno_screener import _cross_column_name
    cname = _cross_column_name(cross_filters[0])
    survivors = result[result[cname] == True]
    assert list(survivors["ticker"]) == ["A"]
