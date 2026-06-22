"""
MA Cross + DMI Strategy [Alorse] — Python translation
Original: strategies/trend/MA Cross + DMI.pine

Entry: Fast MA crosses above slow MA AND ADX > threshold (strong trend)
Exit: Fast MA crosses below slow MA

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
fast_ma = 20
slow_ma = 50
adx_period = 14
adx_threshold = 25

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
ema_fast = vbt.MA.run(close, window=fast_ma, ewm=True).ma
ema_slow = vbt.MA.run(close, window=slow_ma, ewm=True).ma

ADX = vbt.IndicatorFactory.from_pandas_ta('adx')
adx = ADX.run(high, low, close, length=adx_period)
adx_val = adx.adx

# ── Signal Generation ───────────────────────────────────────────────────
# Broadcast non-parameterized operands to match ema_fast columns when optimizing
ef_bc = ema_fast
es_bc = _bc(ema_slow, ema_fast)
adx_bc = _bc(adx_val, ema_fast)
entries = (ef_bc > es_bc) & (ef_bc.shift(1) <= es_bc.shift(1)) & (adx_bc > adx_threshold)
exits = (ef_bc < es_bc) & (ef_bc.shift(1) >= es_bc.shift(1))

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)