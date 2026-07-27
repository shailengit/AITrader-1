"""
SMA50/200 Golden Cross — Volume Surge Strategy
================================================
Two-phase pipeline:
  Phase 1: Screen for SMA50/200 golden cross + volume surge (1.5× 50-day avg)
  Phase 2: Trade top 5 with score-weighted sizing, exit on death cross /
           trailing stop / take profit / time stop

Screening:
  - SMA50 crosses above SMA200 on the as-of-date
  - Average volume over last 5 days > 1.5× 50-day rolling average volume
  - Score: 60% SMA crossover angle + 40% market cap

Trading:
  - Top 5, score-weighted sizing (30/25/20/15/10%)
  - Exit: death cross, 20% trailing stop, 20% take profit, 45-day time stop
  - Min hold days: 10

Usage (standalone backtest):
  cd backend && ./venv/bin/python ../strategies/sma50_200_golden_cross.py

Usage (Alpaca live trading):
  from app.services.strategies.sma50_200_golden_cross import SMA50_200GoldenCross
  runner = StrategyRunner(SMA50_200GoldenCross())
  result = runner.run_daily()
"""

import os
import sys
import warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import OrderedDict
from typing import List, Dict, Any, Optional, Tuple

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

# ── Configuration ──────────────────────────────────────────────────────────
AS_OF = "2020-01-01"
END = "2026-07-17"
CAPITAL = 100_000.0
MAX_HOLDINGS = 5
TOP_N = 5

# Screening parameters
ANGLE_WEIGHT = 0.60
CAP_WEIGHT = 0.40
VOLUME_MULTIPLIER = 1.5
VOLUME_LOOKBACK = 5
VOLUME_MA_PERIOD = 50

# Trading parameters
TRAILING_STOP = 0.20
TAKE_PROFIT = 0.20
TIME_STOP_DAYS = 45
MIN_HOLD_DAYS = 10
SIZING_PCTS = [0.30, 0.25, 0.20, 0.15, 0.10]

# ── Pluggable Strategy (for Alpaca Runner) ─────────────────────────────────
from app.services.strategy_base import Strategy, Signal, ExitCheck, get_all_tickers
from sqlalchemy import Engine, text


