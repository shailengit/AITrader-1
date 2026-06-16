"""
Bollinger Breakout Strategy [kodify] — Python translation
Original: strategies/mean-reversion/Bollinger Breakout [kodify].pine

Entry (long): Close crosses above upper Bollinger Band (breakout)
Entry (short): Close crosses below lower Bollinger Band (breakdown)
Exit: Close crosses back to the middle SMA line
"""
import numpy as np
import vectorbt as vbt

# ── Parameters ─────────────────────────────────────────────────────────
bb_length = 20            # Bollinger Bands SMA period
bb_std = 2.0              # Standard deviation multiplier

# ── Data Loading ────────────────────────────────────────────────────────
close = ohlcv['Close']

# ── Indicator Computation ───────────────────────────────────────────────
from ta.volatility import BollingerBands

bb = BollingerBands(close, window=bb_length, window_dev=bb_std)
bb_upper = bb.bollinger_hband()
bb_lower = bb.bollinger_lband()
bb_mid = bb.bollinger_mavg()

# ── Signal Generation ───────────────────────────────────────────────────
# Long entry: close crosses above upper band
enter_long = (close > bb_upper) & (close.shift(1) <= bb_upper.shift(1))
# Long exit: close crosses below middle band
exit_long = (close < bb_mid) & (close.shift(1) >= bb_mid.shift(1))

# Short entry: close crosses below lower band
enter_short = (close < bb_lower) & (close.shift(1) >= bb_lower.shift(1))
# Short exit: close crosses above middle band
exit_short = (close > bb_mid) & (close.shift(1) <= bb_mid.shift(1))

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
