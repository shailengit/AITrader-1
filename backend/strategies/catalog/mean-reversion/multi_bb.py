"""
Multi BB Strategy [Alorse] — Python translation
Original: strategies/mean-reversion/Multi BB.pine

Entry: Price is below the lower band of multiple Bollinger Bands (20, 50, 100)
Exit: Price returns above the middle band of the shortest BB

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
bb_period_short = 20
bb_period_mid = 50
bb_period_long = 100
bb_std = 2.0

# ── Ticker & Date Range ─────────────────────────────────────────────────
ticker = 'AAPL'
start = '2023-01-01'
end = '2024-01-01'

# ── Data Loading ────────────────────────────────────────────────────────
data = get_data(ticker, start, end)
ohlcv = data
close = ohlcv['Close']

# ── Indicator Computation (VBT built-in) ───────────────────────────────
bb_short = vbt.BBANDS.run(close, window=bb_period_short, alpha=bb_std)
bb_mid = vbt.BBANDS.run(close, window=bb_period_mid, alpha=bb_std)
bb_long = vbt.BBANDS.run(close, window=bb_period_long, alpha=bb_std)

lower_short = bb_short.lower
lower_mid = bb_mid.lower
lower_long = bb_long.lower

mid_short = bb_short.middle

# ── Signal Generation ───────────────────────────────────────────────────
# Each BB period may produce a different column structure; broadcast close and
# each band onto the shortest-BB columns before comparing.
c = _bc(close, lower_short)
entries = (c < lower_short) & (c < _bc(lower_mid, lower_short)) & (c < _bc(lower_long, lower_short))
# Exit: price returns above short BB middle band
exits = c > _bc(mid_short, lower_short)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=exits,
    broadcast_kwargs={'keep_pd': True}, direction='longonly',
)