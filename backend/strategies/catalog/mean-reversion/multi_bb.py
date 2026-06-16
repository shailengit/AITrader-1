"""
Multi BB Strategy [Alorse] — Python translation
Original: strategies/mean-reversion/Multi BB.pine

Entry: Price is below the lower band of multiple Bollinger Bands (20, 50, 100)
Exit: Price returns above the middle band of the shortest BB
"""
import numpy as np
import vectorbt as vbt

bb_period_short = 20
bb_period_mid = 50
bb_period_long = 100
bb_std = 2.0

close = ohlcv['Close']

from ta.volatility import BollingerBands

bb_short = BollingerBands(close, window=bb_period_short, window_dev=bb_std)
bb_mid = BollingerBands(close, window=bb_period_mid, window_dev=bb_std)
bb_long = BollingerBands(close, window=bb_period_long, window_dev=bb_std)

lower_short = bb_short.bollinger_lband()
lower_mid = bb_mid.bollinger_lband()
lower_long = bb_long.bollinger_lband()

mid_short = bb_short.bollinger_mavg()

# Entry: price below all 3 lower bands
entries = (close < lower_short) & (close < lower_mid) & (close < lower_long)
# Exit: price returns above short BB middle band
exits = close > mid_short

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)
