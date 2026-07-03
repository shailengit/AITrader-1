"""
Chart data service.

Provides a single ticker of OHLCV candles + indicator time series for chart
rendering. Used by the Custom Screener's per-row Chart button — the scan
result row carries current snapshot values, but the chart needs the historical
series so the user can visually inspect the indicator at and around the
as-of-date.

Reuses the canonical indicator pipeline:
  - `add_all_ta_features` from the `ta` library (matches standalone scanner)
  - `INDICATOR_REGISTRY` from `app.services.agno_screener` for any column the
    ta library doesn't auto-produce (e.g. `sma_200`, `ema_20`).
  - `_recompute_indicator(..., custom_params=...)` for per-tunable override
    (e.g. `ema_20` with `window=200` — same backendColumn, different window).

Indicators may be requested with custom parameters via the `overrides` map.
The output bar's `indicators` payload is keyed by `column@@<params_signature>`
so the frontend can disambiguate two requests for the same column with
different windows (e.g. EMA20 vs EMA200, both rooted at `ema_20`).

No business logic — this is a pure data-fetch concern.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from ta import add_all_ta_features

from app.services.agno_screener import (
    DB_URL,
    INDICATOR_REGISTRY,
    _recompute_indicator,
)
from app.utils.security import get_safe_table_name

logger = logging.getLogger(__name__)

# Singleton worker engine. Chart-data fetches are lightweight enough that a
# pool of one is fine; the screener's `create_engine(..., pool_size=1)` per
# worker is mirrored here to match.
_chart_engine = create_engine(DB_URL, poolclass=QueuePool, pool_size=2, max_overflow=4)


def _series_to_indicator_payload(
    df: pd.DataFrame,
    column: str,
) -> List[Dict[str, Any]]:
    """Reduce a DataFrame column to lightweight-charts `{time, value}` array.

    NaNs are dropped so the chart never gets a `null` value. Bars with no
    indicator value are simply missing from the overlay series — visually
    identical to a "gap" and avoids the "series stops at first valid value"
    pitfall you get when you keep NaNs as `null`.
    """
    if column not in df.columns:
        return []
    out: List[Dict[str, Any]] = []
    sub = df[['time', column]].dropna(subset=[column])
    for t, v in zip(sub['time'].tolist(), sub[column].tolist()):
        try:
            out.append({'time': int(t), 'value': float(v)})
        except (TypeError, ValueError):
            continue
    return out


def _params_signature(params: Optional[Dict[str, Any]]) -> str:
    """Stable short signature for an override-params dict.

    Two requests with identical params collapse to the same signature, so we
    can use it as a deduplication key without a full dict comparison.

    The encoding is shared with the frontend's `paramsSignature` in
    `filterCatalog.ts` so the `payloadKey` the client builds matches the
    one the server produces — that way `bar.indicators[payloadKey]` lines
    up with `chartIndicators[].id` without a translation step.

    Examples:
        None        → ""
        {w:20}      → "w20"
        {w:200}     → "w200"
        {w:20,b:2}  → "b2_w20"  (sorted keys for determinism)
    """
    if not params:
        return ""
    items = sorted((str(k), str(v)) for k, v in params.items())
    return "_".join(f"{k}{v}" for k, v in items)


def get_chart_data(
    ticker: str,
    indicators: List[str],
    days: int = 250,
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Fetch OHLCV candles for `ticker` with indicator time series.

    Args:
        ticker: Ticker symbol (will be sanitized).
        indicators: Backend column names to overlay (e.g. `['ema_20', 'sma_200']`).
            Each name must exist in `INDICATOR_REGISTRY` or be auto-produced by
            `add_all_ta_features`. Unknown columns are silently skipped — the
            frontend treats unknown columns as "no overlay" rather than failing
            the whole chart.
        days: How many calendar days of history (default 250). The ta library
            needs ~200 days to compute SMA/EMA 200, so going lower than 200
            returns unusable indicator values.
        overrides: Optional map of `{column: custom_params}` for indicators
            that need non-default parameters. e.g. `{'ema_20': {'window': 200}}`
            requests a 200-period EMA using the `ema_20` indicator. Each
            distinct (column, params) pair gets a unique payload key in the
            output (`<column>__<sig>`) so the frontend can render both side
            by side.

    Returns:
        List of `{time, open, high, close, volume, high, low, indicators: {...}}`
        bars, oldest first. The `indicators` dict is keyed by `<column>__<sig>`
        for entries with overrides and by `<column>` for entries without.
        Returns None when the ticker has no data or fewer than 50 rows.
    """
    try:
        safe = get_safe_table_name(ticker)
    except ValueError:
        return None
    if not safe:
        return None

    try:
        df = pd.read_sql(
            f'SELECT * FROM "{safe}" ORDER BY "Date" DESC LIMIT {days}',
            _chart_engine,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning('chart_data: DB read failed for %s: %s', safe, exc)
        return None

    if df.empty or len(df) < 50:
        return None

    df = df.sort_values(by='Date').reset_index(drop=True)

    # Compute the full TA bundle once. This matches `_worker_ta_analysis` so
    # any indicator computed here lines up with the values used during the
    # actual scan (no risk of "the chart shows a slightly different SMA").
    df = add_all_ta_features(df, "Open", "High", "Low", "Close", "Volume", fillna=True)

    # Auto-recompute any requested indicator not produced by add_all_ta_features
    # (e.g. ema_20, sma_200, sma_100). Each (column, params) pair is computed
    # into a uniquely-named DataFrame column so two requests for the same
    # backendColumn with different windows (e.g. ema_20 w=20 vs w=200) both
    # produce distinct series.
    overrides = overrides or {}

    # Build the list of (payload_key, backend_column, params) we need to
    # produce. payload_key is what the frontend will see in `bar.indicators`.
    #
    # When a column is requested with an override, the same column with its
    # default params is ALSO produced — this is what lets the chart render
    # both `EMA 20` (default) and `EMA 200` (override) side by side even
    # though they share the `ema_20` registry entry.
    needs: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
    seen_keys: set[str] = set()

    def add_need(col: str, params: Optional[Dict[str, Any]]) -> None:
        sig = _params_signature(params)
        payload_key = f"{col}__{sig}" if sig else col
        if payload_key in seen_keys:
            return
        seen_keys.add(payload_key)
        needs.append((payload_key, col, params))

    for col in indicators:
        params = overrides.get(col)
        # Always produce the default-param series for the column so the
        # frontend can render the "natural" version even when an override
        # is also requested for the same column. (Skip when no override is
        # present — the default IS the only request in that case, and we'd
        # produce a duplicate.)
        if params:
            add_need(col, None)
        add_need(col, params)

    for payload_key, col, params in needs:
        if params:
            # Custom-param request — always recompute. Store in a uniquely-named
            # column so multiple param sets for the same backendColumn coexist.
            if col in INDICATOR_REGISTRY:
                series = _recompute_indicator(df, col, custom_params=params)
                if series is not None:
                    df[payload_key] = series
        else:
            # Default-param request — only recompute if the auto-bundle
            # didn't already produce the column.
            if col not in df.columns and col in INDICATOR_REGISTRY:
                series = _recompute_indicator(df, col)
                if series is not None:
                    df[payload_key] = series
            elif col in df.columns:
                # Mirror the auto-produced column to the payload key so the
                # rest of the pipeline can treat every entry uniformly.
                df[payload_key] = df[col]

    # Time axis: lightweight-charts wants unix seconds (UTC).
    df['time'] = pd.to_datetime(df['Date']).apply(
        lambda d: int(d.replace(tzinfo=pd.Timestamp.utcnow().tzinfo).timestamp())
        if hasattr(d, 'tzinfo') and d.tzinfo else int(d.timestamp())
    )

    bars: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            bar = {
                'time': int(row['time']),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': float(row['Volume']) if pd.notna(row['Volume']) else 0.0,
            }
        except (TypeError, ValueError):
            continue
        bars.append(bar)

    # Attach indicator series to each bar — match the format CandleStickChart
    # expects ({time, value} array per indicator). The frontend has been
    # updated to look up `bar.indicators[payload_key]` rather than `bar.
    # indicators[column]`, so the keyed layout works for both default and
    # override requests.
    indicator_payload: Dict[str, List[Dict[str, Any]]] = {}
    for payload_key, _col, _params in needs:
        payload = _series_to_indicator_payload(df, payload_key)
        if payload:
            indicator_payload[payload_key] = payload

    for bar in bars:
        bar_ind: Dict[str, Any] = {}
        for payload_key, series in indicator_payload.items():
            bar_ind[payload_key] = next((p['value'] for p in series if p['time'] == bar['time']), None)
        bar['indicators'] = bar_ind

    return bars
