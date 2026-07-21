"""Golden Cross Rotation — thin config layer using StrategyEngine.

Scans 1500 stocks daily for EMA20/200 golden cross.
Ranks by: 60% crossover angle + 40% market cap.
Holds top 5, rotates when better candidates appear.
Exits: death cross, death cross warning, take profit, trailing stop, time stop, or rotated out.

This file contains ONLY the 4 strategy-specific filter functions + a
StrategyConfig instantiation. The mechanical engine (daily loop, portfolio
state, position sizing, Markov regime, reporting) is in strategies/engine.py.

Usage:
  cd backend && ./venv/bin/python ../strategies/golden_cross.py
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")


# ── Strategy-specific parameters ──────────────────────────────────────────
AS_OF = "2020-01-01"
END = "2026-07-08"
CAPITAL = 100_000.0
ANGLE_WEIGHT = 0.60
CAP_WEIGHT = 0.40

# Exit thresholds (used by exit_check)
TAKE_PROFIT_PCT = 0.30
TRAILING_STOP_PCT = 0.20
TIME_STOP_DAYS = 60
DEATH_CROSS_WARNING_PCT = 0.001  # within 0.1% of death cross


def compute_ema_crossover_angle(close, ema20, ema200, cross_idx, lookback=3):
    """Compute angle between EMA20 and EMA200 at crossover."""
    if cross_idx < lookback:
        return 0.0
    end = min(cross_idx + lookback, len(close) - 1)
    start = max(0, cross_idx - lookback)
    if end == start:
        return 0.0
    spread_before = (ema20.iloc[start] - ema200.iloc[start])
    spread_after = (ema20.iloc[end] - ema200.iloc[end])
    angle = (spread_after - spread_before) / (end - start)
    return float(angle) if pd.notna(angle) else 0.0


def precompute(tickers, start, end):
    """Pre-compute EMA20, EMA200, crossover dates, angles, sectors for all stocks."""
    from app.db.database import engine
    from app.utils.security import get_safe_table_name
    from sqlalchemy import text

    stock_data = {}

    for ticker in tickers:
        try:
            safe = get_safe_table_name(ticker)
        except ValueError:
            continue

        try:
            with engine.connect() as conn:
                df = pd.read_sql(
                    f'SELECT "Date", "Close", "Volume" FROM "{safe}" '
                    f'WHERE "Date" >= \'{start}\' AND "Date" <= \'{end}\' ORDER BY "Date"',
                    conn,
                )
        except Exception:
            continue

        if df.empty or len(df) < 250:
            continue

        close = df["Close"]
        volume = df["Volume"].astype(float)
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema200 = close.rolling(window=200).mean()
        volume_ma50 = volume.rolling(50).mean()
        returns = close.pct_change()
        vol_14 = returns.rolling(14).std()

        crossovers = []
        for i in range(1, len(df)):
            if (pd.notna(ema20.iloc[i]) and pd.notna(ema200.iloc[i]) and
                pd.notna(ema20.iloc[i-1]) and pd.notna(ema200.iloc[i-1])):
                if ema20.iloc[i-1] <= ema200.iloc[i-1] and ema20.iloc[i] > ema200.iloc[i]:
                    angle = compute_ema_crossover_angle(close, ema20, ema200, i)
                    volatility = float(vol_14.iloc[i]) if pd.notna(vol_14.iloc[i]) else 0.0
                    vol_ratio = (float(volume.iloc[i] / volume_ma50.iloc[i])
                                 if pd.notna(volume_ma50.iloc[i]) and volume_ma50.iloc[i] > 0 else 0.0)
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10],
                        "price": float(close.iloc[i]),
                        "angle": angle,
                        "volatility": volatility,
                        "volume_ratio": vol_ratio,
                    })
                elif ema20.iloc[i-1] >= ema200.iloc[i-1] and ema20.iloc[i] < ema200.iloc[i]:
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10],
                        "price": float(close.iloc[i]),
                        "angle": 0.0,
                        "death_cross": True,
                    })

        if crossovers:
            mc = 0.0
            sector = "Unknown"
            try:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT market_cap, sector FROM stock_metadata WHERE ticker = :t"),
                        {"t": ticker.upper()}
                    ).fetchone()
                if row:
                    if row[0] is not None:
                        mc = float(row[0])
                    if row[1] is not None:
                        sector = row[1]
            except Exception:
                pass

            stock_data[ticker.upper()] = {
                "close": close.values,
                "dates": df["Date"].values,
                "ema20": ema20.values,
                "ema200": ema200.values,
                "crossovers": crossovers,
                "market_cap": mc,
                "sector": sector,
            }

    return stock_data


def entry_score(candidate, market_cap_stats):
    """60% angle (sigmoid) + 40% market cap (normalized)."""
    angle = candidate.get("angle", 0)
    market_cap = candidate.get("market_cap", 0)
    angle_norm = 1 / (1 + np.exp(-angle * 100))
    cap_norm = ((market_cap - market_cap_stats["cap_min"]) / market_cap_stats["cap_range"]
                if market_cap_stats["cap_range"] > 0 else 0.5)
    return ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm


def holding_score(ticker, date_str, holding, market_cap_stats):
    """Re-score an existing holding using current EMA20/EMA200 spread + market cap.

    The engine passes the holding dict (with entry_date, entry_price, etc.)
    and the full market_cap_stats. We need access to the EMA values to compute
    the spread. The strategy does this by reaching into stock_db via the
    engine-injected '_stock_data' field (set during entry).
    """
    data = holding.get("_stock_data")
    if data is None:
        return 0.0
    dates = data["dates"]
    arr20 = data["ema20"]
    arr200 = data["ema200"]
    target = pd.Timestamp(date_str)
    ema20_val = 0.0
    ema200_val = 0.0
    for i in range(len(dates) - 1, -1, -1):
        if pd.Timestamp(dates[i]) <= target:
            ema20_val = float(arr20[i])
            ema200_val = float(arr200[i])
            break
    if ema20_val <= 0 or ema200_val <= 0:
        return 0.0
    spread_pct = (ema20_val - ema200_val) / ema200_val
    angle_norm = 1 / (1 + np.exp(-spread_pct * 100))
    cap_norm = ((holding.get("market_cap", 0) - market_cap_stats["cap_min"]) / market_cap_stats["cap_range"]
                if market_cap_stats["cap_range"] > 0 else 0.5)
    return ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm


def exit_check(ticker, date_str, holding, stock_db):
    """Return exit reason string or None.

    Checks in order: death cross, take profit, trailing stop, death-cross warning, time stop.
    """
    data = stock_db.get(ticker)
    if data is None:
        return None

    # Death cross check
    dc_dates = [co["date"] for co in data.get("crossovers", []) if co.get("death_cross")]
    has_dc = any(holding["entry_date"] < d <= date_str for d in dc_dates)
    if has_dc:
        return "Death Cross"

    # Current price + indicators (most recent on or before date_str)
    dates = data["dates"]
    close_arr = data["close"]
    ema20_arr = data["ema20"]
    ema200_arr = data["ema200"]
    target = pd.Timestamp(date_str)
    cur_price = 0.0
    ema20_val = 0.0
    ema200_val = 0.0
    for i in range(len(dates) - 1, -1, -1):
        if pd.Timestamp(dates[i]) <= target:
            cur_price = float(close_arr[i])
            ema20_val = float(ema20_arr[i])
            ema200_val = float(ema200_arr[i])
            break

    if cur_price <= 0:
        return None

    ret = (cur_price - holding["entry_price"]) / holding["entry_price"]

    if ret >= TAKE_PROFIT_PCT:
        return "Take Profit"

    dd = (holding["peak_price"] - cur_price) / holding["peak_price"]
    if dd >= TRAILING_STOP_PCT:
        return f"Trailing Stop ({dd:.1%})"

    if ema20_val > 0 and ema200_val > 0 and ret < 0:
        spread_pct = (ema20_val - ema200_val) / ema200_val
        if spread_pct < DEATH_CROSS_WARNING_PCT:
            return "Death Cross Warning"

    hold_days = (pd.Timestamp(date_str) - pd.Timestamp(holding["entry_date"])).days
    if hold_days >= TIME_STOP_DAYS:
        return f"Time Stop ({hold_days}d)"

    return None


# ── Config builder ─────────────────────────────────────────────────────────
def build_config(as_of=None, end=None, capital=None):
    """Build a StrategyConfig for the golden cross strategy.

    Defaults to module-level AS_OF / END / CAPITAL constants.
    """
    import importlib.util
    import sys
    _engine_path = os.path.join(os.path.dirname(__file__), "engine.py")
    _spec = importlib.util.spec_from_file_location("strategies_engine_for_gc", _engine_path)
    _engine = importlib.util.module_from_spec(_spec)
    sys.modules["strategies_engine_for_gc"] = _engine
    _spec.loader.exec_module(_engine)

    return _engine.StrategyConfig(
        as_of=as_of or AS_OF,
        end=end or END,
        capital=capital or CAPITAL,
        max_holdings=5,
        min_hold_days=7,
        trailing_stop=TRAILING_STOP_PCT,
        take_profit=TAKE_PROFIT_PCT,
        time_stop_days=TIME_STOP_DAYS,
        max_volatility=0.05,
        max_sector_count=2,
        bull_exposure=1.0,
        bear_exposure=0.50,
        angle_weight=ANGLE_WEIGHT,
        cap_weight=CAP_WEIGHT,
        precompute_fn=precompute,
        entry_score_fn=entry_score,
        holding_score_fn=holding_score,
        exit_check_fn=exit_check,
        name="Golden Cross Rotation",
        score_squared_sizing=True,
    )


def main():
    import importlib.util
    import sys
    _engine_path = os.path.join(os.path.dirname(__file__), "engine.py")
    _spec = importlib.util.spec_from_file_location("strategies_engine_for_gc", _engine_path)
    _engine = importlib.util.module_from_spec(_spec)
    sys.modules["strategies_engine_for_gc"] = _engine
    _spec.loader.exec_module(_engine)

    cfg = build_config()
    print("=" * 80)
    print(f"  {cfg.name} STRATEGY (via StrategyEngine)")
    print("=" * 80)
    print(f"  Period:    {cfg.as_of} → {cfg.end}")
    print(f"  Capital:   ${cfg.capital:,.2f}")
    print(f"  Holdings:  Top {cfg.max_holdings}")
    print("=" * 80)

    result = _engine.StrategyEngine(cfg).run()
    summary = result["summary"]

    print(f"\n{'='*80}")
    print("  PORTFOLIO SUMMARY")
    print("=" * 80)
    print(f"  Initial:   ${summary['initial_capital']:>10,.2f}")
    print(f"  Final:     ${summary['final_portfolio']:>10,.2f}")
    print(f"  Return:    {summary['total_return_pct']:>+8.2f}%")
    print(f"  CAGR:      {summary['cagr_pct']:>+8.2f}%")
    print(f"  SPY:       {summary['spy_return_pct']:>+8.2f}%")
    print(f"  Alpha:     {summary['alpha_pct']:>+8.2f}%")
    print(f"\n  Trades:    {summary['total_trades']}")
    print(f"  Win Rate:  {summary['win_rate']:.1f}%")
    print(f"  PF:        {summary['profit_factor']:.2f}")
    print(f"\n  Exits:     {summary['exit_reasons']}")
    print("=" * 80)

    # Write summary JSON
    import json
    report_dir = os.path.join(os.path.dirname(__file__), "..", "docs", "reports")
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(report_dir, "trades.json"), "w") as f:
        json.dump(result["trades"], f, indent=2)
    with open(os.path.join(report_dir, "daily_equity.json"), "w") as f:
        json.dump(result["daily_equity"], f, indent=2)


if __name__ == "__main__":
    main()
