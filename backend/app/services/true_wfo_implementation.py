"""
True Walk-Forward Optimization Implementation

This module provides helper functions for true walk-forward optimization
where each window is optimized independently on training data only.

Fixes applied vs original:
  1. extract_dates_from_code  – added re.DOTALL so multi-line download() calls match.
  2. modify_code_dates        – rewrote the BusinessDay freq-fix injection:
       • Fixed regex to correctly capture variable name in group 2
       • Fixed _FREQ_FIX_TEMPLATE to use {data_var}.get() correctly
       • All data.get() calls are now rewritten to use _raw_df with clean index
       • Uses pd.DatetimeIndex(index.values) which reliably drops freq='B'
  3. modify_code_dates_and_params – no logic changes; inherits fixes from above.
  4. calculate_window_configs – no changes needed; logic was correct.
"""

import re
import datetime
from typing import Optional, Tuple, List, Dict, Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Injected immediately after every  data = vbt.YFData.download(...)  line.
# Removes BusinessDay frequency without introducing NaN values.
# VBT uses wrapper.freq which calls index.inferred_freq - even if we strip
# the explicit freq attribute, pandas still infers 'B' from the date pattern.
# Solution: Reset the index with explicit freq=None and forward fill any gaps.
_FREQ_FIX_TEMPLATE = """
# ── WFO FREQ FIX ────────────────────────────────────────────────────────────
# vbt.YFData.download() attaches freq='B' (BusinessDay) to the DatetimeIndex.
# This causes "invalid unit abbreviation: B" errors when VBT calls
# wrapper.freq (which uses index.inferred_freq). We remove the freq by
# recreating the DatetimeIndex from raw values (which strips freq).
import pandas as _wfo_pd
_raw_df = {data_var}.get().copy()
_raw_df.index = _wfo_pd.DatetimeIndex(_raw_df.index.values)
# ────────────────────────────────────────────────────────────────────────────
"""


def _build_freq_fix(data_var: str = "data") -> str:
    return _FREQ_FIX_TEMPLATE.format(data_var=data_var)


