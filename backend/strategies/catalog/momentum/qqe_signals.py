"""
QQE Signals Strategy [Alorse] — Python translation
Original: strategies/momentum/QQE signals.pine

Entry: RSI crosses above adaptive threshold (momentum shift)
Exit: RSI crosses below adaptive threshold

Data: Loads from local PostgreSQL via get_data(ticker, start, end)
Uses VBT built-in indicators for optimization/WFO.
"""
import numpy as np
import vectorbt as vbt

# ── Parameters ─────────────────────────────────────────────────────────
rsi_length = 14
smooth_length = 5
fast_factor = 2.0
slow_factor = 4.0

# ── Ticker & Date Range ─────────────────────────────────────────────────
ticker = 'AAPL'
start = '2023-01-01'
end = '2024-01-01'

# ── Data Loading ────────────────────────────────────────────────────────
data = get_data(ticker, start, end)
ohlcv = data
close = ohlcv['Close']

# ── Indicator Computation (VBT built-in) ───────────────────────────────
rsi = vbt.RSI.run(close, window=rsi_length).rsi

# Rolling operations — when rsi is a DataFrame (parameterized), all derived
# series share the same MultiIndex, so comparisons work without broadcasting.
rsi_smooth = rsi.rolling(window=smooth_length).mean()
rsi_std = rsi.rolling(window=rsi_length).std()

# Adaptive threshold based on RSI volatility
upper_threshold = 50 + (rsi_std * fast_factor)
lower_threshold = 50 - (rsi_std * fast_factor)

# ── Signal Generation ───────────────────────────────────────────────────
entries = (rsi_smooth > upper_threshold) & (rsi_smooth.shift(1) <= upper_threshold.shift(1))
exits = (rsi_smooth < lower_threshold) & (rsi_smooth.shift(1) >= lower_threshold.shift(1))

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)