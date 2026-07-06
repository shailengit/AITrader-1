"""Screening indicators — registry, classes, and per-column helpers.

Re-exports INDICATOR_REGISTRY (moved from app.services.agno_screener).
"""
from __future__ import annotations

# Mapping of backend column name → ta-library instantiation spec.
# Used by chart_data, screener workers, and per-ticker detail endpoints to
# recompute indicators that add_all_ta_features does not produce on its own.
INDICATOR_REGISTRY = {
    # Volume
    'volume_adi': {'module': 'ta.volume', 'class': 'AccDistIndexIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}},
    'volume_obv': {'module': 'ta.volume', 'class': 'OnBalanceVolumeIndicator', 'params': {'close': 'Close', 'volume': 'Volume'}},
    'volume_cmf': {'module': 'ta.volume', 'class': 'ChaikinMoneyFlowIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, 'default_window': 20},
    'volume_fi': {'module': 'ta.volume', 'class': 'ForceIndexIndicator', 'params': {'close': 'Close', 'volume': 'Volume'}, 'default_window': 13},
    'volume_em': {'module': 'ta.volume', 'class': 'EaseOfMovementIndicator', 'params': {'high': 'High', 'low': 'Low', 'volume': 'Volume'}},
    'volume_mfi': {'module': 'ta.volume', 'class': 'MFIIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, 'default_window': 14},
    'volume_vwap': {'module': 'ta.volume', 'class': 'VolumeWeightedAveragePrice', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}},
    'volume_nvi': {'module': 'ta.volume', 'class': 'NegativeVolumeIndexIndicator', 'params': {'close': 'Close', 'volume': 'Volume'}},
    # Volatility
    'volatility_bbm': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_mavg'},
    'volatility_bbh': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_hband'},
    'volatility_bbl': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_lband'},
    'volatility_bbw': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_wband'},
    'volatility_bbp': {'module': 'ta.volatility', 'class': 'BollingerBands', 'params': {'close': 'Close'}, 'default_window': 20, 'default_window_dev': 2, 'output': 'bollinger_pband'},
    'volatility_kcw': {'module': 'ta.volatility', 'class': 'KeltnerChannel', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 20, 'output': 'keltner_channel_wband'},
    'volatility_atr': {'module': 'ta.volatility', 'class': 'AverageTrueRange', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 14},
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
    'trend_aroon_up': {'module': 'ta.trend', 'class': 'AroonIndicator', 'params': {'close': 'Close'}, 'default_window': 25},
    'trend_aroon_down': {'module': 'ta.trend', 'class': 'AroonIndicator', 'params': {'close': 'Close'}, 'default_window': 25},
    'trend_aroon_ind': {'module': 'ta.trend', 'class': 'AroonIndicator', 'params': {'close': 'Close'}, 'default_window': 25},
    'trend_stc': {'module': 'ta.trend', 'class': 'STCIndicator', 'params': {'close': 'Close'}},
    # Momentum
    'momentum_rsi': {'module': 'ta.momentum', 'class': 'RSIIndicator', 'params': {'close': 'Close'}, 'default_window': 14},
    'momentum_stoch': {'module': 'ta.momentum', 'class': 'StochasticOscillator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 14, 'default_smooth_window': 3},
    'momentum_stoch_signal': {'module': 'ta.momentum', 'class': 'StochasticOscillator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_window': 14, 'default_smooth_window': 3, 'output': 'stoch_signal'},
    'momentum_wr': {'module': 'ta.momentum', 'class': 'WilliamsRIndicator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}, 'default_lbp': 14},
    'momentum_ao': {'module': 'ta.momentum', 'class': 'AwesomeOscillatorIndicator', 'params': {'high': 'High', 'low': 'Low'}},
    'momentum_roc': {'module': 'ta.momentum', 'class': 'ROCIndicator', 'params': {'close': 'Close'}, 'default_window': 12},
    'momentum_tsi': {'module': 'ta.momentum', 'class': 'TSIIndicator', 'params': {'close': 'Close'}, 'default_window_slow': 25, 'default_window_fast': 13},
    'momentum_uo': {'module': 'ta.momentum', 'class': 'UltimateOscillator', 'params': {'high': 'High', 'low': 'Low', 'close': 'Close'}},
    'momentum_kama': {'module': 'ta.momentum', 'class': 'KAMAIndicator', 'params': {'close': 'Close'}, 'default_window': 10, 'default_pow1': 2, 'default_pow2': 30},
    'momentum_ppo': {'module': 'ta.momentum', 'class': 'PercentagePriceOscillator', 'params': {'close': 'Close'}, 'default_window_slow': 26, 'default_window_fast': 12, 'default_window_sign': 9},
    # Others
    'others_dr': {'module': 'ta.others', 'class': 'DailyReturnIndicator', 'params': {'close': 'Close'}},
}
