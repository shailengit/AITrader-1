"""
Multi-resolution feature engineering for Markov Chain Trader.

Produces feature vectors for both the Jump Model (ETF-level) and
Pattern Recognizer (ticker-level) from daily and 1-minute data.
"""
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from app.services.data_service import DataService

logger = logging.getLogger(__name__)

# Label thresholds (default ±2%, user-configurable)
DEFAULT_BUY_THRESHOLD = 0.02
DEFAULT_SELL_THRESHOLD = -0.02

# Minimum data requirements
MIN_DAILY_DAYS = 252  # 1 trading year
MIN_1M_DAYS = 20      # 20 trading days of 1m data for microstructure


def compute_log_returns(close: pd.Series, window: int = 20) -> pd.Series:
    """20-day rolling log returns."""
    return np.log(close / close.shift(window))


def compute_downside_deviation(returns: pd.Series, half_life: int = 10) -> pd.Series:
    """Exponentially weighted downside deviation (only negative returns)."""
    neg_returns = returns.where(returns < 0, 0)
    neg_var = (neg_returns ** 2).ewm(halflife=half_life).mean()
    return np.sqrt(neg_var)


def compute_sortino_ratio(returns: pd.Series, half_life: int = 20) -> pd.Series:
    """Sortino ratio using EWM downside deviation."""
    dd = compute_downside_deviation(returns, half_life)
    ewma_mean = returns.ewm(halflife=half_life).mean()
    return ewma_mean / dd.replace(0, np.nan)


def compute_realized_variance(close_1m: pd.Series, periods_per_day: int = 390) -> pd.Series:
    """Realized variance from 1-minute returns, aggregated daily."""
    log_ret_1m = np.log(close_1m / close_1m.shift(1))
    daily_rv = log_ret_1m.resample('1D').apply(lambda x: np.sum(x ** 2))
    return daily_rv * periods_per_day


def compute_realized_quarticity(close_1m: pd.Series, periods_per_day: int = 390) -> pd.Series:
    """Realized quarticity from 1-minute returns."""
    log_ret_1m = np.log(close_1m / close_1m.shift(1))
    daily_rq = log_ret_1m.resample('1D').apply(lambda x: np.sum(x ** 4))
    return daily_rq * periods_per_day


def compute_signed_jump_variation(close_1m: pd.Series) -> pd.Series:
    """Signed jump variation: realized variance - bipower variation."""
    log_ret_1m = np.log(close_1m / close_1m.shift(1))
    bipower = log_ret_1m.resample('1D').apply(
        lambda x: np.sum(np.abs(x) * np.abs(x.shift(1)))
    )
    rv = log_ret_1m.resample('1D').apply(lambda x: np.sum(x ** 2))
    return rv - bipower


def compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    # When loss is 0, RS is infinite → RSI = 100
    zero_loss = loss == 0
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # Only fill NaN where loss was exactly 0 (not the early rolling NaN values)
    rsi[zero_loss] = 100.0
    return rsi


def compute_macd(close: pd.Series) -> pd.Series:
    """MACD line (12-26 EMA difference)."""
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    return ema12 - ema26


def compute_bollinger_position(close: pd.Series, window: int = 20) -> pd.Series:
    """Position within Bollinger Bands: 0=lower, 1=upper."""
    sma = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return (close - lower) / (upper - lower).replace(0, np.nan)


def compute_ath_proximity(close: pd.Series) -> pd.Series:
    """Close / 52-week high (min_periods=1 for short series)."""
    high_52w = close.rolling(252, min_periods=1).max()
    return close / high_52w.replace(0, np.nan)


def compute_volume_ratio(volume: pd.Series, window: int = 50) -> pd.Series:
    """Current volume / rolling average volume."""
    avg_vol = volume.rolling(window).mean()
    return volume / avg_vol.replace(0, np.nan)


def compute_3day_forward_return(close: pd.Series) -> pd.Series:
    """3-day forward return for label generation."""
    return close.shift(-3) / close - 1


def label_forward_return(fwd_return: pd.Series, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                        sell_threshold: float = DEFAULT_SELL_THRESHOLD) -> pd.Series:
    """Bin 3-day forward return into BUY/HOLD/SELL labels.

    Returns: 0=SELL, 1=HOLD, 2=BUY
    """
    labels = pd.Series(1, index=fwd_return.index, dtype=int)  # Default HOLD
    labels[fwd_return > buy_threshold] = 2   # BUY
    labels[fwd_return < sell_threshold] = 0  # SELL
    return labels