class SMA50_200GoldenCross(Strategy):
    """SMA50/200 golden cross with volume surge confirmation."""

    def get_name(self) -> str:
        return "SMA50/200 Golden Cross + Volume Surge"

    @property
    def max_holdings(self) -> int:
        return MAX_HOLDINGS

    @property
    def sizing_pcts(self) -> List[float]:
        return SIZING_PCTS

    # ── Signal Generation ──────────────────────────────────────────────

    def get_signals(self, as_of_date: str, engine: Engine) -> List[Signal]:
        """Phase 1: Screen for SMA50/200 golden cross + volume surge."""
        from app.utils.security import get_safe_table_name

        tickers = get_all_tickers(engine)
        candidates: List[Signal] = []

        for ticker in tickers:
            try:
                safe = get_safe_table_name(ticker)
            except ValueError:
                continue

            try:
                with engine.connect() as conn:
                    df = pd.read_sql(
                        f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" FROM "{safe}" '
                        f'WHERE "Date" <= \'{as_of_date}\' ORDER BY "Date" DESC LIMIT 300',
                        conn,
                    )
            except Exception:
                continue

            if df.empty or len(df) < 250:
                continue

            df = df.sort_values("Date").reset_index(drop=True)
            close = df["Close"]
            volume = df["Volume"]

            # SMA50 and SMA200
            sma50 = close.rolling(window=50).mean()
            sma200 = close.rolling(window=200).mean()

            # Volume MA
            vol_ma50 = volume.rolling(window=VOLUME_MA_PERIOD).mean()

            # Check SMA50/200 golden cross on the most recent trading day
            i = len(df) - 1
            if not (pd.notna(sma50.iloc[i]) and pd.notna(sma200.iloc[i]) and
                    pd.notna(sma50.iloc[i - 1]) and pd.notna(sma200.iloc[i - 1])):
                continue

            if not (sma50.iloc[i - 1] <= sma200.iloc[i - 1] and sma50.iloc[i] > sma200.iloc[i]):
                continue

            # Volume surge check: average volume over last N days > multiplier × 50-day avg
            if i < VOLUME_LOOKBACK:
                continue

            avg_vol_last_n = volume.iloc[i - VOLUME_LOOKBACK + 1:i + 1].mean()
            if pd.isna(avg_vol_last_n) or pd.isna(vol_ma50.iloc[i]) or vol_ma50.iloc[i] <= 0:
                continue
            if avg_vol_last_n <= vol_ma50.iloc[i] * VOLUME_MULTIPLIER:
                continue

            # Compute crossover angle
            angle = self._compute_crossover_angle(close, sma50, sma200, i)

            # Market cap for scoring
            mc = 0.0
            try:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT market_cap FROM stock_metadata WHERE ticker = :t"),
                        {"t": ticker.upper()},
                    ).fetchone()
                if row and row[0] is not None:
                    mc = float(row[0])
            except Exception:
                pass

            angle_norm = 1 / (1 + np.exp(-angle * 100))
            cap_norm = min(1.0, mc / 100e9)
            score = ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm

            candidates.append(Signal(
                ticker=ticker.upper(),
                side="long",
                score=round(score, 4),
                angle=round(angle, 4),
                price=float(close.iloc[i]),
                entry_date=str(df["Date"].iloc[i])[:10],
                entry_type="GC",
            ))

        candidates.sort(key=lambda s: s.score, reverse=True)
        return candidates[:MAX_HOLDINGS]

    # ── Exit Logic ────────────────────────────────────────────────────

    def should_exit(self, ticker: str, as_of_date: str,
                    engine: Engine, side: str = "long") -> ExitCheck:
        """Phase 2 exit check: death cross, trailing stop, take profit, time stop.

        Note: trailing stop, take profit, and time stop are handled by the
        runner's bracket orders and MIN_HOLD_DAYS logic. This method checks
        for death cross (SMA50 < SMA200) as the strategy-specific exit.
        """
        if side != "long":
            return ExitCheck()

        try:
            from app.utils.security import get_safe_table_name
            safe = get_safe_table_name(ticker)
            with engine.connect() as conn:
                df = pd.read_sql(
                    f'SELECT "Date", "Close" FROM "{safe}" '
                    f'WHERE "Date" <= \'{as_of_date}\' ORDER BY "Date" DESC LIMIT 250',
                    conn,
                )
            if df.empty or len(df) < 50:
                return ExitCheck()
            df = df.sort_values("Date").reset_index(drop=True)
            sma50 = df["Close"].rolling(window=50).mean()
            sma200 = df["Close"].rolling(window=200).mean()
            if pd.notna(sma50.iloc[-1]) and pd.notna(sma200.iloc[-1]):
                if sma50.iloc[-1] < sma200.iloc[-1]:
                    return ExitCheck(should_close=True, reason="Death Cross (SMA50<200)")
        except Exception:
            pass
        return ExitCheck()

    # ── Internal Helpers ──────────────────────────────────────────────

    @staticmethod
    def _compute_crossover_angle(close, sma50, sma200, cross_idx):
        """Compute the angle between SMA50 and SMA200 at crossover.

        Uses the rate of change of the spread over lookback*2 bars
        centered on the crossover. Falls back to the spread itself
        when future data is unavailable (latest bar).
        """
        lookback = 3
        if cross_idx < lookback:
            return 0.0

        end = min(cross_idx + lookback, len(close) - 1)
        start = max(0, cross_idx - lookback)

        if end == start:
            return 0.0

        spread_before = (sma50.iloc[start] - sma200.iloc[start])
        spread_after = (sma50.iloc[end] - sma200.iloc[end])
        angle = (spread_after - spread_before) / (end - start)
        return float(angle) if pd.notna(angle) else 0.0


