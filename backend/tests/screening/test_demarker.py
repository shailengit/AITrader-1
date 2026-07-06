"""Tests for the DeMarker (Tom DeMark) momentum oscillator.

Covers:
  1. `compute()` — numpy convenience wrapper shape, range, warmup NaN count.
  2. `DeMarkerIndicator` — class adapter for INDICATOR_REGISTRY dispatch.
     Asserts `.demarker()` returns a pd.Series aligned to the input index.
  3. `DeMarker` (vbt.IndicatorFactory) — VBT integration returns a Series
     keyed by `.demarker` aligned to the input index.
  4. `window` param is tunable: smaller window → fewer NaNs.
  5. Monotonic-input semantics: strictly rising price action → DeMarker
     near 1.0 (DeMax dominates); strictly falling → near 0.0 (DeMin
     dominates).
  6. Class and `compute()` agree when the same window is used.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.screening.indicators.demarker import (
    DeMarker,
    DeMarkerIndicator,
    DEFAULT_WINDOW,
    compute,
)


def _make_ohlcv(n: int, seed: int = 0):
    """Build a synthetic OHLCV DataFrame with a Date index."""
    rng = np.random.RandomState(seed)
    close = 100 + np.cumsum(rng.randn(n))
    high = close + rng.rand(n)
    low = close - rng.rand(n)
    return pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=n, freq='D'),
        'Open': close,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': np.ones(n) * 1_000_000,
    })


def test_compute_shape_and_range():
    """compute() returns a (n,) array, [0, 1] range, with window-1 warmup NaNs."""
    df = _make_ohlcv(60)
    out = compute(df['High'].to_numpy(), df['Low'].to_numpy(), window=14)
    assert out.shape == (60,)
    assert np.isnan(out).sum() == 14  # SMA warmup: first 14 values are NaN
    valid = out[~np.isnan(out)]
    assert ((valid >= 0) & (valid <= 1)).all()


def test_indicator_class_returns_aligned_series():
    """DeMarkerIndicator().demarker() returns pd.Series aligned to input index."""
    df = _make_ohlcv(60)
    idx = pd.date_range('2024-01-01', periods=60, freq='D')
    high = pd.Series(df['High'].to_numpy(), index=idx)
    low = pd.Series(df['Low'].to_numpy(), index=idx)
    ind = DeMarkerIndicator(high=high, low=low, window=14)
    s = ind.demarker()
    assert isinstance(s, pd.Series)
    assert s.index.equals(idx)
    assert s.shape == (60,)
    assert s.isna().sum() == 14
    valid = s.dropna()
    assert valid.between(0, 1).all()


def test_vbt_factory_returns_aligned_series():
    """DeMarker.run().demarker is a pd.Series aligned to the input index."""
    df = _make_ohlcv(60)
    idx = pd.date_range('2024-01-01', periods=60, freq='D')
    high = pd.Series(df['High'].to_numpy(), index=idx)
    low = pd.Series(df['Low'].to_numpy(), index=idx)
    res = DeMarker.run(high, low, window=14)
    assert isinstance(res.demarker, pd.Series)
    assert res.demarker.index.equals(idx)


def test_tunable_window_fewer_nans():
    """Smaller window produces fewer warmup NaNs than the default."""
    df = _make_ohlcv(60)
    out_14 = compute(df['High'].to_numpy(), df['Low'].to_numpy(), window=14)
    out_5 = compute(df['High'].to_numpy(), df['Low'].to_numpy(), window=5)
    assert np.isnan(out_5).sum() < np.isnan(out_14).sum()
    assert np.isnan(out_5).sum() == 5  # window-1 = 4, plus 1 for the shift(1) → 5


def test_strictly_rising_input_demax_dominates():
    """Strictly rising price action → DeMarker near 1.0 (DeMax dominates)."""
    n = 60
    high = np.arange(100, 100 + n, dtype=float)
    low = high - 0.5  # Lows also rise by the same amount
    out = compute(high, low, window=14)
    valid = out[~np.isnan(out)]
    # All values should be at or very near 1.0 (DeMax > 0 always, DeMin == 0 always).
    assert (valid >= 0.99).all(), f"expected ~1.0, got min={valid.min()}"


def test_strictly_falling_input_demin_dominates():
    """Strictly falling price action → DeMarker near 0.0 (DeMin dominates)."""
    n = 60
    high = np.arange(100 + n, 100, -1, dtype=float)
    low = high - 0.5  # Lows also fall by the same amount (so DeMin = 0.5)
    out = compute(high, low, window=14)
    valid = out[~np.isnan(out)]
    # DeMax = 0 always (no rising high), DeMin = 0.5 always → DeMark = 0.
    assert (valid <= 0.01).all(), f"expected ~0.0, got max={valid.max()}"


def test_class_matches_compute_same_window():
    """DeMarkerIndicator().demarker() matches compute() element-wise at same window."""
    df = _make_ohlcv(60)
    high_arr = df['High'].to_numpy()
    low_arr = df['Low'].to_numpy()
    ind = DeMarkerIndicator(high=high_arr, low=low_arr, window=7)
    out_ind = ind.demarker()
    out_compute = compute(high_arr, low_arr, window=7)
    # Series vs numpy: drop the index comparison, compare values
    np.testing.assert_array_almost_equal(out_ind.to_numpy(), out_compute)


def test_default_window_constant():
    """DEFAULT_WINDOW must be 14 to match Tom DeMark's original setting."""
    assert DEFAULT_WINDOW == 14


@pytest.mark.parametrize("window", [5, 14, 25])
def test_window_keeps_values_in_unit_interval(window):
    """For any reasonable window, valid values stay in [0, 1]."""
    df = _make_ohlcv(80, seed=window)
    out = compute(df['High'].to_numpy(), df['Low'].to_numpy(), window=window)
    valid = out[~np.isnan(out)]
    assert ((valid >= 0) & (valid <= 1)).all()