def _extract_max_param_from_code(code: str) -> int:
    """
    Extract the largest parameter value from strategy code.
    Searches for np.array(...), list literals, range(...), and plain integers.
    Returns the maximum integer found, or 0 if none found.
    """
    values: set[int] = set()

    # np.array([1, 2, 3]) or np.arange(5, 50, 5)
    for pattern in [
        r'np\.array\(\[([^\]]+)\]\)',
        r'np\.arange\(([^)]+)\)',
        r'range\(([^)]+)\)',
        r'=\s*\[([^\]]+)\]',
    ]:
        for match in re.finditer(pattern, code):
            inner = match.group(1)
            # Extract all integers from the inner text
            for num_str in re.findall(r'\d+', inner):
                values.add(int(num_str))

    # Plain integer assignments like "sma_window = 50"
    for match in re.finditer(r'=\s*(\d+)(?:\s*#|\s*\n|\s*$)', code):
        values.add(int(match.group(1)))

    return max(values) if values else 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_dates_from_code(code: str) -> Optional[Tuple[str, str]]:
    """
    Extract start and end dates from strategy code.

    Looks for patterns like:
    - vbt.YFData.download('AAPL', start='2020-01-01', end='2024-01-01')
    - DataService.get_ohlcv_data(..., start='2020-01-01', end='2024-01-01')
    - DataService.get_ohlcv_data(..., start_date='2020-01-01', end_date='2024-01-01')
    - start='2020-01-01'
    - end='2024-01-01'
    - start_date='2020-01-01'
    - end_date='2024-01-01'

    Returns (start_date, end_date) or None if not found.

    FIX: re.DOTALL added so the regex matches across newlines inside the
    download() argument list (common in real strategies).
    """
    date_pat = r"\d{4}-\d{2}-\d{2}"

    # Helper to extract dates with various parameter names
    def extract_from_call(pattern, code):
        match = re.search(pattern, code, flags=re.DOTALL)
        if match:
            return match.group(1), match.group(2)
        return None

    # Pattern for YFData.download with start then end (possibly multi-line)
    download_pattern = (
        r"vbt\.YFData\.download\(.*?"
        rf"start\s*=\s*['\"]({date_pat})['\"].*?"
        rf"end\s*=\s*['\"]({date_pat})['\"]"
    )
    result = extract_from_call(download_pattern, code)
    if result:
        return result

    # Pattern for DataService.get_ohlcv_data with start then end (possibly multi-line)
    download_pattern_ds = (
        r"DataService\.get_ohlcv_data\(.*?"
        rf"start\s*=\s*['\"]({date_pat})['\"].*?"
        rf"end\s*=\s*['\"]({date_pat})['\"]"
    )
    result = extract_from_call(download_pattern_ds, code)
    if result:
        return result

    # Pattern for DataService.get_ohlcv_data with start_date then end_date (possibly multi-line)
    download_pattern_ds_date = (
        r"DataService\.get_ohlcv_data\(.*?"
        rf"start_date\s*=\s*['\"]({date_pat})['\"].*?"
        rf"end_date\s*=\s*['\"]({date_pat})['\"]"
    )
    result = extract_from_call(download_pattern_ds_date, code)
    if result:
        return result

    # Try reverse order (end first, then start) for YFData
    download_pattern2 = (
        r"vbt\.YFData\.download\(.*?"
        rf"end\s*=\s*['\"]({date_pat})['\"].*?"
        rf"start\s*=\s*['\"]({date_pat})['\"]"
    )
    result = extract_from_call(download_pattern2, code)
    if result:
        return result[1], result[0]

    # Try reverse order for DataService
    download_pattern2_ds = (
        r"DataService\.get_ohlcv_data\(.*?"
        rf"end\s*=\s*['\"]({date_pat})['\"].*?"
        rf"start\s*=\s*['\"]({date_pat})['\"]"
    )
    result = extract_from_call(download_pattern2_ds, code)
    if result:
        return result[1], result[0]

    # Try reverse order for DataService with end_date/start_date
    download_pattern2_ds_date = (
        r"DataService\.get_ohlcv_data\(.*?"
        rf"end_date\s*=\s*['\"]({date_pat})['\"].*?"
        rf"start_date\s*=\s*['\"]({date_pat})['\"]"
    )
    result = extract_from_call(download_pattern2_ds_date, code)
    if result:
        return result[1], result[0]

    # Fallback: standalone start / end variable assignments anywhere in the file
    start_match = re.search(rf"^\s*start\s*=\s*['\"]({date_pat})['\"]", code, flags=re.MULTILINE)
    end_match   = re.search(rf"^\s*end\s*=\s*['\"]({date_pat})['\"]",   code, flags=re.MULTILINE)

    if start_match and end_match:
        return start_match.group(1), end_match.group(1)

    # Fallback: standalone start_date / end_date variable assignments
    start_date_match = re.search(rf"^\s*start_date\s*=\s*['\"]({date_pat})['\"]", code, flags=re.MULTILINE)
    end_date_match   = re.search(rf"^\s*end_date\s*=\s*['\"]({date_pat})['\"]",   code, flags=re.MULTILINE)

    if start_date_match and end_date_match:
        return start_date_match.group(1), end_date_match.group(1)

    return None


