"""Tests for the exit-rule engine."""
import numpy as np
import pandas as pd
import pytest

from app.services.backtest.exit_engine import (
    ExitSignal,
    PositionState,
    evaluate_stop_loss,
    evaluate_take_profit,
    evaluate_trailing_stop,
    evaluate_trend_break,
    ExitConfig,
    TradeResult,
    simulate_position,
)


def _bars(closes):
    n = len(closes)
    return pd.DataFrame({
        "Date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "Open": closes, "High": closes, "Low": closes,
        "Close": closes, "Volume": np.ones(n) * 1_000_000,
    })


def test_stop_loss_triggers_when_close_drops_below_threshold():
    closes = [100.0, 95.0, 90.0]   # -5% on day 1, -10% on day 2
    bars = _bars(closes)
    state = PositionState(entry_price=100.0, high_water_mark=100.0, mfe_pct=0.0, mae_pct=0.0)
    sig = evaluate_stop_loss(bars, state, pct=0.08)
    # threshold = 100 * (1 - 0.08) = 92.0
    # day 1: 95.0 > 92.0 → no fire
    # day 2: 90.0 <= 92.0 → fire
    assert sig is not None
    assert sig.exit_idx == 2
    assert sig.reason == "stop_loss"
    assert sig.exit_price == 90.0


def test_stop_loss_does_not_trigger_when_drop_above_threshold():
    closes = [100.0, 95.0, 96.0]   # max drop = -5%, threshold is -8%
    bars = _bars(closes)
    state = PositionState(entry_price=100.0, high_water_mark=100.0, mfe_pct=0.0, mae_pct=0.0)
    assert evaluate_stop_loss(bars, state, pct=0.08) is None


def test_stop_loss_triggers_on_first_bar_at_or_below_threshold():
    closes = [100.0, 92.0, 95.0]   # day 1 at exactly threshold (100 * 0.92)
    bars = _bars(closes)
    state = PositionState(entry_price=100.0, high_water_mark=100.0, mfe_pct=0.0, mae_pct=0.0)
    sig = evaluate_stop_loss(bars, state, pct=0.08)
    assert sig is not None
    assert sig.exit_idx == 1
    assert sig.exit_price == 92.0


def test_take_profit_triggers_when_close_rises_above_threshold():
    closes = [100.0, 110.0, 115.0]   # +10% then +15%
    bars = _bars(closes)
    state = PositionState(entry_price=100.0, high_water_mark=100.0, mfe_pct=0.0, mae_pct=0.0)
    sig = evaluate_take_profit(bars, state, pct=0.20)
    assert sig is None  # +10% < +20%
    bars2 = _bars([100.0, 110.0, 125.0])  # +25%
    sig2 = evaluate_take_profit(bars2, state, pct=0.20)
    assert sig2 is not None
    assert sig2.exit_idx == 2
    assert sig2.reason == "take_profit"
    assert sig2.exit_price == 125.0


def test_trailing_stop_tracks_high_water_mark():
    # entry 100, runs to 120, then drops to 110 (-8.3% from hwm 120, threshold -8%)
    closes = [100.0, 110.0, 120.0, 110.0]
    bars = _bars(closes)
    state = PositionState(entry_price=100.0, high_water_mark=100.0, mfe_pct=0.0, mae_pct=0.0)
    sig = evaluate_trailing_stop(bars, state, pct=0.08)
    assert sig is not None
    assert sig.exit_idx == 3
    assert sig.reason == "trailing_stop"
    assert sig.exit_price == 110.0


def test_trailing_stop_no_trigger_when_always_above_threshold():
    closes = [100.0, 105.0, 110.0, 108.0]  # max drawdown from hwm 110 → -1.8%
    bars = _bars(closes)
    state = PositionState(entry_price=100.0, high_water_mark=100.0, mfe_pct=0.0, mae_pct=0.0)
    assert evaluate_trailing_stop(bars, state, pct=0.05) is None


def test_trend_break_exits_when_close_below_sma20():
    # Build 25 bars so we have a 20-day SMA in flight
    closes = [100.0] * 20 + [110.0] * 3 + [95.0, 90.0]   # SMA(20) of last 20 closes
    bars = _bars(closes)
    state = PositionState(entry_price=100.0, high_water_mark=100.0, mfe_pct=0.0, mae_pct=0.0)
    sig = evaluate_trend_break(bars, state, sma_n=20)
    assert sig is not None
    # The first bar where close < SMA(20) computed up to that bar
    # (the rule may fire on the first 95.0 bar or earlier — just assert it fires and the reason)
    assert sig.reason == "trend_break"
    assert sig.exit_idx >= 20


