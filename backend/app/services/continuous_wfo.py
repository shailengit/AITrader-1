"""
Continuous True Walk-Forward Optimization implementation.

The core idea: For each rolling window,
1. Optimize parameters on training data
2. Get signal from training window's last day for the NEXT day
3. Trade ONLY on that next day (the first day of test window)
4. Repeat for the next rolling window

There is NO test period loop - we just trade the single day after each training window.
"""

import contextlib
import io
import warnings
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, cast

import pandas as pd
import numpy as np

# Suppress VBT warnings during optimization (expected with param arrays and WFO)
warnings.filterwarnings('ignore', message='.*multiple columns.*')
warnings.filterwarnings('ignore', message='.*Aggregating using.*')
warnings.filterwarnings('ignore', message='.*requires frequency to be set.*')
warnings.filterwarnings('ignore', message='.*Changing the frequency will create a copy.*')

from app.services.true_wfo_implementation import (
    extract_dates_from_code,
    calculate_window_configs,
    modify_code_dates,
    modify_code_dates_and_params
)
from app.services.portfolio_tracker import PortfolioTracker
from app.services.signal_extractor import (
    extract_signal_from_strategy,
    extract_ticker_from_code,
    get_price_for_date,
    get_price_data_for_range
)
from app.services.wfo_metrics import compute_ohlcv_from_data


