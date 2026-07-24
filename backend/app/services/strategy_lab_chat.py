"""Chat service for the Strategy Lab performance chatbot.

Provides session-scoped, stateful chat with multi-LLM support and
cross-model critique functionality.
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.strategy_lab import StrategyChatMessage, StrategySession, StrategyExperiment, StrategyBatchSummary
from app.services.strategy_lab_llm import _chat

logger = logging.getLogger(__name__)


def get_chat_history(db: Session, session_id: UUID, limit: int = 20) -> List[Dict[str, Any]]:
    """Return the last N chat messages for a session, oldest first."""
    rows = (
        db.query(StrategyChatMessage)
        .filter(StrategyChatMessage.session_id == session_id)
        .order_by(StrategyChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "role": r.role,
            "content": r.content,
            "model_id": r.model_id,
            "critique_of": str(r.critique_of) if r.critique_of else None,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


def add_chat_message(db: Session, session_id: UUID, role: str, content: str,
                     model_id: str = "", critique_of: Optional[UUID] = None) -> StrategyChatMessage:
    """Persist a chat message and return the ORM object."""
    msg = StrategyChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        model_id=model_id,
        critique_of=critique_of,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def build_chat_context(db: Session, session: StrategySession) -> str:
    """Build a system context string from the session's plan, code, experiments, and summaries."""
    parts = []

    if session.plan_text:
        parts.append(f"## Strategy Plan\n\n{session.plan_text}")

    if session.code_text:
        code = session.code_text[:2000]
        parts.append(f"## Strategy Code (truncated)\n\n```python\n{code}\n```")

    # Load experiments
    exps = (
        db.query(StrategyExperiment)
        .filter(StrategyExperiment.session_id == session.id)
        .order_by(StrategyExperiment.started_at.desc())
        .limit(100)
        .all()
    )
    if exps:
        rows = []
        for e in exps:
            k = e.kpis or {}
            rows.append({
                "run": e.run_index,
                "batch": str(e.batch_id)[:8],
                "start": e.start_date.isoformat() if e.start_date else "",
                "ret": k.get("total_return_pct"),
                "wr": k.get("win_rate"),
                "trades": k.get("total_trades"),
                "status": e.status,
            })
        parts.append(f"## Backtest Results ({len(rows)} runs)\n\n{json.dumps(rows, indent=2)}")

    # Load summaries
    summaries = (
        db.query(StrategyBatchSummary)
        .filter(StrategyBatchSummary.session_id == session.id)
        .order_by(StrategyBatchSummary.created_at.desc())
        .limit(5)
        .all()
    )
    if summaries:
        summary_texts = [f"### Summary {i+1}\n{s.summary_text}" for i, s in enumerate(summaries)]
        parts.append("## Batch Summaries\n\n" + "\n\n".join(summary_texts))

    return "\n\n".join(parts)


def chat_with_llm(db: Session, session_id: UUID, user_message: str,
                  model: str, critique_of: Optional[UUID] = None) -> Tuple[str, List[Dict[str, Any]]]:
    """Process a chat message and return (response_text, updated_history)."""
    # Store user message
    add_chat_message(db, session_id, "user", user_message, model_id=model)

    # Load session
    session = db.query(StrategySession).filter(StrategySession.id == session_id).first()
    if not session:
        raise ValueError("Session not found")

    # Build context
    context = build_chat_context(db, session)

    # Build system prompt
    if critique_of:
        critiqued = db.query(StrategyChatMessage).filter(StrategyChatMessage.id == critique_of).first()
        critiqued_text = critiqued.content if critiqued else "(not found)"
        system_prompt = (
            "You are a quantitative analyst critiquing another model's analysis of backtest results. "
            "Be constructive. Point out strengths, weaknesses, gaps, and alternative interpretations. "
            "Reference specific numbers and runs. Be concise but thorough.\n\n"
            f"## Session Context\n\n{context}\n\n"
            f"## Analysis to Critique\n\n{critiqued_text}"
        )
    else:
        system_prompt = (
            "You are a quantitative analyst assistant. You have access to the strategy plan, code, "
            "and backtest results. Answer questions about performance, compare runs, suggest improvements. "
            "Be specific — reference actual numbers and runs. Be concise.\n\n"
            f"## Session Context\n\n{context}"
        )

    # Load conversation history (last 20 messages)
    history = get_chat_history(db, session_id, limit=20)

    # Build messages for LLM
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        if h["role"] in ("user", "assistant"):
            messages.append({"role": h["role"], "content": h["content"]})

    # Call LLM
    content, finish_reason, err = _chat(messages, model=model, max_tokens=16384, temperature=0.3, timeout=180)
    if err or content is None:
        raise RuntimeError(err or "LLM returned empty response")

    # Store assistant response
    add_chat_message(db, session_id, "assistant", content, model_id=model, critique_of=critique_of)

    # Return updated history
    updated_history = get_chat_history(db, session_id, limit=20)
    return content, updated_history
