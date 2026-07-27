"""
Golden Cross Rotation — 8 Tweak Comparison
=============================================
Compares the baseline strategy against 8 variants to find the best performer.

Variants:
  1. BASELINE:  Equal-weight top 5, fixed 20% trailing stop, daily rebalance
  2. DYN_SIZE:  Position sizing by conviction score (30/25/20/15/10%)
  3. ATR_STOP:  ATR-based trailing stop (3× ATR14) instead of fixed 20%
  4. WEEKLY:    Rebalance weekly instead of daily
  5. SECTOR:    Max 2 stocks per sector
  6. VOLUME:    Volume confirmation (>1.5× 50d avg) on entry
  7. MIN_HOLD:  Minimum 10-day holding period before rotation
  8. DECAY:     Momentum score decay (re-score every 30 days)
  9. BEAR_SHORT: Short bottom 5 during bear regimes

Usage:
  cd backend && ./venv/bin/python ../strategies/golden_cross_comparison.py
"""

import os
import sys
import warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import OrderedDict
import time

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")

AS_OF = "2020-01-01"
END = "2026-07-08"
CAPITAL = 100_000.0
MAX_HOLDINGS = 5
ANGLE_WEIGHT = 0.60
CAP_WEIGHT = 0.40

SECTOR_TO_ETF = {
    "Technology": "XLK", "Energy": "XLE", "Financials": "XLF",
    "Financial Services": "XLF", "Health Care": "XLV", "Healthcare": "XLV",
    "Consumer Discretionary": "XLY", "Consumer Cyclical": "XLY",
    "Industrials": "XLI", "Communication Services": "XLC",
    "Consumer Staples": "XLP", "Consumer Defensive": "XLP",
    "Materials": "XLB", "Basic Materials": "XLB",
    "Real Estate": "XLRE", "Utilities": "XLU",
}


def get_sector(ticker: str) -> str:
    from app.db.database import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT sector FROM stock_metadata WHERE ticker = :t"),
                {"t": ticker.upper()}
            ).fetchone()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    return "Unknown"


def get_sector_etf(ticker: str) -> str:
    sector = get_sector(ticker)
    return SECTOR_TO_ETF.get(sector, "XLK")


def compute_ema_crossover_angle(close, ema20, ema200, cross_idx):
    lookback = 3
    if cross_idx < lookback or cross_idx + lookback >= len(close):
        return 0.0
    spread_before = (ema20.iloc[cross_idx - lookback] - ema200.iloc[cross_idx - lookback])
    spread_after = (ema20.iloc[cross_idx + lookback] - ema200.iloc[cross_idx + lookback])
    angle = (spread_after - spread_before) / (lookback * 2)
    return float(angle) if pd.notna(angle) else 0.0