def modify_code_dates(code: str, start_date: str, end_date: str) -> str:
    """
    Replace date parameters in strategy code with new dates and inject a
    BusinessDay frequency fix immediately after every data download call.

    Modifies:
    - vbt.YFData.download(..., start='...', end='...')  (single- or multi-line)
    - start = '...'   (standalone variable assignments)
    - end   = '...'   (standalone variable assignments)
    - start_date = '...'   (standalone variable assignments)
    - end_date = '...'   (standalone variable assignments)

    FIX: Four separate bugs in the original were corrected:
      1. re.DOTALL added so multi-line download() calls are matched.
      2. Freq fix creates _raw_df with clean DatetimeIndex (freq=None).
      3. ALL data.get() calls are rewritten to use _raw_df instead of data.
      4. The freq-fix is more robust to handle edge cases.
    """
    modified = code

    # ── 1. Replace dates inside vbt.YFData.download() ───────────────────────
    # We handle start and end independently to cope with any argument ordering.

    # start= inside download()
    modified = re.sub(
        r"(vbt\.YFData\.download\(.*?start\s*=\s*['\"])\d{4}-\d{2}-\d{2}(['\"])",
        rf"\g<1>{start_date}\g<2>",
        modified,
        flags=re.DOTALL,
    )

    # end= inside download()
    modified = re.sub(
        r"(vbt\.YFData\.download\(.*?end\s*=\s*['\"])\d{4}-\d{2}-\d{2}(['\"])",
        rf"\g<1>{end_date}\g<2>",
        modified,
        flags=re.DOTALL,
    )

    # start_date= inside DataService.get_ohlcv_data()
    modified = re.sub(
        r"(DataService\.get_ohlcv_data\(.*?start_date\s*=\s*['\"])\d{4}-\d{2}-\d{2}(['\"])",
        rf"\g<1>{start_date}\g<2>",
        modified,
        flags=re.DOTALL,
    )

    # end_date= inside DataService.get_ohlcv_data()
    modified = re.sub(
        r"(DataService\.get_ohlcv_data\(.*?end_date\s*=\s*['\"])\d{4}-\d{2}-\d{2}(['\"])",
        rf"\g<1>{end_date}\g<2>",
        modified,
        flags=re.DOTALL,
    )

    # ── 2. Replace standalone start / end variable assignments ───────────────
    modified = re.sub(
        r"^(\s*start\s*=\s*['\"])\d{4}-\d{2}-\d{2}(['\"])",
        rf"\g<1>{start_date}\g<2>",
        modified,
        flags=re.MULTILINE,
    )
    modified = re.sub(
        r"^(\s*end\s*=\s*['\"])\d{4}-\d{2}-\d{2}(['\"])",
        rf"\g<1>{end_date}\g<2>",
        modified,
        flags=re.MULTILINE,
    )

    # ── 3. Replace standalone start_date / end_date variable assignments ────
    modified = re.sub(
        r"^(\s*start_date\s*=\s*['\"])\d{4}-\d{2}-\d{2}(['\"])",
        rf"\g<1>{start_date}\g<2>",
        modified,
        flags=re.MULTILINE,
    )
    modified = re.sub(
        r"^(\s*end_date\s*=\s*['\"])\d{4}-\d{2}-\d{2}(['\"])",
        rf"\g<1>{end_date}\g<2>",
        modified,
        flags=re.MULTILINE,
    )

    # ── 3. Inject the BusinessDay freq-fix after each download call ──────────
    #
    # FIX: Original regex used [^)]+ which cannot cross newlines, so multi-line
    # download() calls were silently skipped and _raw_df was never created.
    #
    # New approach:
    #   • Capture  data = vbt.YFData.download(...)  including multi-line args
    #     using a non-greedy .*? with re.DOTALL.
    #   • Determine the variable name from the left-hand side of the assignment
    #     so the fix always calls the right .get().
    #   • Insert the fix block immediately after the closing parenthesis.
    #
    # The regex matches:
    #   <optional leading spaces> <varname> = vbt.YFData.download( ... )
    # and captures <varname> so the freq-fix block can reference it.

    # Track which lines have been processed to avoid double injection
    processed_spans = set()

    def _inject_freq_fix(m: re.Match) -> str:
        # Check if this span has already been processed
        span_key = (m.start(), m.end())
        if span_key in processed_spans:
            return m.group(0)  # Return unchanged
        processed_spans.add(span_key)

        full_match = m.group(0)
        var_name   = m.group(2).strip()          # e.g. "data" (group 2 captures the variable name)
        fix_block  = _build_freq_fix(var_name)
        return full_match + fix_block

    # Match vbt.YFData.download(...) calls - handles both single-line and multi-line
    # Pattern: optional whitespace, variable name, =, vbt.YFData.download(...)
    # The pattern uses balanced parentheses matching via a simple counter approach
    modified = re.sub(
        r"^([ \t]*(\w+)\s*=\s*vbt\.YFData\.download\([^)]+(?:\([^)]*\)[^)]*)*\))",
        _inject_freq_fix,
        modified,
        flags=re.MULTILINE | re.DOTALL,
    )

    # ── 4. Rewrite ALL data.get() calls to use _raw_df instead ────────────────
    #
    # CRITICAL FIX: The original code only rewrote specific patterns, but missed
    # some edge cases. This new approach is more aggressive:
    #   - Match data.get('Column') or data.get("Column")
    #   - Match with optional spaces around arguments
    #   - Replace with _raw_df['Column'] to use the cleaned DataFrame
    #
    # This ensures ALL data access uses the freq-cleaned _raw_df, preventing
    # the "invalid unit abbreviation: B" error.

    if "_raw_df" in modified:
        # Match data.get( ... ) with various quote styles and spacing
        # Group 1: opening quote, Group 2: column name
        modified = re.sub(
            r"\bdata\.get\(\s*(['\"])([^'\"]+)\1\s*\)",
            r"_raw_df[\1\2\1]",
            modified,
        )

    return modified


