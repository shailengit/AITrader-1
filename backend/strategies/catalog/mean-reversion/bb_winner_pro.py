"""
BB Winner PRO [Alorse] — Python translation
Original: strategies/mean-reversion/BB Winner PRO.pine v2.0.8

Multi-filter mean reversion:
1. Bollinger Bands — entry when candle body penetrates band
2. RSI filter — long only when RSI < threshold
3. MA filter — close above/below 200 EMA/SMA
4. Early close — close when price touches opposite band

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
use_rsi = True
rsi_above = 45
rsi_length = 14
use_ma = True
ma_type = 'EMA'
ma_length = 200
candle_pct = 0.30
close_early = True
use_stop_loss = True
sl_percent = 0.07

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
open_p = ohlcv['Open']

# ── Indicator Computation (VBT built-in) ───────────────────────────────
bb = vbt.BBANDS.run(close, window=bb_length, alpha=bb_mult)
bb_upper = bb.upper
bb_lower = bb.lower
bb_mid = bb.middle

rsi = vbt.RSI.run(close, window=rsi_length).rsi

if ma_type == 'EMA':
    ma = vbt.MA.run(close, window=ma_length, ewm=True).ma
else:
    ma = vbt.MA.run(close, window=ma_length, ewm=False).ma

# ── Signal Generation ───────────────────────────────────────────────────
# Candle body and penetration zones
candle_body = (close - open_p).abs()
body_low = pd.Series(np.where(close > open_p, open_p, close), index=close.index)
body_high = pd.Series(np.where(close > open_p, close, open_p), index=close.index)
penetration_zone_low = body_low - (candle_body * candle_pct)
penetration_zone_high = body_high + (candle_body * candle_pct)

# Broadcast Series/arrays to match BB MultiIndex columns during optimization
pzl = _bc(penetration_zone_low, bb_lower)
pzh = _bc(penetration_zone_high, bb_upper)
close_l = _bc(close, bb_lower)
close_u = _bc(close, bb_upper)
open_l = _bc(open_p, bb_lower)
open_u = _bc(open_p, bb_upper)

# Long: bearish candle body penetrates below lower BB
long_candle = (pzl < bb_lower) & (close_l < open_l)
# Short: bullish candle body penetrates above upper BB
short_candle = (pzh > bb_upper) & (close_u > open_u)

# Filters
rsi_filter_long = (_bc(rsi, bb_lower) < rsi_above) if use_rsi else True
rsi_filter_short = (_bc(rsi, bb_upper) > (100 - rsi_above)) if use_rsi else True
ma_filter_long = (close_l > _bc(ma, bb_lower)) if use_ma else True
ma_filter_short = (close_u < _bc(ma, bb_upper)) if use_ma else True

# Combined entries
entries_long = long_candle & rsi_filter_long & ma_filter_long
entries_short = short_candle & rsi_filter_short & ma_filter_short
entries = entries_long | entries_short

# Exits: early close when price touches opposite band
long_exits = close_early & (close_l >= bb_upper) if close_early else entries_short
short_exits = close_early & (close_u <= bb_lower) if close_early else entries_long
exits = long_exits | short_exits

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    sl_stop=sl_percent if use_stop_loss else None,
    broadcast_kwargs={'keep_pd': True},
    direction='both',
)