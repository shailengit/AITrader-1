"""
TTM Squeeze Strategy [Alorse] — Python translation
Original: strategies/momentum/TTM Squeeze.pine

Entry: Bollinger Bands expand outside Keltner Channels (squeeze fires) in direction of momentum
Exit: Opposite squeeze fire or trend reversal

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
bb_length = 20
bb_mult = 2.0
kc_mult = 1.5

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
bb = vbt.BBANDS.run(close, window=bb_length, alpha=bb_mult)
bb_upper = bb.upper
bb_lower = bb.lower
bb_mid = bb.middle

atr = vbt.ATR.run(high, low, close, window=bb_length).atr

# Broadcast ATR to match BB column structure when parameterized
atr_bc = _bc(atr, bb_mid)

# Keltner Channels
kc_upper = bb_mid + (kc_mult * atr_bc)
kc_lower = bb_mid - (kc_mult * atr_bc)

# ── Signal Generation ───────────────────────────────────────────────────
# Broadcast BB bands to match Keltner columns before comparison
bb_upper_bc = _bc(bb_upper, kc_upper)
bb_lower_bc = _bc(bb_lower, kc_lower)

# Squeeze: BB inside Keltner
squeeze_on = (bb_upper_bc < kc_upper) & (bb_lower_bc > kc_lower)
# Squeeze fire: BB was inside Keltner, now outside (expanding)
squeeze_fire = _bc(squeeze_on.shift(1), squeeze_on) & ~squeeze_on

# Direction: close relative to mid-BB
close_bc = _bc(close, bb_mid)
entries = squeeze_fire & (close_bc > bb_mid)
exits = squeeze_fire & (close_bc < bb_mid)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)