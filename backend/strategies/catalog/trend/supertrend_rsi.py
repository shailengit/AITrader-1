"""
Supertrend + RSI Strategy [Alorse] — Python translation
Original: strategies/trend/Supertrend + RSI.pine

Entry: Supertrend flips to uptrend AND RSI > threshold
Exit: Supertrend flips to downtrend

Data: Loads from local PostgreSQL via get_data(ticker, start, end)
Uses VBT-compatible indicators for optimization/WFO.
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
period = 10
multiplier = 3.0
rsi_length = 14
rsi_threshold = 50

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

# ── Indicator Computation ──────────────────────────────────────────────
Supertrend = vbt.IndicatorFactory.from_pandas_ta('supertrend')
st = Supertrend.run(high, low, close, length=period, multiplier=multiplier)
trend = st.supertd

rsi = vbt.RSI.run(close, window=rsi_length).rsi

# ── Signal Generation ───────────────────────────────────────────────────
entries = (trend == 1) & (trend.shift(1) == -1) & _bc(rsi > rsi_threshold, trend)
exits = (trend == -1) & (trend.shift(1) == 1)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)