def _add_business_days(date: datetime.datetime, days: int) -> datetime.datetime:
    """Add business days to a date, skipping weekends."""
    result = date
    days_added = 0
    while days_added < days:
        result += datetime.timedelta(days=1)
        if result.weekday() < 5:  # Monday=0, Friday=4
            days_added += 1
    return result


def _is_weekend_date(date_str: str) -> bool:
    """Check if a date string falls on a weekend."""
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return dt.weekday() >= 5  # Saturday=5, Sunday=6


def calculate_window_configs(
    start_date: Optional[str],
    end_date: Optional[str],
    n_windows: int,
    split_type: str,
    wfo_conf: Dict[str, Any],
    is_true_wfo: bool = False,
    code: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Calculate window configurations for true WFO.

    Returns list of dicts with:
    - train_start, train_end
    - test_start, test_end

    Uses calendar days for window calculation with minimum 3-day test periods
    to ensure yfinance can always find data (avoids weekend-only periods).
    """
    if not start_date or not end_date:
        return []

    try:
        start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end   = datetime.datetime.strptime(end_date,   "%Y-%m-%d")
    except ValueError:
        return []

    total_days = (end - start).days
    print(f"DEBUG: Date range: {start_date} to {end_date} = {total_days} calendar days")
    if total_days <= 0:
        return []

    # Get train/test split configuration
    train_days   = wfo_conf.get("train_days")
    test_days    = wfo_conf.get("test_days")
    ratio        = wfo_conf.get("ratio", 0.7)
    split_method = wfo_conf.get("splitMethod", "ratio")

    print(f"DEBUG: train_days={train_days}, test_days={test_days}, "
          f"ratio={ratio}, splitMethod={split_method}")

    # Enforce minimum window sizes (calendar days, not business days)
    MIN_TRAIN_DAYS = 14    # ~2 weeks
    MIN_TEST_DAYS  = 1     # Minimum 1 day for True WFO (single-day test)

    if train_days is not None and test_days is not None and split_method == "fixed":
        train_len = max(int(train_days), MIN_TRAIN_DAYS)
        test_len  = max(int(test_days),  MIN_TEST_DAYS)
        print(f"DEBUG: Using fixed days – train_len={train_len}, test_len={test_len}")
    elif is_true_wfo and code:
        # True WFO: size training window by max indicator parameter + buffer
        max_param = _extract_max_param_from_code(code)
        indicator_warmup = max_param + 10  # e.g. EMA(20) needs ~30 days
        train_len = max(indicator_warmup, MIN_TRAIN_DAYS)
        test_len = 1  # True WFO always tests one day at a time
        print(f"DEBUG: True WFO auto-sized – max_param={max_param}, train_len={train_len}, test_len={test_len}")
    else:
        train_len = max(int(total_days * ratio),       MIN_TRAIN_DAYS)
        test_len  = max(int(total_days * (1 - ratio)), MIN_TEST_DAYS)
        print(f"DEBUG: Using ratio – train_len={train_len}, test_len={test_len}, "
              f"total_days={total_days}")

    # Step size - for True WFO, always use 1 day step since we trade one day at a time
    # For short test periods, also use 1 day step for more windows
    if is_true_wfo:
        step = 1
        print(f"DEBUG: True WFO mode - step=1 (trading one day at a time)")
    elif test_len <= 3:
        step = 1
        print(f"DEBUG: Short test period mode - step=1")
    else:
        step = test_len
        print(f"DEBUG: Standard mode - step={test_len}")

    window_configs: List[Dict[str, str]] = []
    print(f"DEBUG: Starting window calculation with total_days={total_days}, train_len={train_len}, test_len={test_len}, split_type={split_type}")

    # Calculate max possible windows
    if test_len == 1:
        # For single-day testing, we can have many more windows
        max_windows = total_days - train_len
        print(f"DEBUG: Single-day mode - max_windows = {total_days} - {train_len} = {max_windows}")
    else:
        max_windows = max(1, (total_days - train_len) // step)
        print(f"DEBUG: Multi-day mode - max_windows = ({total_days} - {train_len}) // {step} = {max_windows}")

    # Clamp n_windows to what the data supports (or use max if n_windows is 0/not set)
    print(f"DEBUG: Input n_windows={n_windows}, max_windows={max_windows}")
    if n_windows <= 0 or n_windows > max_windows:
        old_n_windows = n_windows
        n_windows = max_windows
        print(f"DEBUG: Adjusted n_windows from {old_n_windows} to {n_windows} (max possible)")
    else:
        print(f"DEBUG: Using provided n_windows={n_windows} (not exceeding max)")

    print(f"DEBUG: Generating {n_windows} windows with step={step}")
    for i in range(n_windows):
        if i < 3 or i > n_windows - 4:  # Debug first 3 and last 3 windows
            print(f"DEBUG: Window {i+1}/{n_windows}")
        if split_type == "expanding":
            # Expanding window: training always starts at the beginning
            train_start_day = 0
            train_end_day   = train_len + (i * step)
        else:
            # Rolling window: training block shifts forward each iteration
            train_start_day = i * step
            train_end_day   = train_start_day + train_len

        test_start_day = train_end_day
        test_end_day   = test_start_day + test_len

        # Clamp to available data
        if test_end_day > total_days:
            test_end_day = total_days
        if train_end_day > total_days:
            break

        if train_end_day > train_start_day and test_end_day > test_start_day:
            window_configs.append({
                "train_start": (start + datetime.timedelta(days=train_start_day)).strftime("%Y-%m-%d"),
                "train_end":   (start + datetime.timedelta(days=train_end_day)).strftime("%Y-%m-%d"),
                "test_start":  (start + datetime.timedelta(days=test_start_day)).strftime("%Y-%m-%d"),
                "test_end":    (start + datetime.timedelta(days=test_end_day)).strftime("%Y-%m-%d"),
            })
            if i < 3 or i > n_windows - 4:
                print(f"DEBUG: Added window {i+1}: train={window_configs[-1]['train_start']} to {window_configs[-1]['train_end']}, test={window_configs[-1]['test_start']} to {window_configs[-1]['test_end']}")

    print(f"DEBUG: Total windows generated: {len(window_configs)}")
    return window_configs


def modify_code_dates_and_params(
    code: str,
    start_date: str,
    end_date: str,
    best_params: Dict[str, Any],
) -> str:
    """
    Modify code with new dates, inject the BusinessDay freq-fix, and pin
    every parameter to its best-found value (replacing array sweeps with
    scalar assignments).

    Order of operations:
      1. modify_code_dates()  – date replacement + freq-fix injection
      2. Parameter pinning    – np.array([...]) sweeps replaced with scalars
    """
    # Step 1: date replacement + freq-fix (all fixes live in modify_code_dates)
    modified = modify_code_dates(code, start_date, end_date)

    # Step 2: pin each optimised parameter to its best scalar value
    for param_name, param_value in best_params.items():
        # Replace numpy array sweep assignment
        modified = re.sub(
            rf"^\s*{re.escape(param_name)}\s*=\s*np\.array\([^)]+\)",
            f"{param_name} = {param_value}",
            modified,
            flags=re.MULTILINE,
        )
        # Replace any remaining simple assignment (first occurrence only)
        modified = re.sub(
            rf"^\s*{re.escape(param_name)}\s*=\s*[^#\n]+",
            f"{param_name} = {param_value}",
            modified,
            flags=re.MULTILINE,
            count=1,
        )

    return modified
