"""
StochRSI + Supertrend Strategy [Alorse] — Python translation
Original: strategies/momentum/StochRSI + Supertrend Strategy.pine

Entry: StochRSI crosses above oversold level AND Supertrend is in uptrend
Exit: StochRSI crosses below overbought level OR Supertrend flips

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
stochrsi_period = 14
stochrsi_k = 3
stochrsi_d = 3
oversold = 20
overbought = 80
st_period = 10
st_mult = 3.0

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
# StochRSI approximated as Stochastic applied to the RSI series
rsi = vbt.RSI.run(close, window=stochrsi_period).rsi
stoch = vbt.STOCH.run(rsi, rsi, rsi, k_window=stochrsi_k, d_window=stochrsi_d)
k_line = stoch.percent_k

Supertrend = vbt.IndicatorFactory.from_pandas_ta('supertrend')
st = Supertrend.run(high, low, close, length=st_period, multiplier=st_mult)
trend = st.supertd

# ── Signal Generation ───────────────────────────────────────────────────
entries = (
    _bc(k_line > oversold, trend)
    & _bc(k_line.shift(1) <= oversold, trend)
    & (trend == 1)
)
exits = (
    _bc(k_line < overbought, trend) & _bc(k_line.shift(1) >= overbought, trend)
) | (trend == -1)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)