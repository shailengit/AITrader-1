"""
MACD + RSI Strategy [Alorse] — Python translation
Original: strategies/momentum/MACD+RSI.pine

Entry: MACD crosses above signal line AND RSI was < oversold_level in last N candles
Exit: MACD crosses below signal line AND RSI was > overbought_level in last N candles
Stop: Fixed percentage stop loss from entry price
"""
import numpy as np
import vectorbt as vbt

# ── Parameters (tunable by QuantGen optimizer) ──────────────────────────
fast_length = 12          # MACD fast EMA period
slow_length = 26          # MACD slow EMA period
signal_length = 9         # MACD signal line period
rsi_length = 14           # RSI period
rsi_oversold = 30         # RSI oversold threshold
rsi_overbought = 70       # RSI overbought threshold
rsi_lookback = 5          # Check RSI condition over last N candles
stop_loss_pct = 0.01      # 1% stop loss

# ── Data Loading ────────────────────────────────────────────────────────
close = ohlcv['Close']

# ── Indicator Computation ───────────────────────────────────────────────
from ta.trend import MACD
from ta.momentum import RSIIndicator

macd = MACD(close, window_slow=slow_length, window_fast=fast_length, window_sign=signal_length)
macd_line = macd.macd()
signal_line = macd.macd_signal()

rsi = RSIIndicator(close, window=rsi_length).rsi()

# ── Signal Generation (VectorBT-compatible) ─────────────────────────────
bull_cross = macd_line.vbt.crossed_above(signal_line)
bear_cross = macd_line.vbt.crossed_below(signal_line)

rsi_was_oversold = rsi.rolling(rsi_lookback).min() < rsi_oversold
rsi_was_overbought = rsi.rolling(rsi_lookback).max() > rsi_overbought

entries = np.logical_and(bull_cross, rsi_was_oversold)

exits = bear_cross

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    sl_stop=stop_loss_pct,
    broadcast_kwargs={'keep_pd': True},
    direction='longonly',
)
