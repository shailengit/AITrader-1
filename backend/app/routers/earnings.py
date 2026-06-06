"""
Earnings calendar router for TradeCraft API.

Endpoints:
- GET /api/earnings/calendar   — upcoming earnings in a date range
- GET /api/earnings/next/{ticker} — next earnings for a single ticker
- POST /api/earnings/sync     — trigger manual sync from Finnhub
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.earnings_service import get_next_earnings, get_earnings_window
from app.services.earnings_sync import sync_earnings_calendar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/earnings", tags=["earnings"])


# =============================================================================
# Models
# =============================================================================

class SyncRequest(BaseModel):
    """Manual sync request body."""
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD


class SyncResponse(BaseModel):
    """Sync result summary."""
    success: bool
    events: int
    inserted: int
    updated: int
    failed: int
    error: Optional[str] = None


class EarningsEvent(BaseModel):
    """Single earnings event."""
    ticker: str
    report_date: str
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    eps_estimate: Optional[float] = None
    revenue_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    revenue_actual: Optional[float] = None
    time_of_day: str
    source: str
    days_until: Optional[int] = None


class NextEarningsResponse(BaseModel):
    """Response for next earnings lookup."""
    ticker: str
    event: Optional[EarningsEvent] = None


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/calendar", response_model=List[EarningsEvent])
async def earnings_calendar(
    from_date: Optional[str] = Query(None, alias="from", description="Start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, alias="to", description="End date YYYY-MM-DD"),
    tickers: Optional[str] = Query(None, description="Comma-separated tickers"),
    days: int = Query(14, description="Days forward from today if from/to not set"),
):
    """
    Get upcoming earnings events.

    If `from` and `to` are provided, they define the range.
    Otherwise returns the next `days` days.
    Optionally filter to a comma-separated list of tickers.
    """
    ticker_list: Optional[List[str]] = None
    if tickers:
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

    try:
        events = get_earnings_window(
            days=days,
            tickers=ticker_list,
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error fetching earnings calendar: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch earnings calendar") from e

    return events


@router.get("/next/{ticker}", response_model=NextEarningsResponse)
async def next_earnings(ticker: str):
    """Get the next upcoming earnings event for a single ticker."""
    try:
        event = get_next_earnings(ticker, auto_sync=True)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error fetching next earnings for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail="Failed to fetch next earnings") from e

    if event is None:
        return NextEarningsResponse(ticker=ticker.upper(), event=None)

    return NextEarningsResponse(ticker=ticker.upper(), event=EarningsEvent(**event))


@router.post("/sync", response_model=SyncResponse)
async def manual_sync(request: SyncRequest):
    """
    Manually trigger an earnings calendar sync from Finnhub.
    Requires FINNHUB_API_KEY to be configured.
    """
    try:
        result = sync_earnings_calendar(request.start_date, request.end_date)
    except ValueError as e:
        logger.warning("Sync failed due to missing config: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Sync error: %s", e)
        raise HTTPException(status_code=503, detail="Sync failed") from e

    return SyncResponse(
        success=result.get("success", False),
        events=result.get("events", 0),
        inserted=result.get("inserted", 0),
        updated=result.get("updated", 0),
        failed=result.get("failed", 0),
        error=result.get("error"),
    )