def precompute_all():
    """Pre-compute all stock data, crossovers, and regimes. Returns everything needed."""
    from app.services.data_service import get_data
    from app.services.markov.regime_model import SectorRegimeManager
    from app.db.database import engine
    from sqlalchemy import text
    from app.utils.security import get_safe_table_name

    print("=" * 80)
    print("  PRE-COMPUTING DATA")
    print("=" * 80)

    # Get all tickers
    with engine.connect() as conn:
        res = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ))
        skip = {'stock_metadata', 'stock_financials_quarterly', 'stock_financials_yearly',
                'xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly'}
        all_tickers = [row[0] for row in res if row[0] not in skip]

    # Pre-compute stock data
    print(f"\n📥 Pre-computing {len(all_tickers)} stocks...")
    stock_db = {}
    for idx, ticker in enumerate(all_tickers):
        if (idx + 1) % 200 == 0:
            print(f"  {idx+1}/{len(all_tickers)}")
        try:
            safe = get_safe_table_name(ticker)
        except ValueError:
            continue
        try:
            with engine.connect() as conn:
                df = pd.read_sql(
                    f'SELECT "Date", "Close", "Volume" FROM "{safe}" WHERE "Date" >= \'2018-01-01\' AND "Date" <= \'{END}\' ORDER BY "Date"',
                    conn
                )
        except Exception:
            continue
        if df.empty or len(df) < 250:
            continue

        close = df["Close"]
        volume = df["Volume"]
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema200 = close.rolling(window=200).mean()
        vol_ma50 = volume.rolling(window=50).mean()
        atr14 = close.rolling(window=14).std()  # Simplified ATR

        crossovers = []
        for i in range(1, len(df)):
            if (pd.notna(ema20.iloc[i]) and pd.notna(ema200.iloc[i]) and
                pd.notna(ema20.iloc[i-1]) and pd.notna(ema200.iloc[i-1])):
                if ema20.iloc[i-1] <= ema200.iloc[i-1] and ema20.iloc[i] > ema200.iloc[i]:
                    angle = compute_ema_crossover_angle(close, ema20, ema200, i)
                    vol_ratio = float(volume.iloc[i] / vol_ma50.iloc[i]) if vol_ma50.iloc[i] > 0 else 0
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10],
                        "price": float(close.iloc[i]),
                        "angle": angle,
                        "vol_ratio": vol_ratio,
                        "atr": float(atr14.iloc[i]) if pd.notna(atr14.iloc[i]) else 0,
                    })
                elif ema20.iloc[i-1] >= ema200.iloc[i-1] and ema20.iloc[i] < ema200.iloc[i]:
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10],
                        "price": float(close.iloc[i]),
                        "angle": 0.0,
                        "vol_ratio": 0,
                        "atr": 0,
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
                    mc = float(row[0]) if row[0] else 0.0
                    sector = row[1] if row[1] else "Unknown"
            except Exception:
                pass

            stock_db[ticker.upper()] = {
                "close": close.values,
                "dates": df["Date"].values,
                "volume": volume.values,
                "ema20": ema20.values,
                "ema200": ema200.values,
                "crossovers": crossovers,
                "market_cap": mc,
                "sector": sector,
            }

    print(f"  Done. {len(stock_db)} stocks with crossover data.")

    # Build daily crossover calendar
    print("\n📅 Building daily crossover calendar...")
    daily_crossovers = {}
    daily_death_crosses = {}
    for ticker, data in stock_db.items():
        for co in data["crossovers"]:
            if co.get("death_cross"):
                d = co["date"]
                if d < AS_OF:
                    continue
                if ticker not in daily_death_crosses:
                    daily_death_crosses[ticker] = []
                daily_death_crosses[ticker].append(d)
            else:
                d = co["date"]
                if d < AS_OF:
                    continue
                if d not in daily_crossovers:
                    daily_crossovers[d] = []
                daily_crossovers[d].append({
                    "ticker": ticker,
                    "angle": co["angle"],
                    "market_cap": data["market_cap"],
                    "price": co["price"],
                    "vol_ratio": co["vol_ratio"],
                    "atr": co["atr"],
                    "sector": data["sector"],
                })

    print(f"  {len(daily_crossovers)} days with new golden crosses")
    print(f"  {sum(len(v) for v in daily_crossovers.values())} total events")

    # Pre-compute Markov regimes
    print("\n🧠 Training Markov regime models...")
    start_dt = datetime.strptime(AS_OF, "%Y-%m-%d")
    end_dt = datetime.strptime(END, "%Y-%m-%d")

    retrain_dates = []
    d = start_dt + timedelta(days=3 * 365)
    while d < end_dt:
        retrain_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=180)

    regime_cache = {}
    for i, rd in enumerate(retrain_dates):
        ts = (datetime.strptime(rd, "%Y-%m-%d") - timedelta(days=3 * 365 + 35)).strftime("%Y-%m-%d")
        print(f"  Model #{i+1}: {ts} → {rd}")
        rm = SectorRegimeManager(jump_penalty=10.0)
        rm.train_all(ts, rd)
        we = retrain_dates[i + 1] if i + 1 < len(retrain_dates) else END
        cur = datetime.strptime(rd, "%Y-%m-%d")
        we_dt = datetime.strptime(we, "%Y-%m-%d")
        day = cur
        while day <= we_dt:
            ds = day.strftime("%Y-%m-%d")
            regime_cache[ds] = rm.get_regime("SPY", ds)
            day += timedelta(days=1)

    # Normalization constants
    all_market_caps = [v["market_cap"] for v in stock_db.values() if v["market_cap"] > 0]
    cap_max = max(all_market_caps) if all_market_caps else 1
    cap_min = min(all_market_caps) if all_market_caps else 0
    cap_range = cap_max - cap_min if cap_max > cap_min else 1

    all_dates = sorted(daily_crossovers.keys())

    return {
        "stock_db": stock_db,
        "daily_crossovers": daily_crossovers,
        "daily_death_crosses": daily_death_crosses,
        "regime_cache": regime_cache,
        "all_dates": all_dates,
        "cap_max": cap_max,
        "cap_min": cap_min,
        "cap_range": cap_range,
    }


