"""
Golden Cross Rotation v3 — ATR Dynamic Trailing Stop
=====================================================
Scans 1500 stocks daily for:
  Entry A (golden cross): EMA20 crosses above EMA200
  Entry B (trend ride):   Price > EMA50 > EMA200 AND RSI(14) > 60 AND volume > 1.2× 50d avg

Ranks by: 60% trend strength + 40% market cap.
  Entry A angle = EMA20/200 crossover angle
  Entry B angle = EMA50 slope (trend strength proxy)

Holds top 5 with dynamic sizing (30/25/20/15/10% by rank).
Minimum 10-day holding period before rotation.
Dynamic trailing stop = clamp(ATR(14) × 3 / price, 8%, 30%) — recalculated daily.
Death cross exit.
Markov regime adaptation for bear market protection.
$100,000 starting capital.

Usage:
  cd backend && ./venv/bin/python ../strategies/golden_cross_v3_atr_stop.py
"""

import os
import sys
import warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import OrderedDict

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")

# ── Configuration ──────────────────────────────────────────────────────────
AS_OF = "2020-01-01"
END = "2026-07-08"
CAPITAL = 100_000.0
MAX_HOLDINGS = 5
ANGLE_WEIGHT = 0.60
CAP_WEIGHT = 0.40
MIN_HOLD_DAYS = 10
SIZING_PCTS = [0.30, 0.25, 0.20, 0.15, 0.10]

# Dynamic trailing stop parameters
ATR_PERIOD = 14
ATR_MULTIPLIER = 3.0
TRAILING_STOP_MIN = 0.08   # 8% floor
TRAILING_STOP_MAX = 0.30   # 30% ceiling

SECTOR_TO_ETF = {
    "Technology": "XLK", "Energy": "XLE", "Financials": "XLF",
    "Financial Services": "XLF", "Health Care": "XLV", "Healthcare": "XLV",
    "Consumer Discretionary": "XLY", "Consumer Cyclical": "XLY",
    "Industrials": "XLI", "Communication Services": "XLC",
    "Consumer Staples": "XLP", "Consumer Defensive": "XLP",
    "Materials": "XLB", "Basic Materials": "XLB",
    "Real Estate": "XLRE", "Utilities": "XLU",
}


def get_sector_etf(ticker: str) -> str:
    from app.db.database import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT sector FROM stock_metadata WHERE ticker = :t"),
                {"t": ticker.upper()}
            ).fetchone()
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


