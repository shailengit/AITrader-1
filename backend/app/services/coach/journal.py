"""Trade-journal write helpers for the Coach agent.

Failure-isolated: every function catches DB exceptions, logs a warning,
and returns None so the user's primary flow is never blocked.
"""
from __future__ import annotations
import logging
from datetime import datetime, date as date_cls
from typing import Any, Dict, Optional, Union
import uuid

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.journal import JournalStrategy, JournalStrategyRun, JournalSignal

logger = logging.getLogger(__name__)


def record_journal_failure(operation: str, exc: Exception) -> None:
    """Log a journal write failure at WARNING. Never raises."""
    logger.warning("Coach journal %s failed: %s", operation, exc, exc_info=False)


def upsert_strategy(
    kind: str,
    name: str,
    params: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    session: Optional[Any] = None,
) -> Optional[JournalStrategy]:
    """Insert or update a strategy by (kind, name). Returns the row, or None on failure."""
    op = "upsert_strategy"
    own_session = session is None
    try:
        s = session or SessionLocal()
        try:
            row = s.query(JournalStrategy).filter_by(kind=kind, name=name).one_or_none()
            if row is None:
                row = JournalStrategy(kind=kind, name=name, params=params or {}, notes=notes)
                s.add(row)
            else:
                if params is not None:
                    row.params = params
                if notes is not None:
                    row.notes = notes
            if own_session:
                s.commit()
                s.refresh(row)
            else:
                s.flush()
            return row
        finally:
            if own_session:
                s.close()
    except SQLAlchemyError as e:
        record_journal_failure(op, e)
        return None


def record_strategy_run(
    strategy_id: uuid.UUID,
    started_at: datetime,
    result_summary: Optional[Dict[str, Any]] = None,
    as_of_date: Optional[date_cls] = None,
    regime_at_run: Optional[str] = None,
    finished_at: Optional[datetime] = None,
    session: Optional[Any] = None,
) -> Optional[JournalStrategyRun]:
    """Insert a strategy_run row. Returns the row, or None on failure."""
    op = "record_strategy_run"
    own_session = session is None
    try:
        s = session or SessionLocal()
        try:
            row = JournalStrategyRun(
                strategy_id=strategy_id,
                started_at=started_at,
                finished_at=finished_at or datetime.utcnow(),
                result_summary=result_summary or {},
                as_of_date=as_of_date,
                regime_at_run=regime_at_run,
            )
            s.add(row)
            if own_session:
                s.commit()
                s.refresh(row)
            else:
                s.flush()
            return row
        finally:
            if own_session:
                s.close()
    except SQLAlchemyError as e:
        record_journal_failure(op, e)
        return None


def record_signal(
    run_id: uuid.UUID,
    ticker: str,
    signal_type: str,
    as_of_date: date_cls,
    signal_strength: Optional[float] = None,
    payload: Optional[Dict[str, Any]] = None,
    session: Optional[Any] = None,
) -> Optional[JournalSignal]:
    """Insert a single signal. Returns the row, or None on failure."""
    op = "record_signal"
    own_session = session is None
    try:
        s = session or SessionLocal()
        try:
            row = JournalSignal(
                strategy_run_id=run_id,
                ticker=ticker,
                signal_type=signal_type,
                as_of_date=as_of_date,
                signal_strength=signal_strength,
                payload=payload or {},
            )
            s.add(row)
            if own_session:
                s.commit()
                s.refresh(row)
            else:
                s.flush()
            return row
        finally:
            if own_session:
                s.close()
    except SQLAlchemyError as e:
        record_journal_failure(op, e)
        return None
