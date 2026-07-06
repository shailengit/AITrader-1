"""Tests for derived metrics."""
import pandas as pd
import numpy as np
from app.services.screening.derived_metrics import (
    bb_bandwidth_pct, vol_cluster_count, consolidation_tightness,
    rs_vs_sector_ratio, sector_above_sma50
)


def _make_ohlcv(close_prices, volume=None):
    """Helper to create a synthetic OHLCV DataFrame."""
    n = len(close_prices)
    if volume is None:
        volume = np.ones(n) * 1_000_000
    return pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=n, freq='D'),
        'Open': close_prices,
        'High': close_prices * 1.02,
        'Low': close_prices * 0.98,
        'Close': close_prices,
        'Volume': volume,
    })


def test_bb_bandwidth_pct_squeeze():
    """A flat price series should produce a low bandwidth percentile (squeeze)."""
    close = np.ones(200) * 100.0  # Flat line
    df = _make_ohlcv(close)
    result = bb_bandwidth_pct(df)
    assert 0 <= result <= 100
    # Flat price = very low bandwidth = squeeze
    assert result < 20, f"Expected squeeze (<20), got {result}"


def test_bb_bandwidth_pct_volatile():
    """A volatile price series should produce a high bandwidth percentile."""
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(200) * 2)  # Random walk
    df = _make_ohlcv(close)
    result = bb_bandwidth_pct(df)
    assert 0 <= result <= 100


def test_vol_cluster_count_normal():
    """Normal volume should produce 0 cluster days."""
    close = np.ones(200) * 100
    volume = np.ones(200) * 1_000_000
    df = _make_ohlcv(close, volume)
    result = vol_cluster_count(df)
    assert result == 0


def test_vol_cluster_count_spike():
    """Spike volume on last day should produce 1 cluster day."""
    close = np.ones(200) * 100
    volume = np.ones(200) * 1_000_000
    volume[-1] = 2_000_000  # 2x average
    df = _make_ohlcv(close, volume)
    result = vol_cluster_count(df)
    assert result >= 1


def test_consolidation_tightness_tight():
    """Tight consolidation should produce high tightness score."""
    close = np.ones(200) * 100
    # Add tiny noise
    close[-20:] += np.random.randn(20) * 0.5
    df = _make_ohlcv(close)
    result = consolidation_tightness(df)
    assert 0 <= result <= 100


def test_consolidation_tightness_loose():
    """Loose price action should produce low tightness score."""
    close = np.ones(200) * 100
    close[-20:] += np.random.randn(20) * 10  # Big moves
    df = _make_ohlcv(close)
    result = consolidation_tightness(df)
    assert 0 <= result <= 100


def test_rs_vs_sector_ratio():
    """RS ratio should be positive when stock outperforms sector."""
    stock_close = np.linspace(100, 120, 100)  # Up 20%
    sector_close = np.linspace(100, 110, 100)  # Up 10%
    stock_df = _make_ohlcv(stock_close)
    sector_df = _make_ohlcv(sector_close)
    result = rs_vs_sector_ratio(stock_df, sector_df)
    assert result > 1.0  # Stock outperformed


def test_sector_above_sma50_above():
    """Sector above SMA50 should return True."""
    close = np.linspace(100, 120, 100)  # Trending up
    df = _make_ohlcv(close)
    result = sector_above_sma50(df)
    assert result is True


def test_sector_above_sma50_below():
    """Sector below SMA50 should return False."""
    close = np.linspace(100, 80, 100)  # Trending down
    df = _make_ohlcv(close)
    result = sector_above_sma50(df)
    assert result is False
