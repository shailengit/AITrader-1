"""Top-level orchestrator for the screener-exit backtest endpoint.

This module is the *only* place that talks to the DB and to the existing
screener entry points. The router calls `run_backtest(req)` and gets back
a fully-assembled BacktestExitResponse.

The orchestrator is split into three concerns:
  1. run_screener_at_as_of   — calls Dormant Giant or Custom at cutoff_date
  2. get_ohlcv_for_backtest  — fetches daily bars for one ticker from as_of forward
  3. get_spy_bars            — fetches SPY bars over the same window

Each is a small wrapper. They are the patch points used in tests.
"""
from __future__ import annotations
from typing import List, Dict, Any
from datetime import timedelta
import logging

import pandas as pd

from app.services.backtest.schemas import (
    BacktestExitRequest,
    BacktestExitResponse,
    DEFAULT_TOTAL_CAPITAL,
    ScreenerKind,
)
from app.services.backtest.exit_engine import ExitConfig
from app.services.backtest import portfolio_simulator as sim
from app.services.backtest.sizing import compute_position_dollars

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# External I/O wrappers (patch points in tests)
# ---------------------------------------------------------------------------

def _normalize_screener_result(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert the heterogeneous per-screener result dicts into a uniform
    candidate list: {ticker, score, close, sector?}.
    """
    out: List[Dict[str, Any]] = []
    for r in results or []:
        ticker = r.get("ticker")
        if not ticker:
            continue
        score = r.get("score")
        try:
            score = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        close = r.get("close")
        try:
            close = float(close) if close is not None else 0.0
        except (TypeError, ValueError):
            close = 0.0
        out.append({
            "ticker": ticker,
            "score": score,
            "close": close,
            "sector": r.get("sector"),
        })
    return out


def run_screener_at_as_of(req: BacktestExitRequest) -> List[Dict[str, Any]]:
    """Run the user's chosen screener at as_of_date, return a list of
    candidate dicts, each with at least {ticker, score, close, sector?}.
    """
    if req.screener.kind == ScreenerKind.DORMANT_GIANT:
        from app.services.agno_screener import run_dormant_giant_screener
        result = run_dormant_giant_screener(cutoff_date=req.as_of_date.isoformat())
        return _normalize_screener_result(result.get("results", []))
    else:
        from app.services.agno_screener import run_quant_strategy_screener
        result = run_quant_strategy_screener(
            prompt="",
            cutoff_date=req.as_of_date.isoformat(),
            filters=req.screener.filters,
        )
        return _normalize_screener_result(result.get("results", []))


def get_ohlcv_for_backtest(ticker: str, start_date, end_date) -> pd.DataFrame:
    """Fetch daily OHLCV bars for one ticker. Thin wrapper over data_service."""
    from app.services.data_service import get_data
    df = get_data(
        ticker=ticker,
        start_date=start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date),
        end_date=end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date),
        frequency="daily",
    )
    if df is None or df.empty:
        return pd.DataFrame()
    # Ensure we have a Date column and the standard OHLCV shape
    if "Date" not in df.columns and df.index.name == "Date":
        df = df.reset_index()
    return df.reset_index(drop=True)


def get_spy_bars(start_date, end_date) -> pd.DataFrame:
    """Fetch SPY bars over the backtest window. Tries multiple tickers/cases
    (the existing backtest-hold endpoint tries "SPY" then "spy") and returns
    an empty DataFrame on miss — the alpha helper treats empty SPY as 0%.
    """
    from app.services.data_service import get_data
    start_str = start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date)
    end_str = end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date)
    for ticker in ("SPY", "spy", "SPY_PROXY"):
        try:
            df = get_data(ticker=ticker, start_date=start_str, end_date=end_str, frequency="daily")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug("SPY fetch failed for %s: %s", ticker, exc)
            df = None
        if df is None or df.empty:
            continue
        if "Date" not in df.columns and df.index.name == "Date":
            df = df.reset_index()
        return df.reset_index(drop=True)
    logger.warning("SPY data unavailable for backtest window %s..%s; alpha will be 0", start_str, end_str)
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def _to_exit_config(req: BacktestExitRequest) -> ExitConfig:
    er = req.exit_rules
    return ExitConfig(
        stop_loss_pct=er.stop_loss_pct,
        take_profit_pct=er.take_profit_pct,
        trailing_stop_pct=er.trailing_stop_pct,
        trend_break_sma=er.trend_break_sma,
        max_holding_days=er.max_holding_days,
    )


def _compute_vols(bars_by_ticker: Dict[str, pd.DataFrame], tickers: List[str]) -> List[float]:
    """20-day rolling vol of daily returns per ticker. Used by inverse_vol sizing."""
    out = []
    for t in tickers:
        bars = bars_by_ticker.get(t)
        if bars is None or bars.empty or len(bars) < 21:
            out.append(0.0)   # signals sizing to fail loud downstream
            continue
        rets = bars["Close"].pct_change().dropna().tail(20)
        out.append(float(rets.std()) if len(rets) > 1 else 0.0)
    return out


def run_backtest(req: BacktestExitRequest) -> BacktestExitResponse:
    """End-to-end: screener → top N → bars → exit engine → equity curve → SPY alpha."""
    candidates = run_screener_at_as_of(req)
    warnings: List[str] = []

    if not candidates:
        # Empty screener result — return an empty but well-formed response
        return _empty_response(req, note="no candidates: screener returned 0 results at the given as_of_date")

    # Sort by score desc and take top N
    candidates = sorted(candidates, key=lambda c: c.get("score", 0.0), reverse=True)[: req.top_n]
    tickers = [c["ticker"] for c in candidates]
    entry_prices = [c["close"] for c in candidates]
    scores = [c.get("score", 0.0) for c in candidates]

    # Fetch bars in the forward window
    end_date = req.as_of_date + timedelta(days=req.exit_rules.max_lookback_days)
    bars_by_ticker: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        bars_by_ticker[t] = get_ohlcv_for_backtest(t, req.as_of_date, end_date)
        if bars_by_ticker[t] is None or bars_by_ticker[t].empty:
            warnings.append(f"missing data for {t}")

    # Sizing
    vols = _compute_vols(bars_by_ticker, tickers)
    mode_value = req.sizing.mode.value
    if mode_value == "inverse_vol":
        dollars_list = compute_position_dollars(
            "inverse_vol", n=len(tickers), scores=None, vols=vols,
        )
    elif mode_value == "score_weighted":
        dollars_list = compute_position_dollars(
            "score_weighted", n=len(tickers), scores=scores, vols=None,
        )
    elif mode_value == "capital_capped":
        dollars_list = compute_position_dollars(
            "capital_capped", n=len(tickers), scores=None, vols=None,
            per_position_cap=req.sizing.per_position_cap,
        )
    else:  # equal_weight
        dollars_list = compute_position_dollars(
            "equal_weight", n=len(tickers), scores=None, vols=None,
        )
    dollars_by_ticker = dict(zip(tickers, dollars_list))
    positions = [
        {"ticker": t, "entry_price": ep, "dollars": d}
        for t, ep, d in zip(tickers, entry_prices, dollars_list)
    ]

    # Simulate
    config = _to_exit_config(req)
    trades = sim.run_many(positions, config, bars_by_ticker)

    equity_curve = sim.build_portfolio_equity_curve(
        trades, bars_by_ticker, dollars_by_ticker, total_capital=DEFAULT_TOTAL_CAPITAL,
    )
    summary = sim.compute_summary(trades, equity_curve, total_capital=DEFAULT_TOTAL_CAPITAL)

    # Drawdown curve
    if equity_curve:
        values = [p["value"] for p in equity_curve]
        running_max = []
        cur = values[0]
        for v in values:
            cur = max(cur, v)
            running_max.append(cur)
        drawdown_curve = [
            {"time": p["time"], "dd_pct": ((p["value"] - rm) / rm * 100) if rm > 0 else 0.0}
            for p, rm in zip(equity_curve, running_max)
        ]
    else:
        drawdown_curve = []

    # SPY alpha
    spy_bars = get_spy_bars(req.as_of_date, end_date)
    benchmark = sim.compute_spy_alpha(equity_curve, spy_bars, trades, total_capital=DEFAULT_TOTAL_CAPITAL)

    # Build per_trade response entries
    sector_by_ticker = {c["ticker"]: c.get("sector") for c in candidates}
    per_trade = []
    for t in trades:
        per_trade.append({
            "ticker": t.ticker,
            "sector": sector_by_ticker.get(t.ticker),
            "entry_date": t.entry_date,
            "entry_price": t.entry_price,
            "exit_date": t.exit_date,
            "exit_price": t.exit_price,
            "exit_reason": t.exit_reason,
            "holding_days": t.holding_days,
            "pnl_dollars": t.pnl_dollars,
            "pnl_pct": t.pnl_pct,
            "mfe_pct": t.mfe_pct,
            "mae_pct": t.mae_pct,
        })

    return BacktestExitResponse(
        config={
            "as_of_date": req.as_of_date.isoformat(),
            "top_n": req.top_n,
            "sizing": req.sizing.model_dump(),
            "exit_rules": req.exit_rules.model_dump(),
            "total_capital": DEFAULT_TOTAL_CAPITAL,
        },
        warnings=warnings,
        per_trade=per_trade,
        summary=summary,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        benchmark=benchmark,
    )


def _empty_response(req: BacktestExitRequest, note: str) -> BacktestExitResponse:
    return BacktestExitResponse(
        config={
            "as_of_date": req.as_of_date.isoformat(),
            "top_n": req.top_n,
            "sizing": req.sizing.model_dump(),
            "exit_rules": req.exit_rules.model_dump(),
            "total_capital": DEFAULT_TOTAL_CAPITAL,
        },
        warnings=[note],
        per_trade=[],
        summary={
            "total_return_pct": 0.0, "annualized_return_pct": 0.0,
            "sharpe": 0.0, "sortino": 0.0, "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0, "profit_factor": 0.0,
            "avg_winner_pct": 0.0, "avg_loser_pct": 0.0,
            "avg_holding_days": 0.0,
            "n_trades": 0, "n_winners": 0, "n_losers": 0,
        },
        equity_curve=[],
        drawdown_curve=[],
        benchmark={"spy_return_pct": 0.0, "alpha_pct": 0.0, "spy_equity_curve": []},
    )
