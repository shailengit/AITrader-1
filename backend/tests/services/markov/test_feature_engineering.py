"""Tests for feature engineering module."""
import pytest
import pandas as pd
import numpy as np
from app.services.markov.feature_engineering import (
    compute_log_returns,
    compute_downside_deviation,
    compute_sortino_ratio,
    compute_rsi,
    compute_macd,
    compute_bollinger_position,
    compute_ath_proximity,
    compute_volume_ratio,
    compute_3day_forward_return,
    label_forward_return,
    DEFAULT_BUY_THRESHOLD,
    DEFAULT_SELL_THRESHOLD,
)


def test_compute_log_returns():
    close = pd.Series([100.0, 102.0, 105.0, 103.0, 101.0])
    result = compute_log_returns(close, window=2)
    expected = np.log(close / close.shift(2))
    pd.testing.assert_series_equal(result, expected)


def test_compute_rsi():
    close = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
                       111, 112, 113, 114, 115])
    rsi = compute_rsi(close, window=14)
    assert rsi.iloc[-1] > 50  # Upward trend → RSI > 50
    assert rsi.notna().sum() == 3  # 16 data points - 13 NaN from 14-period window = 3 valid


def test_compute_macd():
    close = pd.Series(range(100, 200))
    macd = compute_macd(close)
    assert len(macd) == 100
    assert macd.iloc[-1] > 0  # Upward trend → MACD positive


def test_bollinger_position():
    close = pd.Series(range(100, 200))
    pos = compute_bollinger_position(close, window=20)
    assert pos.iloc[-1] > 0.5  # Upward trend → near upper band
    assert pos.min() >= 0
    assert pos.max() <= 1


def test_ath_proximity():
    close = pd.Series([100, 90, 95, 110, 105])
    ath = compute_ath_proximity(close)
    assert ath.iloc[-1] <= 1.0
    assert ath.iloc[3] == 1.0  # Index 3 is the high


def test_volume_ratio():
    volume = pd.Series([100] * 50 + [200] * 10)
    vr = compute_volume_ratio(volume, window=50)
    assert vr.iloc[-1] > 1.0  # Recent volume is double


def test_3day_forward_return():
    close = pd.Series([100, 101, 102, 103, 104, 105])
    fwd = compute_3day_forward_return(close)
    assert fwd.iloc[0] == 103 / 100 - 1  # 3 days forward
    assert pd.isna(fwd.iloc[-1])  # Last 3 have no forward data


def test_label_forward_return_default():
    fwd = pd.Series([0.05, 0.01, -0.01, -0.03])
    labels = label_forward_return(fwd)
    assert labels.iloc[0] == 2  # BUY
    assert labels.iloc[1] == 1  # HOLD
    assert labels.iloc[2] == 1  # HOLD
    assert labels.iloc[3] == 0  # SELL


def test_label_forward_return_custom_threshold():
    fwd = pd.Series([0.03, 0.01, -0.01, -0.03])
    labels = label_forward_return(fwd, buy_threshold=0.02, sell_threshold=-0.02)
    assert labels.iloc[0] == 2  # BUY (3% > 2%)
    assert labels.iloc[1] == 1  # HOLD (1% < 2%)
    assert labels.iloc[2] == 1  # HOLD (-1% > -2%)
    assert labels.iloc[3] == 0  # SELL (-3% < -2%)
