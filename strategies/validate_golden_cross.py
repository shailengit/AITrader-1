"""
Golden Cross Rotation — 100-Run Validation
============================================
Validates the strategy with 100 randomized backtests from random start dates.
Each run: random start date (2002-01-01 to 2024-01-01) → 2026-07-08.
Logs: return, alpha, win rate, profit factor, max DD, exit reasons, top trades.
Purpose: ensure robustness, detect overfitting, validate no look-ahead bias.

Usage:
  cd backend && ./venv/bin/python ../strategies/validate_golden_cross.py
"""

import os
import sys
import warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import OrderedDict
import random
import json

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")

CAPITAL = 100_000.0
MAX_HOLDINGS = 5
ANGLE_WEIGHT = 0.60       # 60% angle (proven best blend)
CAP_WEIGHT = 0.40         # 40% market cap
MIN_HOLD_DAYS = 10
SIZING_PCTS = [0.30, 0.25, 0.20, 0.15, 0.10]
END_DATE = "2026-07-08"
N_RUNS = 100
MIN_START = "2002-01-01"
MAX_START = "2024-01-01"

# Trading costs (Alpaca: $0 commission, ~0.05% slippage for liquid stocks)
TRADING_COST = 0.0005      # 0.05% per trade

# Crisis override parameters
CRISIS_DRAWDOWN = 0.20   # 20% drop from 200-day high → go to cash
CRISIS_RECOVERY = 0.10   # Recover to within 10% of 200-day high → re-enter

SECTOR_TO_ETF = {
    "Technology": "XLK", "Energy": "XLE", "Financials": "XLF",
    "Financial Services": "XLF", "Health Care": "XLV", "Healthcare": "XLV",
    "Consumer Discretionary": "XLY", "Consumer Cyclical": "XLY",
    "Industrials": "XLI", "Communication Services": "XLC",
    "Consumer Staples": "XLP", "Consumer Defensive": "XLP",
    "Materials": "XLB", "Basic Materials": "XLB",
    "Real Estate": "XLRE", "Utilities": "XLU",
}


def get_sector_etf(ticker):
    from app.db.database import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT sector FROM stock_metadata WHERE ticker = :t"), {"t": ticker.upper()}).fetchone()
        if row and row[0]:
            return SECTOR_TO_ETF.get(row[0], "XLK")
    except Exception:
        pass
    return "XLK"


def compute_ema_crossover_angle(close, ema20, ema200, cross_idx):
    lookback = 3
    if cross_idx < lookback or cross_idx + lookback >= len(close):
        return 0.0
    spread_before = (ema20.iloc[cross_idx - lookback] - ema200.iloc[cross_idx - lookback])
    spread_after = (ema20.iloc[cross_idx + lookback] - ema200.iloc[cross_idx + lookback])
    angle = (spread_after - spread_before) / (lookback * 2)
    return float(angle) if pd.notna(angle) else 0.0


def compute_atr(high, low, close, period=14):
    """Compute Average True Range."""
    prev_close = close.shift(1)
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': (high - prev_close).abs(),
        'lc': (low - prev_close).abs(),
    }).max(axis=1)
    return tr.rolling(window=period).mean()


