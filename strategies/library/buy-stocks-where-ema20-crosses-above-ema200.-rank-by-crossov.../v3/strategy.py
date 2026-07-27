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
MIN_HOLD_DAYS = 1
TRAILING_STOP = 0.20
TAKE_PROFIT = 999.0       # disabled by default
TIME_STOP_DAYS = 9999     # disabled by default
MAX_SECTOR_COUNT = 2
BULL_EXPOSURE = 1.0
BEAR_EXPOSURE = 0.50
ANGLE_WEIGHT = 0.50
CAP_WEIGHT = 0.50
STRATEGY_NAME = "Golden Cross with Angle & Cap"

# Global cache for SPY data (populated in precompute)
_spy_data: Dict[str, Any] = {}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  FILL IN THE 4 FUNCTIONS BELOW                                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def precompute(tickers: List[str], start: str, end: str) -> Dict[str, Any]:
    """Build stock_db: ticker → {close, dates, ema20, ema200, crossovers, market_cap, sector, atr}.

    For each ticker:
      1. Get safe table name: get_safe_table_name(ticker)
      2. Query OHLCV: SELECT "Date", "Open", "High", "Low", "Close", "Volume"
         FROM "{table}" WHERE "Date" >= :start AND "Date" <= :end ORDER BY "Date"
         Use pd.read_sql(text(query), engine, params={...})
      3. Compute indicators (EMA20, EMA200, ATR, etc.)
      4. Detect golden crosses (EMA20 crosses above EMA200) and death crosses
      5. Get metadata: SELECT sector, market_cap FROM stock_metadata WHERE ticker = :ticker
         Use ticker.upper() for the parameter
         IMPORTANT: market_cap can be None — skip if so
      6. Populate crossovers list with {date, price, angle, volatility, volume_ratio}
         and {date, death_cross: True} for death crosses

    Returns stock_db dict.
    """
    global _spy_data
    stock_db: Dict[str, Any] = {}

    # Pre-fetch SPY data for bull market filter
    try:
        spy_table = get_safe_table_name("SPY")
        spy_query = text(
            f'SELECT "Date", "Close" '
            f'FROM "{spy_table}" WHERE "Date" >= :start AND "Date" <= :end ORDER BY "Date"'
        )
        spy_df = pd.read_sql(spy_query, engine, params={"start": start, "end": end})
        if not spy_df.empty:
            spy_dates = spy_df["Date"].values.astype("datetime64[ns]")
            spy_close = spy_df["Close"].values.astype(float)
            spy_sma200 = pd.Series(spy_close).rolling(window=200).mean().values
            _spy_data = {
                "dates": spy_dates,
                "close": spy_close,
                "sma200": spy_sma200,
            }
    except Exception:
        _spy_data = {}  # If SPY fails, skip bull filter

    for ticker in tickers:
        try:
            table = get_safe_table_name(ticker)
        except ValueError:
            continue

        # Query OHLCV
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

        # Convert columns
        dates = df["Date"].values.astype("datetime64[ns]")
        close = df["Close"].values.astype(float)
        high = df["High"].values.astype(float)
        low = df["Low"].values.astype(float)
        volume = df["Volume"].values.astype(float)

        # Compute EMAs
        ema20 = pd.Series(close).ewm(span=20, adjust=False).mean().values
        ema200 = pd.Series(close).ewm(span=200, adjust=False).mean().values

        # Compute ATR (20-day EMA of True Range)
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]  # first day no previous
        tr = np.maximum(high - low,
                        np.maximum(np.abs(high - prev_close),
                                   np.abs(low - prev_close)))
        atr = pd.Series(tr).ewm(span=20, adjust=False).mean().values

        # Compute volume ratio (20-day average)
        vol_avg = pd.Series(volume).rolling(window=20).mean().values
        vol_ratio = np.where(vol_avg > 0, volume / vol_avg, 0.0)

        # Detect golden crosses (EMA20 crosses above EMA200)
        golden_cross_idx = np.where(
            (ema20[1:] > ema200[1:]) & (ema20[:-1] <= ema200[:-1])
        )[0] + 1  # +1 because we compare shifted

        # Detect death crosses (EMA20 crosses below EMA200)
        death_cross_idx = np.where(
            (ema20[1:] < ema200[1:]) & (ema20[:-1] >= ema200[:-1])
        )[0] + 1

        # Get metadata
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
        market_cap = float(market_cap)

        # Build crossovers list
        crossovers = []
        for idx in golden_cross_idx:
            if idx < 5:  # need at least 5 days for angle calculation
                continue
            # Compute angle: slope of EMA20 over last 5 days
            slope = (ema20[idx] - ema20[idx - 4]) / 5.0
            angle_rad = np.arctan(slope)
            angle_deg = np.degrees(angle_rad)
            angle_score = max(0.0, min(angle_deg / 90.0, 1.0))

            # ATR filter: skip if ATR < 0.5% of price
            if atr[idx] / close[idx] < 0.005:
                continue

            crossover_entry = {
                "date": pd.Timestamp(dates[idx]).strftime("%Y-%m-%d"),
                "price": float(close[idx]),
                "angle": float(angle_score),
                "market_cap": market_cap,
                "sector": sector,
                "volume_ratio": float(vol_ratio[idx]),
                "atr": float(atr[idx]),
            }
            crossovers.append(crossover_entry)

        # Add death crosses (for exit detection)
        for idx in death_cross_idx:
            crossovers.append({
                "date": pd.Timestamp(dates[idx]).strftime("%Y-%m-%d"),
                "price": float(close[idx]),
                "death_cross": True,
            })

        stock_db[ticker] = {
            "close": close,
            "dates": dates,
            "ema20": ema20,
            "ema200": ema200,
            "crossovers": crossovers,
            "market_cap": market_cap,
            "sector": sector,
            "atr": atr,
        }

    return stock_db


