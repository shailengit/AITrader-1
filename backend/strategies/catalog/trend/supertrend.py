"""
Supertrend Strategy [Alorse] — Python translation
Original: strategies/trend/Supertrend.pine

Entry: Supertrend flips from downtrend to uptrend (trend goes from -1 to +1)
Exit: Supertrend flips from uptrend to downtrend (trend goes from +1 to -1)

Data: Loads from local PostgreSQL via get_data(ticker, start, end)
Uses VBT-compatible indicators for optimization/WFO.
"""
import numpy as np
import vectorbt as vbt

# ── Parameters ─────────────────────────────────────────────────────────
period = 10               # ATR period
multiplier = 3.7           # ATR multiplier

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
trend = st.supertd        # 1 = uptrend, -1 = downtrend

# ── Signal Generation ───────────────────────────────────────────────────
entries = (trend == 1) & (trend.shift(1) == -1)
exits = (trend == -1) & (trend.shift(1) == 1)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    broadcast_kwargs={'keep_pd': True},
    direction='longonly',
)