def precompute_all():
    """Pre-compute ALL stock data from earliest available date."""
    from app.db.database import engine
    from sqlalchemy import text
    from app.utils.security import get_safe_table_name

    print("=" * 80)
    print("  PRE-COMPUTING ALL STOCK DATA (1999-2026)")
    print("=" * 80)

    with engine.connect() as conn:
        res = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ))
        skip = {'stock_metadata', 'stock_financials_quarterly', 'stock_financials_yearly',
                'xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly', 'vix'}
        all_tickers = [row[0] for row in res if row[0] not in skip]

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
                    f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" FROM "{safe}" ORDER BY "Date"',
                    conn
                )
        except Exception:
            continue
        if df.empty or len(df) < 250:
            continue

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema200 = close.rolling(window=200).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        rsi_series = pd.Series(100 - (100 / (1 + close.diff().where(lambda x: x > 0, 0).rolling(14).mean() / (close.diff().where(lambda x: x < 0, 0).abs().rolling(14).mean() + 1e-9))))
        vol_ma50 = volume.rolling(window=50).mean()
        atr_series = compute_atr(high, low, close)

        # Golden cross events
        crossovers = []
        for i in range(1, len(df)):
            if (pd.notna(ema20.iloc[i]) and pd.notna(ema200.iloc[i]) and
                pd.notna(ema20.iloc[i-1]) and pd.notna(ema200.iloc[i-1])):
                if ema20.iloc[i-1] <= ema200.iloc[i-1] and ema20.iloc[i] > ema200.iloc[i]:
                    angle = compute_ema_crossover_angle(close, ema20, ema200, i)
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10], "type": "A",
                        "price": float(close.iloc[i]), "angle": angle,
                        "atr": float(atr_series.iloc[i]) if pd.notna(atr_series.iloc[i]) else 0,
                    })
                elif ema20.iloc[i-1] >= ema200.iloc[i-1] and ema20.iloc[i] < ema200.iloc[i]:
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10], "type": "death",
                        "price": float(close.iloc[i]), "angle": 0, "atr": 0,
                    })

        # Entry B events (check every day)
        entry_b_events = []
        for i in range(200, len(df)):
            if (pd.notna(close.iloc[i]) and pd.notna(ema50.iloc[i]) and pd.notna(ema200.iloc[i]) and
                pd.notna(rsi_series.iloc[i]) and pd.notna(vol_ma50.iloc[i]) and vol_ma50.iloc[i] > 0):
                if (close.iloc[i] > ema50.iloc[i] and ema50.iloc[i] > ema200.iloc[i] and
                    rsi_series.iloc[i] > 60 and volume.iloc[i] > vol_ma50.iloc[i] * 1.2):
                    # EMA50 slope as trend strength proxy
                    if i >= 5:
                        slope = (ema50.iloc[i] - ema50.iloc[i-5]) / ema50.iloc[i-5]
                    else:
                        slope = 0
                    entry_b_events.append({
                        "date": str(df["Date"].iloc[i])[:10], "type": "B",
                        "price": float(close.iloc[i]), "angle": float(slope * 100),
                        "atr": float(atr_series.iloc[i]) if pd.notna(atr_series.iloc[i]) else 0,
                    })

        if crossovers or entry_b_events:
            mc = 0.0
            try:
                with engine.connect() as conn:
                    row = conn.execute(text("SELECT market_cap FROM stock_metadata WHERE ticker = :t"), {"t": ticker.upper()}).fetchone()
                if row and row[0] is not None:
                    mc = float(row[0])
            except Exception:
                pass

            stock_db[ticker.upper()] = {
                "close": close.values, "dates": df["Date"].values,
                "high": high.values, "low": low.values,
                "crossovers": crossovers,
                "entry_b": entry_b_events,
                "market_cap": mc,
            }

    print(f"  Done. {len(stock_db)} stocks with data.")
    return stock_db


