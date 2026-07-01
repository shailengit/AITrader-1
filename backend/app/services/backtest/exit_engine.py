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


def evaluate_trailing_stop(
    bars: pd.DataFrame, state: PositionState, pct: float
) -> Optional[ExitSignal]:
    """Return ExitSignal on the first bar where close drops by pct from its
    running high-water mark (entry_price updated to each new high).
    """
    if pct <= 0:
        return None
    hwm = state.entry_price
    for i, close in enumerate(bars["Close"]):
        if close > hwm:
            hwm = float(close)
        if hwm > 0 and (hwm - close) / hwm >= pct:
            return ExitSignal(exit_idx=i, reason="trailing_stop", exit_price=float(close))
    return None


def evaluate_trend_break(
    bars: pd.DataFrame, state: PositionState, sma_n: int
) -> Optional[ExitSignal]:
    """Return ExitSignal on the first bar where close < SMA(sma_n) computed
    on all bars up to and including the current bar.

    Note: we use the *full* rolling window, not just bars since entry, so the
    SMA is well-formed immediately after the warmup (window-1) bars. The
    orchestrator is responsible for slicing the input bars to start at entry.
    """
    if sma_n < 2:
        return None
    sma = bars["Close"].rolling(window=sma_n).mean()
    for i in range(len(bars)):
        v = sma.iloc[i]
        if pd.notna(v) and bars["Close"].iloc[i] < v:
            return ExitSignal(
                exit_idx=i, reason="trend_break", exit_price=float(bars["Close"].iloc[i])
            )
    return None


class ExitConfig(NamedTuple):
    """User-configurable exit rules. Any field set to 0 is disabled."""
    stop_loss_pct: float       # e.g. 0.08 = -8% from entry
    take_profit_pct: float     # e.g. 0.20 = +20% from entry
    trailing_stop_pct: float   # e.g. 0.10 = -10% from running high-water mark
    trend_break_sma: int       # e.g. 20 = exit when close < SMA(20); 0 disables
    max_holding_days: int      # force-exit after N bars; 0 means "use whatever data we have"


class TradeResult(NamedTuple):
    """The output of simulate_position — one row of the per-trade ledger."""
    ticker: str
    entry_date: str          # ISO date string
    entry_price: float
    exit_date: str           # ISO date string
    exit_price: float
    exit_reason: str         # 'stop_loss' | 'take_profit' | 'trailing_stop' | 'trend_break' | 'max_lookback' | 'data_unavailable'
    holding_days: int
    pnl_dollars: float
    pnl_pct: float
    mfe_pct: float
    mae_pct: float
    exit_idx: int            # index into bars where exit occurred (for diagnostics)


def _to_iso(date_value) -> str:
    if hasattr(date_value, "date"):
        return date_value.date().isoformat()
    return str(date_value)[:10]


def _update_mfe_mae(state: PositionState, close: float) -> PositionState:
    """Return a new state with updated high-water mark, MFE, MAE."""
    hwm = max(state.high_water_mark, close)
    mfe = max(state.mfe_pct, (hwm - state.entry_price) / state.entry_price)
    mae = min(state.mae_pct, (close - state.entry_price) / state.entry_price)
    return PositionState(
        entry_price=state.entry_price,
        high_water_mark=hwm,
        mfe_pct=mfe,
        mae_pct=mae,
    )


def simulate_position(
    ticker: str,
    bars: pd.DataFrame,
    entry_price: float,
    dollars: float,
    config: ExitConfig,
) -> TradeResult:
    """Walk bars from entry, evaluate rules in precedence, return one TradeResult.

    `bars` must start at the entry bar (i.e. bars.iloc[0]['Close'] is the entry
    close, which equals `entry_price` to within float tolerance). The function
    itself does not slice — the caller is expected to have already sliced
    `bars` from the as_of_date forward.
    """
    if bars is None or bars.empty:
        return TradeResult(
            ticker=ticker,
            entry_date="", entry_price=entry_price,
            exit_date="", exit_price=entry_price,
            exit_reason="data_unavailable",
            holding_days=0, pnl_dollars=0.0, pnl_pct=0.0,
            mfe_pct=0.0, mae_pct=0.0, exit_idx=-1,
        )

    entry_date = _to_iso(bars["Date"].iloc[0])
    state = PositionState(
        entry_price=entry_price, high_water_mark=entry_price, mfe_pct=0.0, mae_pct=0.0,
    )

    # Walk bars from index 0; evaluate rules on each iteration.
    # Index 0 is the entry bar itself — rules that need a future bar will not
    # fire here because the entry close is the reference.
    exit_idx = -1
    exit_reason = ""
    exit_price = entry_price
    last_idx = len(bars) - 1

    for i in range(len(bars)):
        close = float(bars["Close"].iloc[i])
        state = _update_mfe_mae(state, close)

        # Time stop (max_holding_days) — checked at i == max_holding_days - 1
        # (the bar where we have been in the position for `max_holding_days` bars)
        if config.max_holding_days > 0 and i >= config.max_holding_days - 1:
            exit_idx = i
            exit_reason = "max_lookback"
            exit_price = close
            break

        # The remaining bars are the forward-walk — skip the entry bar itself
        # for these rules (entry close vs entry close is always 0% change).
        if i == 0:
            continue

        # 1) Stop-loss
        if config.stop_loss_pct > 0:
            sig = evaluate_stop_loss(bars.iloc[i:i+1].reset_index(drop=True), state, config.stop_loss_pct)
            if sig is not None:
                exit_idx = i
                exit_reason = "stop_loss"
                exit_price = sig.exit_price
                break

        # 2) Take-profit
        if config.take_profit_pct > 0:
            sig = evaluate_take_profit(bars.iloc[i:i+1].reset_index(drop=True), state, config.take_profit_pct)
            if sig is not None:
                exit_idx = i
                exit_reason = "take_profit"
                exit_price = sig.exit_price
                break

        # 3) Trailing stop — uses full history through bar i (not just the single bar)
        if config.trailing_stop_pct > 0:
            sig = evaluate_trailing_stop(bars.iloc[:i+1].reset_index(drop=True), state, config.trailing_stop_pct)
            if sig is not None:
                exit_idx = i
                exit_reason = "trailing_stop"
                exit_price = sig.exit_price
                break

        # 4) Trend break (close < SMA) — uses full history through bar i
        if config.trend_break_sma >= 2:
            sig = evaluate_trend_break(bars.iloc[:i+1].reset_index(drop=True), state, config.trend_break_sma)
            if sig is not None:
                exit_idx = i
                exit_reason = "trend_break"
                exit_price = sig.exit_price
                break

    if exit_idx == -1:
        # No rule fired; exit at the last bar with reason max_lookback
        exit_idx = last_idx
        exit_reason = "max_lookback"
        exit_price = float(bars["Close"].iloc[last_idx])

    holding_days = exit_idx  # entry at idx 0; exit at idx N means N bars held
    pnl_pct = (exit_price - entry_price) / entry_price
    pnl_dollars = pnl_pct * dollars
    exit_date = _to_iso(bars["Date"].iloc[exit_idx])

    return TradeResult(
        ticker=ticker,
        entry_date=entry_date, entry_price=entry_price,
        exit_date=exit_date, exit_price=exit_price,
        exit_reason=exit_reason, holding_days=holding_days,
        pnl_dollars=pnl_dollars, pnl_pct=pnl_pct,
        mfe_pct=state.mfe_pct, mae_pct=state.mae_pct,
        exit_idx=exit_idx,
    )
