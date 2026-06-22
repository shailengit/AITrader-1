"""
Bollinger Breakout Strategy [kodify] — Python translation
Original: strategies/mean-reversion/Bollinger Breakout [kodify].pine

Entry (long): Close crosses above upper Bollinger Band (breakout)
Entry (short): Close crosses below lower Bollinger Band (breakdown)
Exit: Close crosses back to the middle SMA line

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
bb_length = 20            # Bollinger Bands SMA period
bb_std = 2.0              # Standard deviation multiplier

# ── Ticker & Date Range ─────────────────────────────────────────────────
ticker = 'AAPL'
start = '2023-01-01'
end = '2024-01-01'

# ── Data Loading ────────────────────────────────────────────────────────
data = get_data(ticker, start, end)
ohlcv = data
close = ohlcv['Close']

# ── Indicator Computation (VBT built-in) ───────────────────────────────
bb = vbt.BBANDS.run(close, window=bb_length, alpha=bb_std)
bb_upper = bb.upper
bb_lower = bb.lower
bb_mid = bb.middle

# ── Signal Generation ───────────────────────────────────────────────────
# Broadcast close to match the BB DataFrame columns before comparison
c_bc = _bc(close, bb_upper)

# Long entry: close crosses above upper band
enter_long = (c_bc > bb_upper) & (c_bc.shift(1) <= bb_upper.shift(1))
# Long exit: close crosses below middle band
exit_long = (c_bc < bb_mid) & (c_bc.shift(1) >= bb_mid.shift(1))

# Short entry: close crosses below lower band
enter_short = (c_bc < bb_lower) & (c_bc.shift(1) >= bb_lower.shift(1))
# Short exit: close crosses above middle band
exit_short = (c_bc > bb_mid) & (c_bc.shift(1) <= bb_mid.shift(1))

# Combined entries and exits
entries = enter_long | enter_short
exits = exit_long | exit_short

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    broadcast_kwargs={'keep_pd': True},
    direction='both',
)