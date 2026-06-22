"""
MACD + RSI Strategy [Alorse] — Python translation
Original: strategies/momentum/MACD+RSI.pine

Entry: MACD crosses above signal line AND RSI was < oversold_level in last N candles
Exit: MACD crosses below signal line AND RSI was > overbought_level in last N candles
Stop: Fixed percentage stop loss from entry price

Data: Loads from local PostgreSQL via get_data(ticker, start, end)
Uses VBT built-in indicators for optimization/WFO compatibility.
"""
import numpy as np
import pandas as pd
import vectorbt as vbt


def _bc(s, ref):
    """Broadcast to match reference shape for safe &/| with MultiIndex columns."""
    if isinstance(s, pd.Series) and isinstance(ref, (pd.DataFrame, pd.Series)) and hasattr(ref, 'columns') and ref.columns.nlevels > 1:
        return pd.DataFrame(np.broadcast_to(s.values[:, None], ref.shape), index=ref.index, columns=ref.columns)
    if isinstance(s, pd.DataFrame) and isinstance(ref, pd.DataFrame):
        if s.columns.nlevels != ref.columns.nlevels or s.columns.tolist() != ref.columns.tolist():
            return pd.DataFrame(np.broadcast_to(s.values, ref.shape), index=ref.index, columns=ref.columns)
    return s

# ── Parameters (tunable by QuantGen optimizer) ──────────────────────────
fast_length = 12          # MACD fast EMA period
slow_length = 26          # MACD slow EMA period
signal_length = 9         # MACD signal line period
rsi_length = 14           # RSI period
rsi_oversold = 30         # RSI oversold threshold
rsi_overbought = 70       # RSI overbought threshold
rsi_lookback = 5          # Check RSI condition over last N candles
stop_loss_pct = 0.01      # 1% stop loss

# ── Ticker & Date Range (overridden by Builder UI) ───────────────────────
ticker = 'AAPL'
start = '2023-01-01'
end = '2024-01-01'

# ── Data Loading from PostgreSQL ────────────────────────────────────────
data = get_data(ticker, start, end)
ohlcv = data
close = ohlcv['Close']

# ── Indicator Computation (VBT built-in) ───────────────────────────────
macd = vbt.MACD.run(close, fast_window=fast_length, slow_window=slow_length, signal_window=signal_length)
macd_line = macd.macd
signal_line = macd.signal

rsi = vbt.RSI.run(close, window=rsi_length).rsi

# ── Signal Generation ───────────────────────────────────────────────────
bull_cross = macd_line.vbt.crossed_above(signal_line)
bear_cross = macd_line.vbt.crossed_below(signal_line)

rsi_was_oversold = _bc(rsi.rolling(rsi_lookback).min() < rsi_oversold, bull_cross)

entries = bull_cross & rsi_was_oversold
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