"""
Earnings calendar sync service for TradeCraft.

Fetches upcoming earnings dates from Finnhub (primary) and yfinance (fallback),
upserts them into the local PostgreSQL earnings_calendar table.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
import pandas as pd
from sqlalchemy import text

from app.db.database import engine

logger = logging.getLogger(__name__)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def _get_finnhub_api_key() -> str:
    """Return the Finnhub API key or raise a clear error."""
    key = FINNHUB_API_KEY
    if not key:
        raise ValueError(
            "FINNHUB_API_KEY environment variable is not set. "
            "Get a free key at https://finnhub.io and set it before running sync."
        )
    return key


def fetch_finnhub_earnings(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Fetch earnings calendar from Finnhub for a date range.

    Args:
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD

    Returns:
        List of earnings event dicts.
    """
    key = _get_finnhub_api_key()
    url = f"{FINNHUB_BASE_URL}/calendar/earnings"
    params = {
        "from": start_date,
        "to": end_date,
        "token": key,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("earningsCalendar", [])
    except requests.RequestException as e:
        logger.error("Finnhub earnings fetch failed: %s", e)
        raise


def fetch_yfinance_earnings(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch upcoming earnings date for a single ticker via yfinance.
    Used as a fallback when a ticker is missing from the local cache.

    Args:
        ticker: Stock symbol

    Returns:
        Dict with report_date, eps_estimate, etc., or None if not found.
    """
    try:
        import yfinance as yf  # pylint: disable=import-outside-toplevel
        t = yf.Ticker(ticker)
        dates = t.earnings_dates
        if dates is None or dates.empty:
            return None

        # Find the first future date
        now = pd.Timestamp.now(tz=dates.index.tz)
        future = dates[dates.index > now]
        if future.empty:
            return None

        next_date = future.index[0]
        row = future.iloc[0]
        return {
            "ticker": ticker.upper(),
            "report_date": next_date.strftime("%Y-%m-%d"),
            "eps_estimate": row.get("EPS Estimate") if pd.notna(row.get("EPS Estimate")) else None,
            "eps_actual": row.get("Reported EPS") if pd.notna(row.get("Reported EPS")) else None,
            "source": "yfinance",
            "time_of_day": "tns",
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("yfinance fallback failed for %s: %s", ticker, e)
        return None



def _to_native(val: Any) -> Any:
    """Convert numpy/pandas types to native Python types for psycopg2."""
    if val is None or pd.isna(val):
        return None
    if hasattr(val, "item"):  # numpy scalar
        return val.item()
    return val


def _upsert_earnings(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Upsert a list of earnings rows into PostgreSQL.
    Returns counts of inserted / updated / failed.
    """
    inserted = 0
    updated = 0
    failed = 0

    upsert_sql = text("""
        INSERT INTO earnings_calendar (
            ticker, report_date, fiscal_year, fiscal_quarter,
            eps_estimate, revenue_estimate, eps_actual, revenue_actual,
            time_of_day, source, updated_at
        ) VALUES (
            :ticker, :report_date, :fiscal_year, :fiscal_quarter,
            :eps_estimate, :revenue_estimate, :eps_actual, :revenue_actual,
            :time_of_day, :source, CURRENT_TIMESTAMP
        )
        ON CONFLICT (ticker, report_date)
        DO UPDATE SET
            fiscal_year = EXCLUDED.fiscal_year,
            fiscal_quarter = EXCLUDED.fiscal_quarter,
            eps_estimate = EXCLUDED.eps_estimate,
            revenue_estimate = EXCLUDED.revenue_estimate,
            eps_actual = EXCLUDED.eps_actual,
            revenue_actual = EXCLUDED.revenue_actual,
            time_of_day = EXCLUDED.time_of_day,
            source = EXCLUDED.source,
            updated_at = CURRENT_TIMESTAMP;
    """)

    with engine.begin() as conn:
        for row in rows:
            try:
                result = conn.execute(upsert_sql, {
                    "ticker": row.get("ticker", ""),
                    "report_date": row.get("report_date"),
                    "fiscal_year": _to_native(row.get("fiscal_year")),
                    "fiscal_quarter": _to_native(row.get("fiscal_quarter")),
                    "eps_estimate": _to_native(row.get("eps_estimate")),
                    "revenue_estimate": _to_native(row.get("revenue_estimate")),
                    "eps_actual": _to_native(row.get("eps_actual")),
                    "revenue_actual": _to_native(row.get("revenue_actual")),
                    "time_of_day": row.get("time_of_day", "tns"),
                    "source": row.get("source", "finnhub"),
                })
                if result.rowcount > 0:
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Failed to upsert earnings row %s: %s", row, e)
                failed += 1

    return {"inserted": inserted, "updated": updated, "failed": failed}



def sync_earnings_calendar(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Bulk sync earnings calendar from Finnhub for a date range.

    Args:
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD

    Returns:
        Summary dict with counts and metadata.
    """
    logger.info("Syncing earnings calendar from %s to %s", start_date, end_date)

    try:
        raw_events = fetch_finnhub_earnings(start_date, end_date)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to fetch from Finnhub: %s", e)
        return {"success": False, "error": str(e), "inserted": 0, "updated": 0, "failed": 0}

    if not raw_events:
        logger.info("No earnings events found in range.")
        return {"success": True, "inserted": 0, "updated": 0, "failed": 0, "events": 0}

    rows = []
    for evt in raw_events:
        rows.append({
            "ticker": evt.get("symbol", "").upper(),
            "report_date": evt.get("date"),
            "fiscal_year": evt.get("year"),
            "fiscal_quarter": evt.get("quarter"),
            "eps_estimate": evt.get("epsEstimate"),
            "revenue_estimate": evt.get("revenueEstimate"),
            "eps_actual": evt.get("epsActual"),
            "revenue_actual": evt.get("revenueActual"),
            "time_of_day": _map_time_of_day(evt.get("hour")),
            "source": "finnhub",
        })

    counts = _upsert_earnings(rows)
    logger.info(
        "Earnings sync complete: %d events processed (inserted=%d updated=%d failed=%d)",
        len(rows), counts["inserted"], counts["updated"], counts["failed"]
    )

    return {
        "success": True,
        "events": len(rows),
        **counts,
    }


def sync_tickers(tickers: List[str]) -> Dict[str, Any]:
    """
    On-demand sync for specific tickers using yfinance fallback.
    Useful when a ticker is missing from the bulk Finnhub cache.

    Args:
        tickers: List of stock symbols

    Returns:
        Summary dict.
    """
    rows = []
    for ticker in tickers:
        data = fetch_yfinance_earnings(ticker)
        if data:
            rows.append(data)

    if not rows:
        return {"success": True, "inserted": 0, "updated": 0, "failed": 0, "events": 0}

    counts = _upsert_earnings(rows)
    return {
        "success": True,
        "events": len(rows),
        **counts,
    }


def _map_time_of_day(hour: Optional[str]) -> str:
    """Map Finnhub hour field to our time_of_day codes."""
    if not hour:
        return "tns"
    h = str(hour).strip().lower()
    if h in ("bmo", "before market open"):
        return "bmo"
    if h in ("amc", "after market close"):
        return "amc"
    if h in ("dmh", "during market hours"):
        return "dmh"
    return "tns"
