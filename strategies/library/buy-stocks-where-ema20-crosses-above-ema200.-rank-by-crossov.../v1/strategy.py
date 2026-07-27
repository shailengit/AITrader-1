"""Strategy template — fill in the 4 functions below.

This is a KNOWN-WORKING template. Do NOT change:
- The imports at the top
- The engine wiring at the bottom
- The CONFIG instantiation
- The function signatures

Only fill in the bodies of precompute(), entry_score(), holding_score(), exit_check().
"""
import os
import sys
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db.database import engine  # shared engine — do NOT use create_engine()
from app.utils.security import get_safe_table_name
import importlib.util


# ── Constants (override as needed) ─────────────────────────────────────────
AS_OF = "2020-01-01"
END = "2026-07-08"
CAPITAL = 100_000.0
MAX_HOLDINGS = 5
MIN_HOLD_DAYS = 0
TRAILING_STOP = 0.20
TAKE_PROFIT = 999.0       # disabled by default
TIME_STOP_DAYS = 60       # 60 calendar days
MAX_SECTOR_COUNT = 2
BULL_EXPOSURE = 1.0
BEAR_EXPOSURE = 0.50
ANGLE_WEIGHT = 0.60
CAP_WEIGHT = 0.40
STRATEGY_NAME = "Golden Cross with ATR Filter"


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  FILL IN THE 4 FUNCTIONS BELOW                                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def precompute(tickers: List[str], start: str, end: str) -> Dict[str, Any]:
    """Build stock_db: ticker → {close, dates, ema20, ema200, crossovers, market_cap, sector,
    avg_volume_60, spread_min_252, spread_max_252, atr_pct, global_log_cap_min, global_log_cap_max}.

    For each ticker:
      1. Get safe table name: get_safe_table_name(ticker)
      2. Query OHLCV: SELECT "Date", "Open", "High", "Low", "Close", "Volume"
         FROM "{table}" WHERE "Date" >= :start AND "Date" <= :end ORDER BY "Date"
         Use pd.read_sql(text(query), engine, params={...})
      3. Compute indicators (EMA20, EMA200, etc.)
      4. Detect golden crosses (EMA20 crosses above EMA200) and death crosses
      5. Get metadata: SELECT sector, market_cap FROM stock_metadata WHERE ticker = :ticker
         Use ticker.upper() for the parameter
         IMPORTANT: market_cap can be None — skip if so
      6. Populate crossovers list with {date, price, angle, volatility, volume_ratio}
         and {date, death_cross: True} for death crosses

    Returns stock_db dict.
    """
    stock_db = {}
    # We'll collect all log market caps to compute global min/max
    all_log_caps = []

    # Extend start to have enough history for EMA200 (need at least 200 bars before start)
    start_dt = pd.Timestamp(start)
    lookback_start = (start_dt - pd.Timedelta(days=400)).strftime("%Y-%m-%d")

    for ticker in tickers:
        try:
            table = get_safe_table_name(ticker)
        except ValueError:
            continue

        # Query OHLCV with lookback
        query = text(
            f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" '
            f'FROM "{table}" WHERE "Date" >= :start AND "Date" <= :end ORDER BY "Date"'
        )
        try:
            df = pd.read_sql(query, engine, params={"start": lookback_start, "end": end})
        except Exception:
            continue
        if df.empty:
            continue

        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        close = df["Close"].values.astype(float)
        high = df["High"].values.astype(float)
        low = df["Low"].values.astype(float)
        volume = df["Volume"].values.astype(float)
        dates = df.index.values  # numpy datetime64

        # Need at least 200 data points for EMA200
        if len(close) < 200:
            continue

        # Compute EMAs
        ema20 = pd.Series(close).ewm(span=20, adjust=False).mean().values
        ema200 = pd.Series(close).ewm(span=200, adjust=False).mean().values

        # Skip if last EMA200 is NaN (should not happen with enough data)
        if np.isnan(ema200[-1]):
            continue

        # Compute spread = (EMA20 - EMA200) / EMA200 * 100
        spread = (ema20 - ema200) / ema200 * 100.0

        # Compute 252-day min/max of spread (use all available data)
        spread_min_252 = np.nanmin(spread)
        spread_max_252 = np.nanmax(spread)
        if np.isnan(spread_min_252) or np.isnan(spread_max_252):
            continue

        # Compute average volume over last 60 days
        avg_volume_60 = pd.Series(volume).rolling(60).mean().values

        # Compute ATR (20-day average true range as % of close)
        # True range = max(high-low, abs(high-prev_close), abs(low-prev_close))
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]  # first day no previous
        tr = np.maximum(high - low, np.abs(high - prev_close))
        tr = np.maximum(tr, np.abs(low - prev_close))
        atr = pd.Series(tr).rolling(20).mean().values
        atr_pct = atr / close * 100.0  # as percentage of price

        # Detect golden crosses: EMA20 > EMA200 and previous EMA20 <= EMA200
        golden_cross = (ema20 > ema200) & (np.roll(ema20, 1) <= np.roll(ema200, 1))
        golden_cross[0] = False  # no previous day

        # Detect death crosses: EMA20 < EMA200 and previous EMA20 >= EMA200
        death_cross = (ema20 < ema200) & (np.roll(ema20, 1) >= np.roll(ema200, 1))
        death_cross[0] = False

        # Fetch metadata
        meta_query = text(
            "SELECT sector, market_cap FROM stock_metadata WHERE ticker = :ticker"
        )
        try:
            meta_df = pd.read_sql(meta_query, engine, params={"ticker": ticker.upper()})
        except Exception:
            continue
        if meta_df.empty:
            continue
        sector = meta_df.iloc[0]["sector"]
        market_cap = meta_df.iloc[0]["market_cap"]
        if market_cap is None or market_cap <= 0:
            continue
        log_market_cap = np.log10(market_cap)
        all_log_caps.append(log_market_cap)

        # Build crossovers list
        crossovers = []
        for i in range(len(dates)):
            if golden_cross[i]:
                # Apply price filter: close >= $5 at entry
                if close[i] < 5.0:
                    continue
                # Apply volume filter: avg volume > 100k
                if avg_volume_60[i] <= 100000:
                    continue
                # Apply volatility filter: ATR% <= 10%
                if atr_pct[i] > 10.0:
                    continue
                crossovers.append({
                    "date": pd.Timestamp(dates[i]).strftime("%Y-%m-%d"),
                    "price": float(close[i]),
                    "angle": float(spread[i]),
                    "volatility": float(atr_pct[i]),
                    "volume_ratio": float(volume[i] / avg_volume_60[i]) if avg_volume_60[i] > 0 else 0.0,
                    "market_cap": float(market_cap),
                    "sector": sector,
                    "avg_volume_60": float(avg_volume_60[i]),
                    "spread_min_252": float(spread_min_252),
                    "spread_max_252": float(spread_max_252),
                })
            if death_cross[i]:
                crossovers.append({
                    "date": pd.Timestamp(dates[i]).strftime("%Y-%m-%d"),
                    "death_cross": True,
                })

        stock_db[ticker] = {
            "close": close,
            "dates": dates,
            "ema20": ema20,
            "ema200": ema200,
            "crossovers": crossovers,
            "market_cap": float(market_cap),
            "sector": sector,
            "avg_volume_60": avg_volume_60,
            "spread_min_252": spread_min_252,
            "spread_max_252": spread_max_252,
            "atr_pct": atr_pct,
        }

    # Compute global log market cap min/max
    if all_log_caps:
        global_log_cap_min = float(np.min(all_log_caps))
        global_log_cap_max = float(np.max(all_log_caps))
    else:
        global_log_cap_min = 0.0
        global_log_cap_max = 1.0

    # Add global stats to each stock's crossovers (for entry_score access)
    for ticker, data in stock_db.items():
        for co in data["crossovers"]:
            if "death_cross" not in co:
                co["global_log_cap_min"] = global_log_cap_min
                co["global_log_cap_max"] = global_log_cap_max

    return stock_db