def run_simulation(data, variant_name, **kwargs):
    """Run a strategy variant and return results."""
    stock_db = data["stock_db"]
    daily_crossovers = data["daily_crossovers"]
    daily_death_crosses = data["daily_death_crosses"]
    regime_cache = data["regime_cache"]
    all_dates = data["all_dates"]
    cap_max = data["cap_max"]
    cap_min = data["cap_min"]
    cap_range = data["cap_range"]

    # Variant parameters
    use_dynamic_sizing = kwargs.get("use_dynamic_sizing", False)
    use_atr_stop = kwargs.get("use_atr_stop", False)
    use_weekly = kwargs.get("use_weekly", False)
    use_sector_div = kwargs.get("use_sector_div", False)
    use_volume_filter = kwargs.get("use_volume_filter", False)
    use_min_hold = kwargs.get("use_min_hold", False)
    use_decay = kwargs.get("use_decay", False)
    use_bear_short = kwargs.get("use_bear_short", False)

    trailing_stop_pct = kwargs.get("trailing_stop_pct", 0.20)
    atr_multiplier = kwargs.get("atr_multiplier", 3.0)
    vol_ratio_min = kwargs.get("vol_ratio_min", 1.5)
    min_hold_days = kwargs.get("min_hold_days", 10)
    max_per_sector = kwargs.get("max_per_sector", 2)
    decay_days = kwargs.get("decay_days", 30)

    def compute_score(angle, market_cap):
        angle_norm = 1 / (1 + np.exp(-angle * 100))
        cap_norm = (market_cap - cap_min) / cap_range if cap_range > 0 else 0.5
        return ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm

    def get_regime(date_str):
        r = regime_cache.get(date_str, {})
        return r.get("regime", "BULL")

    def get_price(ticker, date_str):
        d = stock_db.get(ticker)
        if d is None:
            return 0.0
        dates = d["dates"]
        close = d["close"]
        target = pd.Timestamp(date_str)
        for i in range(len(dates) - 1, -1, -1):
            if pd.Timestamp(dates[i]) <= target:
                return float(close[i])
        return 0.0

    def get_atr(ticker, date_str):
        """Get ATR for a ticker on a date (from crossover data)."""
        d = stock_db.get(ticker)
        if d is None:
            return 0.0
        # Find the most recent crossover before this date
        last_atr = 0.0
        for co in d["crossovers"]:
            if co.get("death_cross"):
                continue
            if co["date"] <= date_str:
                last_atr = co.get("atr", 0)
        return last_atr

    def has_death_cross(ticker, date_str):
        dc_dates = daily_death_crosses.get(ticker, [])
        return any(d <= date_str for d in dc_dates)

    def is_weekly_rebalance_day(date_str, prev_date_str):
        """Check if we should rebalance today (weekly = Monday)."""
        if not use_weekly:
            return True
        dt = pd.Timestamp(date_str)
        return dt.weekday() == 0  # Monday

    # Portfolio state
    holdings = OrderedDict()
    trades = []
    cash = CAPITAL
    portfolio_value = CAPITAL
    last_rebalance_date = ""

    for sim_idx, current_date in enumerate(all_dates):
        regime = get_regime(current_date)
        is_bear = (regime == "BEAR")

        # Weekly rebalance check
        should_rebalance = is_weekly_rebalance_day(current_date, last_rebalance_date)
        if should_rebalance:
            last_rebalance_date = current_date

        # ── 1. Check exits ────────────────────────────────────────────────
        to_remove = []
        for ticker in list(holdings.keys()):
            h = holdings[ticker]
            current_price = get_price(ticker, current_date)
            if current_price <= 0:
                continue

            h["peak_price"] = max(h["peak_price"], current_price)

            # Death cross exit
            if has_death_cross(ticker, current_date):
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "return_pct": round(ret * 100, 2),
                    "pnl_dollars": round(pnl, 2),
                    "exit_reason": "Death Cross",
                })
                cash += h["shares"] * current_price
                to_remove.append(ticker)
                continue

            # Trailing stop
            if use_atr_stop:
                atr = get_atr(ticker, current_date)
                stop_dist = atr_multiplier * atr if atr > 0 else trailing_stop_pct * h["entry_price"]
                stop_pct = stop_dist / h["peak_price"]
            else:
                stop_pct = trailing_stop_pct

            dd = (h["peak_price"] - current_price) / h["peak_price"]
            if dd >= stop_pct:
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "return_pct": round(ret * 100, 2),
                    "pnl_dollars": round(pnl, 2),
                    "exit_reason": f"Trailing Stop ({dd:.1%})",
                })
                cash += h["shares"] * current_price
                to_remove.append(ticker)
                continue

        for t in to_remove:
            del holdings[t]

        # ── 2. Score new candidates ─────────────────────────────────────────
        new_candidates = daily_crossovers.get(current_date, [])
        scored = []
        for c in new_candidates:
            # Volume filter
            if use_volume_filter and c["vol_ratio"] < vol_ratio_min:
                continue
            score = compute_score(c["angle"], c["market_cap"])
            scored.append({**c, "score": score})

        # ── 3. Merge and rank ──────────────────────────────────────────────
        all_stocks = []
        for ticker, h in holdings.items():
            # Momentum decay: re-score based on recent performance
            if use_decay:
                days_held = (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days
                if days_held > 0 and days_held % decay_days == 0:
                    current_price = get_price(ticker, current_date)
                    if current_price > 0:
                        perf = (current_price - h["entry_price"]) / h["entry_price"]
                        # Decayed score = original score × (1 + recent performance)
                        h["score"] = h["original_score"] * (1 + max(-0.5, min(0.5, perf)))

            all_stocks.append({
                "ticker": ticker,
                "score": h["score"],
                "sector": h.get("sector", "Unknown"),
                "is_holding": True,
            })

        held_tickers = set(holdings.keys())
        for c in scored:
            if c["ticker"] not in held_tickers:
                all_stocks.append({
                    "ticker": c["ticker"],
                    "score": c["score"],
                    "sector": c.get("sector", "Unknown"),
                    "angle": c["angle"],
                    "market_cap": c["market_cap"],
                    "price": c["price"],
                    "is_holding": False,
                })

        # Sort by score descending
        all_stocks.sort(key=lambda x: x["score"], reverse=True)

        # Sector diversification
        if use_sector_div:
            selected = []
            sector_count = {}
            for s in all_stocks:
                sec = s.get("sector", "Unknown")
                if sector_count.get(sec, 0) < max_per_sector:
                    selected.append(s)
                    sector_count[sec] = sector_count.get(sec, 0) + 1
                if len(selected) >= MAX_HOLDINGS:
                    break
            top5 = selected[:MAX_HOLDINGS]
        else:
            top5 = all_stocks[:MAX_HOLDINGS]

        top5_tickers = set(s["ticker"] for s in top5)

        # ── 4. Sell dropped holdings ────────────────────────────────────────
        to_drop = [t for t in holdings if t not in top5_tickers]
        for ticker in to_drop:
            h = holdings[ticker]
            days_held = (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days

            # Minimum holding period
            if use_min_hold and days_held < min_hold_days:
                continue  # Keep it

            current_price = get_price(ticker, current_date)
            if current_price > 0:
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "return_pct": round(ret * 100, 2),
                    "pnl_dollars": round(pnl, 2),
                    "exit_reason": "Rotated Out",
                })
                cash += h["shares"] * current_price
            del holdings[ticker]

        # ── 5. Buy new top 5 ────────────────────────────────────────────────
        for rank, s in enumerate(top5):
            if s["ticker"] not in holdings:
                price = s.get("price", get_price(s["ticker"], current_date))
                if price <= 0:
                    continue

                # Dynamic sizing
                if use_dynamic_sizing:
                    sizing_pcts = [0.30, 0.25, 0.20, 0.15, 0.10]
                    target_pct = sizing_pcts[rank] if rank < len(sizing_pcts) else 0.10
                else:
                    target_pct = 1.0 / MAX_HOLDINGS

                target_value = portfolio_value * target_pct
                shares = int(target_value / price)
                cost = shares * price
                if cost > cash:
                    shares = int(cash / price)
                    cost = shares * price
                if shares <= 0:
                    continue

                cash -= cost
                holdings[s["ticker"]] = {
                    "entry_date": current_date,
                    "entry_price": price,
                    "peak_price": price,
                    "shares": shares,
                    "score": s["score"],
                    "original_score": s["score"],
                    "sector": s.get("sector", "Unknown"),
                    "angle": s.get("angle", 0),
                    "market_cap": s.get("market_cap", 0),
                }

        # ── 6. Bear market shorting ──────────────────────────────────────────
        if use_bear_short and is_bear:
            # Short the bottom 5 ranked stocks (worst scores)
            bottom5 = all_stocks[-5:] if len(all_stocks) >= 5 else all_stocks
            for s in bottom5:
                if s["ticker"] not in holdings:
                    price = get_price(s["ticker"], current_date)
                    if price <= 0:
                        continue
                    short_value = portfolio_value * 0.05  # 5% per short
                    shares = int(short_value / price)
                    if shares <= 0:
                        continue
                    # Track as negative shares for short
                    holdings[f"SHORT_{s['ticker']}"] = {
                        "entry_date": current_date,
                        "entry_price": price,
                        "peak_price": price,
                        "shares": -shares,
                        "score": -s["score"],
                        "original_score": -s["score"],
                        "sector": s.get("sector", "Unknown"),
                        "is_short": True,
                        "ticker": s["ticker"],
                    }
                    cash += shares * price  # Short sale proceeds

        # ── 7. Track portfolio value ────────────────────────────────────────
        holdings_value = 0.0
        for ticker, h in holdings.items():
            price = get_price(ticker.replace("SHORT_", ""), current_date)
            if price > 0:
                if h.get("is_short"):
                    # Short P&L: entry_price - current_price
                    holdings_value += h["shares"] * (h["entry_price"] - price) + h["shares"] * h["entry_price"]
                else:
                    holdings_value += h["shares"] * price

        portfolio_value = cash + holdings_value

    # ── Results ────────────────────────────────────────────────────────────
    total_pnl = portfolio_value - CAPITAL
    total_ret = total_pnl / CAPITAL * 100

    sell_trades = [t for t in trades if t["side"] == "SELL"]
    winners = [t for t in sell_trades if t["pnl_dollars"] > 0]
    losers = [t for t in sell_trades if t["pnl_dollars"] <= 0]
    win_rate = len(winners) / len(sell_trades) * 100 if sell_trades else 0
    avg_win = np.mean([t["pnl_dollars"] for t in winners]) if winners else 0
    avg_loss = np.mean([t["pnl_dollars"] for t in losers]) if losers else 0
    gross_profit = sum(t["pnl_dollars"] for t in winners)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losers))
    profit_factor = gross_profit / (gross_loss + 1e-9)

    # Max drawdown
    peak = CAPITAL
    max_dd = 0.0
    eq = CAPITAL
    for t in sell_trades:
        eq += t["pnl_dollars"]
        peak = max(peak, eq)
        dd = (eq - peak) / peak
        max_dd = min(max_dd, dd)

    return {
        "name": variant_name,
        "final_value": round(portfolio_value, 2),
        "total_return_pct": round(total_ret, 2),
        "n_trades": len(sell_trades),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
    }