def test_trend_break_no_trigger_when_close_stays_above_sma():
    closes = [100.0] * 25   # SMA(20) is always 100, close always 100
    bars = _bars(closes)
    state = PositionState(entry_price=100.0, high_water_mark=100.0, mfe_pct=0.0, mae_pct=0.0)
    assert evaluate_trend_break(bars, state, sma_n=20) is None


def test_simulate_position_stop_loss_fires_first():
    # entry 100, day 0: +2% (no trigger), day 1: -10% (stop_loss fires before take_profit would on day 3)
    closes = [100.0, 102.0, 90.0, 130.0]
    bars = _bars(closes)
    cfg = ExitConfig(
        stop_loss_pct=0.08, take_profit_pct=0.20,
        trailing_stop_pct=0.0, trend_break_sma=0, max_holding_days=0,
    )
    t = simulate_position("AAPL", bars, entry_price=100.0, dollars=5_000.0, config=cfg)
    assert t.exit_reason == "stop_loss"
    assert t.exit_price == 90.0
    assert t.pnl_pct == pytest.approx(-0.10, abs=1e-6)
    assert t.pnl_dollars == pytest.approx(-500.0, abs=1e-6)
    assert t.holding_days == 2  # day index 2 in the walk (entry at idx 0)


def test_simulate_position_take_profit_fires():
    closes = [100.0, 110.0, 125.0, 130.0]
    bars = _bars(closes)
    cfg = ExitConfig(
        stop_loss_pct=0.08, take_profit_pct=0.20,
        trailing_stop_pct=0.0, trend_break_sma=0, max_holding_days=0,
    )
    t = simulate_position("AAPL", bars, entry_price=100.0, dollars=5_000.0, config=cfg)
    assert t.exit_reason == "take_profit"
    assert t.exit_price == 125.0
    assert t.pnl_pct == pytest.approx(0.25, abs=1e-6)


def test_simulate_position_trend_break_only():
    closes = [100.0] * 20 + [110.0] * 5 + [95.0, 90.0]
    bars = _bars(closes)
    cfg = ExitConfig(
        stop_loss_pct=0.0, take_profit_pct=0.0,
        trailing_stop_pct=0.0, trend_break_sma=20, max_holding_days=0,
    )
    t = simulate_position("AAPL", bars, entry_price=100.0, dollars=5_000.0, config=cfg)
    assert t.exit_reason == "trend_break"


def test_simulate_position_max_lookback_forces_exit():
    closes = [100.0 + 0.01 * i for i in range(30)]   # monotonic up, no other rule fires
    bars = _bars(closes)
    cfg = ExitConfig(
        stop_loss_pct=0.0, take_profit_pct=0.0,
        trailing_stop_pct=0.0, trend_break_sma=0, max_holding_days=10,
    )
    t = simulate_position("AAPL", bars, entry_price=100.0, dollars=5_000.0, config=cfg)
    assert t.exit_reason == "max_lookback"
    # holding_days = exit_idx (entry at idx 0, exit at idx 9 → 9 bars held)
    assert t.holding_days == 9
    assert t.exit_price == pytest.approx(100.09, abs=1e-6)


def test_simulate_position_no_rules_uses_max_lookback_zero_as_data_unavailable():
    closes = [100.0, 101.0, 102.0]
    bars = _bars(closes)
    cfg = ExitConfig(
        stop_loss_pct=0.0, take_profit_pct=0.0,
        trailing_stop_pct=0.0, trend_break_sma=0, max_holding_days=0,
    )
    t = simulate_position("AAPL", bars, entry_price=100.0, dollars=5_000.0, config=cfg)
    # No rules and no max_lookback → engine should not crash; either
    # exit at last bar with reason 'max_lookback' (length-based) or 'data_unavailable'.
    # The contract chosen here: if max_lookback == 0, exit at the last bar with
    # reason 'max_lookback' (the orchestrator treats it as "use the data we have").
    assert t.exit_reason in ("max_lookback", "data_unavailable")
    assert t.exit_idx == len(bars) - 1


def test_simulate_position_tracks_mfe_mae():
    closes = [100.0, 120.0, 110.0, 95.0, 80.0]
    bars = _bars(closes)
    cfg = ExitConfig(
        stop_loss_pct=0.50, take_profit_pct=0.0,   # only stop would fire at -50% but max drop is -20%
        trailing_stop_pct=0.0, trend_break_sma=0, max_holding_days=0,
    )
    t = simulate_position("AAPL", bars, entry_price=100.0, dollars=5_000.0, config=cfg)
    # No stop/take fires, so walk reaches end → mfe = 0.20, mae = -0.20
    assert t.mfe_pct == pytest.approx(0.20, abs=1e-6)
    assert t.mae_pct == pytest.approx(-0.20, abs=1e-6)
