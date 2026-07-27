import os
import sys
import math
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

# ===== Environment & Constants =====
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "tradecraft")

CAPITAL = 100_000.0
AS_OF = "2020-01-01"
END = "2026-07-08"

# Strategy parameters
ANGLE_WEIGHT = 0.60
CAP_WEIGHT = 0.40
MAX_HOLDINGS = 5
MIN_HOLD_DAYS = 7
TRAILING_STOP = 0.20
TAKE_PROFIT = 0.30
TIME_STOP_DAYS = 60
MAX_VOLATILITY = 0.05
MAX_SECTOR_COUNT = 2
BULL_EXPOSURE = 1.0
BEAR_EXPOSURE = 0.50

# ===== Database Engine =====
db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(db_url)

# ===== Helper Functions =====
def get_safe_table_name(ticker: str) -> str:
    """Return ticker as-is (tables are named after ticker)."""
    return ticker.lower()

def compute_ema(series: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    alpha = 2 / (period + 1)
    ema = np.full_like(series, np.nan)
    ema[0] = series[0]
    for i in range(1, len(series)):
        ema[i] = alpha * series[i] + (1 - alpha) * ema[i-1]
    return ema

def compute_slope(ema: np.ndarray, lookback: int = 5) -> np.ndarray:
    """Slope of EMA over last `lookback` bars (per bar)."""
    slope = np.full_like(ema, np.nan)
    if len(ema) > lookback:
        slope[lookback:] = (ema[lookback:] - ema[:-lookback]) / lookback
    return slope

def compute_angle(ema20: np.ndarray, ema200: np.ndarray, lookback: int = 5) -> np.ndarray:
    """Angle between EMA20 and EMA200 slopes in degrees."""
    slope20 = compute_slope(ema20, lookback)
    slope200 = compute_slope(ema200, lookback)
    diff = np.abs(slope20 - slope200)
    angle = np.degrees(np.arctan(diff))
    return angle

# ===== Precompute =====
def precompute(tickers: List[str], start: str, end: str) -> Dict[str, Any]:
    stock_db = {}
    for ticker in tickers:
        table_name = get_safe_table_name(ticker)
        query = text(f"""
            SELECT "Date", "Open", "High", "Low", "Close", "Volume"
            FROM "{table_name}"
            WHERE "Date" >= :start AND "Date" <= :end
            ORDER BY "Date"
        """)
        try:
            with engine.connect() as conn:
                df = pd.read_sql(query, conn, params={"start": start, "end": end})
        except Exception as e:
            print(f"Error reading {ticker}: {e}")
            continue
        if df.empty:
            continue

        df["Date"] = pd.to_datetime(df["Date"])
        close = df["Close"].values.astype(float)
        volume = df["Volume"].values.astype(float)
        dates = df["Date"].values

        # Compute EMAs
        ema20 = compute_ema(close, 20)
        ema200 = compute_ema(close, 200)

        # Detect crossovers
        crossovers = []
        for i in range(1, len(close)):
            if np.isnan(ema20[i]) or np.isnan(ema200[i]) or np.isnan(ema20[i-1]) or np.isnan(ema200[i-1]):
                continue
            # Golden cross: EMA20 crosses above EMA200
            if ema20[i-1] <= ema200[i-1] and ema20[i] > ema200[i]:
                angle = compute_angle(ema20, ema200, 5)[i]
                # Volatility: 14-day std of returns
                if i >= 14:
                    returns = np.diff(close[i-14:i+1]) / close[i-14:i]
                    volatility = np.std(returns)
                else:
                    volatility = np.nan
                # Volume ratio: current volume / 20-day average volume
                if i >= 20:
                    avg_vol = np.mean(volume[i-20:i])
                    vol_ratio = volume[i] / avg_vol if avg_vol > 0 else 1.0
                else:
                    vol_ratio = 1.0
                crossovers.append({
                    "date": pd.Timestamp(dates[i]).strftime("%Y-%m-%d"),
                    "price": close[i],
                    "angle": angle,
                    "volatility": volatility,
                    "volume_ratio": vol_ratio
                })
            # Death cross: EMA20 crosses below EMA200
            if ema20[i-1] >= ema200[i-1] and ema20[i] < ema200[i]:
                crossovers.append({
                    "date": pd.Timestamp(dates[i]).strftime("%Y-%m-%d"),
                    "price": close[i],
                    "death_cross": True
                })

        # Get metadata
        meta_query = text("SELECT sector, market_cap FROM stock_metadata WHERE ticker = :ticker")
        try:
            with engine.connect() as conn:
                meta = conn.execute(meta_query, {"ticker": ticker}).fetchone()
        except Exception as e:
            print(f"Error reading metadata for {ticker}: {e}")
            meta = None
        sector = meta[0] if meta else "Unknown"
        market_cap = float(meta[1]) if meta and meta[1] else 0.0

        stock_db[ticker] = {
            "close": close,
            "dates": dates,
            "ema20": ema20,
            "ema200": ema200,
            "crossovers": crossovers,
            "market_cap": market_cap,
            "sector": sector,
            "volume": volume
        }
    return stock_db

# ===== Entry Score =====
def entry_score(candidate: dict, market_cap_stats: dict) -> float:
    """
    Score a candidate using normalized angle and market cap.
    Normalization: angle is normalized by a fixed max of 90 degrees (since arctan max ~90).
    Market cap is normalized using provided min/max.
    """
    angle = candidate.get("angle", 0.0)
    market_cap = candidate.get("market_cap", 0.0)

    # Normalize angle to [0,1] using fixed max 90 degrees
    norm_angle = min(angle / 90.0, 1.0)

    # Normalize market cap using provided stats
    cap_min = market_cap_stats.get("cap_min", 0.0)
    cap_max = market_cap_stats.get("cap_max", 1.0)
    cap_range = cap_max - cap_min
    if cap_range > 0:
        norm_cap = (market_cap - cap_min) / cap_range
    else:
        norm_cap = 0.5  # fallback

    # Clamp to [0,1]
    norm_cap = max(0.0, min(1.0, norm_cap))

    score = ANGLE_WEIGHT * norm_angle + CAP_WEIGHT * norm_cap
    return score

# ===== Holding Score =====
def holding_score(ticker: str, date_str: str, holding: dict, market_cap_stats: dict) -> float:
    """
    Re-score an existing holding using current angle and market cap.
    The holding dict contains '_stock_data' with precomputed arrays.
    """
    stock_data = holding.get("_stock_data")
    if stock_data is None:
        return 0.0

    close = stock_data.get("close")
    dates = stock_data.get("dates")
    ema20 = stock_data.get("ema20")
    ema200 = stock_data.get("ema200")
    if close is None or dates is None or ema20 is None or ema200 is None:
        return 0.0

    # Find index of current date
    current_date = np.datetime64(date_str)
    idx = np.searchsorted(dates, current_date, side="right") - 1
    if idx < 0 or idx >= len(close):
        return 0.0

    # Compute current angle (if enough data)
    if idx >= 5:
        angle = compute_angle(ema20, ema200, 5)[idx]
    else:
        angle = 0.0

    # Market cap from holding (or from stock_data)
    market_cap = holding.get("market_cap", stock_data.get("market_cap", 0.0))

    # Normalize
    norm_angle = min(angle / 90.0, 1.0)
    cap_min = market_cap_stats.get("cap_min", 0.0)
    cap_max = market_cap_stats.get("cap_max", 1.0)
    cap_range = cap_max - cap_min
    if cap_range > 0:
        norm_cap = (market_cap - cap_min) / cap_range
    else:
        norm_cap = 0.5
    norm_cap = max(0.0, min(1.0, norm_cap))

    score = ANGLE_WEIGHT * norm_angle + CAP_WEIGHT * norm_cap
    return score

# ===== Exit Check =====
def exit_check(ticker: str, date_str: str, holding: dict, stock_db: dict) -> Optional[str]:
    """
    Check exit conditions: death cross, take profit, trailing stop, time stop.
    Returns reason string or None.
    """
    stock_data = holding.get("_stock_data")
    if stock_data is None:
        return "No data"

    close = stock_data.get("close")
    dates = stock_data.get("dates")
    ema20 = stock_data.get("ema20")
    ema200 = stock_data.get("ema200")
    if close is None or dates is None or ema20 is None or ema200 is None:
        return "No data"

    current_date = np.datetime64(date_str)
    idx = np.searchsorted(dates, current_date, side="right") - 1
    if idx < 0 or idx >= len(close):
        return "Out of range"

    current_price = close[idx]
    entry_price = holding.get("entry_price", current_price)
    highest_price = holding.get("highest_price", current_price)
    days_held = holding.get("days_held", 0)

    # Update highest price
    if current_price > highest_price:
        highest_price = current_price
        holding["highest_price"] = highest_price

    # Death cross check
    if idx >= 1 and not np.isnan(ema20[idx]) and not np.isnan(ema200[idx]) and not np.isnan(ema20[idx-1]) and not np.isnan(ema200[idx-1]):
        if ema20[idx-1] >= ema200[idx-1] and ema20[idx] < ema200[idx]:
            return "Death Cross"

    # Take profit
    if current_price >= entry_price * (1 + TAKE_PROFIT):
        return "Take Profit"

    # Trailing stop
    if highest_price > 0 and current_price < highest_price * (1 - TRAILING_STOP):
        pct = (highest_price - current_price) / highest_price * 100
        return f"Trailing Stop ({pct:.1f}%)"

    # Time stop
    if days_held >= TIME_STOP_DAYS:
        return f"Time Stop ({TIME_STOP_DAYS}d)"

    return None

# ===== Load Engine and Create Config =====
import importlib.util
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
    max_volatility=MAX_VOLATILITY,
    max_sector_count=MAX_SECTOR_COUNT,
    bull_exposure=BULL_EXPOSURE,
    bear_exposure=BEAR_EXPOSURE,
    angle_weight=ANGLE_WEIGHT,
    cap_weight=CAP_WEIGHT,
    precompute_fn=precompute,
    entry_score_fn=entry_score,
    holding_score_fn=holding_score,
    exit_check_fn=exit_check,
    name="EMA20/200 Crossover with Angle & Cap",
    score_squared_sizing=True
)
