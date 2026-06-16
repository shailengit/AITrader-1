"""
Double Supertrend Strategy [Alorse] — Python translation
Original: strategies/trend/Double Supertrend.pine

Entry: Both fast and slow Supertrends show uptrend
Exit: Either Supertrend flips to downtrend
"""
import numpy as np
import vectorbt as vbt
import pandas_ta as ta

fast_period = 7
fast_mult = 2.0
slow_period = 14
slow_mult = 3.0

close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

st_fast = ta.supertrend(high, low, close, length=fast_period, multiplier=fast_mult)
trend_fast = st_fast[f'SUPERTd_{fast_period}_{fast_mult}']

st_slow = ta.supertrend(high, low, close, length=slow_period, multiplier=slow_mult)
trend_slow = st_slow[f'SUPERTd_{slow_period}_{slow_mult}']

entries = (trend_fast == 1) & (trend_slow == 1) & (trend_fast.shift(1) == -1)
exits = (trend_fast == -1) | (trend_slow == -1)

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)
