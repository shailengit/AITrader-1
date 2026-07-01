"""Tests for the exit-rule engine."""
import numpy as np
import pandas as pd
import pytest

from app.services.backtest.exit_engine import (
    ExitSignal,
    PositionState,
    evaluate_stop_loss,
    evaluate_take_profit,
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
