"""
BB Winner PRO [Alorse] — Python translation
Original: strategies/mean-reversion/BB Winner PRO.pine v2.0.8

Multi-filter mean reversion:
1. Bollinger Bands — entry when candle body penetrates band
2. RSI filter — long only when RSI < threshold
3. MA filter — close above/below 200 EMA/SMA
4. Early close — close when price touches opposite band
"""
import numpy as np
import vectorbt as vbt

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

# ── Data Loading ────────────────────────────────────────────────────────
close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']
open_p = ohlcv['Open']

# ── Indicator Computation ───────────────────────────────────────────────
from ta.volatility import BollingerBands
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, SMAIndicator

bb = BollingerBands(close, window=bb_length, window_dev=bb_mult)
bb_upper = bb.bollinger_hband()
bb_lower = bb.bollinger_lband()
bb_mid = bb.bollinger_mavg()

rsi = RSIIndicator(close, window=rsi_length).rsi()

if ma_type == 'EMA':
    ma = EMAIndicator(close, window=ma_length).ema_indicator()
else:
    ma = SMAIndicator(close, window=ma_length).sma_indicator()

# ── Signal Generation ───────────────────────────────────────────────────
# Candle body and penetration zones
candle_body = (close - open_p).abs()
body_low = np.where(close > open_p, open_p, close)
body_high = np.where(close > open_p, close, open_p)
penetration_zone_low = body_low - (candle_body * candle_pct)
penetration_zone_high = body_high + (candle_body * candle_pct)

# Long: bearish candle body penetrates below lower BB
long_candle = (penetration_zone_low < bb_lower) & (close < open_p)
# Short: bullish candle body penetrates above upper BB
short_candle = (penetration_zone_high > bb_upper) & (close > open_p)

# Filters
rsi_filter_long = (rsi < rsi_above) if use_rsi else True
rsi_filter_short = (rsi > (100 - rsi_above)) if use_rsi else True
ma_filter_long = (close > ma) if use_ma else True
ma_filter_short = (close < ma) if use_ma else True

# Combined entries
entries_long = long_candle & rsi_filter_long & ma_filter_long
entries_short = short_candle & rsi_filter_short & ma_filter_short
entries = entries_long | entries_short

# Exits: early close when price touches opposite band
long_exits = close_early & (close >= bb_upper) if close_early else entries_short
short_exits = close_early & (close <= bb_lower) if close_early else entries_long
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
