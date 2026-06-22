"""
MEMA + BB + RSI Strategy [Alorse] — Python translation
Original: strategies/mean-reversion/MEMA + BB + RSI [Alorse].pine

Entry: Price touches lower BB, RSI is oversold, and EMAs are aligned
Exit: Price touches upper BB or RSI becomes overbought

Data: Loads from local PostgreSQL via get_data(ticker, start, end)
Uses VBT built-in indicators for optimization/WFO.
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

# ── Parameters ─────────────────────────────────────────────────────────
ema_fast = 10
ema_mid = 30
ema_slow = 50
bb_length = 20
rsi_length = 14

# ── Ticker & Date Range ─────────────────────────────────────────────────
ticker = 'AAPL'
start = '2023-01-01'
end = '2024-01-01'

# ── Data Loading ────────────────────────────────────────────────────────
data = get_data(ticker, start, end)
ohlcv = data
close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

# ── Indicator Computation (VBT built-in) ───────────────────────────────
ema10 = vbt.MA.run(close, window=ema_fast, ewm=True).ma
ema30 = vbt.MA.run(close, window=ema_mid, ewm=True).ma
ema50 = vbt.MA.run(close, window=ema_slow, ewm=True).ma

bb = vbt.BBANDS.run(close, window=bb_length, alpha=2.0)
bb_lower = bb.lower
bb_upper = bb.upper

rsi = vbt.RSI.run(close, window=rsi_length).rsi

# ── Signal Generation ───────────────────────────────────────────────────
# Broadcast Series to match BB MultiIndex columns when parameterized
price_near_lower = _bc(close, bb_lower) <= (bb_lower * 1.01)
rsi_oversold = _bc(rsi, bb_lower) < 30
emas_aligned = (_bc(ema10, bb_lower) > _bc(ema30, bb_lower)) & (_bc(ema30, bb_lower) > _bc(ema50, bb_lower))

entries = price_near_lower & rsi_oversold & emas_aligned

# Exit: price reaches upper BB or RSI overbought
exits = (_bc(close, bb_upper) >= bb_upper) | (_bc(rsi, bb_upper) > 70)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)