def main():
    # Pre-compute data once
    data = precompute_all()

    # SPY benchmark
    from app.services.data_service import get_data
    spy_df = get_data("SPY", start_date=AS_OF, end_date=END, frequency="daily")
    spy_ret = 0.0
    if spy_df is not None and not spy_df.empty:
        if "Date" not in spy_df.columns and spy_df.index.name == "Date":
            spy_df = spy_df.reset_index()
        spy_ret = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100

    # Define all variants
    variants = [
        ("1. BASELINE", {}),
        ("2. DYN_SIZE", {"use_dynamic_sizing": True}),
        ("3. ATR_STOP", {"use_atr_stop": True}),
        ("4. WEEKLY", {"use_weekly": True}),
        ("5. SECTOR", {"use_sector_div": True}),
        ("6. VOLUME", {"use_volume_filter": True}),
        ("7. MIN_HOLD", {"use_min_hold": True}),
        ("8. DECAY", {"use_decay": True}),
        ("9. BEAR_SHORT", {"use_bear_short": True}),
    ]

    # Run all variants
    print("\n" + "=" * 80)
    print("  RUNNING 9 STRATEGY VARIANTS")
    print("=" * 80)

    results = []
    for name, params in variants:
        print(f"\n  ▶ {name}...")
        t0 = time.time()
        result = run_simulation(data, name, **params)
        elapsed = time.time() - t0
        result["time_s"] = round(elapsed, 1)
        results.append(result)
        print(f"    Return: {result['total_return_pct']:>+8.2f}%  "
              f"Trades: {result['n_trades']}  "
              f"Win: {result['win_rate']}%  "
              f"DD: {result['max_drawdown_pct']:.1f}%  "
              f"({elapsed:.1f}s)")

    # ── Comparison Table ──────────────────────────────────────────────────
    print("\n" + "=" * 120)
    print("  COMPARISON TABLE")
    print("=" * 120)
    print(f"  {'Variant':>20}  {'Return':>10}  {'vs SPY':>10}  {'Final':>12}  "
          f"{'Trades':>7}  {'Win%':>6}  {'PF':>6}  {'AvgWin':>9}  {'AvgLoss':>9}  {'MaxDD':>7}  {'Time':>7}")
    print(f"  {'-'*20}  {'-'*10}  {'-'*10}  {'-'*12}  {'-'*7}  {'-'*6}  {'-'*6}  "
          f"{'─'*9}  {'─'*9}  {'─'*7}  {'─'*7}")

    spy_row = f"  {'SPY':>20}  {spy_ret:>+9.2f}%  {'—':>10}  ${CAPITAL*(1+spy_ret/100):>9,.0f}  "
    print(spy_row)

    for r in sorted(results, key=lambda x: x["total_return_pct"], reverse=True):
        alpha = r["total_return_pct"] - spy_ret
        print(f"  {r['name']:>20}  {r['total_return_pct']:>+9.2f}%  {alpha:>+9.2f}%  "
              f"${r['final_value']:>9,.0f}  {r['n_trades']:>7}  {r['win_rate']:>5.1f}%  "
              f"{r['profit_factor']:>5.2f}  ${r['avg_win']:>+7,.0f}  ${r['avg_loss']:>+7,.0f}  "
              f"{r['max_drawdown_pct']:>6.1f}%  {r['time_s']:>5.1f}s")

    # ── Best Variant ───────────────────────────────────────────────────────
    best = max(results, key=lambda x: x["total_return_pct"])
    print(f"\n{'='*120}")
    print(f"  🏆 BEST: {best['name']} — {best['total_return_pct']:+.2f}% vs SPY {spy_ret:+.2f}%")
    print(f"     Alpha: {best['total_return_pct'] - spy_ret:+.2f}%")
    print(f"     Final: ${best['final_value']:,.0f}")
    print(f"     Trades: {best['n_trades']} | Win Rate: {best['win_rate']}% | PF: {best['profit_factor']}")
    print(f"     Max DD: {best['max_drawdown_pct']}%")
    print("=" * 120)

    # ── Save results ──────────────────────────────────────────────────────
    out_path = os.path.join(os.path.dirname(__file__), "comparison_results.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\n💾 Results saved to: {out_path}")
    print("  ✅ DONE")


if __name__ == "__main__":
    main()
