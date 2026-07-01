"""Exit-rule engine for screener-driven backtests.

A position is walked bar-by-bar from entry. At each bar, the engine
evaluates the active rule families in precedence order:
    stop_loss  →  take_profit  →  signal-based (trend_break)  →  time

The first rule that fires on a given bar wins. The engine never evaluates
a rule that wasn't configured.

All rule functions are pure: they take a bars DataFrame and a
PositionState, and return either an ExitSignal or None. They never
mutate state. MFE/MAE tracking is the orchestrator's responsibility
(see simulate_position).
"""
from __future__ import annotations
from typing import NamedTuple, Optional

import pandas as pd


class PositionState(NamedTuple):
    """Snapshot of a position at any bar during the walk.

    The orchestrator updates these fields after each bar — rule functions
    read but do not write them.
    """
    entry_price: float
    high_water_mark: float
    mfe_pct: float
    mae_pct: float


class ExitSignal(NamedTuple):
    """The orchestrator's signal that a position should be closed."""
    exit_idx: int          # integer index into bars (relative to entry bar = 0)
    reason: str            # 'stop_loss' | 'take_profit' | 'trailing_stop' | 'trend_break' | 'max_lookback'
    exit_price: float


def evaluate_stop_loss(
    bars: pd.DataFrame, state: PositionState, pct: float
) -> Optional[ExitSignal]:
    """Return ExitSignal on the first bar where close <= entry * (1 - pct)."""
    if pct <= 0:
        return None
    threshold = state.entry_price * (1.0 - pct)
    for i, close in enumerate(bars["Close"]):
        if close <= threshold:
            return ExitSignal(exit_idx=i, reason="stop_loss", exit_price=float(close))
    return None


def evaluate_take_profit(
    bars: pd.DataFrame, state: PositionState, pct: float
) -> Optional[ExitSignal]:
    """Return ExitSignal on the first bar where close >= entry * (1 + pct)."""
    if pct <= 0:
        return None
    threshold = state.entry_price * (1.0 + pct)
    for i, close in enumerate(bars["Close"]):
        if close >= threshold:
            return ExitSignal(exit_idx=i, reason="take_profit", exit_price=float(close))
    return None