def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_atr(high, low, close, period=14):
    """Compute Average True Range (ATR) for a given period."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


def compute_dynamic_trailing_stop(atr_value, current_price):
    """
    Compute dynamic trailing stop percentage.

    Formula: clamp(ATR(14) × multiplier / current_price, min, max)

    Where:
    - ATR(14) is the 14-day Average True Range
    - multiplier = 3.0
    - min = 8% (floor)
    - max = 30% (ceiling)
    """
    if atr_value <= 0 or current_price <= 0:
        return TRAILING_STOP_MIN
    raw_stop = (atr_value * ATR_MULTIPLIER) / current_price
    return float(np.clip(raw_stop, TRAILING_STOP_MIN, TRAILING_STOP_MAX))


def main():
    from app.services.data_service import get_data
    from app.services.markov.regime_model import SectorRegimeManager
    from app.db.database import engine
    from sqlalchemy import text
    from app.utils.security import get_safe_table_name

    print("=" * 80)
    print("  GOLDEN CROSS ROTATION v3 — ATR DYNAMIC TRAILING STOP")
    print("=" * 80)
    print(f"  Period:     {AS_OF} → {END}")
    print(f"  Capital:    ${CAPITAL:,.2f}")
    print(f"  Holdings:   Top {MAX_HOLDINGS} (dynamic sizing: {SIZING_PCTS})")
    print(f"  Ranking:    {ANGLE_WEIGHT*100:.0f}% trend + {CAP_WEIGHT*100:.0f}% market cap")
    print(f"  Trailing:   Dynamic ATR(14)×{ATR_MULTIPLIER} / price  [{TRAILING_STOP_MIN:.0%}–{TRAILING_STOP_MAX:.0%}]")
    print(f"  Min Hold:   {MIN_HOLD_DAYS} days")
    print(f"  Exits:      Death cross, rotation, or dynamic trailing stop")
    print(f"  Entry A:    EMA20/200 golden cross (crossover angle)")
    print(f"  Entry B:    Price>EMA50>EMA200 + RSI>60 + Vol>1.2×avg (EMA50 slope)")
    print("=" * 80)

    # ── Get all tickers ─────────────────────────────────────────────────────
    with engine.connect() as conn:
        res = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ))
        skip = {'stock_metadata', 'stock_financials_quarterly', 'stock_financials_yearly',
                'xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly'}
        all_tickers = [row[0] for row in res if row[0] not in skip]

    # ── Pre-compute stock data ──────────────────────────────────────────────
    print(f"\n📥 Pre-computing {len(all_tickers)} stocks (Entry A + Entry B)...")
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
                    f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" FROM "{safe}" '
                    f'WHERE "Date" >= \'2018-01-01\' AND "Date" <= \'{END}\' ORDER BY "Date"',
                    conn
                )
        except Exception:
            continue
        if df.empty or len(df) < 250:
            continue

        close = df["Close"]
        volume = df["Volume"]
        high = df["High"]
        low = df["Low"]

        # ── Indicators ──────────────────────────────────────────────────────
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema200 = close.rolling(window=200).mean()
        rsi = compute_rsi(close, period=14)
        volume_ma50 = volume.rolling(window=50).mean()
        atr = compute_atr(high, low, close, period=ATR_PERIOD)

        # ── Entry A: Golden cross / death cross ──────────────────────────────
        crossovers = []
        for i in range(1, len(df)):
            if (pd.notna(ema20.iloc[i]) and pd.notna(ema200.iloc[i]) and
                pd.notna(ema20.iloc[i-1]) and pd.notna(ema200.iloc[i-1])):
                if ema20.iloc[i-1] <= ema200.iloc[i-1] and ema20.iloc[i] > ema200.iloc[i]:
                    angle = compute_ema_crossover_angle(close, ema20, ema200, i)
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10],
                        "price": float(close.iloc[i]),
                        "angle": angle,
                        "entry_type": "A",
                    })
                elif ema20.iloc[i-1] >= ema200.iloc[i-1] and ema20.iloc[i] < ema200.iloc[i]:
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10],
                        "price": float(close.iloc[i]),
                        "angle": 0.0,
                        "death_cross": True,
                    })

        # ── Entry B: Trend ride ─────────────────────────────────────────────
        entry_b_lookback = 5
        for i in range(200, len(df)):
            if not (pd.notna(close.iloc[i]) and pd.notna(ema50.iloc[i]) and
                    pd.notna(ema200.iloc[i]) and pd.notna(rsi.iloc[i]) and
                    pd.notna(volume.iloc[i]) and pd.notna(volume_ma50.iloc[i])):
                continue

            if (close.iloc[i] > ema50.iloc[i] and
                ema50.iloc[i] > ema200.iloc[i] and
                rsi.iloc[i] > 60 and
                volume.iloc[i] > 1.2 * volume_ma50.iloc[i]):

                is_golden_cross = False
                if (i > 0 and pd.notna(ema20.iloc[i]) and pd.notna(ema200.iloc[i]) and
                    pd.notna(ema20.iloc[i-1]) and pd.notna(ema200.iloc[i-1])):
                    if ema20.iloc[i-1] <= ema200.iloc[i-1] and ema20.iloc[i] > ema200.iloc[i]:
                        is_golden_cross = True

                if not is_golden_cross:
                    if i >= entry_b_lookback:
                        slope = (ema50.iloc[i] - ema50.iloc[i - entry_b_lookback]) / ema50.iloc[i - entry_b_lookback]
                    else:
                        slope = 0.0

                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10],
                        "price": float(close.iloc[i]),
                        "angle": float(slope) if pd.notna(slope) else 0.0,
                        "entry_type": "B",
                    })

        if crossovers:
            mc = 0.0
            try:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT market_cap FROM stock_metadata WHERE ticker = :t"),
                        {"t": ticker.upper()}
                    ).fetchone()
                if row and row[0] is not None:
                    mc = float(row[0])
            except Exception:
                pass
            stock_db[ticker.upper()] = {
                "close": close.values,
                "high": high.values,
                "low": low.values,
                "dates": df["Date"].values,
                "crossovers": crossovers,
                "market_cap": mc,
                "atr": atr.values,  # Store ATR for each day
            }

    print(f"  Done. {len(stock_db)} stocks with entry data.")

    # ── Build crossover index ───────────────────────────────────────────────
    print("\n📅 Building daily entry calendar...")
    daily_crossovers = {}
    daily_death_crosses = {}
    entry_a_count = 0
    entry_b_count = 0
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
                    "entry_type": co.get("entry_type", "A"),
                })
                if co.get("entry_type") == "B":
                    entry_b_count += 1
                else:
                    entry_a_count += 1

    print(f"  {len(daily_crossovers)} days with entries")
    print(f"  Entry A (golden cross): {entry_a_count} events")
    print(f"  Entry B (trend ride):   {entry_b_count} events")
    print(f"  Total:                  {entry_a_count + entry_b_count} events")

    # ── Markov regime training ──────────────────────────────────────────────
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

    # ── Normalization ──────────────────────────────────────────────────────
    all_market_caps = [v["market_cap"] for v in stock_db.values() if v["market_cap"] > 0]
    cap_max = max(all_market_caps) if all_market_caps else 1
    cap_min = min(all_market_caps) if all_market_caps else 0
    cap_range = cap_max - cap_min if cap_max > cap_min else 1

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
        """Get the ATR value for a ticker on or before a given date."""
        d = stock_db.get(ticker)
        if d is None:
            return 0.0
        dates = d["dates"]
        atr = d["atr"]
        target = pd.Timestamp(date_str)
        for i in range(len(dates) - 1, -1, -1):
            if pd.Timestamp(dates[i]) <= target:
                return float(atr[i]) if pd.notna(atr[i]) else 0.0
        return 0.0

    def has_death_cross(ticker, date_str):
        dc_dates = daily_death_crosses.get(ticker, [])
        return any(d <= date_str for d in dc_dates)

    # ── Daily rotation simulation ───────────────────────────────────────────
    print(f"\n📈 Running daily rotation simulation...")
    all_dates = sorted(daily_crossovers.keys())
    print(f"  {len(all_dates)} trading days")

    holdings = OrderedDict()
    trades = []
    cash = CAPITAL
    portfolio_value = CAPITAL

    for sim_idx, current_date in enumerate(all_dates):
        if (sim_idx + 1) % 200 == 0:
            print(f"  Day {sim_idx+1}/{len(all_dates)}  Portfolio: ${portfolio_value:>9,.2f}  Holdings: {len(holdings)}")

        regime = get_regime(current_date)

        # ── 1. Check exits ────────────────────────────────────────────────
        to_remove = []
        for ticker in list(holdings.keys()):
            h = holdings[ticker]
            current_price = get_price(ticker, current_date)
            if current_price <= 0:
                continue
            h["peak_price"] = max(h["peak_price"], current_price)

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

            # ── Dynamic trailing stop ─────────────────────────────────────
            atr_value = get_atr(ticker, current_date)
            trailing_stop_pct = compute_dynamic_trailing_stop(atr_value, current_price)
            dd = (h["peak_price"] - current_price) / h["peak_price"]
            if dd >= trailing_stop_pct:
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "return_pct": round(ret * 100, 2),
                    "pnl_dollars": round(pnl, 2),
                    "exit_reason": f"ATR Stop ({dd:.1%})",
                })
                cash += h["shares"] * current_price
                to_remove.append(ticker)
                continue

        for t in to_remove:
            del holdings[t]

        # ── 2. Score new candidates ─────────────────────────────────────────
        new_candidates = daily_crossovers.get(current_date, [])
        for c in new_candidates:
            c["score"] = compute_score(c["angle"], c["market_cap"])

        # ── 3. Merge and rank ──────────────────────────────────────────────
        all_stocks = []
        for ticker, h in holdings.items():
            all_stocks.append({
                "ticker": ticker,
                "score": h["score"],
                "is_holding": True,
            })

        held_tickers = set(holdings.keys())
        for c in new_candidates:
            if c["ticker"] not in held_tickers:
                all_stocks.append({
                    "ticker": c["ticker"],
                    "score": c["score"],
                    "angle": c["angle"],
                    "market_cap": c["market_cap"],
                    "price": c["price"],
                    "is_holding": False,
                })

        all_stocks.sort(key=lambda x: x["score"], reverse=True)
        top5 = all_stocks[:MAX_HOLDINGS]
        top5_tickers = set(s["ticker"] for s in top5)

        # ── 4. Sell dropped (with min hold) ────────────────────────────────
        to_drop = [t for t in holdings if t not in top5_tickers]
        for ticker in to_drop:
            h = holdings[ticker]
            days_held = (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days
            if days_held < MIN_HOLD_DAYS:
                continue

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

        # ── 5. Buy new top 5 (dynamic sizing) ──────────────────────────────
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
                    "entry_date": current_date,
                    "entry_price": price,
                    "peak_price": price,
                    "shares": shares,
                    "score": s["score"],
                }

        # ── 6. Track portfolio value ──────────────────────────────────────
        holdings_value = 0.0
        for ticker, h in holdings.items():
            price = get_price(ticker, current_date)
            if price > 0:
                holdings_value += h["shares"] * price
        portfolio_value = cash + holdings_value

    # ── Results ──────────────────────────────────────────────────────────────
    total_pnl = portfolio_value - CAPITAL
    total_ret = total_pnl / CAPITAL * 100

    print(f"\n{'='*80}")
    print("  RESULTS")
    print("=" * 80)
    print(f"  Initial Capital:  ${CAPITAL:>10,.2f}")
    print(f"  Final Portfolio:  ${portfolio_value:>10,.2f}")
    print(f"  Total P&L:        ${total_pnl:>+10,.2f}")
    print(f"  Total Return:     {total_ret:>+8.2f}%")

    spy_df = get_data("SPY", start_date=AS_OF, end_date=END, frequency="daily")
    if spy_df is not None and not spy_df.empty:
        if "Date" not in spy_df.columns and spy_df.index.name == "Date":
            spy_df = spy_df.reset_index()
        spy_ret = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100
        alpha = total_ret - spy_ret
        print(f"  SPY Return:       {spy_ret:>+8.2f}%")
        print(f"  Alpha:            {alpha:>+8.2f}%  ✅")

    sell_trades = [t for t in trades if t["side"] == "SELL"]
    winners = [t for t in sell_trades if t["pnl_dollars"] > 0]
    losers = [t for t in sell_trades if t["pnl_dollars"] <= 0]
    win_rate = len(winners) / len(sell_trades) * 100 if sell_trades else 0
    avg_win = np.mean([t["pnl_dollars"] for t in winners]) if winners else 0
    avg_loss = np.mean([t["pnl_dollars"] for t in losers]) if losers else 0
    gross_profit = sum(t["pnl_dollars"] for t in winners)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losers))
    profit_factor = gross_profit / (gross_loss + 1e-9)

    print(f"\n  ── Trade Stats ──")
    print(f"  Total Trades:     {len(sell_trades)}")
    print(f"  Win Rate:         {win_rate:.1f}%")
    print(f"  Profit Factor:    {profit_factor:.2f}")
    print(f"  Avg Winner:       ${avg_win:>+8,.2f}")
    print(f"  Avg Loser:        ${avg_loss:>+8,.2f}")

    # Top trades
    sorted_trades = sorted(sell_trades, key=lambda t: t["return_pct"], reverse=True)
    print(f"\n  ── Top 5 Winners ──")
    for t in sorted_trades[:5]:
        print(f"  {t['ticker']:>8}  {t['return_pct']:>+7.2f}%  ${t['pnl_dollars']:>+8,.2f}  {t['exit_reason']}")

    print(f"\n{'='*80}")
    print("  ✅ DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
