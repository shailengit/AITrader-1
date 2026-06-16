"""
StochRSI + Supertrend Strategy [Alorse] — Python translation
Original: strategies/momentum/StochRSI + Supertrend Strategy.pine

Entry: StochRSI crosses above oversold level AND Supertrend is in uptrend
Exit: StochRSI crosses below overbought level OR Supertrend flips
"""
import numpy as np
import vectorbt as vbt
import pandas_ta as pta

stochrsi_period = 14
stochrsi_k = 3
stochrsi_d = 3
oversold = 20
overbought = 80
st_period = 10
st_mult = 3.0

close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

from ta.momentum import StochRSIIndicator
stoch_rsi = StochRSIIndicator(close, window=stochrsi_period, smooth1=stochrsi_k, smooth2=stochrsi_d)
k_line = stoch_rsi.stochrsi_k()
d_line = stoch_rsi.stochrsi_d()

st = pta.supertrend(high, low, close, length=st_period, multiplier=st_mult)
trend = st[f'SUPERTd_{st_period}_{st_mult}']

entries = (k_line > oversold) & (k_line.shift(1) <= oversold) & (trend == 1)
exits = (k_line < overbought) & (k_line.shift(1) >= overbought) | (trend == -1)

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)
