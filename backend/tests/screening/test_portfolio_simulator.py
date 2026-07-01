"""Tests for the portfolio simulator I/O orchestrator."""
import numpy as np
import pandas as pd
import pytest

from app.services.backtest.portfolio_simulator import (
    run_one,
    run_many,
    build_portfolio_equity_curve,
    compute_summary,
    compute_spy_alpha,
)
from app.services.backtest.exit_engine import ExitConfig


def _bars(closes, start="2024-01-01"):
    n = len(closes)
    return pd.DataFrame({
        "Date": pd.date_range(start, periods=n, freq="D"),
        "Open": closes, "High": closes, "Low": closes,
        "Close": closes, "Volume": np.ones(n) * 1_000_000,
    })


def test_run_one_delegates_to_exit_engine():
    closes = [100.0, 110.0, 125.0]
    bars = _bars(closes)
    cfg = ExitConfig(
        stop_loss_pct=0.0, take_profit_pct=0.20,
        trailing_stop_pct=0.0, trend_break_sma=0, max_holding_days=0,
    )
    t = run_one("AAPL", bars, entry_price=100.0, dollars=5_000.0, config=cfg)
    assert t.ticker == "AAPL"
    assert t.exit_reason == "take_profit"
    assert t.pnl_dollars == pytest.approx(1_250.0, abs=1e-6)


def test_run_many_returns_one_trade_per_position():
    bars1 = _bars([100.0, 110.0, 125.0])
    bars2 = _bars([50.0, 55.0, 60.0])
    positions = [
        {"ticker": "AAPL", "entry_price": 100.0, "dollars": 5_000.0},
        {"ticker": "MSFT", "entry_price": 50.0, "dollars": 5_000.0},
    ]
    bars_by_ticker = {"AAPL": bars1, "MSFT": bars2}
    cfg = ExitConfig(0.0, 0.20, 0.0, 0, 0)
    trades = run_many(positions, cfg, bars_by_ticker)
    assert len(trades) == 2
    assert {t.ticker for t in trades} == {"AAPL", "MSFT"}


def test_run_many_skips_missing_bars_as_data_unavailable():
    positions = [{"ticker": "BAD", "entry_price": 100.0, "dollars": 5_000.0}]
    cfg = ExitConfig(0.08, 0.20, 0.0, 0, 0)
    trades = run_many(positions, cfg, {"BAD": None})  # type: ignore[dict-item]
    assert len(trades) == 1
    assert trades[0].exit_reason == "data_unavailable"


def test_build_portfolio_equity_curve_sums_open_position_mtm():
    # Two positions, each closes on day 2 at +25%
    bars1 = _bars([100.0, 110.0, 125.0])
    bars2 = _bars([50.0, 55.0, 62.5])
    positions = [
        {"ticker": "AAPL", "entry_price": 100.0, "dollars": 5_000.0},
        {"ticker": "MSFT", "entry_price": 50.0, "dollars": 5_000.0},
    ]
    bars_by_ticker = {"AAPL": bars1, "MSFT": bars2}
    dollars_by_ticker = {"AAPL": 5_000.0, "MSFT": 5_000.0}
    cfg = ExitConfig(0.0, 0.20, 0.0, 0, 0)
    trades = run_many(positions, cfg, bars_by_ticker)
    curve = build_portfolio_equity_curve(
        trades, bars_by_ticker, dollars_by_ticker, total_capital=100_000.0
    )
    # Both positions exit on day 2 (take_profit); the curve is the cross-sectional
    # sum of MTM at each unique date both were open.
    # day 0: AAPL 100 → 5000, MSFT 50 → 5000 → 10000
    # day 1: AAPL 110 → 5500, MSFT 55 → 5500 → 11000
    # day 2: AAPL 125 (take_profit fires) → 6250, MSFT 62.5 (take_profit fires) → 6250 → 12500
    assert len(curve) == 3
    assert curve[0]["value"] == pytest.approx(10_000.0)
    assert curve[1]["value"] == pytest.approx(11_000.0)
    assert curve[2]["value"] == pytest.approx(12_500.0)
    assert all(isinstance(p["time"], int) for p in curve)


