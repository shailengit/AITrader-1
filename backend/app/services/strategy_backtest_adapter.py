"""Backtesting adapter for Strategy ABC subclasses.

Takes any Strategy subclass (the same interface used by alpaca_runner)
and runs it through a daily simulation loop, producing the same KPI
output format as the existing StrategyEngine. This lets Claude Code
generate Strategy subclasses that can be both backtested in the app
AND deployed to Alpaca — no translation layer needed.

Usage:
    from app.services.strategies.daily_golden_cross import DailyGoldenCrossRotation
    adapter = StrategyBacktestAdapter(DailyGoldenCrossRotation())
    result = adapter.run(as_of="2020-01-01", end="2026-07-08", capital=100_000)
    # result == {"trades": [...], "daily_equity": [...], "summary": {...}}
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db.database import engine as db_engine
from app.services.strategy_base import Strategy, Signal, ExitCheck

logger = logging.getLogger(__name__)


class StrategyBacktestAdapter:
    """Runs a daily backtest simulation for any Strategy ABC subclass.

    The adapter handles the daily loop, portfolio state, position sizing,
    trade logging, and KPI computation — everything that doesn't change
    between strategies. The Strategy answers only two questions:
      1. What should I buy/sell?  (get_signals)
      2. When should I exit?      (should_exit)
    """

    def __init__(self, strategy: Strategy):
        self.strategy = strategy
        # Cache for get_signals results: date_str -> List[Signal]
        self._signals_cache: Dict[str, List[Signal]] = {}
        self._last_signal_date: Optional[str] = None

    def run(
        self,
        as_of: str = "2020-01-01",
        end: str = "2026-07-08",
        capital: float = 100_000.0,
        max_holdings: Optional[int] = None,
        min_hold_days: int = 7,
        trailing_stop: float = 0.20,
        take_profit: float = 0.30,
        time_stop_days: int = 60,
        max_sector_count: int = 2,
    ) -> Dict[str, Any]:
        """Run the daily simulation. Returns trades, daily_equity, summary."""
        from collections import OrderedDict

        cfg_max_holdings = max_holdings or self.strategy.max_holdings

        # ── 1. Build trading calendar from SPY ──────────────────────────
        with db_engine.connect() as conn:
            spy_dates = pd.read_sql(
                f'SELECT "Date" FROM spy '
                f'WHERE "Date" >= \'{as_of}\' AND "Date" <= \'{end}\' '
                f'ORDER BY "Date"',
                conn,
            )
        all_dates = [str(d)[:10] for d in spy_dates["Date"]]
        if not all_dates:
            logger.warning("No SPY trading dates in range %s to %s", as_of, end)
            return {"trades": [], "daily_equity": [], "summary": _empty_summary(capital)}

        # ── 2. Pre-fetch price cache for all tickers ─────────────────────
        logger.info("Building price cache for %d dates...", len(all_dates))
        with db_engine.connect() as conn:
            res = conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            skip = {
                "stock_metadata", "stock_financials_quarterly",
                "stock_financials_yearly",
                "xlb", "xlc", "xle", "xlf", "xli", "xlk", "xlp",
                "xlre", "xlu", "xlv", "xly",
            }
            all_tickers = [row[0] for row in res if row[0] not in skip]

        # Cache: ticker -> {date_str -> close_price}
        price_cache: Dict[str, Dict[str, float]] = {}
        for ticker in all_tickers:
            try:
                from app.utils.security import get_safe_table_name
                safe = get_safe_table_name(ticker)
                with db_engine.connect() as conn:
                    df = pd.read_sql(
                        f'SELECT "Date", "Close" FROM "{safe}" '
                        f'WHERE "Date" >= \'{as_of}\' AND "Date" <= \'{end}\' '
                        f'ORDER BY "Date"',
                        conn,
                    )
                cache: Dict[str, float] = {}
                for _, row in df.iterrows():
                    cache[str(pd.Timestamp(row["Date"]))[:10]] = float(row["Close"])
                price_cache[ticker] = cache
            except Exception:
                continue

        def get_price(ticker: str, date_str: str) -> float:
            tc = price_cache.get(ticker.lower(), {})
            if not tc:
                return 0.0
            # Find the closest date <= date_str
            if date_str in tc:
                return tc[date_str]
            # Walk backwards to find the most recent price
            d = pd.Timestamp(date_str)
            for _ in range(10):
                d -= pd.Timedelta(days=1)
                ds = d.strftime("%Y-%m-%d")
                if ds in tc:
                    return tc[ds]
            return 0.0

        # ── 3. Daily simulation loop ────────────────────────────────────
        holdings: Dict[str, Any] = OrderedDict()
        trades: List[Dict[str, Any]] = []
        daily_equity: List[Dict[str, Any]] = []
        cash = capital
        portfolio_value = capital
        last_signal_date = ""

        for sim_idx, current_date in enumerate(all_dates):
            # ── 3a. Check exits ─────────────────────────────────────────
            to_remove: List[str] = []
            for ticker in list(holdings.keys()):
                h = holdings[ticker]
                current_price = get_price(ticker, current_date)
                if current_price <= 0:
                    continue

                h["peak_price"] = max(h["peak_price"], current_price)
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])

                reason: Optional[str] = None

                # Hard stop loss (overrides min hold)
                if ret <= -0.10:
                    reason = "Stop Loss"

                # Trailing stop
                if reason is None and trailing_stop > 0:
                    peak = h["peak_price"]
                    drawdown = (peak - current_price) / peak
                    if drawdown >= trailing_stop:
                        reason = "Trailing Stop"

                # Take profit
                if reason is None and take_profit > 0:
                    if ret >= take_profit:
                        reason = "Take Profit"

                # Time stop
                if reason is None and time_stop_days > 0:
                    hold_days = (
                        pd.Timestamp(current_date) -
                        pd.Timestamp(h["entry_date"])
                    ).days
                    if hold_days >= time_stop_days:
                        reason = "Time Stop"

                # Strategy-specific exit check
                if reason is None:
                    try:
                        exit_check = self.strategy.should_exit(
                            ticker, current_date, db_engine, "long"
                        )
                        if exit_check.should_close:
                            reason = exit_check.reason
                    except Exception as e:
                        logger.warning("should_exit failed for %s: %s", ticker, e)

                if reason is not None:
                    trades.append({
                        "ticker": ticker, "side": "SELL",
                        "entry_date": h["entry_date"],
                        "exit_date": current_date,
                        "entry_price": round(h["entry_price"], 2),
                        "exit_price": round(current_price, 2),
                        "return_pct": round(ret * 100, 2),
                        "holding_days": (
                            pd.Timestamp(current_date) -
                            pd.Timestamp(h["entry_date"])
                        ).days,
                        "exit_reason": reason,
                        "pnl_dollars": round(pnl, 2),
                    })
                    cash += h["shares"] * current_price
                    to_remove.append(ticker)

            for t in to_remove:
                del holdings[t]

            # ── 3b. Get signals (cached, reuse for 5 days) ─────────────
            signals: List[Signal] = []
            slots = cfg_max_holdings - len(holdings)
            if slots > 0:
                # Reuse cached signals for up to 5 days to avoid re-scanning
                # all 1500 stocks on every trading day. Golden crosses persist
                # until a death cross, so 5-day-old signals are still valid.
                use_cache = (
                    self._last_signal_date is not None
                    and self._signals_cache
                    and self._last_signal_date in self._signals_cache
                )
                if use_cache:
                    # Check if last signal date is within 5 trading days
                    last_dt = pd.Timestamp(self._last_signal_date)
                    cur_dt = pd.Timestamp(current_date)
                    if (cur_dt - last_dt).days <= 7:
                        signals = self._signals_cache.get(self._last_signal_date, [])
                if not use_cache or not signals:
                    try:
                        signals = self.strategy.get_signals(current_date, db_engine)
                        self._signals_cache[current_date] = signals
                        if signals:
                            self._last_signal_date = current_date
                    except Exception as e:
                        logger.warning("get_signals failed for %s: %s", current_date, e)

            signal_tickers = {s.ticker for s in signals}

            # ── 3c. Rotate out positions not in signals ────────────────
            if signals:
                to_drop = []
                for ticker in list(holdings.keys()):
                    if ticker not in signal_tickers:
                        h = holdings[ticker]
                        hold_days = (
                            pd.Timestamp(current_date) -
                            pd.Timestamp(h["entry_date"])
                        ).days
                        if hold_days < min_hold_days:
                            continue
                        to_drop.append(ticker)

                for ticker in to_drop:
                    h = holdings[ticker]
                    current_price = get_price(ticker, current_date)
                    if current_price > 0:
                        ret = (current_price - h["entry_price"]) / h["entry_price"]
                        pnl = h["shares"] * (current_price - h["entry_price"])
                        hold_days = (
                            pd.Timestamp(current_date) -
                            pd.Timestamp(h["entry_date"])
                        ).days
                        trades.append({
                            "ticker": ticker, "side": "SELL",
                            "entry_date": h["entry_date"],
                            "exit_date": current_date,
                            "entry_price": round(h["entry_price"], 2),
                            "exit_price": round(current_price, 2),
                            "return_pct": round(ret * 100, 2),
                            "holding_days": hold_days,
                            "exit_reason": "Rotated Out",
                            "pnl_dollars": round(pnl, 2),
                        })
                        cash += h["shares"] * current_price
                    del holdings[ticker]

            # ── 3d. Open new positions ─────────────────────────────────
            slots_available = cfg_max_holdings - len(holdings)
            if slots_available > 0 and signals:
                sector_counts: Dict[str, int] = {}
                for t, h in holdings.items():
                    sec = h.get("sector", "Unknown")
                    sector_counts[sec] = sector_counts.get(sec, 0) + 1

                new_entries = []
                for s in signals:
                    if len(new_entries) >= slots_available:
                        break
                    if s.ticker in holdings:
                        continue
                    sec = getattr(s, "sector", "Unknown")
                    if sector_counts.get(sec, 0) >= max_sector_count:
                        continue
                    new_entries.append(s)
                    sector_counts[sec] = sector_counts.get(sec, 0) + 1

                total_score = sum(s.score for s in new_entries if s.score > 0)
                if total_score > 0:
                    for s in new_entries:
                        price = s.price if s.price > 0 else get_price(s.ticker, current_date)
                        if price <= 0:
                            continue
                        weight = s.score / total_score
                        target_value = portfolio_value * weight
                        shares = int(target_value / price)
                        cost = shares * price
                        if cost > cash:
                            shares = int(cash / price)
                            cost = shares * price
                        if shares <= 0:
                            continue
                        cash -= cost
                        holdings[s.ticker] = {
                            "entry_date": current_date,
                            "entry_price": price,
                            "peak_price": price,
                            "shares": shares,
                            "score": s.score,
                            "angle": getattr(s, "angle", 0),
                            "market_cap": 0,
                            "sector": getattr(s, "sector", "Unknown"),
                        }
                        trades.append({
                            "ticker": s.ticker, "side": "BUY",
                            "entry_date": current_date, "exit_date": "",
                            "entry_price": round(price, 2), "exit_price": 0,
                            "return_pct": 0.0, "holding_days": 0,
                            "exit_reason": "New Entry", "pnl_dollars": 0.0,
                        })

            # ── 3e. Track daily equity ──────────────────────────────────
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

        # ── 3. Summary KPIs ─────────────────────────────────────────────
        summary = _compute_summary(trades, daily_equity, capital, as_of, end)
        return {"trades": trades, "daily_equity": daily_equity, "summary": summary}


def _compute_summary(
    trades: List[Dict[str, Any]],
    daily_equity: List[Dict[str, Any]],
    capital: float,
    as_of: str,
    end: str,
) -> Dict[str, Any]:
    """Compute KPIs from trades and equity curve. Same format as StrategyEngine."""
    if not daily_equity:
        return _empty_summary(capital)

    portfolio_value = daily_equity[-1]["value"]
    total_pnl = portfolio_value - capital
    total_ret = total_pnl / capital * 100
    sell_trades = [t for t in trades if t["side"] == "SELL"]
    winners = [t for t in sell_trades if t["pnl_dollars"] > 0]
    losers = [t for t in sell_trades if t["pnl_dollars"] <= 0]
    win_rate = len(winners) / len(sell_trades) * 100 if sell_trades else 0
    avg_win = float(np.mean([t["pnl_dollars"] for t in winners])) if winners else 0
    avg_loss = float(np.mean([t["pnl_dollars"] for t in losers])) if losers else 0
    gross_profit = sum(t["pnl_dollars"] for t in winners)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losers))
    profit_factor = gross_profit / (gross_loss + 1e-9) if gross_loss > 0 else 0.0

    reasons: Dict[str, int] = {}
    for t in sell_trades:
        r = t["exit_reason"].split("(")[0].strip()
        reasons[r] = reasons.get(r, 0) + 1

    # SPY benchmark
    spy_ret = 0.0
    try:
        with db_engine.connect() as conn:
            spy_df = pd.read_sql(
                f'SELECT "Date", "Close" FROM spy '
                f'WHERE "Date" >= \'{as_of}\' AND "Date" <= \'{end}\' '
                f'ORDER BY "Date"',
                conn,
            )
        if not spy_df.empty:
            spy_ret = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100
    except Exception:
        pass

    years = (
        datetime.strptime(end, "%Y-%m-%d") -
        datetime.strptime(as_of, "%Y-%m-%d")
    ).days / 365.25
    cagr = ((portfolio_value / capital) ** (1 / max(years, 0.01)) - 1) * 100

    # Annualized Sharpe
    sharpe = 0.0
    max_dd = 0.0
    if len(daily_equity) > 1:
        eq_vals = np.array([d["value"] for d in daily_equity], dtype=float)
        daily_rets = np.diff(eq_vals) / eq_vals[:-1]
        if np.std(daily_rets) > 0 and len(daily_rets) > 0:
            sharpe = float(np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252))
        peak = eq_vals[0]
        for v in eq_vals:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    max_dd_pct = round(max_dd * 100, 2)

    def _json_safe(val: float) -> float:
        if np.isinf(val) or np.isnan(val):
            return 0.0
        return float(val)

    sell_trades_sorted = sorted(
        sell_trades, key=lambda t: t.get("pnl_dollars", 0), reverse=True
    )
    top_winners = sell_trades_sorted[:5]
    top_losers = (
        sell_trades_sorted[-5:]
        if len(sell_trades_sorted) >= 5
        else sell_trades_sorted[::-1]
    )

    return {
        "initial_capital": capital,
        "final_portfolio": portfolio_value,
        "total_return_pct": _json_safe(round(total_ret, 2)),
        "cagr_pct": _json_safe(round(cagr, 2)),
        "sharpe_ratio": _json_safe(round(sharpe, 2)),
        "max_drawdown_pct": _json_safe(max_dd_pct),
        "total_trades": len(sell_trades),
        "win_rate": _json_safe(round(win_rate, 1)),
        "profit_factor": _json_safe(round(profit_factor, 2)),
        "avg_winner": _json_safe(round(avg_win, 2)),
        "avg_loser": _json_safe(round(avg_loss, 2)),
        "exit_reasons": reasons,
        "spy_return_pct": _json_safe(round(spy_ret, 2)),
        "alpha_pct": _json_safe(round(total_ret - spy_ret, 2)),
        "top_winners": [
            {"ticker": t.get("ticker", ""), "return_pct": t.get("return_pct", 0),
             "pnl_dollars": t.get("pnl_dollars", 0),
             "exit_reason": t.get("exit_reason", "")}
            for t in top_winners
        ],
        "top_losers": [
            {"ticker": t.get("ticker", ""), "return_pct": t.get("return_pct", 0),
             "pnl_dollars": t.get("pnl_dollars", 0),
             "exit_reason": t.get("exit_reason", "")}
            for t in top_losers
        ],
    }


def _empty_summary(capital: float) -> Dict[str, Any]:
    return {
        "initial_capital": capital,
        "final_portfolio": capital,
        "total_return_pct": 0.0,
        "cagr_pct": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown_pct": 0.0,
        "total_trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "avg_winner": 0.0,
        "avg_loser": 0.0,
        "exit_reasons": {},
        "spy_return_pct": 0.0,
        "alpha_pct": 0.0,
        "top_winners": [],
        "top_losers": [],
    }
