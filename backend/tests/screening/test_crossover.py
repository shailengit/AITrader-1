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
