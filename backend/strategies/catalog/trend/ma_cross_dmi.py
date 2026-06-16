"""
MA Cross + DMI Strategy [Alorse] — Python translation
Original: strategies/trend/MA Cross + DMI.pine

Entry: Fast MA crosses above slow MA AND ADX > threshold (strong trend)
Exit: Fast MA crosses below slow MA
"""
import numpy as np
import vectorbt as vbt

fast_ma = 20
slow_ma = 50
adx_period = 14
adx_threshold = 25

close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

from ta.trend import EMAIndicator, ADXIndicator

ema_fast = EMAIndicator(close, window=fast_ma).ema_indicator()
ema_slow = EMAIndicator(close, window=slow_ma).ema_indicator()

adx = ADXIndicator(high, low, close, window=adx_period)
adx_val = adx.adx()

entries = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1)) & (adx_val > adx_threshold)
exits = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)