def entry_score(candidate: dict, market_cap_stats: dict) -> float:
    """Score a candidate in [0, 1]. Higher = better.

    candidate has: ticker, angle, market_cap, price, sector, volume_ratio,
                   volatility, avg_volume_60, spread_min_252, spread_max_252,
                   global_log_cap_min, global_log_cap_max
    market_cap_stats has: cap_min, cap_max, cap_range (not used, we use global stats)

    Use ANGLE_WEIGHT and CAP_WEIGHT for the weighted score.
    Normalize angle and market_cap to [0, 1] before combining.
    """
    # Price filter
    if candidate.get("price", 0) < 5.0:
        return 0.0
    # Volume filter
    if candidate.get("avg_volume_60", 0) <= 100000:
        return 0.0
    # Volatility filter (ATR% <= 10%)
    if candidate.get("volatility", 100) > 10.0:
        return 0.0

    # Normalize angle using stock-specific 252-day min/max
    angle = candidate["angle"]
    spread_min = candidate["spread_min_252"]
    spread_max = candidate["spread_max_252"]
    if spread_max > spread_min:
        norm_angle = (angle - spread_min) / (spread_max - spread_min)
    else:
        norm_angle = 0.5
    norm_angle = max(0.0, min(1.0, norm_angle))

    # Normalize log market cap using global min/max
    log_cap = np.log10(candidate["market_cap"])
    global_min = candidate["global_log_cap_min"]
    global_max = candidate["global_log_cap_max"]
    if global_max > global_min:
        norm_cap = (log_cap - global_min) / (global_max - global_min)
    else:
        norm_cap = 0.5
    norm_cap = max(0.0, min(1.0, norm_cap))

    score = ANGLE_WEIGHT * norm_angle + CAP_WEIGHT * norm_cap
    return score


