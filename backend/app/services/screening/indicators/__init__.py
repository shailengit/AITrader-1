"""Screening indicators — registry, classes, and per-column helpers.

Re-exports INDICATOR_REGISTRY (moved from app.services.agno_screener).
"""
from __future__ import annotations

from typing import Any, Callable, Dict

import pandas as pd


def _compute_kdj(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """pandas-ta KDJ — returns the K line (primary). D and J are also
    produced by the function but we expose K as the canonical series.
    """
    import pandas_ta as pta
    length = int(params.get('length', 9))
    signal = int(params.get('signal', 3))
    result = pta.kdj(
        high=params['high'],
        low=params['low'],
        close=params['close'],
        length=length,
        signal=signal,
    )
    if result is None or result.empty:
        return pd.Series(dtype=float)
    # pandas-ta returns columns named e.g. "K_9_3", "D_9_3", "J_9_3".
    # Pick the K column (K_<length>_<signal>).
    k_col = f'K_{length}_{signal}'
    if k_col in result.columns:
        return result[k_col]
    # Fallback: first column whose name starts with "K_"
    for c in result.columns:
        if c.startswith('K_'):
            return result[c]
    return result.iloc[:, 0]


def _compute_supertrend(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """pandas-ta Supertrend — returns the trend line (SUPERT_<len>_<mult>)."""
    import pandas_ta as pta
    length = int(params.get('length', 10))
    multiplier = float(params.get('multiplier', 3.0))
    result = pta.supertrend(
        high=params['high'],
        low=params['low'],
        close=params['close'],
        length=length,
        multiplier=multiplier,
    )
    if result is None or result.empty:
        return pd.Series(dtype=float)
    # pandas-ta returns columns named "SUPERT_<len>_<mult>", "SUPERTd_…",
    # "SUPERTl_…", "SUPERTs_…". We expose the trend line.
    sup_col = f'SUPERT_{length}_{multiplier}'
    if sup_col in result.columns:
        return result[sup_col]
    for c in result.columns:
        if c.startswith('SUPERT_') and not c.startswith('SUPERTd'):
            return result[c]
    return result.iloc[:, 0]


def _compute_ttm_squeeze(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """pandas-ta TTM Squeeze — returns the momentum line
    (SQZ_<length>_<bb_mult>_<length>_<kc_mult>)."""
    import pandas_ta as pta
    length = int(params.get('length', 20))
    bb_mult = float(params.get('bb_mult', 2.0))
    kc_mult = float(params.get('kc_mult', 1.5))
    result = pta.squeeze(
        high=params['high'],
        low=params['low'],
        close=params['close'],
        length=length,
        bb_mult=bb_mult,
        kc_mult=kc_mult,
    )
    if result is None or result.empty:
        return pd.Series(dtype=float)
    sqz_col = f'SQZ_{length}_{bb_mult}_{length}_{kc_mult}'
    if sqz_col in result.columns:
        return result[sqz_col]
    for c in result.columns:
        if c.startswith('SQZ_') and not c.startswith('SQZ_ON') and not c.startswith('SQZ_OFF') and not c.startswith('SQZ_NO'):
            return result[c]
    return result.iloc[:, 0]


def _compute_psar(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """ta-library PSAR — single continuous Series (the active SAR
    value for each bar). add_all_ta_features only emits the
    up/down split (`trend_psar_up` / `trend_psar_down`), so this is
    the canonical way to plot PSAR as one line on the price chart.
    """
    from ta.trend import PSARIndicator
    step = float(params.get('step', 0.02))
    max_step = float(params.get('max_step', 0.2))
    psar = PSARIndicator(
        high=params['high'],
        low=params['low'],
        close=params['close'],
        step=step,
        max_step=max_step,
    )
    return psar.psar()


# Mapping of backend column name → ta-library instantiation spec.
# Used by chart_data, screener workers, and per-ticker detail endpoints to
# recompute indicators that add_all_ta_features does not produce on its own.
#
# Entries with a `compute` callable bypass the module/class shape and
# delegate to a custom function — used for pandas-ta-only indicators
# (KDJ, Supertrend, TTM Squeeze) which don't fit the ta-library
# convention.
INDICATOR_REGISTRY = {
    # Volume
    'volume_adi': {'module': 'ta.volume', 'class': 'AccDistIndexIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}},
    'volume_obv': {'module': 'ta.volume', 'class': 'OnBalanceVolumeIndicator', 'params': {'close': 'Close', 'volume': 'Volume'}},
    'volume_cmf': {'module': 'ta.volume', 'class': 'ChaikinMoneyFlowIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, 'default_window': 20, 'output': 'chaikin_money_flow'},
    'volume_fi': {'module': 'ta.volume', 'class': 'ForceIndexIndicator', 'params': {'close': 'Close', 'volume': 'Volume'}, 'default_window': 13},
    'volume_em': {'module': 'ta.volume', 'class': 'EaseOfMovementIndicator', 'params': {'high': 'High', 'low': 'Low', 'volume': 'Volume'}},
    'volume_mfi': {'module': 'ta.volume', 'class': 'MFIIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, 'default_window': 14, 'output': 'money_flow_index'},
    'volume_vwap': {'module': 'ta.volume', 'class': 'VolumeWeightedAveragePrice', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}},
    'volume_nvi': {'module': 'ta.volume', 'class': 'NegativeVolumeIndexIndicator', 'params': {'close': 'Close', 'volume': 'Volume'}},
    # Volatility
    'volatility_bbm': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_mavg'},
    'volatility_bbh': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_hband'},
    'volatility_bbl': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_lband'},
    'volatility_bbw': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_wband'},
    'volatility_bbp': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_pband'},
    'volatility_kcw': {'module': 'ta.volatility', 'class': 'KeltnerChannel', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 20, 'output': 'keltner_channel_wband'},
    'volatility_atr': {'module': 'ta.volatility', 'class': 'AverageTrueRange', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 14, 'output': 'average_true_range'},
    'volatility_ui': {'module': 'ta.volatility', 'class': 'UlcerIndex', 'params': {'close': 'Close'}, 'default_window': 14},
    # Trend
    'trend_sma_fast': {'module': 'ta.trend', 'class': 'SMAIndicator', 'params': {'close': 'Close'}, 'default_window': 20, 'output': 'sma_indicator'},
    'trend_sma_slow': {'module': 'ta.trend', 'class': 'SMAIndicator', 'params': {'close': 'Close'}, 'default_window': 50, 'output': 'sma_indicator'},
    'trend_ema_fast': {'module': 'ta.trend', 'class': 'EMAIndicator', 'params': {'close': 'Close'}, 'default_window': 12, 'output': 'ema_indicator'},
    'trend_ema_slow': {'module': 'ta.trend', 'class': 'EMAIndicator', 'params': {'close': 'Close'}, 'default_window': 26, 'output': 'ema_indicator'},
    'trend_macd': {'module': 'ta.trend', 'class': 'MACD', 'params': {'close': 'Close'}, 'default_window_slow': 26, 'default_window_fast': 12, 'default_window_sign': 9},
    'trend_macd_signal': {'module': 'ta.trend', 'class': 'MACD', 'params': {'close': 'Close'}, 'default_window_slow': 26, 'default_window_fast': 12, 'default_window_sign': 9, 'output': 'macd_signal'},
    'trend_macd_diff': {'module': 'ta.trend', 'class': 'MACD', 'params': {'close': 'Close'}, 'default_window_slow': 26, 'default_window_fast': 12, 'default_window_sign': 9, 'output': 'macd_diff'},
    'trend_adx': {'module': 'ta.trend', 'class': 'ADXIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 14},
    'trend_cci': {'module': 'ta.trend', 'class': 'CCIIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 20},
    'trend_trix': {'module': 'ta.trend', 'class': 'TRIXIndicator', 'params': {'close': 'Close'}, 'default_window': 15},
    'trend_mass_index': {'module': 'ta.trend', 'class': 'MassIndex', 'params': {'high': 'High', 'low': 'Low'}},
    'trend_aroon_up': {'module': 'ta.trend', 'class': 'AroonIndicator', 'params': {'high': 'High', 'low': 'Low'}, 'default_window': 25, 'output': 'aroon_up'},
    'trend_aroon_down': {'module': 'ta.trend', 'class': 'AroonIndicator', 'params': {'high': 'High', 'low': 'Low'}, 'default_window': 25, 'output': 'aroon_down'},
    'trend_aroon_ind': {'module': 'ta.trend', 'class': 'AroonIndicator', 'params': {'high': 'High', 'low': 'Low'}, 'default_window': 25, 'output': 'aroon_indicator'},
    'trend_stc': {'module': 'ta.trend', 'class': 'STCIndicator', 'params': {'close': 'Close'}},
    # Momentum
    'momentum_rsi': {'module': 'ta.momentum', 'class': 'RSIIndicator', 'params': {'close': 'Close'}, 'default_window': 14},
    'momentum_stoch': {'module': 'ta.momentum', 'class': 'StochasticOscillator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 14, 'default_smooth_window': 3},
    'momentum_stoch_signal': {'module': 'ta.momentum', 'class': 'StochasticOscillator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 14, 'default_smooth_window': 3, 'output': 'stoch_signal'},
    'momentum_wr': {'module': 'ta.momentum', 'class': 'WilliamsRIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_lbp': 14, 'output': 'williams_r'},
    'momentum_ao': {'module': 'ta.momentum', 'class': 'AwesomeOscillatorIndicator', 'params': {'high': 'High', 'low': 'Low'}, 'output': 'awesome_oscillator'},
    'momentum_roc': {'module': 'ta.momentum', 'class': 'ROCIndicator', 'params': {'close': 'Close'}, 'default_window': 12},
    'momentum_tsi': {'module': 'ta.momentum', 'class': 'TSIIndicator', 'params': {'close': 'Close'}, 'default_window_slow': 25, 'default_window_fast': 13},
    'momentum_uo': {'module': 'ta.momentum', 'class': 'UltimateOscillator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}},
    'momentum_kama': {'module': 'ta.momentum', 'class': 'KAMAIndicator', 'params': {'close': 'Close'}, 'default_window': 10, 'default_pow1': 2, 'default_pow2': 30},
    'momentum_ppo': {'module': 'ta.momentum', 'class': 'PercentagePriceOscillator', 'params': {'close': 'Close'}, 'default_window_slow': 26, 'default_window_fast': 12, 'default_window_sign': 9},
    # Others
    'others_dr': {'module': 'ta.others', 'class': 'DailyReturnIndicator', 'params': {'close': 'Close'}},
    # pandas-ta-only indicators (no ta-library equivalent). Custom
    # compute functions take the merged param dict and return a
    # pd.Series; the column key is what the chart endpoint and
    # frontend look up.
    'momentum_kdj': {'compute': _compute_kdj, 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_length': 9, 'default_signal': 3},
    'trend_supertrend': {'compute': _compute_supertrend, 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_length': 10, 'default_multiplier': 3.0},
    'volatility_ttm_squeeze': {'compute': _compute_ttm_squeeze, 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_length': 20, 'default_bb_mult': 2.0, 'default_kc_mult': 1.5},
    'trend_psar': {'compute': _compute_psar, 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_step': 0.02, 'default_max_step': 0.2},
}