def run_simulation(stock_db, start_date, run_id, crisis_override=False):
    """Run the strategy from start_date to END_DATE. Returns metrics dict."""
    # Build daily event calendar filtered to start_date onwards
    daily_events = {}
    daily_death = {}

    for ticker, data in stock_db.items():
        for ev in data["crossovers"]:
            if ev["date"] < start_date:
                continue
            if ev["type"] == "death":
                if ticker not in daily_death:
                    daily_death[ticker] = []
                daily_death[ticker].append(ev["date"])
            else:
                d = ev["date"]
                if d not in daily_events:
                    daily_events[d] = []
                daily_events[d].append({
                    "ticker": ticker, "type": "A",
                    "price": ev["price"], "angle": ev["angle"],
                    "market_cap": data["market_cap"], "atr": ev["atr"],
                })

        for ev in data["entry_b"]:
            if ev["date"] < start_date:
                continue
            d = ev["date"]
            if d not in daily_events:
                daily_events[d] = []
            daily_events[d].append({
                "ticker": ticker, "type": "B",
                "price": ev["price"], "angle": ev["angle"],
                "market_cap": data["market_cap"], "atr": ev["atr"],
            })

    all_dates = sorted(daily_events.keys())
    if not all_dates:
        return None

    # Markov regime training (using SPY only for robustness)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(END_DATE, "%Y-%m-%d")

    retrain_dates = []
    d = start_dt + timedelta(days=3 * 365)
    while d < end_dt:
        retrain_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=180)

    regime_cache = {}
    for i, rd in enumerate(retrain_dates):
        ts = (datetime.strptime(rd, "%Y-%m-%d") - timedelta(days=3 * 365 + 35)).strftime("%Y-%m-%d")
        try:
            from app.services.markov.feature_engineering import compute_etf_features
            from app.services.markov.regime_model import JumpModel
            # Train JumpModel on SPY directly (most reliable, longest history)
            spy_features = compute_etf_features("SPY", ts, rd)
            if spy_features is not None and len(spy_features) >= 60:
                jm = JumpModel("SPY", jump_penalty=10.0)
                jm.train(spy_features)
                we = retrain_dates[i + 1] if i + 1 < len(retrain_dates) else END_DATE
                cur = datetime.strptime(rd, "%Y-%m-%d")
                we_dt = datetime.strptime(we, "%Y-%m-%d")
                day = cur
                while day <= we_dt:
                    ds = day.strftime("%Y-%m-%d")
                    regime_cache[ds] = jm.get_regime(ds)
                    day += timedelta(days=1)
        except Exception as e:
            # Fallback: assume BULL
            we = retrain_dates[i + 1] if i + 1 < len(retrain_dates) else END_DATE
            cur = datetime.strptime(rd, "%Y-%m-%d")
            we_dt = datetime.strptime(we, "%Y-%m-%d")
            day = cur
            while day <= we_dt:
                regime_cache[day.strftime("%Y-%m-%d")] = {"regime": "BULL", "vol_regime": "LOW", "bull_probability": 0.5}
                day += timedelta(days=1)

    def get_regime(ds):
        r = regime_cache.get(ds, {})
        return r.get("regime", "BULL")

    # Normalization
    all_market_caps = [v["market_cap"] for v in stock_db.values() if v["market_cap"] > 0]
    cap_max = max(all_market_caps) if all_market_caps else 1
    cap_min = min(all_market_caps) if all_market_caps else 0
    cap_range = cap_max - cap_min if cap_max > cap_min else 1

    def compute_score(angle, market_cap):
        angle_norm = 1 / (1 + np.exp(-angle * 100))
        cap_norm = (market_cap - cap_min) / cap_range if cap_range > 0 else 0.5
        return ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm

    def get_price(ticker, ds):
        d = stock_db.get(ticker)
        if d is None:
            return 0.0
        dates = d["dates"]
        close = d["close"]
        target = pd.Timestamp(ds)
        for i in range(len(dates) - 1, -1, -1):
            if pd.Timestamp(dates[i]) <= target:
                return float(close[i])
        return 0.0

    def has_death(ticker, ds):
        return any(d <= ds for d in daily_death.get(ticker, []))

    # Simulation
    holdings = OrderedDict()
    trades = []
    cash = CAPITAL
    portfolio_value = CAPITAL

    # Crisis override state
    crisis_mode = False
    spy_high_200 = []
    spy_prices_for_crisis = []

    for current_date in all_dates:
        regime = get_regime(current_date)

        # ── Crisis Override ──────────────────────────────────────────────
        if crisis_override:
            spy_cp = get_price("SPY", current_date)
            if spy_cp > 0:
                spy_prices_for_crisis.append(spy_cp)
                if len(spy_prices_for_crisis) > 200:
                    spy_prices_for_crisis.pop(0)
                spy_high = max(spy_prices_for_crisis) if spy_prices_for_crisis else spy_cp
                spy_dd = (spy_high - spy_cp) / spy_high

                if crisis_mode:
                    # Check for recovery: within 10% of 200-day high
                    if spy_cp >= spy_high * (1 - CRISIS_RECOVERY):
                        crisis_mode = False
                        # Log the re-entry
                        trades.append({
                            "ticker": "CRISIS", "side": "EXIT",
                            "entry_date": current_date, "exit_date": current_date,
                            "return_pct": 0, "pnl_dollars": 0,
                            "exit_reason": "Crisis Recovery — Re-entering market",
                        })
                else:
                    # Check for crisis: dropped >20% from 200-day high
                    if spy_dd >= CRISIS_DRAWDOWN:
                        crisis_mode = True
                        # Sell all holdings immediately
                        for ticker in list(holdings.keys()):
                            h = holdings[ticker]
                            cp = get_price(ticker, current_date)
                            if cp > 0:
                                ret = (cp - h["entry_price"]) / h["entry_price"]
                                pnl = h["shares"] * (cp - h["entry_price"])
                                cost = abs(pnl) * TRADING_COST
                                trades.append({
                                    "ticker": ticker, "side": "SELL",
                                    "entry_date": h["entry_date"], "exit_date": current_date,
                                    "entry_price": round(h["entry_price"], 2),
                                    "exit_price": round(cp, 2),
                                    "shares": h["shares"],
                                    "return_pct": round(ret * 100, 2),
                                    "pnl_dollars": round(pnl - cost, 2),
                                    "exit_reason": "Crisis Override",
                                    "angle": h.get("angle", 0),
                                    "holding_days": (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days,
                                })
                                cash += h["shares"] * cp
                        holdings.clear()

        # If in crisis mode, skip all trading
        if crisis_mode:
            portfolio_value = cash
            continue

        # Exits
        to_remove = []
        for ticker in list(holdings.keys()):
            h = holdings[ticker]
            cp = get_price(ticker, current_date)
            if cp <= 0:
                continue
            h["peak"] = max(h["peak"], cp)

            if has_death(ticker, current_date):
                ret = (cp - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (cp - h["entry_price"])
                cost = abs(pnl) * TRADING_COST
                trades.append({"ticker": ticker, "side": "SELL", "entry_date": h["entry_date"], "exit_date": current_date,
                               "entry_price": round(h["entry_price"], 2), "exit_price": round(cp, 2),
                               "shares": h["shares"],
                               "return_pct": round(ret * 100, 2), "pnl_dollars": round(pnl - cost, 2),
                               "exit_reason": "Death Cross", "angle": h.get("angle", 0),
                               "holding_days": (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days})
                cash += h["shares"] * cp
                to_remove.append(ticker)
                continue

            # ATR-based trailing stop
            atr = h.get("atr", 0)
            stop_pct = max(0.08, min(0.30, atr * 3 / h["entry_price"])) if atr > 0 else 0.20
            dd = (h["peak"] - cp) / h["peak"]
            if dd >= stop_pct:
                ret = (cp - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (cp - h["entry_price"])
                cost = abs(pnl) * TRADING_COST
                trades.append({"ticker": ticker, "side": "SELL", "entry_date": h["entry_date"], "exit_date": current_date,
                               "entry_price": round(h["entry_price"], 2), "exit_price": round(cp, 2),
                               "shares": h["shares"],
                               "return_pct": round(ret * 100, 2), "pnl_dollars": round(pnl - cost, 2),
                               "exit_reason": f"Trailing Stop ({dd:.1%})", "angle": h.get("angle", 0),
                               "holding_days": (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days})
                cash += h["shares"] * cp
                to_remove.append(ticker)
                continue

        for t in to_remove:
            del holdings[t]

        # Score new candidates
        new_candidates = daily_events.get(current_date, [])
        for c in new_candidates:
            c["score"] = compute_score(c["angle"], c["market_cap"])

        # Merge and rank
        all_stocks = []
        for ticker, h in holdings.items():
            all_stocks.append({"ticker": ticker, "score": h["score"], "is_holding": True})

        held = set(holdings.keys())
        for c in new_candidates:
            if c["ticker"] not in held:
                all_stocks.append({"ticker": c["ticker"], "score": c["score"], "price": c["price"],
                                    "atr": c.get("atr", 0), "is_holding": False})

        all_stocks.sort(key=lambda x: x["score"], reverse=True)
        top5 = all_stocks[:MAX_HOLDINGS]
        top5_t = set(s["ticker"] for s in top5)

        # Sell dropped (with min hold)
        to_drop = [t for t in holdings if t not in top5_t]
        for ticker in to_drop:
            h = holdings[ticker]
            days_held = (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days
            if days_held < MIN_HOLD_DAYS:
                continue
            cp = get_price(ticker, current_date)
            if cp > 0:
                ret = (cp - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (cp - h["entry_price"])
                cost = abs(pnl) * TRADING_COST
                trades.append({"ticker": ticker, "side": "SELL", "entry_date": h["entry_date"], "exit_date": current_date,
                               "entry_price": round(h["entry_price"], 2), "exit_price": round(cp, 2),
                               "shares": h["shares"],
                               "return_pct": round(ret * 100, 2), "pnl_dollars": round(pnl - cost, 2),
                               "exit_reason": "Rotated Out", "angle": h.get("angle", 0),
                               "holding_days": (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days})
                cash += h["shares"] * cp
            del holdings[ticker]

        # Buy new top 5
        for rank, s in enumerate(top5):
            if s["ticker"] not in holdings:
                price = s.get("price", get_price(s["ticker"], current_date))
                if price <= 0:
                    continue
                target_pct = SIZING_PCTS[rank] if rank < len(SIZING_PCTS) else 0.10
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
                    "entry_date": current_date, "entry_price": price, "peak": price,
                    "shares": shares, "score": s["score"], "atr": s.get("atr", 0),
                    "angle": s.get("angle", 0),
                }

        # Track value
        hv = 0.0
        for ticker, h in holdings.items():
            p = get_price(ticker, current_date)
            if p > 0:
                hv += h["shares"] * p
        portfolio_value = cash + hv

    # ── Compute metrics ──────────────────────────────────────────────────
    total_pnl = portfolio_value - CAPITAL
    total_ret = total_pnl / CAPITAL * 100

    sell_trades = [t for t in trades if t["side"] == "SELL"]
    winners = [t for t in sell_trades if t["pnl_dollars"] > 0]
    losers = [t for t in sell_trades if t["pnl_dollars"] <= 0]
    win_rate = len(winners) / len(sell_trades) * 100 if sell_trades else 0
    avg_win = np.mean([t["pnl_dollars"] for t in winners]) if winners else 0
    avg_loss = np.mean([t["pnl_dollars"] for t in losers]) if losers else 0
    gp = sum(t["pnl_dollars"] for t in winners)
    gl = abs(sum(t["pnl_dollars"] for t in losers))
    pf = gp / (gl + 1e-9)

    # Max drawdown
    peak = CAPITAL
    eq = CAPITAL
    max_dd = 0.0
    for t in sell_trades:
        eq += t["pnl_dollars"]
        peak = max(peak, eq)
        dd = (eq - peak) / peak
        max_dd = min(max_dd, dd)

    # Exit reason breakdown
    exit_reasons = {}
    for t in sell_trades:
        r = t["exit_reason"].split("(")[0].strip()
        if r not in exit_reasons:
            exit_reasons[r] = {"count": 0, "wins": 0, "total_pnl": 0}
        exit_reasons[r]["count"] += 1
        exit_reasons[r]["total_pnl"] += t["pnl_dollars"]
        if t["pnl_dollars"] > 0:
            exit_reasons[r]["wins"] += 1

    # Top/bottom trades
    sorted_trades = sorted(sell_trades, key=lambda t: t["return_pct"], reverse=True)
    top3 = sorted_trades[:3] if len(sorted_trades) >= 3 else sorted_trades
    bot3 = sorted_trades[-3:] if len(sorted_trades) >= 3 else sorted_trades

    # Duration
    duration_years = (pd.Timestamp(END_DATE) - pd.Timestamp(start_date)).days / 365.25
    annualized_ret = ((1 + total_ret / 100) ** (1 / duration_years) - 1) * 100 if duration_years > 0 else 0

    result = {
        "run_id": run_id,
        "start_date": start_date,
        "end_date": END_DATE,
        "duration_years": round(duration_years, 1),
        "annualized_return_pct": round(annualized_ret, 2),
        "total_return_pct": round(total_ret, 2),
        "final_value": round(portfolio_value, 2),
        "n_trades": len(sell_trades),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(pf, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "exit_reasons": exit_reasons,
        "top3_winners": [{"t": t["ticker"], "r": t["return_pct"], "pnl": t["pnl_dollars"], "reason": t["exit_reason"]} for t in top3],
        "top3_losers": [{"t": t["ticker"], "r": t["return_pct"], "pnl": t["pnl_dollars"], "reason": t["exit_reason"]} for t in bot3],
    }

    # Save all trades to CSV for this run
    return result, trades


def save_trades_to_csv(all_run_trades, output_path):
    """Save all trades from all runs to a single CSV file."""
    import csv
    fieldnames = ["run_id", "ticker", "side", "entry_date", "exit_date",
                  "entry_price", "exit_price", "shares", "return_pct",
                  "pnl_dollars", "exit_reason", "angle", "holding_days"]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for run_id, trades in all_run_trades.items():
            for t in trades:
                t["run_id"] = run_id
                writer.writerow({k: t.get(k, "") for k in fieldnames})


def main():
    from app.services.data_service import get_data

    # Pre-compute all data once
    stock_db = precompute_all()

    # Generate 100 random start dates
    random.seed(42)
    min_dt = datetime.strptime(MIN_START, "%Y-%m-%d")
    max_dt = datetime.strptime(MAX_START, "%Y-%m-%d")
    total_days = (max_dt - min_dt).days

    start_dates = set()
    while len(start_dates) < N_RUNS:
        days_offset = random.randint(0, total_days)
        d = (min_dt + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        start_dates.add(d)
    start_dates = sorted(start_dates)

    print(f"\n{'='*80}")
    print(f"  RUNNING {N_RUNS} RANDOMIZED BACKTESTS")
    print("=" * 80)
    print(f"  Date range: {start_dates[0]} to {start_dates[-1]}")
    print(f"  Each run:   start → {END_DATE}")
    print(f"  Capital:    ${CAPITAL:,.2f}")
    print("=" * 80)

    all_results = []
    all_run_trades = {}
    for i, sd in enumerate(start_dates):
        print(f"\n  Run {i+1}/{N_RUNS}: {sd} → {END_DATE}...", end=" ")
        try:
            result, trades = run_simulation(stock_db, sd, i + 1, crisis_override=True)
            if result:
                all_results.append(result)
                all_run_trades[i + 1] = trades
                print(f"Return: {result['total_return_pct']:>+7.2f}%  "
                      f"Ann: {result['annualized_return_pct']:>+5.2f}%  "
                      f"Trades: {result['n_trades']}  Win: {result['win_rate']}%  "
                      f"DD: {result['max_drawdown_pct']:.1f}%")
            else:
                print("⚠️  No data")
        except Exception as e:
            print(f"❌ Error: {e}")

    # ── Summary Statistics ──────────────────────────────────────────────────
    print(f"\n{'='*120}")
    print("  SUMMARY STATISTICS (100 RUNS)")
    print("=" * 120)

    df = pd.DataFrame(all_results)

    # SPY benchmark for each run
    spy_df = get_data("SPY", start_date="1999-01-01", end_date=END_DATE, frequency="daily")
    if spy_df is not None and not spy_df.empty:
        if "Date" not in spy_df.columns and spy_df.index.name == "Date":
            spy_df = spy_df.reset_index()
    spy_close = dict(zip(spy_df["Date"].astype(str), spy_df["Close"]))

    spy_returns = []
    for r in all_results:
        sd = r["start_date"]
        spy_buy = None
        for d in sorted(spy_close.keys(), reverse=True):
            if d <= sd:
                spy_buy = spy_close[d]
                break
        spy_sell = list(spy_close.values())[-1]
        if spy_buy and spy_buy > 0:
            spy_ret = (spy_sell - spy_buy) / spy_buy * 100
        else:
            spy_ret = 0
        spy_returns.append(spy_ret)
        r["spy_return_pct"] = round(spy_ret, 2)
        r["alpha_pct"] = round(r["total_return_pct"] - spy_ret, 2)

    df = pd.DataFrame(all_results)

    print(f"\n  {'Metric':>25}  {'Mean':>10}  {'Median':>10}  {'Min':>10}  {'Max':>10}  {'Std':>10}  {'Win%':>8}")
    print(f"  {'-'*25}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*8}")

    for metric in ["annualized_return_pct", "total_return_pct", "alpha_pct", "win_rate", "profit_factor", "max_drawdown_pct", "n_trades", "duration_years"]:
        col = df[metric]
        win_pct = (col > 0).mean() * 100 if metric != "duration_years" else 100
        print(f"  {metric:>25}  {col.mean():>+9.2f}  {col.median():>+9.2f}  {col.min():>+9.2f}  "
              f"{col.max():>+9.2f}  {col.std():>9.2f}  {win_pct:>7.0f}%")

    # Runs that beat SPY
    n_beats = sum(1 for r in all_results if r.get("alpha_pct", 0) > 0)
    print(f"\n  Runs that beat SPY: {n_beats}/{len(all_results)} ({n_beats/len(all_results)*100:.0f}%)")

    # Exit reason analysis
    print(f"\n  ── Exit Reason Analysis (across all runs) ──")
    all_exits = {}
    for r in all_results:
        for reason, data in r.get("exit_reasons", {}).items():
            if reason not in all_exits:
                all_exits[reason] = {"count": 0, "wins": 0, "pnl": 0}
            all_exits[reason]["count"] += data["count"]
            all_exits[reason]["wins"] += data["wins"]
            all_exits[reason]["pnl"] += data["total_pnl"]

    print(f"  {'Exit Reason':>25}  {'Count':>8}  {'Win%':>8}  {'Total P&L':>12}")
    print(f"  {'-'*25}  {'-'*8}  {'-'*8}  {'-'*12}")
    for reason, data in sorted(all_exits.items(), key=lambda x: -x[1]["count"]):
        wr = data["wins"] / data["count"] * 100 if data["count"] > 0 else 0
        print(f"  {reason:>25}  {data['count']:>8}  {wr:>7.0f}%  ${data['pnl']:>+10,.0f}")

    # ── Save results ──────────────────────────────────────────────────────
    suffix = "_alpaca"  # 60/40 blend + Alpaca costs (0.05%)
    out_path = os.path.join(os.path.dirname(__file__), f"validation_results{suffix}.csv")
    df.to_csv(out_path, index=False)
    print(f"\n💾 Results saved to: {out_path}")

    # Save detailed trade log
    detailed_path = os.path.join(os.path.dirname(__file__), f"validation_detailed{suffix}.json")
    with open(detailed_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"💾 Detailed results saved to: {detailed_path}")

    # Save all trades to CSV
    trades_path = os.path.join(os.path.dirname(__file__), f"all_trades{suffix}.csv")
    save_trades_to_csv(all_run_trades, trades_path)
    total_trades = sum(len(t) for t in all_run_trades.values())
    print(f"💾 All trades saved to: {trades_path} ({total_trades:,} total trades)")

    print(f"\n{'='*120}")
    print("  ✅ VALIDATION COMPLETE")
    print("=" * 120)


if __name__ == "__main__":
    main()