def holding_score(ticker: str, date_str: str, holding: dict, market_cap_stats: dict) -> float:
    """Re-score an existing holding in [0, 1]. 0 = weak, rotate out.

    holding has: entry_date, entry_price, peak_price, shares, score, angle,
                 market_cap, sector, _stock_data
    holding._stock_data has the precomputed arrays: close, dates, ema20, ema200,
                 spread_min_252, spread_max_252, global_log_cap_min, global_log_cap_max

    Use np.searchsorted(dates, np.datetime64(date_str)) to find the current index.
    """
    sd = holding["_stock_data"]
    dates = sd["dates"]
    idx = np.searchsorted(dates, np.datetime64(date_str))
    if idx >= len(dates):
        idx = len(dates) - 1

    # Current spread
    ema20 = sd["ema20"][idx]
    ema200 = sd["ema200"][idx]
    if ema200 == 0:
        return 0.0
    spread = (ema20 - ema200) / ema200 * 100.0

    # Normalize angle
    spread_min = sd["spread_min_252"]
    spread_max = sd["spread_max_252"]
    if spread_max > spread_min:
        norm_angle = (spread - spread_min) / (spread_max - spread_min)
    else:
        norm_angle = 0.5
    norm_angle = max(0.0, min(1.0, norm_angle))

    # Normalize log market cap (use global stats from holding's _stock_data)
    log_cap = np.log10(holding["market_cap"])
    global_min = sd.get("global_log_cap_min", 0.0)
    global_max = sd.get("global_log_cap_max", 1.0)
    if global_max > global_min:
        norm_cap = (log_cap - global_min) / (global_max - global_min)
    else:
        norm_cap = 0.5
    norm_cap = max(0.0, min(1.0, norm_cap))

    score = ANGLE_WEIGHT * norm_angle + CAP_WEIGHT * norm_cap
    return score


def exit_check(ticker: str, date_str: str, holding: dict, stock_db: dict) -> Optional[str]:
    """Return exit reason string or None to hold.

    Priority order: Death Cross, Trailing Stop, Take Profit, Time Stop.
    Check holding._stock_data for indicator arrays.
    Use np.searchsorted(dates, np.datetime64(date_str)) for index lookup.
    """
    sd = holding["_stock_data"]
    dates = sd["dates"]
    idx = np.searchsorted(dates, np.datetime64(date_str))
    if idx >= len(dates):
        idx = len(dates) - 1

    # 1. Death Cross
    if idx >= 1:
        ema20_curr = sd["ema20"][idx]
        ema200_curr = sd["ema200"][idx]
        ema20_prev = sd["ema20"][idx - 1]
        ema200_prev = sd["ema200"][idx - 1]
        if ema20_curr < ema200_curr and ema20_prev >= ema200_prev:
            return "Death Cross"

    # 2. Trailing Stop
    close = sd["close"][idx]
    peak_price = holding["peak_price"]
    if close < peak_price * (1.0 - TRAILING_STOP):
        return "Trailing Stop"

    # 3. Take Profit (disabled)
    # if close >= holding["entry_price"] * (1.0 + TAKE_PROFIT):
    #     return "Take Profit"

    # 4. Time Stop
    entry_date = holding["entry_date"]
    days_held = (pd.Timestamp(date_str) - pd.Timestamp(entry_date)).days
    if days_held > TIME_STOP_DAYS:
        return "Time Stop"

    return None


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  DO NOT CHANGE BELOW THIS LINE — engine wiring                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

_engine_path = os.path.join(os.path.dirname(__file__), "..", "..", "engine.py")
_spec = importlib.util.spec_from_file_location("strategies_engine_inline", _engine_path)
_engine = importlib.util.module_from_spec(_spec)
sys.modules["strategies_engine_inline"] = _engine
_spec.loader.exec_module(_engine)

CONFIG = _engine.StrategyConfig(
    as_of=AS_OF,
    end=END,
    capital=CAPITAL,
    max_holdings=MAX_HOLDINGS,
    min_hold_days=MIN_HOLD_DAYS,
    trailing_stop=TRAILING_STOP,
    take_profit=TAKE_PROFIT,
    time_stop_days=TIME_STOP_DAYS,
    max_sector_count=MAX_SECTOR_COUNT,
    bull_exposure=BULL_EXPOSURE,
    bear_exposure=BEAR_EXPOSURE,
    angle_weight=ANGLE_WEIGHT,
    cap_weight=CAP_WEIGHT,
    precompute_fn=precompute,
    entry_score_fn=entry_score,
    holding_score_fn=holding_score,
    exit_check_fn=exit_check,
    name=STRATEGY_NAME,
    score_squared_sizing=True,
)
