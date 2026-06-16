"""
Supertrend Strategy [Alorse] — Python translation
Original: strategies/trend/Supertrend.pine

Entry: Supertrend flips from downtrend to uptrend (trend goes from -1 to +1)
Exit: Supertrend flips from uptrend to downtrend (trend goes from +1 to -1)
"""
import numpy as np
import vectorbt as vbt
import pandas_ta as ta

# ── Parameters ─────────────────────────────────────────────────────────
period = 10               # ATR period
multiplier = 3.7          # ATR multiplier

# ── Data Loading ────────────────────────────────────────────────────────
close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

# ── Indicator Computation ───────────────────────────────────────────────
st = ta.supertrend(high, low, close, length=period, multiplier=multiplier)
col_trend = f'SUPERTd_{period}_{multiplier}'
trend = st[col_trend]        # 1 = uptrend, -1 = downtrend

# ── Signal Generation ───────────────────────────────────────────────────
entries = (trend == 1) & (trend.shift(1) == -1)
exits = (trend == -1) & (trend.shift(1) == 1)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    broadcast_kwargs={'keep_pd': True},
    direction='longonly',
)