# ── Standalone Backtest ────────────────────────────────────────────────────

def compute_sma_crossover_angle(close, sma50, sma200, cross_idx):
    """Standalone version of crossover angle computation."""
    lookback = 3
    if cross_idx < lookback:
        return 0.0
    end = min(cross_idx + lookback, len(close) - 1)
    start = max(0, cross_idx - lookback)
    if end == start:
        return 0.0
    spread_before = (sma50.iloc[start] - sma200.iloc[start])
    spread_after = (sma50.iloc[end] - sma200.iloc[end])
    angle = (spread_after - spread_before) / (end - start)
    return float(angle) if pd.notna(angle) else 0.0


def precompute_stock_data(tickers: list, start: str, end: str) -> dict:
    """Pre-compute SMA50, SMA200, crossover dates, and angles for all stocks."""
    from app.db.database import engine
    from app.utils.security import get_safe_table_name
    from sqlalchemy import text

    print(f"\n📥 Pre-computing data for {len(tickers)} stocks...")
    stock_data = {}

    for idx, ticker in enumerate(tickers):
        if (idx + 1) % 200 == 0:
            print(f"  Progress: {idx+1}/{len(tickers)}")

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
        volume = df["Volume"]
        sma50 = close.rolling(window=50).mean()
        sma200 = close.rolling(window=200).mean()
        vol_ma50 = volume.rolling(window=50).mean()

        # Find all SMA50/200 golden crossovers
        crossovers = []
        for i in range(1, len(df)):
            if (pd.notna(sma50.iloc[i]) and pd.notna(sma200.iloc[i]) and
                    pd.notna(sma50.iloc[i - 1]) and pd.notna(sma200.iloc[i - 1])):

                # Golden cross: SMA50 crosses above SMA200
                if sma50.iloc[i - 1] <= sma200.iloc[i - 1] and sma50.iloc[i] > sma200.iloc[i]:
                    # Volume surge check
                    if i >= 5:
                        avg_vol_5d = volume.iloc[i - 4:i + 1].mean()
                        if pd.notna(avg_vol_5d) and pd.notna(vol_ma50.iloc[i]) and vol_ma50.iloc[i] > 0:
                            if avg_vol_5d > vol_ma50.iloc[i] * VOLUME_MULTIPLIER:
                                angle = compute_sma_crossover_angle(close, sma50, sma200, i)
                                crossovers.append({
                                    "date": str(df["Date"].iloc[i])[:10],
                                    "price": float(close.iloc[i]),
                                    "angle": angle,
                                })

                # Death cross: SMA50 crosses below SMA200
                elif sma50.iloc[i - 1] >= sma200.iloc[i - 1] and sma50.iloc[i] < sma200.iloc[i]:
                    crossovers.append({
                        "date": str(df["Date"].iloc[i])[:10],
                        "price": float(close.iloc[i]),
                        "angle": 0.0,
                        "death_cross": True,
                    })

        if crossovers:
            mc = 0.0
            try:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT market_cap FROM stock_metadata WHERE ticker = :t"),
                        {"t": ticker.upper()},
                    ).fetchone()
                if row and row[0] is not None:
                    mc = float(row[0])
            except Exception:
                pass

            stock_data[ticker.upper()] = {
                "close": close.values,
                "dates": df["Date"].values,
                "sma50": sma50.values,
                "sma200": sma200.values,
                "crossovers": crossovers,
                "market_cap": mc,
            }

    print(f"  Done. {len(stock_data)} stocks with crossover data.")
    return stock_data


