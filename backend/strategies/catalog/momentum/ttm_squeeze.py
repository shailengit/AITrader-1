"""
TTM Squeeze Strategy [Alorse] — Python translation
Original: strategies/momentum/TTM Squeeze.pine

Entry: Bollinger Bands expand outside Keltner Channels (squeeze fires) in direction of momentum
Exit: Opposite squeeze fire or trend reversal
"""
import numpy as np
import vectorbt as vbt

bb_length = 20
bb_mult = 2.0
kc_mult = 1.5

close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

from ta.volatility import BollingerBands, AverageTrueRange

bb = BollingerBands(close, window=bb_length, window_dev=bb_mult)
bb_upper = bb.bollinger_hband()
bb_lower = bb.bollinger_lband()
bb_mid = bb.bollinger_mavg()

atr = AverageTrueRange(high, low, close, window=bb_length).average_true_range()

# Keltner Channels
kc_upper = bb_mid + (kc_mult * atr)
kc_lower = bb_mid - (kc_mult * atr)

# Squeeze: BB inside Keltner
squeeze_on = (bb_upper < kc_upper) & (bb_lower > kc_lower)
# Squeeze fire: BB was inside Keltner, now outside (expanding)
squeeze_fire = squeeze_on.shift(1) & ~squeeze_on

# Direction: close relative to mid-BB
entries = squeeze_fire & (close > bb_mid)
exits = squeeze_fire & (close < bb_mid)

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)
