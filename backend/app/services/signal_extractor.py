"""
Extract trading signals from VectorBT strategy code for single-day execution.
"""

import re
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict

# Import the freq-fix capable date modifier
from app.services.true_wfo_implementation import modify_code_dates
from app.services.data_service import SafeDataService


def transform_code_for_local_data(code: str, start_date: str, end_date: str) -> str:
    """
    Transform strategy code to use local database instead of YFData.download.

    This replaces:
    - vbt.YFData.download(...) with DataService.get_ohlcv_data(ticker, start, end)
    - data.get('Column') with data['Column']
    """
    modified = code

    # Extract ticker from the download call
    ticker_match = re.search(r"vbt\.YFData\.download\(\s*['\"](\w+)['\"]", modified)
    if not ticker_match:
        # Try alternate format: YFData.download
        ticker_match = re.search(r"YFData\.download\(\s*['\"](\w+)['\"]", modified)

    if ticker_match:
        ticker = ticker_match.group(1).upper()

        # Replace the YFData.download call with DataService call
        # Match multi-line download calls
        modified = re.sub(
            r"\w+\s*=\s*vbt\.YFData\.download\([^)]+(?:\([^)]*\)[^)]*)*\)",
            f"data = DataService.get_ohlcv_data('{ticker}', '{start_date}', '{end_date}')",
            modified,
            flags=re.DOTALL
        )

        # Also try without vbt. prefix
        modified = re.sub(
            r"\w+\s*=\s*YFData\.download\([^)]+(?:\([^)]*\)[^)]*)*\)",
            f"data = DataService.get_ohlcv_data('{ticker}', '{start_date}', '{end_date}')",
            modified,
            flags=re.DOTALL
        )

        # Replace data.get('Column') with data['Column']
        modified = re.sub(
            r"data\.get\(['\"](\w+)['\"]\)",
            r"data['\1']",
            modified
        )

    return modified


def extract_signal_from_strategy(code: str, target_date: datetime,
                                   price_data: Optional[pd.DataFrame] = None) -> str:
    """
    Execute strategy code and extract the trading signal for a specific date.

    Args:
        code: Strategy code to execute
        target_date: Date to extract signal for
        price_data: Optional pre-loaded price data

    Returns:
        'BUY', 'SELL', or 'HOLD'
    """
    try:
        # Use a 50-day window to ensure enough data for indicators to warm up
        # SMA-50 needs 50 days to warm up, so we use 50 days before the target
        # Most common indicators (SMA-50, EMA-20, etc.) need at least 20-50 days
        start_date = target_date - timedelta(days=45)
        end_date = target_date + timedelta(days=2)

        # Transform code to use local database instead of YFData.download
        modified = transform_code_for_local_data(
            code,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )

        # Replace the dates in the code with the new window
        modified = re.sub(
            r"start\s*=\s*['\"]\d{4}-\d{2}-\d{2}['\"]",
            f"start='{start_date.strftime('%Y-%m-%d')}'",
            modified
        )
        modified = re.sub(
            r"end\s*=\s*['\"]\d{4}-\d{2}-\d{2}['\"]",
            f"end='{end_date.strftime('%Y-%m-%d')}'",
            modified
        )

        # Execute to get signals with DataService available
        globals_dict = {'__name__': '__main__', 'DataService': SafeDataService}
        exec(modified, globals_dict)

        # Extract signals from the executed strategy
        # VectorBT strategies typically create 'entries' and 'exits' variables
        if 'entries' in globals_dict and 'exits' in globals_dict:
            entries = globals_dict['entries']
            exits = globals_dict['exits']

            # Handle different return types
            if isinstance(entries, pd.Series):
                # Check if target_date is in the index
                date_str = target_date.strftime('%Y-%m-%d')

                # Debug: Show signal statistics for the window
                entry_sum = entries.sum() if len(entries) > 0 else 0
                exit_sum = exits.sum() if isinstance(exits, pd.Series) and len(exits) > 0 else 0
                print(f"DEBUG: Signal window - entries sum={entry_sum}, exits sum={exit_sum}")
                print(f"DEBUG: Signal window - entries type={entries.dtype}, exits type={exits.dtype if hasattr(exits, 'dtype') else type(exits)}")
                print(f"DEBUG: Signal window - target_date={target_date}, date_str={date_str}")
                print(f"DEBUG: Signal window - entries index first={entries.index[0] if len(entries) > 0 else 'N/A'}")
                print(f"DEBUG: Signal window - entries index last={entries.index[-1] if len(entries) > 0 else 'N/A'}")
                print(f"DEBUG: Signal window - entries index type={type(entries.index)}")
                print(f"DEBUG: Signal window - target_date in entries.index: {target_date in entries.index}")
                # Show index as strings
                idx_list = [str(idx) for idx in entries.index[:5]]
                print(f"DEBUG: Signal window - first 5 index strings: {idx_list}")

                # Try exact match first
                # Debug: check exact match
                target_date_check = target_date
                print(f"DEBUG: Checking exact match - target_date={target_date_check}, type={type(target_date_check)}")
                if target_date_check in entries.index:
                    print(f"DEBUG: EXACT MATCH FOUND!")
                    entry_signal = bool(entries.loc[target_date])
                    exit_signal = bool(exits.loc[target_date]) if isinstance(exits, pd.Series) and target_date in exits.index else False
                    if entry_signal and not exit_signal:
                        return 'BUY'
                    elif exit_signal and not entry_signal:
                        return 'SELL'
                    return 'HOLD'

                # Try string matching as fallback
                entry_signal = False
                exit_signal = False

                # Find the signal for the target date or the most recent signal
                for idx, val in entries.items():
                    idx_str = str(idx)
                    if date_str in idx_str:
                        entry_signal = bool(val)
                        break

                if isinstance(exits, pd.Series):
                    for idx, val in exits.items():
                        idx_str = str(idx)
                        if date_str in idx_str:
                            exit_signal = bool(val)
                            break

                # If no signal found for exact date, use the most recent signal
                if not entry_signal:
                    # Find the last True entry signal
                    for idx, val in entries.items():
                        if bool(val):
                            entry_signal = True
                            break

                if isinstance(exits, pd.Series) and not exit_signal:
                    for idx, val in exits.items():
                        if bool(val):
                            exit_signal = True
                            break

                if entry_signal and not exit_signal:
                    return 'BUY'
                elif exit_signal and not entry_signal:
                    return 'SELL'

            elif isinstance(entries, (bool, int)):
                # Single value returned
                if entries and not exits:
                    return 'BUY'
                elif exits and not entries:
                    return 'SELL'

        # Alternative: check for signal variables
        if 'signal' in globals_dict:
            signal = globals_dict['signal']
            if isinstance(signal, str):
                return signal.upper() if signal.upper() in ['BUY', 'SELL', 'HOLD'] else 'HOLD'
            elif isinstance(signal, (int, float)):
                if signal > 0:
                    return 'BUY'
                elif signal < 0:
                    return 'SELL'

        return 'HOLD'

    except Exception as e:
        print(f"Signal extraction error: {e}")
        return 'HOLD'


