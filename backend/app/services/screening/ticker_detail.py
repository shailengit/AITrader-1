"""Per-ticker detail payload for the Custom Screener row-click drawer.

Returns a single dict containing fundamentals, an indicator snapshot, and the
next earnings event for one ticker. The shape is consumed by the new
TickerDetailDrawer frontend component via GET /api/screener/ticker/{ticker}.

This is intentionally a small, single-ticker function. It reuses
`enrich_results` (one-element list) for fundamentals so we keep the
existing batched-query logic, and computes the simple indicator values
inline from a 250-day lookback of OHLCV bars. Bespoke multi-factor
indicators (volume_cluster_count, rs_vs_sector, consolidation_tightness)
are left as None in this version — the drawer renders them as `--`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
from ta import add_all_ta_features

from app.exceptions import DataNotFoundError
from app.services.data_service import DataService
from app.services.earnings_service import get_next_earnings
from app.services.screening.enrich import enrich_results

logger = logging.getLogger(__name__)

# Earliest bar date the snapshot can return. If the requested as_of_date is
# before this, the function raises DataNotFoundError so the frontend can
# surface a 404 instead of returning a half-populated payload.
_LOOKBACK_DAYS = 250


def _resolve_as_of(ticker: str, as_of_date: Optional[str]) -> str:
    """Return YYYY-MM-DD — the input if given, else the most recent bar date."""
    if as_of_date:
        return as_of_date
    df = DataService.get_ohlcv_data(ticker, limit=1)
    if df is None or df.empty:
        raise DataNotFoundError(
            f"No data for ticker {ticker}",
            details={"ticker": ticker},
        )
    last = df.index[0]
    if isinstance(last, pd.Timestamp):
        return last.strftime("%Y-%m-%d")
    return str(last)[:10]


def _snapshot_indicators(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Run add_all_ta_features and pull a small fixed set of columns from the
    last bar. Missing columns become None (frontend renders '--')."""
    df = add_all_ta_features(df, "Open", "High", "Low", "Close", "Volume", fillna=True)
    last = df.iloc[-1]

    # Column → null. Values are stored as-is from the ta library
    # (floats; may be None if the window isn't long enough).
    wanted = {
        "rsi": "momentum_rsi",
        "macd": "trend_macd",
        "mfi": "volume_mfi",
        "bbw": "volatility_bbw",
        "volume_ratio": "volume_ratio",  # custom field, computed below
        "ath_proximity": "ath_proximity",  # custom field, computed below
        "volume_cluster_count": "volume_cluster_count",  # not produced here
        "rs_vs_sector": "rs_vs_sector",  # not produced here
    }
    out: Dict[str, Optional[float]] = {}
    for key, col in wanted.items():
        if col in last.index:
            v = last[col]
            out[key] = None if pd.isna(v) else float(v)
        else:
            out[key] = None

    # volume_ratio = latest Volume / 50-day average
    try:
        avg_vol_50 = float(df["Volume"].tail(50).mean())
        latest_vol = float(df["Volume"].iloc[-1])
        out["volume_ratio"] = round(latest_vol / avg_vol_50, 4) if avg_vol_50 > 0 else None
    except Exception:
        out["volume_ratio"] = None

    # ath_proximity = latest Close / all-time High
    try:
        ath = float(df["High"].max())
        latest_close = float(df["Close"].iloc[-1])
        out["ath_proximity"] = round(latest_close / ath, 4) if ath > 0 else None
    except Exception:
        out["ath_proximity"] = None

    return out


def _normalize_earnings(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Reshape earnings_service's output into the drawer's expected schema."""
    if not raw:
        return None
    return {
        "date": raw.get("report_date"),
        "days_away": raw.get("days_until"),
        "eps_estimate": raw.get("eps_estimate"),
    }


def get_ticker_detail(ticker: str, as_of_date: Optional[str] = None) -> Dict[str, Any]:
    """Build the TickerDetail payload for one ticker.

    Args:
        ticker: Symbol, e.g. 'AAPL'. Upper-cased internally.
        as_of_date: YYYY-MM-DD cutoff. If None, the most recent bar is used.

    Returns:
        Dict matching the TickerDetail schema (see app.services.screening.ticker_detail).

    Raises:
        DataNotFoundError: when the ticker has no bars on the as-of date or
            no data in the lookback window for the indicator snapshot.
    """
    symbol = ticker.upper()
    as_of = _resolve_as_of(symbol, as_of_date)

    # Pull a 250-day lookback so add_all_ta_features has enough history for
    # SMA200 and similar. End at the as-of date inclusive.
    end_dt = datetime.strptime(as_of, "%Y-%m-%d") + timedelta(days=1)
    start_dt = end_dt - timedelta(days=_LOOKBACK_DAYS)
    df = DataService.get_ohlcv_data(
        symbol,
        start_date=start_dt.strftime("%Y-%m-%d"),
        end_date=end_dt.strftime("%Y-%m-%d"),
    )
    if df is None or df.empty:
        raise DataNotFoundError(
            f"No OHLCV data for {symbol} on {as_of}",
            details={"ticker": symbol, "as_of_date": as_of},
        )

    # DataService.get_ohlcv_data sets Date as the index; trim to as_of
    # inclusive in case the DB returned a future bar.
    df = df[df.index <= pd.Timestamp(as_of)]
    if df.empty:
        raise DataNotFoundError(
            f"No OHLCV data for {symbol} on or before {as_of}",
            details={"ticker": symbol, "as_of_date": as_of},
        )

    close = float(df["Close"].iloc[-1])
    indicators = _snapshot_indicators(df)

    # Enrichment: company_name, sector, market_cap, beta, pe_ttm, peg_ratio,
    # eps_growth_qoq, revenue_growth_qoq.
    enriched = enrich_results([{"ticker": symbol, "close": close}])
    base = enriched[0] if enriched else {}

    earnings = _normalize_earnings(get_next_earnings(symbol))

    return {
        "ticker": symbol,
        "company_name": base.get("company_name", symbol),
        "sector": base.get("sector", "N/A"),
        "close": close,
        "as_of_date": as_of,
        "fundamentals": {
            "market_cap": base.get("market_cap"),
            "beta": base.get("beta"),
            "peg_ratio": base.get("peg_ratio"),
            "eps_growth_qoq": base.get("eps_growth_qoq"),
            "revenue_growth_qoq": base.get("revenue_growth_qoq"),
        },
        "indicators": indicators,
        "earnings_next": earnings,
    }
