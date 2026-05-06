"""
Compute comprehensive portfolio statistics from walk-forward equity curves.

This module replaces VectorBT's pf.stats() for WFO results, which returns NaN
for most metrics when the test window is only 1 day. Instead, we collect daily
PnL across all windows and compute all metrics from the accumulated series.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime


def compute_wfo_stats(
    equity_curve: List[Dict[str, Any]],
    initial_cash: float = 100000.0,
    benchmark_prices: Optional[pd.Series] = None,
    trades: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Compute comprehensive portfolio statistics from a walk-forward equity curve.

    This avoids the NaN problem of VBT's pf.stats() on single-day windows by
    computing all metrics from the accumulated multi-day out-of-sample series.

    Args:
        equity_curve: List of dicts with 'time' (timestamp) and 'value' keys
        initial_cash: Starting capital (default 100000.0; use 1.0 for normalized curves)
        benchmark_prices: Optional pandas Series of benchmark close prices
        trades: Optional list of trade dicts with 'action' and 'realized_pnl' keys

    Returns:
        Dict with VBT-compatible stat keys and computed values
    """
    if not equity_curve or len(equity_curve) < 2:
        return _empty_stats()

    # Convert equity curve to pandas Series
    try:
        times = [datetime.fromtimestamp(p['time']) for p in equity_curve]
        values = pd.Series(
            [p['value'] for p in equity_curve],
            index=pd.DatetimeIndex(times),
            dtype=float
        )
    except Exception:
        return _empty_stats()

    if len(values) < 2:
        return _empty_stats()

    # Compute daily returns
    daily_returns = values.pct_change().dropna()

    # Remove any inf/nan from returns
    daily_returns = daily_returns.replace([np.inf, -np.inf], np.nan).dropna()

    if len(daily_returns) < 1:
        return _empty_stats()

    # --- Return-based metrics ---
    start_value = float(values.iloc[0])
    end_value = float(values.iloc[-1])
    total_return = (end_value / start_value) - 1.0

    # Period info
    n_days = len(values)
    n_years = n_days / 252.0
    start_date = values.index[0]
    end_date = values.index[-1]

    # Annualized return (CAGR)
    if n_years > 0 and total_return > -1.0:
        annualized_return = (1 + total_return) ** (1 / max(n_years, 1/252)) - 1
    else:
        annualized_return = 0.0

    # Annualized volatility
    if len(daily_returns) >= 2:
        annualized_vol = float(daily_returns.std() * np.sqrt(252))
    else:
        annualized_vol = 0.0

    # Sharpe Ratio
    if len(daily_returns) >= 2 and daily_returns.std() > 0:
        sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252))
    else:
        sharpe = 0.0

    # Sortino Ratio
    downside_returns = daily_returns[daily_returns < 0]
    if len(downside_returns) >= 2 and downside_returns.std() > 0:
        sortino = float((daily_returns.mean() / downside_returns.std()) * np.sqrt(252))
    elif len(downside_returns) >= 1:
        # With only one downside return, use its absolute value as "std"
        sortino = float((daily_returns.mean() / abs(downside_returns.iloc[0])) * np.sqrt(252)) if downside_returns.iloc[0] != 0 else 0.0
    else:
        sortino = 0.0

    # Max Drawdown
    cummax = values.cummax()
    drawdown_series = (values - cummax) / cummax
    max_drawdown = float(drawdown_series.min())

    # Max Drawdown Duration
    in_drawdown = drawdown_series < 0
    if in_drawdown.any():
        # Find the longest consecutive stretch of drawdown days
        dd_groups = (in_drawdown != in_drawdown.shift()).cumsum()
        dd_durations = in_drawdown.groupby(dd_groups).sum()
        max_dd_duration_days = int(dd_durations.max())
    else:
        max_dd_duration_days = 0

    # Calmar Ratio
    if max_drawdown != 0:
        calmar = float(annualized_return / abs(max_drawdown))
    else:
        calmar = 0.0

    # Omega Ratio (threshold = 0, daily returns)
    if len(daily_returns) >= 2:
        threshold = 0.0
        gains = daily_returns[daily_returns > threshold]
        losses = daily_returns[daily_returns <= threshold]
        sum_gains = gains.sum() if len(gains) > 0 else 0.0
        sum_losses = abs(losses.sum()) if len(losses) > 0 else 0.0
        omega = float(sum_gains / sum_losses) if sum_losses > 0 else float('inf') if sum_gains > 0 else 0.0
    else:
        omega = 0.0

    # Tail Ratio (ratio of 95th to 5th percentile)
    if len(daily_returns) >= 10:
        p95 = daily_returns.quantile(0.95)
        p5 = daily_returns.quantile(0.05)
        tail_ratio = float(abs(p95 / p5)) if p5 != 0 else 0.0
    else:
        tail_ratio = None

    # Common Sense Ratio (CSR = Profit Factor * Tail Ratio)
    # Will be computed after trade-based metrics if available

    # Value at Risk (95% confidence)
    if len(daily_returns) >= 10:
        var_95 = float(daily_returns.quantile(0.05))
    else:
        var_95 = None

    # --- Trade-based metrics (if trades provided) ---
    win_rate = None
    total_trades = None
    profit_factor = None
    expectancy = None
    avg_win_pct = None
    avg_loss_pct = None
    best_trade_pct = None
    worst_trade_pct = None
    total_closed_trades = None
    total_open_trades = None
    open_trade_pnl = None

    if trades:
        sell_trades = [t for t in trades if t.get('action') == 'SELL' and t.get('realized_pnl') is not None]
        total_trades_val = len(trades)
        closed_trades_val = len(sell_trades)

        total_trades = total_trades_val
        total_closed_trades = closed_trades_val
        total_open_trades = total_trades_val - closed_trades_val

        if closed_trades_val > 0:
            wins = [t for t in sell_trades if t['realized_pnl'] > 0]
            losses = [t for t in sell_trades if t['realized_pnl'] < 0]

            win_rate = float(len(wins) / closed_trades_val) * 100

            total_gains = sum(t['realized_pnl'] for t in wins) if wins else 0.0
            total_losses = abs(sum(t['realized_pnl'] for t in losses)) if losses else 0.0

            profit_factor = float(total_gains / total_losses) if total_losses > 0 else float('inf') if total_gains > 0 else 0.0
            expectancy = float(sum(t['realized_pnl'] for t in sell_trades) / closed_trades_val)

            avg_win_pct = float(total_gains / len(wins) / initial_cash * 100) if wins else 0.0
            avg_loss_pct = float(total_losses / len(losses) / initial_cash * 100) if losses else 0.0

            # Best/worst trade as % of initial_cash
            trade_pnls = [t['realized_pnl'] for t in sell_trades]
            best_trade_pct = float(max(trade_pnls) / initial_cash * 100)
            worst_trade_pct = float(min(trade_pnls) / initial_cash * 100)

        # Open trade PnL
        open_trades = [t for t in trades if t.get('action') == 'BUY']
        open_trade_pnl = float(sum(0 for _ in open_trades))  # Can't compute PnL for open trades without current price

    # Build stats dict matching VBT format
    stats = {
        'Start': str(start_date),
        'End': str(end_date),
        'Period': f"{n_days} days",
        'Start Value': round(start_value, 2),
        'End Value': round(end_value, 2),
        'Total Return [%]': round(total_return * 100, 4),
        'Max Gross Exposure [%]': 100.0,  # WFO is always fully invested or cash
        'Total Fees Paid': 0.0,
        'Annualized Return [%]': round(annualized_return * 100, 4) if not np.isnan(annualized_return) else 0.0,
        'Annualized Volatility [%]': round(annualized_vol * 100, 4) if not np.isnan(annualized_vol) else 0.0,
        'Sharpe Ratio': round(sharpe, 4) if not np.isnan(sharpe) else 0.0,
        'Sortino Ratio': round(sortino, 4) if not np.isnan(sortino) else 0.0,
        'Calmar Ratio': round(calmar, 4) if not np.isnan(calmar) else 0.0,
        'Max Drawdown [%]': round(max_drawdown * 100, 4),
        'Max Drawdown Duration': f"{max_dd_duration_days} days",
        'Omega Ratio': round(omega, 4) if not (np.isnan(omega) or np.isinf(omega)) else None,
    }

    # Optional metrics (only add if we have enough data)
    if tail_ratio is not None:
        stats['Tail Ratio'] = round(tail_ratio, 4)
    if var_95 is not None:
        stats['Value at Risk'] = round(var_95 * 100, 4)

    # Trade-based metrics
    if total_trades is not None:
        stats['Total Trades'] = total_trades
    if total_closed_trades is not None:
        stats['Total Closed Trades'] = total_closed_trades
    if total_open_trades is not None:
        stats['Total Open Trades'] = total_open_trades
    if open_trade_pnl is not None:
        stats['Open Trade PnL'] = open_trade_pnl
    if win_rate is not None:
        stats['Win Rate [%]'] = round(win_rate, 2)
    if best_trade_pct is not None:
        stats['Best Trade [%]'] = round(best_trade_pct, 2)
    if worst_trade_pct is not None:
        stats['Worst Trade [%]'] = round(worst_trade_pct, 2)
    if avg_win_pct is not None:
        stats['Avg Winning Trade [%]'] = round(avg_win_pct, 2)
    if avg_loss_pct is not None:
        stats['Avg Losing Trade [%]'] = round(avg_loss_pct, 2)
    if profit_factor is not None:
        stats['Profit Factor'] = round(profit_factor, 4) if not (np.isinf(profit_factor) or np.isnan(profit_factor)) else None
    if expectancy is not None:
        stats['Expectancy'] = round(expectancy, 2)

    # Common Sense Ratio (only if we have both profit factor and tail ratio)
    if profit_factor is not None and tail_ratio is not None:
        csr = profit_factor * tail_ratio
        stats['Common Sense Ratio'] = round(csr, 4) if not np.isinf(csr) else 0.0

    # --- Benchmark metrics ---
    if benchmark_prices is not None and len(benchmark_prices) >= 2:
        bench_returns = benchmark_prices.pct_change().dropna()
        bench_returns = bench_returns.replace([np.inf, -np.inf], np.nan).dropna()

        if len(bench_returns) >= 2:
            bench_total_return = (float(benchmark_prices.iloc[-1]) / float(benchmark_prices.iloc[0])) - 1.0
            bench_sharpe = float((bench_returns.mean() / bench_returns.std()) * np.sqrt(252)) if bench_returns.std() > 0 else 0.0

            bench_cummax = benchmark_prices.cummax()
            bench_drawdown = (benchmark_prices - bench_cummax) / bench_cummax
            bench_max_dd = float(bench_drawdown.min())

            stats['Benchmark Return [%]'] = round(bench_total_return * 100, 4)
            stats['Benchmark Sharpe Ratio'] = round(bench_sharpe, 4) if not np.isnan(bench_sharpe) else 0.0
            stats['Benchmark Max Drawdown [%]'] = round(bench_max_dd * 100, 4)

    return stats