def run_continuous_true_wfo(
    code: str,
    modified_code: str,
    strategy_params: Dict[str, Any],
    config: Dict[str, Any],
    param_names: List[str],
    combinations: List[tuple],
    metric_name: str,
    result: Dict[str, Any],
    output_buffer: io.StringIO
) -> Dict[str, Any]:
    """
    Run continuous True WFO that uses training window's last day indicators
    to generate signals for the next trading day.

    Algorithm:
    1. For each training window, optimize parameters on training data
    2. Execute strategy with best params on training window's last day
    3. Get entries/exits for that day - this determines signal for NEXT day
    4. Execute trade NEXT day (BUY if position=0 and entry=True, SELL if position=1 and exit=True)
    5. Maintain portfolio state across windows
    6. NO test period loop - just trade the single day after each training window
    """
    wfo_conf = config.get("wfo", {})
    train_days = wfo_conf.get("train_days")
    test_days = wfo_conf.get("test_days")
    split_method = wfo_conf.get("splitMethod", "ratio")

    # Calculate windows
    # For True WFO, always auto-calculate to use ALL possible windows (step 1 day at a time)
    if split_method == "fixed" and train_days is not None and test_days is not None:
        n_windows = 0  # Will be auto-calculated based on fixed days
    else:
        # For ratio-based True WFO, use 0 to auto-calculate max windows
        # This ensures we trade every single day in the date range
        n_windows = 0

    dates = extract_dates_from_code(code)
    if not dates:
        result["output"] += "ERROR: Could not parse dates from code\n"
        return result

    start_date, end_date = dates
    window_configs = calculate_window_configs(
        start_date, end_date, n_windows,
        wfo_conf.get("type", "rolling"), wfo_conf,
        is_true_wfo=True  # True WFO always steps 1 day at a time
    )

    # Validate windows
    valid_windows = []
    for cfg in window_configs:
        try:
            train_start = datetime.strptime(cfg['train_start'], "%Y-%m-%d")
            train_end = datetime.strptime(cfg['train_end'], "%Y-%m-%d")
            test_start = datetime.strptime(cfg['test_start'], "%Y-%m-%d")

            train_d = (train_end - train_start).days

            if train_d >= 14:
                valid_windows.append(cfg)
        except:
            continue

    window_configs = valid_windows

    if not window_configs:
        result["output"] += "ERROR: No valid windows\n"
        return result

    result["output"] += f"Processing {len(window_configs)} windows continuously...\n"

    ticker = extract_ticker_from_code(code)
    result["output"] += f"Trading ticker: {ticker}\n"

    # Initialize portfolio tracker
    tracker = PortfolioTracker(initial_cash=100000.0)
    # Initialize at the start of the first window's test period
    first_test_start = datetime.strptime(window_configs[0]['test_start'], "%Y-%m-%d")
    tracker.initialize(first_test_start - timedelta(days=1))

    window_results = []
    position = 0  # Track current position state (0 = no position, 1 = long)
    current_signal = 'HOLD'  # Track signal for current window
    current_trade_date = None  # Track trade date for current window

    for i, cfg in enumerate(window_configs):
        result["output"] += f"\nWindow {i+1}/{len(window_configs)}:\n"

        best_params = None
        best_val = 0.0
        current_signal = 'HOLD'  # Reset signal for each window
        current_trade_date = None

        try:
            # Run optimization on training data
            train_code = modify_code_dates(modified_code, cfg['train_start'], cfg['train_end'])

            with contextlib.redirect_stdout(output_buffer):
                # Inject DataService into globals
                from app.services.data_service import DataService
                train_globals = {'DataService': DataService}
                exec(train_code, train_globals)

                # Check for portfolio - could be named 'pf' or 'portfolio'
                if 'pf' in train_globals:
                    train_pf = train_globals['pf']
                elif 'portfolio' in train_globals:
                    train_pf = train_globals['portfolio']
                else:
                    result["output"] += "  Warning: No training portfolio found (pf or portfolio variable missing)\n"
                    continue
                train_returns = train_pf.returns()  # type: ignore[attr-defined]

                # Calculate metric for optimization
                if isinstance(train_returns, pd.DataFrame):
                    if metric_name == "sharpe":
                        col_means = train_returns.mean(axis=0)
                        col_stds = train_returns.std(axis=0)
                        # Handle zero/NaN std by replacing with inf, then clip
                        m_vals = (col_means / col_stds.clip(min=1e-10)) * np.sqrt(252)
                        # Replace inf with NaN for later handling
                        m_vals = m_vals.replace([np.inf, -np.inf], np.nan)
                    else:
                        m_vals = (1 + train_returns).prod(axis=0) - 1
                else:
                    m_vals: Any
                    if metric_name == "sharpe":
                        std_val = train_returns.std()
                        # Handle zero/NaN std - return 0Sharpe if insufficient data
                        if std_val is None or std_val == 0 or pd.isna(std_val):
                            m_vals = 0.0
                        else:
                            m_vals = train_returns.mean() / std_val * np.sqrt(252)
                        # Check if result is NaN or inf
                        if pd.isna(m_vals) or np.isinf(m_vals):
                            m_vals = 0.0
                    else:
                        m_vals = (1 + train_returns).prod() - 1

                # Get best parameter combination
                if isinstance(m_vals, pd.Series):
                    best_idx = int(m_vals.values.argmax())
                    best_val = m_vals.iloc[best_idx]
                elif hasattr(m_vals, 'argmax'):
                    # Check if m_vals is a scalar (0-d array)
                    if hasattr(m_vals, 'ndim') and m_vals.ndim == 0:
                        best_idx = 0
                        best_val = float(m_vals)
                    else:
                        best_idx = int(m_vals.argmax())
                        best_val = m_vals[best_idx] if best_idx < len(m_vals) else m_vals
                else:
                    best_idx = 0
                    best_val = float(m_vals) if isinstance(m_vals, (np.floating, float)) else m_vals

                # Handle case where there are no parameters (empty combinations)
                # In this case, we just use the default parameters from the code
                if len(combinations) > 0 and best_idx < len(combinations):
                    best_params = dict(zip(param_names, combinations[best_idx]))
                else:
                    # No parameters to optimize - use defaults from code
                    best_params = {}

                result["output"] += f"  Training: {cfg['train_start']} to {cfg['train_end']}\n"
                result["output"] += f"  Best params: {best_params}\n"
                result["output"] += f"  Best training metric: {float(best_val):.4f}\n"

        except Exception as err:
            result["output"] += f"  Training error: {err}\n"
            continue

        if best_params is None:
            continue

        # Get the NEXT day after training window - this is when we trade
        # For True WFO Continuous, we don't have a test period - we trade the single day
        # immediately after the training window ends
        next_day = datetime.strptime(cfg['train_end'], "%Y-%m-%d") + timedelta(days=1)

        # Skip weekends - if next day is weekend, use next weekday
        while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
            next_day += timedelta(days=1)

        trade_date = next_day

        result["output"] += f"  Training window end: {datetime.strptime(cfg['train_end'], '%Y-%m-%d').strftime('%Y-%m-%d')}\n"
        result["output"] += f"  Trade date (next trading day after training): {trade_date.strftime('%Y-%m-%d')}\n"

        # Execute strategy on training window with best params to get signal
        # for the NEXT trading day
        try:
            # Run strategy on full training window with best params
            train_code_with_params = modify_code_dates_and_params(
                modified_code,
                cfg['train_start'],
                cfg['train_end'],
                best_params
            )

            with contextlib.redirect_stdout(output_buffer):
                from app.services.data_service import DataService
                train_globals = {'DataService': DataService}
                exec(train_code_with_params, train_globals)

                if 'entries' not in train_globals or 'exits' not in train_globals:
                    result["output"] += f"  Warning: No entries/exits found in training result\n"
                    continue

                entries: Any = train_globals['entries']
                exits: Any = train_globals['exits']

                result["output"] += f"  entries type: {type(entries)}\n"
                result["output"] += f"  entries length: {len(entries) if hasattr(entries, '__len__') else 'N/A'}\n"
                result["output"] += f"  entries sum: {entries.sum().sum() if isinstance(entries, pd.DataFrame) else (entries.sum() if isinstance(entries, pd.Series) else 'N/A')}\n"

                # Get signal for the trade date (next day after training)
                date_str = trade_date.strftime('%Y-%m-%d')
                entry_val = None
                exit_val = None

                # Handle DataFrame case (from optimization with multiple parameters)
                if isinstance(entries, pd.DataFrame):
                    # Get the most recent signal across all parameter combinations
                    # Find the last row where any entry or exit is True
                    if trade_date in entries.index:
                        entry_row = entries.loc[trade_date]
                        exit_row = exits.loc[trade_date] if isinstance(exits, pd.DataFrame) else pd.Series([], dtype=bool)
                        entry_val = entry_row.any() if len(entry_row) > 0 else False
                        exit_val = exit_row.any() if len(exit_row) > 0 else False
                        result["output"] += f"  entry[{date_str}]={entry_val}, exit[{date_str}]={exit_val} [DataFrame match]\n"
                    else:
                        # Find the most recent signal in the DataFrame
                        last_true_row = None
                        for idx in reversed(entries.index):
                            if entries.loc[idx].any():
                                last_true_row = idx
                                break
                        if last_true_row is not None:
                            entry_val = entries.loc[last_true_row].any()
                            exit_val = exits.loc[last_true_row].any() if isinstance(exits, pd.DataFrame) else False
                            result["output"] += f"  Found most recent entry at {last_true_row}, using for {date_str}\n"
                elif isinstance(entries, pd.Series):
                    # Try exact date match first
                    if trade_date in entries.index:
                        entry_val = bool(entries.loc[trade_date])
                        exit_val = bool(exits.loc[trade_date]) if isinstance(exits, pd.Series) else False
                        result["output"] += f"  entry[{date_str}]={entry_val}, exit[{date_str}]={exit_val} [exact match]\n"
                    else:
                        # Try string matching
                        for idx, val in entries.items():
                            if date_str in str(idx) and bool(val):
                                entry_val = True
                                break
                        if isinstance(exits, pd.Series):
                            for idx, val in exits.items():
                                if date_str in str(idx) and bool(val):
                                    exit_val = True
                                    break

                # Extract signal based on position
                # Key insight: For True WFO, we use the signal from the LAST day of training
                # to determine what to do on the NEXT day (trade_date)
                # The strategy was run on training data, so we need to get the signal from train_end
                train_end_date = datetime.strptime(cfg['train_end'], "%Y-%m-%d")
                signal = _extract_signal_from_entries_exits(entries, exits, train_end_date, position)

                # If we can't find a signal for the exact train_end_date, use the most recent signal
                # from the training window (the last valid entry/exit)
                if signal == 'HOLD':
                    result["output"] += f"  No exact signal for train end {cfg['train_end']}, checking most recent signal...\n"
                    # Get the last True entry or exit from the training window
                    last_entry_date = None
                    last_exit_date = None

                    # Handle DataFrame case (from optimization with multiple parameters)
                    if isinstance(entries, pd.DataFrame):
                        # For DataFrames, check if ANY column has a True value for each row
                        for idx in entries.index:
                            if entries.loc[idx].any():
                                last_entry_date = idx
                        if isinstance(exits, pd.DataFrame):
                            for idx in exits.index:
                                if exits.loc[idx].any():
                                    last_exit_date = idx
                    elif isinstance(entries, pd.Series):
                        # For Series, iterate through items
                        for idx, val in entries.items():
                            if bool(val):
                                last_entry_date = idx
                        if isinstance(exits, pd.Series):
                            for idx, val in exits.items():
                                if bool(val):
                                    last_exit_date = idx

                    # Determine what signal to use based on which is more recent
                    if last_entry_date is not None and last_exit_date is not None:
                        result["output"] += f"  Last entry: {last_entry_date}, Last exit: {last_exit_date}\n"
                        if last_entry_date > last_exit_date:
                            signal = 'BUY'
                        else:
                            signal = 'SELL'
                    elif last_entry_date is not None:
                        signal = 'BUY'
                    elif last_exit_date is not None:
                        signal = 'SELL'

                result["output"] += f"  Signal for {trade_date.strftime('%Y-%m-%d')}: {signal}\n"
                result["output"] += f"  Current position: {position}\n"

                # Capture signal and trade date for window results
                current_signal = signal
                current_trade_date = trade_date.strftime('%Y-%m-%d')

                # Get price for the trade date
                try:
                    price = get_price_for_date(ticker, trade_date)
                except Exception as price_err:
                    result["output"] += f"  Price retrieval error: {price_err}\n"
                    price = 0

                # Execute trade if signal is BUY or SELL
                if price > 0 and signal in ['BUY', 'SELL']:
                    trade = None

                    if signal == 'BUY' and position == 0:
                        # Enter long position
                        trade = tracker.process_signal(
                            ticker=ticker,
                            signal='BUY',
                            price=price,
                            date=trade_date,
                            size_pct=1.0
                        )
                        position = 1
                        if trade:
                            result["output"] += f"  BUY {trade.shares:.2f} shares @ ${price:.2f} on {trade_date.strftime('%Y-%m-%d')}\n"
                        else:
                            result["output"] += f"  BUY skipped (insufficient funds or error)\n"

                    elif signal == 'SELL' and position == 1:
                        # Exit long position
                        trade = tracker.process_signal(
                            ticker=ticker,
                            signal='SELL',
                            price=price,
                            date=trade_date,
                            size_pct=1.0
                        )
                        position = 0
                        if trade:
                            result["output"] += f"  SELL {trade.shares:.2f} shares @ ${price:.2f} on {trade_date.strftime('%Y-%m-%d')}\n"
                            if trade.realized_pnl:
                                result["output"] += f"    Realized P&L: ${trade.realized_pnl:.2f}\n"
                        else:
                            result["output"] += f"  SELL skipped (no position to sell or error)\n"

                    if trade:
                        result["output"] += f"    Trade: {trade.action} {trade.shares:.2f} shares @ ${trade.price:.2f}\n"

                    # Update prices and record state after each trade
                    if tracker.current_state is not None:
                        tracker.current_state.update_prices({ticker: price}, trade_date)
                    tracker.record_state()

        except Exception as err:
            result["output"] += f"  Signal extraction error: {err}\n"
            import traceback
            result["output"] += f"  Traceback: {traceback.format_exc()}\n"
            continue

        window_results.append({
            "window": i + 1,
            "train_start": cfg['train_start'],
            "train_end": cfg['train_end'],
            "test_date": current_trade_date,
            "next_day_trade": trade_date.strftime('%Y-%m-%d'),
            "best_param": ", ".join([f"{k}={v}" for k, v in best_params.items()]),
            "best_params": best_params,
            "train_metric": float(best_val),
            "signal": current_signal,
            "portfolio_value": tracker.current_state.total_value if tracker.current_state else 0
        })

    result["windows"] = window_results
    result["oos_equity"] = tracker.equity_curve
    result["trades"] = tracker.get_trade_history()

    # Warning if no trades generated
    if not tracker.get_trade_history():
        result["output"] += "\nWARNING: No trades were generated during walk-forward.\n"
        result["output"] += "This can happen when:\n"
        result["output"] += "  - Training windows are too short for indicator warmup\n"
        result["output"] += "  - Strategy signals never trigger (entries/exits all False)\n"
        result["output"] += "  - Parameters found in training don't produce signals on next day\n"

    # Compute comprehensive stats from the accumulated equity curve
    from app.services.wfo_metrics import (
        compute_wfo_stats,
        compute_drawdown_from_equity,
        compute_benchmark_from_prices,
    )

    if len(tracker.equity_curve) > 1:
        stats = compute_wfo_stats(
            equity_curve=tracker.equity_curve,
            initial_cash=tracker.initial_cash,
            trades=tracker.get_trade_history(),
        )

        # Merge tracker's trade-level stats
        tracker_summary = tracker.get_summary()
        if tracker_summary.get('total_trades', 0) > 0:
            stats['Total Trades'] = tracker_summary['total_trades']
            stats['Win Rate [%]'] = tracker_summary['win_rate'] * 100
            stats['Avg Winning Trade [%]'] = tracker_summary.get('avg_win', 0)
            stats['Avg Losing Trade [%]'] = tracker_summary.get('avg_loss', 0)

        # Add best params from last window
        if window_results:
            final_params = cast(Dict[str, Any], window_results[-1]).get('best_params', {})
            for p_name, p_val in final_params.items():
                stats[f"Best {p_name}"] = p_val

        result["stats"] = stats
        result["output"] += f"Comprehensive stats computed: {len(stats)} fields\n"

        # Compute drawdown
        result["drawdown"] = compute_drawdown_from_equity(tracker.equity_curve)
        result["output"] += f"Drawdown computed: {len(result.get('drawdown', {}))} points\n"

        # Get benchmark data
        try:
            first_ts = tracker.equity_curve[0]['time']
            last_ts = tracker.equity_curve[-1]['time']
            start_dt = datetime.fromtimestamp(first_ts).strftime("%Y-%m-%d")
            end_dt = datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d")
            initial_val = tracker.equity_curve[0]['value']

            bench_equity, bench_stats, bench_dd = compute_benchmark_from_prices(
                ticker=ticker,
                start_date=start_dt,
                end_date=end_dt,
                initial_value=initial_val,
            )
            if bench_equity:
                result["benchmark_equity"] = bench_equity
                result["output"] += f"Benchmark equity: {len(bench_equity)} points\n"
            if bench_stats:
                if 'stats' not in result:
                    result["stats"] = {}
                result["stats"].update(bench_stats)
            if bench_dd:
                result["benchmark_drawdown"] = bench_dd
                result["output"] += f"Benchmark drawdown: {len(bench_dd)} points\n"
        except Exception as bench_err:
            result["output"] += f"Warning: Could not compute benchmark: {bench_err}\n"
    else:
        result["stats"] = tracker.get_summary()
        result["output"] += "Warning: Insufficient equity data for comprehensive stats\n"

    # Set equity for frontend display
    if tracker.equity_curve:
        result["equity"] = [
            {"time": float(p['time']), "value": float(p['value'])}
            for p in tracker.equity_curve
        ]
        result["best_equity"] = tracker.equity_curve

    # Extract OHLCV data for Price Action chart
    try:
        # Get the date range from the original code
        dates = extract_dates_from_code(code)
        if dates:
            start_date, end_date = dates
            ohlcv_data = compute_ohlcv_from_data(ticker, start_date, end_date)
            result["ohlcv"] = ohlcv_data
            result["output"] += f"OHLCV data extracted: {len(ohlcv_data)} bars\n"
        else:
            result["output"] += "Warning: Could not extract OHLCV - no dates found in code\n"
    except Exception as ohlcv_err:
        result["output"] += f"Warning: Could not extract OHLCV: {ohlcv_err}\n"

    result["output"] += f"\nContinuous True WFO complete.\n"
    if tracker.current_state:
        result["output"] += f"Final portfolio value: ${tracker.current_state.total_value:,.2f}\n"
        total_return = (tracker.current_state.total_value / tracker.initial_cash - 1) * 100
        result["output"] += f"Total return: {total_return:.2f}%\n"

    return result


