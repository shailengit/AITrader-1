"""AI Strategy Builder router — sessions CRUD + Ollama model list.

Phase 1 scope: no LLM calls, no experiment orchestration, no deploy.
Those land in Phases 2-4. This router establishes the foundation.
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.strategy_lab import StrategySession
from app.services.strategy_lab_models import list_ollama_models
from app.services.strategy_lab_session import (
    create_session as svc_create_session,
    get_session as svc_get_session,
    list_sessions as svc_list_sessions,
    update_session as svc_update_session,
    delete_session as svc_delete_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy-lab", tags=["AI Strategy Builder"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Pydantic models ──────────────────────────────────────────────────────

class VariantResponse(BaseModel):
    name: str
    type: str  # "cloud" or "local"
    size_bytes: Optional[int] = None


class ModelResponse(BaseModel):
    id: str
    variants: List[VariantResponse]


class SessionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    prompt: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)


class SessionUpdate(BaseModel):
    plan_text: Optional[str] = None
    code_text: Optional[str] = None
    tags: Optional[List[str]] = None
    name: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    name: str
    prompt: str
    plan_text: Optional[str] = None
    code_text: Optional[str] = None
    model_id: str
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("/models", response_model=List[ModelResponse])
def get_models():
    """List all available Ollama models from the local manifest directory."""
    raw = list_ollama_models()
    return [
        ModelResponse(
            id=m["id"],
            variants=[VariantResponse(**v) for v in m["variants"]],
        )
        for m in raw
    ]


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def post_session(body: SessionCreate, db: Session = Depends(get_db)):
    """Create a new strategy session."""
    sess = svc_create_session(
        db,
        name=body.name,
        prompt=body.prompt,
        model_id=body.model_id,
        tags=body.tags,
    )
    return SessionResponse(**sess.to_dict())


@router.get("/sessions", response_model=List[SessionResponse])
def get_sessions(
    search: Optional[str] = Query(None, description="Free-text search across name/prompt/plan/code"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags (any match)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List sessions, newest updated first."""
    rows = svc_list_sessions(db, search=search, tags=tags, limit=limit, offset=offset)
    return [SessionResponse(**s.to_dict()) for s in rows]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_one_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    """Fetch one session by id."""
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionResponse(**sess.to_dict())


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
def patch_session(
    session_id: uuid.UUID,
    body: SessionUpdate,
    db: Session = Depends(get_db),
):
    """Update mutable fields on a session."""
    update_kwargs = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    sess = svc_update_session(db, session_id, **update_kwargs)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionResponse(**sess.to_dict())


@router.delete("/sessions/{session_id}", status_code=204)
def delete_one_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a session and all its child rows (cascade)."""
    if not svc_delete_session(db, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return None


# ── LLM endpoints (Phase 2) ─────────────────────────────────────────────

class PlanRequest(BaseModel):
    model: Optional[str] = None  # defaults to OLLAMA_MODEL env var


class PlanResponse(BaseModel):
    plan_text: str


class GenerateCodeRequest(BaseModel):
    model: Optional[str] = None
    plan_text: Optional[str] = None  # if not provided, uses session's stored plan


class GenerateCodeResponse(BaseModel):
    code: str


class RefineCodeRequest(BaseModel):
    model: Optional[str] = None
    current_code: Optional[str] = None  # if not provided, uses session's stored code
    instruction: str = Field(..., min_length=1)


class RefineCodeResponse(BaseModel):
    diff: str
    summary: str  # e.g. "+3 -1 in 1 hunk(s)"


@router.post("/sessions/{session_id}/plan", response_model=PlanResponse)
def post_plan(
    session_id: uuid.UUID,
    body: PlanRequest,
    db: Session = Depends(get_db),
):
    """Generate a structured plan for the session's prompt. Persists to plan_text."""
    from app.services.strategy_lab_llm import generate_plan
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    plan, err = generate_plan(sess.prompt, model=body.model)
    if err or plan is None:
        raise HTTPException(status_code=502, detail={"error": "llm_failed", "details": err})
    # Persist
    svc_update_session(db, session_id, plan_text=plan)
    return PlanResponse(plan_text=plan)


@router.post("/sessions/{session_id}/generate-code", response_model=GenerateCodeResponse)
def post_generate_code(
    session_id: uuid.UUID,
    body: GenerateCodeRequest,
    db: Session = Depends(get_db),
):
    """Generate strategy code (4 filter functions + CONFIG) from the plan. Persists to code_text."""
    from app.services.strategy_lab_llm import generate_code
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    plan = body.plan_text or sess.plan_text
    if not plan:
        raise HTTPException(status_code=400, detail="no plan_text available — call /plan first")
    code, err = generate_code(plan, model=body.model)
    if err or code is None:
        raise HTTPException(status_code=502, detail={"error": "llm_failed", "details": err})
    svc_update_session(db, session_id, code_text=code)
    return GenerateCodeResponse(code=code)


@router.post("/sessions/{session_id}/refine-code", response_model=RefineCodeResponse)
def post_refine_code(
    session_id: uuid.UUID,
    body: RefineCodeRequest,
    db: Session = Depends(get_db),
):
    """Generate a unified diff that refines the session's current code per the instruction."""
    from app.services.strategy_lab_llm import generate_refine_diff
    from app.services.strategy_lab_diff import diff_summary
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    current = body.current_code or sess.code_text
    if not current:
        raise HTTPException(status_code=400, detail="no code_text available — generate code first")
    diff, err = generate_refine_diff(current, body.instruction, model=body.model)
    if err or diff is None:
        raise HTTPException(status_code=502, detail={"error": "llm_failed", "details": err})
    return RefineCodeResponse(diff=diff, summary=diff_summary(diff))


@router.post("/sessions/{session_id}/apply-diff")
def post_apply_diff(
    session_id: uuid.UUID,
    body: RefineCodeRequest,
    db: Session = Depends(get_db),
):
    """Apply a refine diff to the session's code and persist the result.

    Useful when the user accepts a refinement in the UI.
    """
    from app.services.strategy_lab_diff import apply_diff as apply_diff_fn
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    current = body.current_code or sess.code_text
    if not current:
        raise HTTPException(status_code=400, detail="no code_text available")
    try:
        new_code = apply_diff_fn(current, body.instruction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "diff_apply_failed", "details": str(e)})
    svc_update_session(db, session_id, code_text=new_code)
    return {"code": new_code}