def compute_drawdown_from_equity(equity_curve: List[Dict[str, Any]]) -> Dict[float, float]:
    """
    Compute drawdown series from equity curve for charting.

    Args:
        equity_curve: List of dicts with 'time' (timestamp) and 'value' keys

    Returns:
        Dict mapping timestamp (float) to drawdown percentage (float, negative values)
    """
    if not equity_curve or len(equity_curve) < 2:
        return {}

    try:
        times = [p['time'] for p in equity_curve]
        values = pd.Series([p['value'] for p in equity_curve], dtype=float)

        cummax = values.cummax()
        drawdown = ((values - cummax) / cummax) * 100  # as percentage

        dd_dict = {}
        for i, (ts, dd_val) in enumerate(zip(times, drawdown)):
            try:
                dd_dict[float(ts)] = round(float(dd_val), 4) if not (pd.isna(dd_val) or np.isinf(dd_val)) else 0.0
            except (ValueError, TypeError):
                continue

        return dd_dict
    except Exception:
        return {}


def compute_benchmark_from_prices(
    ticker: str,
    start_date: str,
    end_date: str,
    initial_value: float = 1.0,
) -> tuple:
    """
    Fetch benchmark (buy-and-hold) price data and compute equity, stats, and drawdown.

    Args:
        ticker: Stock symbol
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        initial_value: Starting value for equity normalization

    Returns:
        Tuple of (benchmark_equity, benchmark_stats, benchmark_drawdown)
        Each may be None if data is unavailable.
    """
    try:
        from app.services.signal_extractor import get_price_data_for_range

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        df = get_price_data_for_range(ticker, start_dt, end_dt)
        if df is None or len(df) < 2:
            # Fallback to yfinance
            try:
                import yfinance as yf
                df = yf.download(ticker, start=start_date, end=end_date, progress=False)
                if len(df) < 2:
                    return None, None, None
            except Exception:
                return None, None, None

        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        # Normalize to initial_value
        bench_equity_series = (close / close.iloc[0]) * initial_value

        # Benchmark equity curve
        benchmark_equity = []
        for idx, val in bench_equity_series.items():
            ts = idx.timestamp() if hasattr(idx, 'timestamp') else pd.Timestamp(idx).timestamp()
            benchmark_equity.append({"time": float(ts), "value": float(val)})

        # Benchmark stats
        bench_returns = close.pct_change().dropna()
        bench_returns = bench_returns.replace([np.inf, -np.inf], np.nan).dropna()

        if len(bench_returns) >= 2:
            bench_total_return = (float(close.iloc[-1]) / float(close.iloc[0])) - 1.0
            bench_sharpe = float((bench_returns.mean() / bench_returns.std()) * np.sqrt(252)) if bench_returns.std() > 0 else 0.0

            cummax = close.cummax()
            bench_drawdown = ((close - cummax) / cummax) * 100
            bench_max_dd = float(bench_drawdown.min())

            benchmark_stats = {
                'Benchmark Return [%]': round(bench_total_return * 100, 4),
                'Benchmark Sharpe Ratio': round(bench_sharpe, 4) if not np.isnan(bench_sharpe) else 0.0,
                'Benchmark Max Drawdown [%]': round(bench_max_dd, 4),
            }
        else:
            bench_drawdown = pd.Series(dtype=float)
            benchmark_stats = None

        # Benchmark drawdown dict
        benchmark_drawdown = {}
        for idx, dd_val in bench_drawdown.items():
            ts = idx.timestamp() if hasattr(idx, 'timestamp') else pd.Timestamp(idx).timestamp()
            benchmark_drawdown[float(ts)] = round(float(dd_val), 4)

        return benchmark_equity, benchmark_stats, benchmark_drawdown

    except Exception:
        return None, None, None