def _extract_signal_from_entries_exits(
    entries: Any,
    exits: Any,
    target_date: datetime,
    current_position: int
) -> str:
    """
    Extract trading signal from entries/exits arrays for a specific date.

    Args:
        entries: VectorBT entries Series/array
        exits: VectorBT exits Series/array
        target_date: Date to extract signal for
        current_position: Current position state (0 or 1)

    Returns:
        'BUY', 'SELL', or 'HOLD'
    """
    date_str = target_date.strftime('%Y-%m-%d')

    # Handle Series (most common for VectorBT)
    if isinstance(entries, pd.Series):
        # Try exact date match first
        if target_date in entries.index:
            entry_signal = bool(entries.loc[target_date])
            exit_signal = bool(exits.loc[target_date]) if isinstance(exits, pd.Series) else False
        else:
            # Try string matching
            entry_signal = False
            exit_signal = False
            for idx, val in entries.items():
                idx_str = str(idx)
                if date_str in idx_str and bool(val):
                    entry_signal = True
                    break
            if isinstance(exits, pd.Series):
                for idx, val in exits.items():
                    idx_str = str(idx)
                    if date_str in idx_str and bool(val):
                        exit_signal = True
                        break

        # Determine signal based on position and signal type
        if entry_signal and current_position == 0:
            return 'BUY'
        elif exit_signal and current_position == 1:
            return 'SELL'
        else:
            return 'HOLD'

    # Handle numpy arrays
    elif isinstance(entries, np.ndarray):
        return 'HOLD'  # Default for array case

    return 'HOLD'
