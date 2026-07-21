"""Persistence helpers for strategy_experiments and strategy_batch_summaries."""
import json
import logging
import uuid
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.strategy_lab import (
    StrategyExperiment,
    StrategyBatchSummary,
)

logger = logging.getLogger(__name__)


def create_experiment(
    db: Session,
    *,
    session_id: uuid.UUID,
    batch_id: uuid.UUID,
    run_index: int,
    start_date: Any,
    end_date: Any,
    status: str,
    kpis: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    trades_summary: Optional[Dict[str, Any]] = None,
) -> StrategyExperiment:
    """Insert a new experiment row."""
    exp = StrategyExperiment(
        session_id=session_id,
        batch_id=batch_id,
        run_index=run_index,
        start_date=start_date,
        end_date=end_date,
        status=status,
        kpis=kpis,
        error_message=error_message,
        trades_summary=trades_summary,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def update_experiment(
    db: Session,
    experiment_id: uuid.UUID,
    *,
    status: Optional[str] = None,
    kpis: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> Optional[StrategyExperiment]:
    """Update an experiment's status and/or kpis after it completes."""
    exp = db.get(StrategyExperiment, experiment_id)
    if exp is None:
        return None
    if status is not None:
        exp.status = status
    if kpis is not None:
        exp.kpis = kpis
    if error_message is not None:
        exp.error_message = error_message
    from sqlalchemy import text as sa_text
    exp.completed_at = sa_text("now()")
    db.commit()
    db.refresh(exp)
    return exp


def list_experiments(
    db: Session,
    *,
    session_id: Optional[uuid.UUID] = None,
    batch_id: Optional[uuid.UUID] = None,
    limit: int = 200,
) -> List[StrategyExperiment]:
    """List experiments, newest first."""
    q = db.query(StrategyExperiment)
    if session_id is not None:
        q = q.filter(StrategyExperiment.session_id == session_id)
    if batch_id is not None:
        q = q.filter(StrategyExperiment.batch_id == batch_id)
    return q.order_by(StrategyExperiment.started_at.desc()).limit(limit).all()


def get_batch_stats(db: Session, batch_id: uuid.UUID) -> Dict[str, Any]:
    """Compute summary statistics for a completed batch.

    Returns: {n_total, n_completed, n_failed, mean_sharpe, best_sharpe,
              best_experiment_id, top_3_experiments, worst_3_experiments}
    """
    exps = db.query(StrategyExperiment).filter(
        StrategyExperiment.batch_id == batch_id,
        StrategyExperiment.status == "completed",
    ).all()
    if not exps:
        return {
            "n_total": db.query(StrategyExperiment).filter(
                StrategyExperiment.batch_id == batch_id
            ).count(),
            "n_completed": 0,
            "n_failed": 0,
            "mean_sharpe": None,
            "best_sharpe": None,
            "best_experiment_id": None,
            "top_3": [],
            "worst_3": [],
        }

    # Compute Sharpe proxy: total_return_pct / abs(max_drawdown_pct)
    scored = []
    for e in exps:
        k = e.kpis or {}
        ret = k.get("total_return_pct", 0) or 0
        dd = k.get("max_drawdown_pct", -1) or -1
        sharpe_proxy = ret / abs(dd) if dd != 0 else 0
        scored.append((e, sharpe_proxy))

    scored.sort(key=lambda x: x[1], reverse=True)
    n_failed = db.query(StrategyExperiment).filter(
        StrategyExperiment.batch_id == batch_id,
        StrategyExperiment.status == "failed",
    ).count()

    return {
        "n_total": len(exps) + n_failed,
        "n_completed": len(exps),
        "n_failed": n_failed,
        "mean_sharpe": sum(s for _, s in scored) / len(scored) if scored else None,
        "best_sharpe": scored[0][1] if scored else None,
        "best_experiment_id": str(scored[0][0].id) if scored else None,
        "top_3": [
            {"id": str(e.id), "run_index": e.run_index, "start_date": e.start_date.isoformat() if e.start_date else None, "sharpe": s, "kpis": e.kpis}
            for e, s in scored[:3]
        ],
        "worst_3": [
            {"id": str(e.id), "run_index": e.run_index, "start_date": e.start_date.isoformat() if e.start_date else None, "sharpe": s, "kpis": e.kpis}
            for e, s in scored[-3:]
        ],
    }


def create_batch_summary(
    db: Session,
    *,
    session_id: uuid.UUID,
    batch_id: uuid.UUID,
    summary_text: str,
    winner_run_id: Optional[uuid.UUID] = None,
    model_id: str = "",
) -> StrategyBatchSummary:
    """Persist an LLM-generated batch summary."""
    s = StrategyBatchSummary(
        session_id=session_id,
        batch_id=batch_id,
        summary_text=summary_text,
        winner_run_id=winner_run_id,
        model_id=model_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def list_batch_summaries(
    db: Session,
    *,
    session_id: Optional[uuid.UUID] = None,
    batch_id: Optional[uuid.UUID] = None,
) -> List[StrategyBatchSummary]:
    q = db.query(StrategyBatchSummary)
    if session_id is not None:
        q = q.filter(StrategyBatchSummary.session_id == session_id)
    if batch_id is not None:
        q = q.filter(StrategyBatchSummary.batch_id == batch_id)
    return q.order_by(StrategyBatchSummary.created_at.desc()).all()