def modify_code_for_single_day(code: str, target_date: datetime) -> str:
    """
    Modify strategy code to run for a single day only.

    This involves:
    1. Replacing the date range with a 5-day window around target date
    2. This ensures we have data even if target_date is a weekend/holiday
    3. The signal extraction will look for the specific date
    """
    from datetime import timedelta

    # Create a 5-day window around target date to ensure we get data
    start_date = target_date - timedelta(days=2)
    end_date = target_date + timedelta(days=2)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Replace start and end dates
    modified = code

    # Pattern for start='YYYY-MM-DD' or start="YYYY-MM-DD"
    modified = re.sub(
        r"start\s*=\s*['\"]\d{4}-\d{2}-\d{2}['\"]",
        f"start='{start_str}'",
        modified
    )

    # Pattern for end='YYYY-MM-DD' or end="YYYY-MM-DD"
    modified = re.sub(
        r"end\s*=\s*['\"]\d{4}-\d{2}-\d{2}['\"]",
        f"end='{end_str}'",
        modified
    )

    return modified


def extract_ticker_from_code(code: str) -> str:
    """Extract the primary ticker from strategy code."""
    # Look for YFData.download pattern
    patterns = [
        r"YFData\.download\(['\"](\w+)['\"]",
        r"download\(['\"](\w+)['\"]",
        r"['\"]([A-Z]{1,5})['\"]",
    ]

    for pattern in patterns:
        match = re.search(pattern, code)
        if match:
            return match.group(1).upper()

    return "AAPL"  # Default


def get_price_for_date(ticker: str, date: datetime) -> float:
    """Fetch closing price for a specific date."""
    # Skip weekends - no trading data available
    if date.weekday() >= 5:  # Saturday=5, Sunday=6
        return 0.0

    try:
        from app.services.data_service import get_data

        date_str = date.strftime("%Y-%m-%d")
        df = get_data(ticker, date_str, date_str)

        if df is not None and len(df) > 0:
            return float(df['Close'].iloc[0])

        # For single-day lookups, yfinance has limitations. Instead, try to get
        # the most recent price before or on the target date by using a small range.
        # If the database doesn't have this date, it's likely missing data.
        return 0.0

    except Exception as e:
        # Silently return 0.0 for missing data instead of printing
        return 0.0


def get_price_data_for_range(ticker: str, start_date: datetime,
                              end_date: datetime) -> Optional[pd.DataFrame]:
    """Fetch price data for a date range."""
    try:
        from app.services.data_service import get_data

        df = get_data(
            ticker,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )
        return df

    except Exception as e:
        print(f"Error fetching price data: {e}")
        return None


def extract_signals_for_dates(code: str, ticker: str,
                               dates: list) -> Dict[datetime, str]:
    """
    Extract signals for multiple dates.

    Returns:
        Dict mapping date to signal ('BUY', 'SELL', 'HOLD')
    """
    signals = {}
    for date in dates:
        signal = extract_signal_from_strategy(code, date)
        signals[date] = signal
    return signals
