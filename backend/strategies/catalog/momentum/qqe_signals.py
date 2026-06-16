"""
QQE Signals Strategy [Alorse] — Python translation
Original: strategies/momentum/QQE signals.pine

Entry: RSI crosses above adaptive threshold (momentum shift)
Exit: RSI crosses below adaptive threshold
"""
import numpy as np
import vectorbt as vbt

rsi_length = 14
smooth_length = 5
fast_factor = 2.0
slow_factor = 4.0

close = ohlcv['Close']

from ta.momentum import RSIIndicator

rsi = RSIIndicator(close, window=rsi_length).rsi()
rsi_smooth = rsi.rolling(window=smooth_length).mean()

# Adaptive threshold based on RSI volatility
rsi_std = rsi.rolling(window=rsi_length).std()
upper_threshold = 50 + (rsi_std * fast_factor)
lower_threshold = 50 - (rsi_std * fast_factor)

entries = (rsi_smooth > upper_threshold) & (rsi_smooth.shift(1) <= upper_threshold.shift(1))
exits = (rsi_smooth < lower_threshold) & (rsi_smooth.shift(1) >= lower_threshold.shift(1))

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)