def compute_etf_features(etf_ticker: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Compute feature vector for an ETF (used by Jump Model).

    Returns DataFrame with columns: log_return_20d, downside_dev_10, downside_dev_20,
    sortino_20, sortino_60
    """
    df = DataService.get_ohlcv_data(etf_ticker, start_date, end_date, frequency="daily")
    if df is None or len(df) < 60:
        logger.warning(f"Insufficient data for ETF {etf_ticker}: {len(df) if df is not None else 0} rows")
        return None

    close = df['Close']
    returns = close.pct_change().dropna()

    features = pd.DataFrame(index=close.index)
    features['log_return_20d'] = compute_log_returns(close, 20)
    features['downside_dev_10'] = compute_downside_deviation(returns, 10)
    features['downside_dev_20'] = compute_downside_deviation(returns, 20)
    features['sortino_20'] = compute_sortino_ratio(returns, 20)
    features['sortino_60'] = compute_sortino_ratio(returns, 60)
    features = features.dropna()
    return features


def compute_ticker_features(ticker: str, start_date: str, end_date: str,
                            buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                            sell_threshold: float = DEFAULT_SELL_THRESHOLD) -> Optional[Dict[str, Any]]:
    """Compute full feature vector + labels for a ticker (used by Pattern Recognizer).

    Returns dict with:
      - 'features': pd.DataFrame of feature columns
      - 'labels': pd.Series of 0/1/2 labels
      - 'has_microstructure': bool
      - 'ticker': str
    """
    # Load daily data
    df_daily = DataService.get_ohlcv_data(ticker, start_date, end_date, frequency="daily")
    if df_daily is None or len(df_daily) < MIN_DAILY_DAYS:
        logger.warning(f"Insufficient daily data for {ticker}: {len(df_daily) if df_daily is not None else 0} rows")
        return None

    close = df_daily['Close']
    volume = df_daily['Volume']
    returns = close.pct_change().dropna()

    # Load 1-minute data for microstructure (required)
    df_1m = DataService.get_ohlcv_data(ticker, start_date, end_date, frequency="minute")
    has_microstructure = df_1m is not None and len(df_1m) >= MIN_1M_DAYS * 390
    if not has_microstructure:
        logger.warning(f"Insufficient 1m data for {ticker} — skipping (microstructure required)")
        return None

    # Build feature DataFrame
    features = pd.DataFrame(index=close.index)

    # Feature A: Returns & Risk
    features['log_return_20d'] = compute_log_returns(close, 20)
    features['downside_dev_10'] = compute_downside_deviation(returns, 10)
    features['downside_dev_20'] = compute_downside_deviation(returns, 20)
    features['sortino_20'] = compute_sortino_ratio(returns, 20)
    features['sortino_60'] = compute_sortino_ratio(returns, 60)

    # Feature B: Microstructure (from 1m data, resampled to daily)
    close_1m = df_1m['Close']
    rv = compute_realized_variance(close_1m)
    rq = compute_realized_quarticity(close_1m)
    sjv = compute_signed_jump_variation(close_1m)

    # Align microstructure to daily index
    features['realized_variance'] = rv.reindex(features.index).fillna(method='ffill')
    features['realized_quarticity'] = rq.reindex(features.index).fillna(method='ffill')
    features['signed_jump_variation'] = sjv.reindex(features.index).fillna(method='ffill')

    # Feature C: Technical
    features['rsi_14'] = compute_rsi(close, 14)
    features['macd'] = compute_macd(close)
    features['bollinger_position'] = compute_bollinger_position(close, 20)
    features['volume_ratio'] = compute_volume_ratio(volume, 50)
    features['ath_proximity'] = compute_ath_proximity(close)

    # Labels: 3-day forward return
    fwd_ret = compute_3day_forward_return(close)
    labels = label_forward_return(fwd_ret, buy_threshold, sell_threshold)

    # Drop NaN rows
    valid_idx = features.dropna().index.intersection(labels.dropna().index)
    features = features.loc[valid_idx]
    labels = labels.loc[valid_idx]

    if len(features) < 100:
        logger.warning(f"Too few valid feature rows for {ticker}: {len(features)}")
        return None

    return {
        'features': features,
        'labels': labels,
        'has_microstructure': True,
        'ticker': ticker,
    }