def main():
    from app.services.data_service import get_data
    from app.db.database import engine
    from sqlalchemy import text

    print("=" * 80)
    print("  SMA50/200 GOLDEN CROSS + VOLUME SURGE STRATEGY")
    print("=" * 80)
    print(f"  Period:         {AS_OF} → {END}")
    print(f"  Capital:        ${CAPITAL:,.2f}")
    print(f"  Holdings:       Top {MAX_HOLDINGS} (rotate daily)")
    print(f"  Ranking:        {ANGLE_WEIGHT*100:.0f}% angle + {CAP_WEIGHT*100:.0f}% market cap")
    print(f"  Volume surge:   {VOLUME_MULTIPLIER:.1f}× 50-day avg (last {VOLUME_LOOKBACK}d)")
    print(f"  Trailing stop:  {TRAILING_STOP:.0%}")
    print(f"  Take profit:    {TAKE_PROFIT:.0%}")
    print(f"  Time stop:      {TIME_STOP_DAYS}d")
    print(f"  Min hold:       {MIN_HOLD_DAYS}d")
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
    stock_db = precompute_stock_data(all_tickers, "2018-01-01", END)

    # ── Build crossover index ───────────────────────────────────────────────
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
                })

    print(f"  {len(daily_crossovers)} days with new golden crosses")
    print(f"  {sum(len(v) for v in daily_crossovers.values())} total crossover events")

    # ── Daily rotation simulation ───────────────────────────────────────────
    print(f"\n📈 Running daily rotation simulation...")

    all_dates = sorted(daily_crossovers.keys())
    print(f"  {len(all_dates)} trading days to simulate")

    # Portfolio state
    holdings = OrderedDict()
    trades = []
    daily_equity = []

    # Pre-compute market cap normalization
    all_market_caps = [v["market_cap"] for v in stock_db.values() if v["market_cap"] > 0]
    cap_max = max(all_market_caps) if all_market_caps else 1
    cap_min = min(all_market_caps) if all_market_caps else 0
    cap_range = cap_max - cap_min if cap_max > cap_min else 1

    def compute_score(angle: float, market_cap: float) -> float:
        angle_norm = 1 / (1 + np.exp(-angle * 100))
        cap_norm = (market_cap - cap_min) / cap_range if cap_range > 0 else 0.5
        return ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm

    def get_price(ticker: str, date_str: str) -> float:
        data = stock_db.get(ticker)
        if data is None:
            return 0.0
        dates = data["dates"]
        close = data["close"]
        target = pd.Timestamp(date_str)
        for i in range(len(dates) - 1, -1, -1):
            if pd.Timestamp(dates[i]) <= target:
                return float(close[i])
        return 0.0

    def has_death_cross(ticker: str, date_str: str) -> bool:
        dc_dates = daily_death_crosses.get(ticker, [])
        return any(d <= date_str for d in dc_dates)

    cash = CAPITAL
    portfolio_value = CAPITAL

    for sim_idx, current_date in enumerate(all_dates):
        if (sim_idx + 1) % 100 == 0:
            print(f"  Progress: {sim_idx+1}/{len(all_dates)} days  "
                  f"Portfolio: ${portfolio_value:>8,.2f}  "
                  f"Holdings: {len(holdings)}")

        # ── 1. Check exits for current holdings ────────────────────────────
        to_remove = []
        for ticker in list(holdings.keys()):
            h = holdings[ticker]
            current_price = get_price(ticker, current_date)
            if current_price <= 0:
                continue

            # Update peak for trailing stop
            h["peak_price"] = max(h["peak_price"], current_price)

            # Check death cross
            if has_death_cross(ticker, current_date):
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "entry_price": round(h["entry_price"], 2),
                    "exit_price": round(current_price, 2),
                    "return_pct": round(ret * 100, 2),
                    "holding_days": (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days,
                    "exit_reason": "Death Cross",
                    "pnl_dollars": round(pnl, 2),
                })
                cash += h["shares"] * current_price
                to_remove.append(ticker)
                continue

            # Check trailing stop
            dd = (h["peak_price"] - current_price) / h["peak_price"]
            if dd >= TRAILING_STOP:
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "entry_price": round(h["entry_price"], 2),
                    "exit_price": round(current_price, 2),
                    "return_pct": round(ret * 100, 2),
                    "holding_days": (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days,
                    "exit_reason": f"Trailing Stop ({dd:.1%})",
                    "pnl_dollars": round(pnl, 2),
                })
                cash += h["shares"] * current_price
                to_remove.append(ticker)
                continue

            # Check take profit
            gain = (current_price - h["entry_price"]) / h["entry_price"]
            if gain >= TAKE_PROFIT:
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "entry_price": round(h["entry_price"], 2),
                    "exit_price": round(current_price, 2),
                    "return_pct": round(gain * 100, 2),
                    "holding_days": (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days,
                    "exit_reason": f"Take Profit ({gain:.1%})",
                    "pnl_dollars": round(pnl, 2),
                })
                cash += h["shares"] * current_price
                to_remove.append(ticker)
                continue

            # Check time stop
            hold_days = (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days
            if hold_days >= TIME_STOP_DAYS:
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "entry_price": round(h["entry_price"], 2),
                    "exit_price": round(current_price, 2),
                    "return_pct": round(ret * 100, 2),
                    "holding_days": hold_days,
                    "exit_reason": f"Time Stop ({hold_days}d)",
                    "pnl_dollars": round(pnl, 2),
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

        # ── 3. Merge holdings + new candidates, rank, keep top 5 ────────────
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

        # ── 4. Sell dropped holdings (with min hold days check) ─────────────
        to_drop = [t for t in holdings if t not in top5_tickers]
        for ticker in to_drop:
            h = holdings[ticker]
            hold_days = (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days

            # Enforce minimum hold days
            if hold_days < MIN_HOLD_DAYS:
                continue

            current_price = get_price(ticker, current_date)
            if current_price > 0:
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])
                trades.append({
                    "ticker": ticker, "side": "SELL",
                    "entry_date": h["entry_date"], "exit_date": current_date,
                    "entry_price": round(h["entry_price"], 2),
                    "exit_price": round(current_price, 2),
                    "return_pct": round(ret * 100, 2),
                    "holding_days": hold_days,
                    "exit_reason": "Rotated Out",
                    "pnl_dollars": round(pnl, 2),
                })
                cash += h["shares"] * current_price
            del holdings[ticker]

        # ── 5. Buy new top 5 stocks ─────────────────────────────────────────
        target_value = portfolio_value / MAX_HOLDINGS

        for s in top5:
            if s["ticker"] not in holdings:
                price = s.get("price", get_price(s["ticker"], current_date))
                if price <= 0:
                    continue
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
                    "angle": s.get("angle", 0),
                    "market_cap": s.get("market_cap", 0),
                }
                trades.append({
                    "ticker": s["ticker"], "side": "BUY",
                    "entry_date": current_date, "exit_date": "",
                    "entry_price": round(price, 2), "exit_price": 0,
                    "return_pct": 0.0, "holding_days": 0,
                    "exit_reason": "New Entry",
                    "pnl_dollars": 0.0,
                })

        # ── 6. Track daily portfolio value ──────────────────────────────────
        holdings_value = 0.0
        for ticker, h in holdings.items():
            price = get_price(ticker, current_date)
            if price > 0:
                holdings_value += h["shares"] * price

        portfolio_value = cash + holdings_value
        daily_equity.append({
            "date": current_date,
            "value": round(portfolio_value, 2),
            "cash": round(cash, 2),
            "holdings": round(holdings_value, 2),
            "n_holdings": len(holdings),
        })

    # ── Portfolio Summary ──────────────────────────────────────────────────
    total_pnl = portfolio_value - CAPITAL
    total_ret = total_pnl / CAPITAL * 100

    print(f"\n{'='*80}")
    print("  PORTFOLIO SUMMARY")
    print("=" * 80)
    print(f"  Initial Capital:  ${CAPITAL:>10,.2f}")
    print(f"  Final Portfolio:  ${portfolio_value:>10,.2f}")
    print(f"  Total P&L:        ${total_pnl:>+10,.2f}")
    print(f"  Total Return:     {total_ret:>+8.2f}%")

    # SPY benchmark
    spy_df = get_data("SPY", start_date=AS_OF, end_date=END, frequency="daily")
    if spy_df is not None and not spy_df.empty:
        if "Date" not in spy_df.columns and spy_df.index.name == "Date":
            spy_df = spy_df.reset_index()
        spy_ret = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100
        alpha = total_ret - spy_ret
        print(f"  SPY Return:       {spy_ret:>+8.2f}%")
        print(f"  Alpha:            {alpha:>+8.2f}%  {'✅' if alpha > 0 else '❌'}")

    # Trade stats
    buy_trades = [t for t in trades if t["side"] == "BUY"]
    sell_trades = [t for t in trades if t["side"] == "SELL"]
    winners = [t for t in sell_trades if t["pnl_dollars"] > 0]
    losers = [t for t in sell_trades if t["pnl_dollars"] <= 0]
    win_rate = len(winners) / len(sell_trades) * 100 if sell_trades else 0
    avg_win = np.mean([t["pnl_dollars"] for t in winners]) if winners else 0
    avg_loss = np.mean([t["pnl_dollars"] for t in losers]) if losers else 0
    gross_profit = sum(t["pnl_dollars"] for t in winners)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losers))
    profit_factor = gross_profit / (gross_loss + 1e-9)

    print(f"\n  ── Trade Statistics ──")
    print(f"  Total Trades:     {len(sell_trades)}")
    print(f"  Winners:          {len(winners)} ({win_rate:.0f}%)")
    print(f"  Losers:           {len(losers)} ({100-win_rate:.0f}%)")
    print(f"  Avg Winner:       ${avg_win:>+8,.2f}")
    print(f"  Avg Loser:        ${avg_loss:>+8,.2f}")
    print(f"  Profit Factor:    {profit_factor:.2f}")

    # Exit reason breakdown
    print(f"\n  ── Exit Reasons ──")
    reasons = {}
    for t in sell_trades:
        r = t["exit_reason"].split("(")[0].strip()
        reasons[r] = reasons.get(r, 0) + 1
    for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {r:>20}: {c} trades")

    # Top/bottom trades
    if sell_trades:
        sorted_trades = sorted(sell_trades, key=lambda t: t["return_pct"], reverse=True)
        print(f"\n  ── Top 5 Winners ──")
        for t in sorted_trades[:5]:
            print(f"  {t['ticker']:>8}  {t['return_pct']:>+7.2f}%  ${t['pnl_dollars']:>+8,.2f}  "
                  f"{t['holding_days']}d  {t['exit_reason']}")

        print(f"\n  ── Bottom 5 Losers ──")
        for t in sorted_trades[-5:]:
            print(f"  {t['ticker']:>8}  {t['return_pct']:>+7.2f}%  ${t['pnl_dollars']:>+8,.2f}  "
                  f"{t['holding_days']}d  {t['exit_reason']}")

    # Monthly returns
    if daily_equity:
        eq_df = pd.DataFrame(daily_equity)
        eq_df["date"] = pd.to_datetime(eq_df["date"])
        eq_df = eq_df.set_index("date")
        monthly = eq_df["value"].resample("ME").last()
        monthly_ret = monthly.pct_change().dropna() * 100
        print(f"\n  ── Monthly Stats ──")
        print(f"  Best Month:       {monthly_ret.max():>+7.2f}%")
        print(f"  Worst Month:      {monthly_ret.min():>+7.2f}%")
        print(f"  Avg Month:        {monthly_ret.mean():>+7.2f}%")
        print(f"  Positive Months:  {(monthly_ret > 0).sum()}/{len(monthly_ret)} ({(monthly_ret > 0).mean()*100:.0f}%)")

    print(f"\n{'='*80}")
    print("  ✅ DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