def entry_score(candidate: dict, market_cap_stats: dict) -> float:
    """Score a candidate in [0, 1]. Higher = better.

    candidate has: ticker, angle, market_cap, price, sector, volume_ratio, date, atr
    market_cap_stats has: cap_min, cap_max, cap_range

    Use ANGLE_WEIGHT and CAP_WEIGHT for the weighted score.
    Normalize angle and market_cap to [0, 1] before combining.
    """
    # Guard against missing 'date' key (should not happen, but prevents KeyError)
    if "date" not in candidate:
        return 0.0

    # Bull market filter: check SPY close > 200-day SMA
    if _spy_data:
        candidate_date = np.datetime64(candidate["date"])
        spy_idx = np.searchsorted(_spy_data["dates"], candidate_date)
        if spy_idx >= len(_spy_data["dates"]):
            spy_idx = len(_spy_data["dates"]) - 1
        if spy_idx < 0:
            return 0.0
        spy_close = _spy_data["close"][spy_idx]
        spy_sma200 = _spy_data["sma200"][spy_idx]
        if np.isnan(spy_sma200) or spy_close <= spy_sma200:
            return 0.0

    # Volatility filter: ATR must be at least 0.5% of price
    atr = candidate.get("atr", 0.0)
    price = candidate["price"]
    if price > 0 and atr / price < 0.005:
        return 0.0

    # Normalize angle (already in [0,1])
    angle_score = candidate["angle"]

    # Normalize market cap
    cap_min = market_cap_stats.get("cap_min", 0)
    cap_max = market_cap_stats.get("cap_max", 1)
    cap_range = market_cap_stats.get("cap_range", 1)
    if cap_range > 0:
        cap_score = (candidate["market_cap"] - cap_min) / cap_range
    else:
        cap_score = 0.5
    cap_score = max(0.0, min(1.0, cap_score))

    # Weighted score
    score = ANGLE_WEIGHT * angle_score + CAP_WEIGHT * cap_score
    return float(score)


def holding_score(ticker: str, date_str: str, holding: dict, market_cap_stats: dict) -> float:
    """Re-score an existing holding in [0, 1]. 0 = weak, rotate out.

    holding has: entry_date, entry_price, peak_price, shares, score, angle,
                 market_cap, sector, _stock_data
    holding._stock_data has the precomputed arrays: close, dates, ema20, ema200

    Use np.searchsorted(dates, np.datetime64(date_str)) to find the current index.
    """
    # No daily re-score: hold until exit condition is met
    return 1.0


def exit_check(ticker: str, date_str: str, holding: dict, stock_db: dict) -> Optional[str]:
    """Return exit reason string or None to hold.

    Priority order: Death Cross, Trailing Stop, Take Profit, Time Stop.
    Check holding._stock_data for indicator arrays.
    Use np.searchsorted(dates, np.datetime64(date_str)) for index lookup.
    """
    stock_data = holding.get("_stock_data")
    if stock_data is None:
        return None

    dates = stock_data["dates"]
    ema20 = stock_data["ema20"]
    ema200 = stock_data["ema200"]
    close = stock_data["close"]

    current_date = np.datetime64(date_str)
    idx = np.searchsorted(dates, current_date)
    if idx >= len(dates):
        idx = len(dates) - 1
    if idx < 1:
        return None

    # 1. Death Cross: EMA20 crosses below EMA200
    if ema20[idx] < ema200[idx] and ema20[idx - 1] >= ema200[idx - 1]:
        return "Death Cross"

    # 2. Trailing Stop: current close <= (1 - trailing_stop) * peak_price
    peak_price = holding.get("peak_price", holding["entry_price"])
    current_close = close[idx]
    if current_close <= (1.0 - TRAILING_STOP) * peak_price:
        return "Trailing Stop"

    # 3. Take Profit (disabled)
    # 4. Time Stop (disabled)
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
