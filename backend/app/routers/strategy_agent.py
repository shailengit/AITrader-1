"""FastAPI router for the Strategy Agent — a server-side agent loop for
generating, validating, and improving trading strategies with live SSE progress.

Endpoints:
  POST /api/strategy-agent/generate  — Start a generation session
  GET  /api/strategy-agent/{session_id}/stream  — SSE event stream
  GET  /api/strategy-agent/{session_id}/result  — Get final result
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.strategy_agent import (
    start_agent,
    get_session,
    cleanup_old_sessions,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request/Response models ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    status: str
    message: str


class ResultResponse(BaseModel):
    session_id: str
    status: str
    code: Optional[str] = None
    kpis: Optional[dict] = None
    summary: Optional[str] = None
    error: Optional[str] = None


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/strategy-agent/generate")
async def generate_strategy(request: GenerateRequest):
    """Start a new strategy generation session.

    Returns a session_id immediately. The client then connects to
    /strategy-agent/{session_id}/stream to receive live progress events.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    # Clean up old sessions first
    cleanup_old_sessions()

    session_id = await start_agent(request.prompt, model=request.model)
    logger.info(
        "Started agent session %s: prompt=%s...",
        session_id, request.prompt[:100],
    )

    return SessionResponse(
        session_id=session_id,
        status="started",
        message="Agent session started. Connect to the stream endpoint for live progress.",
    )


@router.get("/strategy-agent/{session_id}/stream")
async def stream_agent_progress(session_id: str):
    """SSE endpoint that streams live progress events from the agent.

    The client connects via EventSource and receives JSON events:
      - step events: step lifecycle (running/done/failed)
      - detail events: context, llm_call, code_generated, validation, backtest_result
      - result event: final code + KPIs
      - error_fatal event: unrecoverable error
    """
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return StreamingResponse(
        session.event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/strategy-agent/{session_id}/result")
async def get_agent_result(session_id: str):
    """Get the final result of a completed agent session."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return ResultResponse(
        session_id=session_id,
        status=session.status,
        code=session.code,
        kpis=session.kpis,
        summary=session.summary,
        error=session.error,
    )


@router.get("/strategy-agent/sessions")
async def list_sessions():
    """List all active agent sessions."""
    from app.services.strategy_agent import _sessions
    return {
        "sessions": [
            {
                "session_id": sid,
                "status": s.status,
                "prompt": s.prompt[:100],
                "created_at": s.created_at.isoformat(),
            }
            for sid, s in _sessions.items()
        ],
        "count": len(_sessions),
    }
