"""Portfolio simulator — I/O orchestrator that wires sizing + exit engine
over the existing PortfolioTracker and wfo_metrics.

This file is built up across Tasks 5–7. Task 5 adds the per-ticker
`run_one` wrapper. Task 6 adds the multi-ticker `run` aggregator and
equity-curve construction. Task 7 adds the SPY alpha helper and the
final response shaping.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from datetime import timedelta
import logging

import numpy as np
import pandas as pd

from app.services.backtest.exit_engine import (
    ExitConfig,
    TradeResult,
    simulate_position,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-ticker wrapper
# ---------------------------------------------------------------------------

def run_one(
    ticker: str,
    bars: pd.DataFrame,
    entry_price: float,
    dollars: float,
    config: ExitConfig,
) -> TradeResult:
    """Simulate a single position. Thin wrapper that exists so the rest of
    the simulator can call a uniform interface. Future tasks may wrap this
    around the existing PortfolioTracker to surface equity-curve points per
    ticker; for now it just delegates to the exit engine.
    """
    return simulate_position(ticker, bars, entry_price, dollars, config)


# ---------------------------------------------------------------------------
# Multi-ticker aggregator
# ---------------------------------------------------------------------------

def run_many(
    positions: List[Dict[str, Any]],
    config: ExitConfig,
    bars_by_ticker: Dict[str, pd.DataFrame],
) -> List[TradeResult]:
    """Simulate each position independently. Missing/empty bars for a ticker
    are recorded as a `data_unavailable` TradeResult (not raised).
    """
    out: List[TradeResult] = []
    for p in positions:
        ticker = p["ticker"]
        entry_price = float(p["entry_price"])
        dollars = float(p["dollars"])
        bars = bars_by_ticker.get(ticker)
        out.append(run_one(ticker, bars, entry_price, dollars, config))
    return out


def build_portfolio_equity_curve(
    trades: List[TradeResult],
    bars_by_ticker: Dict[str, pd.DataFrame],
    dollars_by_ticker: Dict[str, float],
    total_capital: float,
) -> List[Dict[str, Any]]:
    """Sum the per-ticker mark-to-market across still-open positions at each
    unique timestamp. Returns a list of `{time, value}` points sorted ascending.

    A position contributes its MTM for bars 0..exit_idx inclusive, then 0
    thereafter. We achieve "0 thereafter" by clipping the per-ticker series
    at exit_idx + 1 bars and NOT forward-filling.
    """
    per_ticker_series: Dict[str, pd.Series] = {}
    for t in trades:
        bars = bars_by_ticker.get(t.ticker)
        dollars = dollars_by_ticker.get(t.ticker, 0.0)
        if bars is None or bars.empty or t.exit_idx < 0:
            continue
        sliced = bars.iloc[: t.exit_idx + 1].reset_index(drop=True)
        mtm = (sliced["Close"] / t.entry_price) * dollars
        per_ticker_series[t.ticker] = pd.Series(
            mtm.to_numpy(),
            index=pd.to_datetime(sliced["Date"]),
        )

    if not per_ticker_series:
        return []

    # Build the union of all per-ticker timestamps. Sum only on dates where
    # each ticker is still alive — do not ffill, so closed positions
    # contribute 0 after their exit.
    all_dates = sorted(set().union(*(s.index for s in per_ticker_series.values())))
    portfolio_value = pd.Series(0.0, index=pd.DatetimeIndex(all_dates))
    for ticker, s in per_ticker_series.items():
        portfolio_value = portfolio_value.add(s.reindex(portfolio_value.index).fillna(0.0), fill_value=0.0)

    return [
        {"time": int(ts.timestamp()), "value": float(v)}
        for ts, v in portfolio_value.items()
    ]


def compute_summary(
    trades: List[TradeResult],
    equity_curve: List[Dict[str, Any]],
    total_capital: float,
) -> Dict[str, Any]:
    """Compute the portfolio-level summary stats from the per-trade ledger
    and the portfolio equity curve.
    """
    valid = [t for t in trades if t.exit_reason != "data_unavailable"]
    n_trades = len(valid)
    winners = [t for t in valid if t.pnl_pct > 0]
    losers = [t for t in valid if t.pnl_pct <= 0]
    n_winners = len(winners)
    n_losers = len(losers)
    win_rate = (n_winners / n_trades * 100.0) if n_trades else 0.0

    total_pnl = sum(t.pnl_dollars for t in valid)
    total_return_pct = total_pnl / total_capital if total_capital else 0.0

    avg_winner = float(np.mean([t.pnl_pct for t in winners])) if winners else 0.0
    avg_loser = float(np.mean([t.pnl_pct for t in losers])) if losers else 0.0

    gross_win = sum(t.pnl_dollars for t in winners)
    gross_loss = abs(sum(t.pnl_dollars for t in losers))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0

    avg_holding_days = float(np.mean([t.holding_days for t in valid])) if valid else 0.0

    # Annualized return from total_return_pct over the curve's span
    if len(equity_curve) >= 2:
        days = max(1, (equity_curve[-1]["time"] - equity_curve[0]["time"]) // 86400)
        years = days / 365.25
        annualized_return_pct = ((1 + total_return_pct) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    else:
        annualized_return_pct = 0.0

    # Daily returns from the equity curve → Sharpe / Sortino / max DD
    if len(equity_curve) >= 2:
        values = np.array([p["value"] for p in equity_curve], dtype=float)
        daily_rets = np.diff(values) / np.maximum(values[:-1], 1e-9)
        if len(daily_rets) >= 2 and daily_rets.std() > 0:
            sharpe = float(daily_rets.mean() / daily_rets.std() * np.sqrt(252))
            downside = daily_rets[daily_rets < 0]
            sortino = float(daily_rets.mean() / downside.std() * np.sqrt(252)) if len(downside) > 1 and downside.std() > 0 else 0.0
        else:
            sharpe = 0.0
            sortino = 0.0
        running_max = np.maximum.accumulate(values)
        drawdown = (values - running_max) / running_max
        max_drawdown_pct = float(drawdown.min() * 100)
    else:
        sharpe = 0.0
        sortino = 0.0
        max_drawdown_pct = 0.0

    return {
        "total_return_pct": total_return_pct * 100,
        "annualized_return_pct": annualized_return_pct,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": max_drawdown_pct,
        "win_rate_pct": win_rate,
        "profit_factor": float(profit_factor),
        "avg_winner_pct": avg_winner * 100,
        "avg_loser_pct": avg_loser * 100,
        "avg_holding_days": avg_holding_days,
        "n_trades": n_trades,
        "n_winners": n_winners,
        "n_losers": n_losers,
    }


# ---------------------------------------------------------------------------
# SPY alpha
# ---------------------------------------------------------------------------

def compute_spy_alpha(
    equity_curve: List[Dict[str, Any]],
    spy_bars: pd.DataFrame,
    total_capital: float,
) -> Dict[str, Any]:
    """Compare the portfolio equity curve to a buy-and-hold of SPY over the
    same window. SPY is normalized to start at `total_capital`.
    """
    if not equity_curve or spy_bars is None or spy_bars.empty:
        return {
            "spy_return_pct": 0.0,
            "alpha_pct": 0.0,
            "spy_equity_curve": [],
        }

    start_ts = equity_curve[0]["time"]
    end_ts = equity_curve[-1]["time"]
    start_dt = pd.to_datetime(start_ts, unit="s")
    end_dt = pd.to_datetime(end_ts, unit="s")

    spy = spy_bars.copy()
    spy["Date"] = pd.to_datetime(spy["Date"])
    spy = spy[(spy["Date"] >= start_dt) & (spy["Date"] <= end_dt)].sort_values("Date")
    if spy.empty:
        return {"spy_return_pct": 0.0, "alpha_pct": 0.0, "spy_equity_curve": []}

    start_price = float(spy["Close"].iloc[0])
    spy["nav"] = spy["Close"] / start_price * total_capital
    spy_equity = [
        {"time": int(row["Date"].timestamp()), "value": float(row["nav"])}
        for _, row in spy.iterrows()
    ]
    spy_return_pct = (float(spy["nav"].iloc[-1]) - total_capital) / total_capital * 100

    portfolio_return_pct = (
        (equity_curve[-1]["value"] - equity_curve[0]["value"]) / equity_curve[0]["value"] * 100
        if equity_curve[0]["value"] > 0
        else 0.0
    )
    return {
        "spy_return_pct": spy_return_pct,
        "alpha_pct": portfolio_return_pct - spy_return_pct,
        "spy_equity_curve": spy_equity,
    }