def compute_ohlcv_from_data(
    ticker: str,
    start_date: str,
    end_date: str,
) -> list:
    """
    Fetch OHLCV price data for charting.

    Args:
        ticker: Stock symbol
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)

    Returns:
        List of OHLCV dicts with time, open, high, low, close, volume keys
    """
    try:
        from app.services.signal_extractor import get_price_data_for_range

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        df = get_price_data_for_range(ticker, start_dt, end_dt)
        if df is None or len(df) < 2:
            return []

        ohlcv_records = []
        for idx in df.index:
            try:
                ts = idx.timestamp() if hasattr(idx, 'timestamp') else pd.Timestamp(idx).timestamp()
                row = df.loc[idx]
                # Handle both Series (single row) and scalar access patterns
                if isinstance(row, pd.Series):
                    open_val = float(row.get('Open', row.get('Close', 0)))
                    high_val = float(row.get('High', row.get('Close', 0)))
                    low_val = float(row.get('Low', row.get('Close', 0)))
                    close_val = float(row.get('Close', 0))
                    volume_val = float(row.get('Volume', 0))
                else:
                    close_val = float(row)
                    open_val = high_val = low_val = close_val
                    volume_val = 0

                ohlcv_records.append({
                    "time": float(ts),
                    "open": open_val,
                    "high": high_val,
                    "low": low_val,
                    "close": close_val,
                    "volume": volume_val,
                })
            except Exception:
                continue

        return ohlcv_records

    except Exception:
        return []


def _empty_stats() -> Dict[str, Any]:
    """Return an empty stats dict for edge cases."""
    return {
        'Start': None,
        'End': None,
        'Period': None,
        'Start Value': None,
        'End Value': None,
        'Total Return [%]': None,
        'Max Drawdown [%]': None,
        'Sharpe Ratio': None,
        'Sortino Ratio': None,
    }