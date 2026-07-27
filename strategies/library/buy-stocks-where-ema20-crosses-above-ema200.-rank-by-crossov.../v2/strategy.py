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
TIME_STOP_DAYS = 9999     # disabled by default
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
    """Build stock_db: ticker → {close, dates, ema20, ema200, crossovers, market_cap, sector, ...}.

    For each ticker:
      1. Get safe table name: get_safe_table_name(ticker)
      2. Query OHLCV: SELECT "Date", "Open", "High", "Low", "Close", "Volume"
         FROM "{table}" WHERE "Date" >= :start AND "Date" <= :end ORDER BY "Date"
         Use pd.read_sql(text(query), engine, params={...})
      3. Compute indicators (EMA20, EMA200, ATR, avg_volume_60)
      4. Detect golden crosses (EMA20 crosses above EMA200) and death crosses
      5. Get metadata: SELECT sector, market_cap FROM stock_metadata WHERE ticker = :ticker
         Use ticker.upper() for the parameter
         IMPORTANT: market_cap can be None — skip if so
      6. Populate crossovers list with {date, price, angle, volatility, volume_ratio}
         and {date, death_cross: True} for death crosses

    Returns stock_db dict.
    """
    stock_db = {}
    # Pre-fetch metadata for all tickers to avoid many queries
    metadata_query = text("SELECT ticker, sector, market_cap FROM stock_metadata WHERE ticker = ANY(:tickers)")
    try:
        meta_df = pd.read_sql(metadata_query, engine, params={"tickers": [t.upper() for t in tickers]})
    except Exception:
        meta_df = pd.DataFrame(columns=["ticker", "sector", "market_cap"])
    meta_dict = {}
    for _, row in meta_df.iterrows():
        t = row["ticker"].upper()
        sector = row["sector"] if pd.notna(row["sector"]) else None
        market_cap = row["market_cap"] if pd.notna(row["market_cap"]) else None
        meta_dict[t] = {"sector": sector, "market_cap": market_cap}

    for ticker in tickers:
        try:
            table = get_safe_table_name(ticker)
        except ValueError:
            continue

        # Fetch OHLCV
        query = text(
            f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" '
            f'FROM "{table}" WHERE "Date" >= :start AND "Date" <= :end ORDER BY "Date"'
        )
        try:
            df = pd.read_sql(query, engine, params={"start": start, "end": end})
        except Exception:
            continue
        if df.empty:
            continue

        # Ensure at least 200 trading days
        if len(df) < 200:
            continue

        close = df["Close"].values.astype(float)
        high = df["High"].values.astype(float)
        low = df["Low"].values.astype(float)
        volume = df["Volume"].values.astype(float)
        dates = df["Date"].values.astype("datetime64[ns]")

        # Compute EMAs
        ema20 = pd.Series(close).ewm(span=20, adjust=False).mean().values
        ema200 = pd.Series(close).ewm(span=200, adjust=False).mean().values

        # Compute ATR (20-day)
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]  # no previous for first bar
        tr = np.maximum(high - low,
                        np.maximum(np.abs(high - prev_close),
                                   np.abs(low - prev_close)))
        atr = pd.Series(tr).rolling(window=20).mean().values

        # Compute average volume over last 60 days
        avg_volume_60 = pd.Series(volume).rolling(window=60).mean().values

        # Get metadata
        meta = meta_dict.get(ticker.upper(), {"sector": None, "market_cap": None})
        sector = meta["sector"]
        market_cap = meta["market_cap"]
        if market_cap is None or market_cap <= 0:
            continue

        # Detect crossovers
        crossovers = []
        for i in range(200, len(close)):
            # Golden cross
            if ema20[i] > ema200[i] and ema20[i-1] <= ema200[i-1]:
                # Apply price filter: close >= $5
                if close[i] < 5.0:
                    continue
                # Apply volume filter: avg volume over last 60 days > 100,000
                if avg_volume_60[i] <= 100_000:
                    continue
                # Apply ATR filter: ATR/close > 10% -> skip
                if atr[i] / close[i] > 0.10:
                    continue
                angle = (ema20[i] - ema200[i]) / ema200[i] * 100.0
                crossovers.append({
                    "date": pd.Timestamp(dates[i]).strftime("%Y-%m-%d"),
                    "price": float(close[i]),
                    "angle": float(angle),
                    "volatility": float(atr[i] / close[i]),
                    "volume_ratio": float(volume[i] / avg_volume_60[i]) if avg_volume_60[i] > 0 else 0.0,
                    "market_cap": float(market_cap),
                    "sector": sector,
                })
            # Death cross
            if ema20[i] < ema200[i] and ema20[i-1] >= ema200[i-1]:
                crossovers.append({
                    "date": pd.Timestamp(dates[i]).strftime("%Y-%m-%d"),
                    "price": float(close[i]),
                    "death_cross": True,
                })

        if not crossovers:
            continue

        stock_db[ticker] = {
            "close": close,
            "dates": dates,
            "ema20": ema20,
            "ema200": ema200,
            "atr": atr,
            "avg_volume_60": avg_volume_60,
            "crossovers": crossovers,
            "market_cap": float(market_cap),
            "sector": sector,
        }

    return stock_db


