"""Chat service for the Strategy Lab performance chatbot.

Provides session-scoped, stateful chat with multi-LLM support and
cross-model critique functionality. Also detects code-change intent
from the LLM and returns structured instructions for the frontend
to trigger the refine-direct flow.
"""
import json
import logging
import re
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


def _extract_code_change(text: str) -> Tuple[str, Optional[str]]:
    """Parse [CODE_CHANGE: ...] marker from the response.

    Returns (cleaned_text, instruction_or_None). The marker can appear
    anywhere in the text — the LAST occurrence wins. The marker is
    stripped from the cleaned text.
    """
    # Find ALL occurrences and take the last one
    matches = list(re.finditer(r'\[CODE_CHANGE:\s*(.+?)\]\s*', text))
    if not matches:
        return text, None
    last = matches[-1]
    instruction = last.group(1).strip()
    # Remove the marker from the text
    cleaned = (text[:last.start()] + text[last.end():]).strip()
    return cleaned, instruction


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
                  model: str, critique_of: Optional[UUID] = None) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Process a chat message and return (response_text, updated_history, code_change_instruction).

    If the LLM detects a code-change intent, it emits a [CODE_CHANGE: ...] marker
    at the end of its response. This function parses that marker and returns the
    instruction separately so the frontend can show an "Apply change" button.
    """
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
            f"## Session Context\n\n{context}\n\n"
            "---\n"
            "## CODE CHANGE MARKER — YOU MUST FOLLOW THIS\n\n"
            "When the user asks you to MODIFY the strategy code (add/remove/change filters, "
            "adjust parameters, change exit logic, etc.), you MUST end your response with "
            "the exact marker on its own line:\n\n"
            "[CODE_CHANGE: <one-line instruction describing the change>]\n\n"
            "This is NOT optional. If the user asks for a code change and you do NOT include "
            "this marker, the change will NOT be applied. The marker is the ONLY mechanism "
            "the system has to apply your suggested changes.\n\n"
            "EXAMPLES:\n"
            "  User: \"add a filter that SPY must be above its 20d MA\"\n"
            "  Bot: \"Looking at the worst runs... [analysis...]\n\n"
            "[CODE_CHANGE: add SPY > 20d MA filter to entry_score]\"\n\n"
            "  User: \"widen the trailing stop to 25%\"\n"
            "  Bot: \"The trailing stop at 20% is too tight...\n\n"
            "[CODE_CHANGE: set trailing_stop=0.25]\"\n\n"
            "  User: \"apply the changes you suggested\"\n"
            "  Bot: \"Here are the changes...\n\n"
            "[CODE_CHANGE: add SPY > 200d MA regime filter to entry_score]\"\n\n"
            "  User: \"why did run 3 underperform?\"\n"
            "  Bot: \"Run 3 started in a bear market...\" (no marker — analysis only)\n\n"
            "If the request is ambiguous, ask ONE clarifying question before including the marker. "
            "But once the user confirms, you MUST include the marker."
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

    # Parse code-change marker
    cleaned_text, code_change_instruction = _extract_code_change(content)

    # Store assistant response (with cleaned text, no marker)
    add_chat_message(db, session_id, "assistant", cleaned_text, model_id=model, critique_of=critique_of)

    # Return updated history
    updated_history = get_chat_history(db, session_id, limit=20)
    return cleaned_text, updated_history, code_change_instruction
