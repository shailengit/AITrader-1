"""
MEMA + BB + RSI Strategy [Alorse] — Python translation
Original: strategies/mean-reversion/MEMA + BB + RSI [Alorse].pine

Entry: Price touches lower BB, RSI is oversold, and EMAs are aligned
Exit: Price touches upper BB or RSI becomes overbought
"""
import numpy as np
import vectorbt as vbt

ema_fast = 10
ema_mid = 30
ema_slow = 50
bb_length = 20
rsi_length = 14

close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

from ta.trend import EMAIndicator
from ta.volatility import BollingerBands
from ta.momentum import RSIIndicator

ema10 = EMAIndicator(close, window=ema_fast).ema_indicator()
ema30 = EMAIndicator(close, window=ema_mid).ema_indicator()
ema50 = EMAIndicator(close, window=ema_slow).ema_indicator()

bb = BollingerBands(close, window=bb_length, window_dev=2.0)
bb_lower = bb.bollinger_lband()
bb_upper = bb.bollinger_hband()

rsi = RSIIndicator(close, window=rsi_length).rsi()

# Long: price near lower BB, RSI oversold (< 30), EMAs aligned (fast > mid > slow = uptrend)
price_near_lower = close <= bb_lower * 1.01
rsi_oversold = rsi < 30
emas_aligned = (ema10 > ema30) & (ema30 > ema50)

entries = price_near_lower & rsi_oversold & emas_aligned

# Exit: price reaches upper BB or RSI overbought
exits = (close >= bb_upper) | (rsi > 70)

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)
