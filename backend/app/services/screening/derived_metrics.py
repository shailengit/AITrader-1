"""
Derived composite metrics for stock screening.

Each function takes a price/volume DataFrame (columns: Date, Open, High, Low, Close, Volume)
and returns a single scalar value representing the latest computed metric.
"""

import pandas as pd
import numpy as np


def bb_bandwidth_pct(df: pd.DataFrame) -> float:
    """
    Bollinger Bandwidth as percentile of 120-day range.
    Used for: Bollinger Squeeze detection.
    Same logic as analyze_single_ticker_dormant_giant() lines 306-318.
    """
    close = df['Close']
    sma_20 = close.rolling(window=20).mean()
    std_20 = close.rolling(window=20).std()
    upper = sma_20 + (std_20 * 2)
    lower = sma_20 - (std_20 * 2)
    bandwidth = (upper - lower) / sma_20
    bw_120 = bandwidth.tail(120)
    min_bw = bw_120.min()
    max_bw = bw_120.max()
    current_bw = bandwidth.iloc[-1]
    bandwidth_pct = (current_bw - min_bw) / (max_bw - min_bw + 1e-9)
    return round(bandwidth_pct * 100, 2)  # 0-100 scale


def vol_cluster_count(df: pd.DataFrame, threshold: float = 1.2, lookback: int = 5) -> int:
    """
    Count of recent days where volume exceeded 1.2x the 50-day average.
    Used for: Volume Cluster detection.
    Same logic as analyze_single_ticker_dormant_giant() lines 344-347.
    """
    volume = df['Volume']
    avg_vol_50 = volume.tail(50).mean()
    if avg_vol_50 == 0:
        return 0
    vol_spike_days = (volume.tail(lookback) > (avg_vol_50 * threshold)).sum()
    return int(vol_spike_days)


def consolidation_tightness(df: pd.DataFrame, lookback: int = 20, max_deviation: float = 0.03, min_days: int = 15) -> float:
    """
    Percentage of days in lookback period where close stayed within max_deviation of SMA(20).
    Used for: Consolidation Tightness.
    Same logic as analyze_single_ticker_dormant_giant() lines 322-326.
    """
    close = df['Close']
    sma_20 = close.rolling(window=20).mean()
    last_close = close.tail(lookback)
    last_sma = sma_20.tail(lookback)
    within_band = (abs(last_close - last_sma) / last_sma) < max_deviation
    return round(float(within_band.sum() / lookback * 100), 2)  # 0-100 scale


def rs_vs_sector_ratio(df: pd.DataFrame, sector_etf_df: pd.DataFrame) -> float:
    """
    20-day relative strength ratio vs sector ETF.
    Used for: RS vs Sector.
    Same logic as analyze_single_ticker_dormant_giant() lines 352-365.
    """
    if sector_etf_df is None or sector_etf_df.empty or len(sector_etf_df) < 20:
        return 1.0
    stock_20d_return = (df['Close'].iloc[-1] / df['Close'].iloc[-20]) - 1
    proxy_close = sector_etf_df['Close']
    proxy_20d_return = (proxy_close.iloc[-1] / proxy_close.iloc[-20]) - 1
    if proxy_20d_return != 0:
        return round(stock_20d_return / proxy_20d_return, 4)
    return 1.0


def sector_above_sma50(sector_etf_df: pd.DataFrame) -> bool:
    """
    Whether the sector ETF's close is above its 50-day SMA.
    Used for: Sector Momentum Gate.
    Same logic as _fetch_sector_etfs() lines 222-243.
    """
    if sector_etf_df is None or sector_etf_df.empty or len(sector_etf_df) < 50:
        return True
    close = sector_etf_df['Close']
    sma_50 = close.rolling(window=50).mean().iloc[-1]
    current = close.iloc[-1]
    return bool(current > sma_50)


# ── Custom User-Defined Composites ─────────────────────────────────────────

def compute_custom_composite(df: pd.DataFrame, left_col: str, right_col: str, operation: str) -> float:
    """
    Compute a user-defined composite metric by applying an operation between two indicator columns.

    Supported operations:
      - 'add':        left + right
      - 'subtract':   left - right
      - 'multiply':   left * right
      - 'divide':     left / right (with zero-guard)
      - 'ratio_pct':  (left / right) * 100 (with zero-guard)

    Returns the latest value as a float, or 0.0 if columns are missing.
    """
    if left_col not in df.columns or right_col not in df.columns:
        return 0.0

    left = df[left_col]
    right = df[right_col].replace(0, np.nan)

    if operation == 'add':
        result = left + right
    elif operation == 'subtract':
        result = left - right
    elif operation == 'multiply':
        result = left * right
    elif operation == 'divide':
        result = left / right
    elif operation == 'ratio_pct':
        result = (left / right) * 100
    else:
        return 0.0

    latest = result.iloc[-1]
    if pd.isna(latest) or np.isinf(latest):
        return 0.0
    return round(float(latest), 4)