def test_build_portfolio_equity_curve_drops_to_zero_after_exit():
    # AAPL exits on day 1, MSFT continues. After day 1 the curve should
    # only reflect MSFT's MTM (AAPL contributes nothing).
    bars1 = _bars([100.0, 90.0, 95.0])    # -10% on day 1, stop_loss fires
    bars2 = _bars([50.0, 55.0, 60.0])     # MSFT goes up
    positions = [
        {"ticker": "AAPL", "entry_price": 100.0, "dollars": 5_000.0},
        {"ticker": "MSFT", "entry_price": 50.0, "dollars": 5_000.0},
    ]
    bars_by_ticker = {"AAPL": bars1, "MSFT": bars2}
    dollars_by_ticker = {"AAPL": 5_000.0, "MSFT": 5_000.0}
    cfg = ExitConfig(0.08, 0.0, 0.0, 0, 0)
    trades = run_many(positions, cfg, bars_by_ticker)
    aapl = next(t for t in trades if t.ticker == "AAPL")
    assert aapl.exit_idx == 1
    curve = build_portfolio_equity_curve(
        trades, bars_by_ticker, dollars_by_ticker, total_capital=100_000.0
    )
    # day 0: AAPL 100→5000 + MSFT 50→5000 = 10000
    # day 1: AAPL 90 (still alive; stop_loss fires on close)→4500 + MSFT 55→5500 = 10000
    # day 2: AAPL 0 (closed) + MSFT 60→6000 = 6000
    assert len(curve) == 3
    assert curve[0]["value"] == pytest.approx(10_000.0)
    assert curve[1]["value"] == pytest.approx(10_000.0)
    assert curve[2]["value"] == pytest.approx(6_000.0)


def test_compute_summary_basic_stats():
    bars1 = _bars([100.0, 110.0, 125.0])  # +25% winner
    bars2 = _bars([100.0, 95.0, 90.0])    # -10% loser
    positions = [
        {"ticker": "AAPL", "entry_price": 100.0, "dollars": 5_000.0},
        {"ticker": "MSFT", "entry_price": 100.0, "dollars": 5_000.0},
    ]
    bars_by_ticker = {"AAPL": bars1, "MSFT": bars2}
    dollars_by_ticker = {"AAPL": 5_000.0, "MSFT": 5_000.0}
    cfg = ExitConfig(0.0, 0.20, 0.0, 0, 0)
    trades = run_many(positions, cfg, bars_by_ticker)
    curve = build_portfolio_equity_curve(
        trades, bars_by_ticker, dollars_by_ticker, total_capital=100_000.0
    )
    summary = compute_summary(trades, curve, total_capital=100_000.0)
    assert summary["n_trades"] == 2
    assert summary["n_winners"] == 1
    assert summary["n_losers"] == 1
    assert summary["win_rate_pct"] == pytest.approx(50.0)
    # total pnl = +1250 (AAPL) - 500 (MSFT) = +750
    # total_return_pct = 750 / 100_000 = 0.75%
    assert summary["total_return_pct"] == pytest.approx(0.75, abs=1e-6)


def test_compute_spy_alpha_simple():
    # Build a portfolio curve and a SPY bars set whose first/last dates
    # fall inside the curve's time range.
    start_dt = pd.Timestamp("2024-01-01")
    end_dt = pd.Timestamp("2024-01-03")
    eq = [
        {"time": int(start_dt.timestamp()), "value": 100_000.0},
        {"time": int(end_dt.timestamp()), "value": 110_000.0},
    ]
    spy = pd.DataFrame({
        "Date": pd.date_range(start_dt, end_dt, freq="D"),
        "Close": [400.0, 410.0, 420.0],   # +5% over 3 days
    })
    out = compute_spy_alpha(eq, spy, total_capital=100_000.0)
    assert out["spy_return_pct"] == pytest.approx(5.0, abs=1e-6)
    # portfolio +10%, SPY +5% → alpha = +5%
    assert out["alpha_pct"] == pytest.approx(5.0, abs=1e-6)
    assert len(out["spy_equity_curve"]) == 3
    assert out["spy_equity_curve"][0]["value"] == pytest.approx(100_000.0)
    assert out["spy_equity_curve"][-1]["value"] == pytest.approx(105_000.0)


def test_compute_spy_alpha_negative_alpha():
    start_dt = pd.Timestamp("2024-01-01")
    end_dt = pd.Timestamp("2024-01-03")
    eq = [
        {"time": int(start_dt.timestamp()), "value": 100_000.0},
        {"time": int(end_dt.timestamp()), "value": 95_000.0},
    ]
    spy = pd.DataFrame({
        "Date": pd.date_range(start_dt, end_dt, freq="D"),
        "Close": [400.0, 405.0, 410.0],   # +2.5%
    })
    out = compute_spy_alpha(eq, spy, total_capital=100_000.0)
    assert out["spy_return_pct"] == pytest.approx(2.5, abs=1e-6)
    # portfolio -5%, SPY +2.5% → alpha = -7.5
    assert out["alpha_pct"] == pytest.approx(-7.5, abs=1e-6)
