"""
Supertrend + RSI Strategy [Alorse] — Python translation
Original: strategies/trend/Supertrend + RSI.pine

Entry: Supertrend flips to uptrend AND RSI > threshold
Exit: Supertrend flips to downtrend
"""
import numpy as np
import vectorbt as vbt
import pandas_ta as ta

period = 10
multiplier = 3.0
rsi_length = 14
rsi_threshold = 50

close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

st = ta.supertrend(high, low, close, length=period, multiplier=multiplier)
trend = st[f'SUPERTd_{period}_{multiplier}']

from ta.momentum import RSIIndicator
rsi = RSIIndicator(close, window=rsi_length).rsi()

entries = (trend == 1) & (trend.shift(1) == -1) & (rsi > rsi_threshold)
exits = (trend == -1) & (trend.shift(1) == 1)

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)
