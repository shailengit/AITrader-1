"""
Double Supertrend Strategy [Alorse] — Python translation
Original: strategies/trend/Double Supertrend.pine

Entry: Both fast and slow Supertrends show uptrend
Exit: Either Supertrend flips to downtrend

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
fast_period = 7
fast_mult = 2.0
slow_period = 14
slow_mult = 3.0

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
st_fast = Supertrend.run(high, low, close, length=fast_period, multiplier=fast_mult)
trend_fast = st_fast.supertd

st_slow = Supertrend.run(high, low, close, length=slow_period, multiplier=slow_mult)
trend_slow = st_slow.supertd

# ── Signal Generation ───────────────────────────────────────────────────
# Broadcast both trends to a common column structure when parameters are arrays
entries = (
    (_bc(trend_fast, trend_fast) == 1)
    & (_bc(trend_slow, trend_fast) == 1)
    & (_bc(trend_fast.shift(1), trend_fast) == -1)
)
exits = (_bc(trend_fast, trend_fast) == -1) | (_bc(trend_slow, trend_fast) == -1)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)