def entry_score(candidate: dict, market_cap_stats: dict) -> float:
    """Score a candidate in [0, 1]. Higher = better.

    candidate has: ticker, angle, market_cap, price, sector, volume_ratio
    market_cap_stats has: cap_min, cap_max, cap_range

    Use ANGLE_WEIGHT and CAP_WEIGHT for the weighted score.
    Normalize angle and market_cap to [0, 1] before combining.
    """
    angle = candidate.get("angle", 0.0)
    market_cap = candidate.get("market_cap", 0.0)

    # Normalize angle: cap at 20% spread, then divide by 20
    norm_angle = min(angle, 20.0) / 20.0

    # Normalize market cap using log10 and provided stats
    cap_min = market_cap_stats.get("cap_min", 1e6)
    cap_max = market_cap_stats.get("cap_max", 1e12)
    cap_range = market_cap_stats.get("cap_range", cap_max - cap_min)
    log_cap = np.log10(max(market_cap, 1e6))
    log_min = np.log10(max(cap_min, 1e6))
    log_max = np.log10(max(cap_max, 1e6))
    if log_max > log_min:
        norm_cap = (log_cap - log_min) / (log_max - log_min)
    else:
        norm_cap = 0.5

    # Weighted score
    score = ANGLE_WEIGHT * norm_angle + CAP_WEIGHT * norm_cap
    return float(np.clip(score, 0.0, 1.0))


def holding_score(ticker: str, date_str: str, holding: dict, market_cap_stats: dict) -> float:
    """Re-score an existing holding in [0, 1]. 0 = weak, rotate out.

    holding has: entry_date, entry_price, peak_price, shares, score, angle,
                 market_cap, sector, _stock_data
    holding._stock_data has the precomputed arrays: close, dates, ema20, ema200

    Use np.searchsorted(dates, np.datetime64(date_str)) to find the current index.
    """
    stock_data = holding.get("_stock_data", {})
    dates = stock_data.get("dates")
    ema20 = stock_data.get("ema20")
    ema200 = stock_data.get("ema200")
    if dates is None or ema20 is None or ema200 is None:
        return 1.0  # fallback

    idx = np.searchsorted(dates, np.datetime64(date_str))
    if idx >= len(dates):
        idx = len(dates) - 1
    if idx < 200:
        return 1.0

    # Current spread
    current_angle = (ema20[idx] - ema200[idx]) / ema200[idx] * 100.0
    norm_angle = min(current_angle, 20.0) / 20.0

    # Market cap normalization (same as entry)
    market_cap = holding.get("market_cap", 1e9)
    cap_min = market_cap_stats.get("cap_min", 1e6)
    cap_max = market_cap_stats.get("cap_max", 1e12)
    log_cap = np.log10(max(market_cap, 1e6))
    log_min = np.log10(max(cap_min, 1e6))
    log_max = np.log10(max(cap_max, 1e6))
    if log_max > log_min:
        norm_cap = (log_cap - log_min) / (log_max - log_min)
    else:
        norm_cap = 0.5

    score = ANGLE_WEIGHT * norm_angle + CAP_WEIGHT * norm_cap
    return float(np.clip(score, 0.0, 1.0))


def exit_check(ticker: str, date_str: str, holding: dict, stock_db: dict) -> Optional[str]:
    """Return exit reason string or None to hold.

    Priority order: Death Cross, Trailing Stop, Take Profit, Time Stop.
    Check holding._stock_data for indicator arrays.
    Use np.searchsorted(dates, np.datetime64(date_str)) for index lookup.
    """
    stock_data = holding.get("_stock_data", {})
    dates = stock_data.get("dates")
    ema20 = stock_data.get("ema20")
    ema200 = stock_data.get("ema200")
    close = stock_data.get("close")
    if dates is None or ema20 is None or ema200 is None or close is None:
        return None

    idx = np.searchsorted(dates, np.datetime64(date_str))
    if idx >= len(dates):
        idx = len(dates) - 1
    if idx < 200:
        return None

    # 1. Death cross
    if ema20[idx] < ema200[idx] and ema20[idx-1] >= ema200[idx-1]:
        return "Death Cross"

    # 2. Trailing stop
    entry_price = holding.get("entry_price", close[idx])
    peak_price = holding.get("peak_price", entry_price)
    # Update peak if current close is higher
    current_close = close[idx]
    if current_close > peak_price:
        peak_price = current_close
        holding["peak_price"] = peak_price
    stop_level = peak_price * (1.0 - TRAILING_STOP)
    if current_close < stop_level:
        return "Trailing Stop"

    # 3. Take profit (disabled by default, but check anyway)
    if TAKE_PROFIT < 999.0:
        take_profit_level = entry_price * (1.0 + TAKE_PROFIT)
        if current_close >= take_profit_level:
            return "Take Profit"

    # 4. Time stop
    entry_date = holding.get("entry_date", date_str)
    days_held = (pd.Timestamp(date_str) - pd.Timestamp(entry_date)).days
    if days_held >= TIME_STOP_DAYS:
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
