"""
Earnings calendar query service for TradeCraft.

Provides fast lookups from the local PostgreSQL earnings_calendar table,
including per-ticker next earnings, date-range queries, and scan enrichment.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date

from sqlalchemy import text

from app.db.database import engine
from app.services.earnings_sync import sync_tickers

logger = logging.getLogger(__name__)


def get_next_earnings(ticker: str, auto_sync: bool = True) -> Optional[Dict[str, Any]]:
    """
    Return the next upcoming earnings event for a single ticker.

    Args:
        ticker: Stock symbol
        auto_sync: If True and no cached data, attempt yfinance fallback sync

    Returns:
        Dict with report_date, eps_estimate, days_until, etc., or None.
    """
    ticker_upper = ticker.upper()
    today = date.today()

    query = text("""
        SELECT ticker, report_date, fiscal_year, fiscal_quarter,
               eps_estimate, revenue_estimate, eps_actual, revenue_actual,
               time_of_day, source, updated_at
        FROM earnings_calendar
        WHERE ticker = :ticker
          AND report_date >= :today
        ORDER BY report_date ASC
        LIMIT 1
    """)

    try:
        with engine.connect() as conn:
            row = conn.execute(query, {"ticker": ticker_upper, "today": today}).fetchone()

        if row:
            return _row_to_dict(row, today)

        if auto_sync:
            logger.info("No cached earnings for %s, trying yfinance fallback.", ticker_upper)
            sync_tickers([ticker_upper])
            # Retry once after sync
            with engine.connect() as conn:
                row = conn.execute(query, {"ticker": ticker_upper, "today": today}).fetchone()
            if row:
                return _row_to_dict(row, today)

        return None
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error getting next earnings for %s: %s", ticker_upper, e)
        return None


def get_earnings_window(
    days: int = 7,
    tickers: Optional[List[str]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return all earnings events within a date window.

    Args:
        days: Number of days forward from today (used if from_date/to_date not set)
        tickers: Optional list of tickers to filter
        from_date: Optional YYYY-MM-DD override for start
        to_date: Optional YYYY-MM-DD override for end

    Returns:
        List of earnings dicts.
    """
    today = date.today()
    start = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else today
    end = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else today

    if not from_date and not to_date:
        # Default window: today to today + days
        from datetime import timedelta
        end = today + timedelta(days=days)

    base_query = """
        SELECT ticker, report_date, fiscal_year, fiscal_quarter,
               eps_estimate, revenue_estimate, eps_actual, revenue_actual,
               time_of_day, source, updated_at
        FROM earnings_calendar
        WHERE report_date BETWEEN :start AND :end
    """
    params: Dict[str, Any] = {"start": start, "end": end}

    if tickers:
        # Use ANY for PostgreSQL array matching
        placeholders = ", ".join([f":t{i}" for i in range(len(tickers))])
        base_query += f" AND ticker IN ({placeholders})"
        for i, t in enumerate(tickers):
            params[f"t{i}"] = t.upper()

    base_query += " ORDER BY report_date ASC, ticker ASC"

    try:
        with engine.connect() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
        return [_row_to_dict(row, today) for row in rows]
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error fetching earnings window: %s", e)
        return []


def enrich_scan_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add next_earnings_date and days_until_earnings to a list of scan results.

    Args:
        results: List of dicts, each must have a 'ticker' key.

    Returns:
        The same list mutated in-place.
    """
    if not results:
        return results

    tickers = [r["ticker"].upper() for r in results if "ticker" in r]
    if not tickers:
        return results

    today = date.today()

    # Batch query: get the next earnings for each ticker
    # Use a CTE to pick the first future row per ticker
    placeholders = ", ".join([f":t{i}" for i in range(len(tickers))])
    query = text(f"""
        WITH upcoming AS (
            SELECT DISTINCT ON (ticker)
                ticker, report_date, eps_estimate, time_of_day
            FROM earnings_calendar
            WHERE ticker IN ({placeholders})
              AND report_date >= :today
            ORDER BY ticker, report_date ASC
        )
        SELECT * FROM upcoming
    """)

    params: Dict[str, Any] = {"today": today}
    for i, t in enumerate(tickers):
        params[f"t{i}"] = t

    earnings_map: Dict[str, Dict[str, Any]] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        for row in rows:
            earnings_map[row[0].upper()] = {
                "next_earnings_date": str(row[1]),
                "days_until_earnings": (row[1] - today).days,
                "eps_estimate": float(row[2]) if row[2] is not None else None,
                "time_of_day": row[3],
            }
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error enriching scan results with earnings: %s", e)

    for result in results:
        t = result.get("ticker", "").upper()
        if t in earnings_map:
            result.update(earnings_map[t])
        else:
            result["next_earnings_date"] = None
            result["days_until_earnings"] = None
            result["eps_estimate"] = None
            result["time_of_day"] = None

    return results


def _row_to_dict(row: Any, today: date) -> Dict[str, Any]:
    """Convert a SQLAlchemy row to a plain dict with days_until computed."""
    report_date = row[1]
    days_until = (report_date - today).days if isinstance(report_date, (date, datetime)) else None
    return {
        "ticker": row[0],
        "report_date": str(report_date) if report_date else None,
        "fiscal_year": row[2],
        "fiscal_quarter": row[3],
        "eps_estimate": float(row[4]) if row[4] is not None else None,
        "revenue_estimate": float(row[5]) if row[5] is not None else None,
        "eps_actual": float(row[6]) if row[6] is not None else None,
        "revenue_actual": float(row[7]) if row[7] is not None else None,
        "time_of_day": row[8],
        "source": row[9],
        "updated_at": str(row[10]) if row[10] else None,
        "days_until": days_until,
    }
