"""AI Strategy Builder router — sessions CRUD + Ollama model list.

Phase 1 scope: no LLM calls, no experiment orchestration, no deploy.
Those land in Phases 2-4. This router establishes the foundation.
"""
import asyncio
import json
import logging
import threading
import uuid
from typing import List, Optional, Any, Dict

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
    plan_text: str = ""
    error: Optional[str] = None


class GenerateCodeRequest(BaseModel):
    model: Optional[str] = None
    plan_text: Optional[str] = None  # if not provided, uses session's stored plan


class GenerateCodeResponse(BaseModel):
    code: str
    validation_status: str = "unknown"  # "passed" | "failed" | "unknown"
    validation_attempts: int = 1
    validation_log: List[str] = Field(default_factory=list)


class RefineCodeRequest(BaseModel):
    model: Optional[str] = None
    current_code: Optional[str] = None  # if not provided, uses session's stored code
    instruction: str = Field(..., min_length=1)


class RefineCodeResponse(BaseModel):
    diff: str = ""
    summary: str = ""
    error: Optional[str] = None


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
        logger.error("Plan generation failed: %s", err)
        return PlanResponse(error=err or "LLM returned no content")
    # Persist
    svc_update_session(db, session_id, plan_text=plan)
    return PlanResponse(plan_text=plan)


@router.post("/sessions/{session_id}/generate-code", response_model=GenerateCodeResponse)
def post_generate_code(
    session_id: uuid.UUID,
    body: GenerateCodeRequest,
    db: Session = Depends(get_db),
):
    """Generate strategy code (4 filter functions + CONFIG) from the plan.
    Persists to code_text. Automatically validates by running a single
    backtest — if validation fails, retries up to 3 times with the error
    message fed back to the LLM so it can fix the issue.
    """
    from app.services.strategy_lab_llm import generate_code, debug_code
    from app.services.strategy_lab_orchestrator import _run_one
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    plan = body.plan_text or sess.plan_text
    if not plan:
        raise HTTPException(status_code=400, detail="no plan_text available — call /plan first")

    max_generate_attempts = 3
    max_debug_cycles = 3
    last_error = None
    validation_log = []
    code = None

    # Stage 1: Generate (with retries and backoff)
    import time as _time
    for attempt in range(1, max_generate_attempts + 1):
        if attempt > 1:
            _time.sleep(2)  # brief backoff before retry
        try:
            code, err = generate_code(plan, model=body.model)
        except Exception as gen_err:
            err = f"{type(gen_err).__name__}: {gen_err}"
            code = None
        if err or code is None:
            last_error = err
            validation_log.append(f"Generate attempt {attempt}: LLM failed — {err}")
            continue
        validation_log.append(f"Generate attempt {attempt}: code generated ({len(code)} chars)")
        break

    if not code:
        # Never throw 502 — return graceful failure so the user sees a clear
        # message with retry button instead of a cryptic server error.
        logger.error("Code generation failed after %d attempts: %s", max_generate_attempts, last_error)
        return GenerateCodeResponse(
            code="",
            validation_status="failed",
            validation_attempts=max_generate_attempts,
            validation_log=validation_log,
        )

    # Stage 2: Validate + Stage 3: Debug loop
    for cycle in range(max_debug_cycles + 1):
        try:
            result = _run_one(
                code_text=code,
                session_id=str(session_id),
                as_of="2022-01-01",
                end_date="2024-01-01",
                run_index=0,
            )
        except Exception as validate_err:
            result = {"status": "failed", "error_message": f"{type(validate_err).__name__}: {validate_err}"}

        if result["status"] == "completed":
            k = result.get("kpis", {})
            logger.info(
                "Code validation passed on cycle %d: ret=%.2f%% trades=%d",
                cycle, k.get("total_return_pct", 0), k.get("total_trades", 0),
            )
            svc_update_session(db, session_id, code_text=code)
            # Auto-save to library
            try:
                from app.services.strategy_lab_library import save_strategy
                save_strategy(
                    name=sess.name or "unnamed",
                    code=code,
                    prompt=sess.prompt or "",
                    plan=sess.plan_text or "",
                    kpis=k,
                    change_description="Auto-saved after code generation",
                    model_id=sess.model_id,
                    session_id=str(session_id),
                )
            except Exception as lib_err:
                logger.warning("Auto-save to library failed: %s", lib_err)
            return GenerateCodeResponse(
                code=code,
                validation_status="passed",
                validation_attempts=cycle + 1,
                validation_log=validation_log,
            )

        last_error = result.get("error_message", "unknown error")
        validation_log.append(f"Debug cycle {cycle}: backtest failed — {last_error}")

        if cycle >= max_debug_cycles:
            break

        # Stage 3: Debug — call LLM with error to produce a complete fixed file
        try:
            fixed, debug_err = debug_code(code, last_error, model=body.model)
            if debug_err or fixed is None:
                validation_log.append(f"Debug cycle {cycle}: debugger failed — {debug_err}")
                continue
            code = fixed
            validation_log.append(f"Debug cycle {cycle}: debugger produced fixed code ({len(fixed)} chars)")
        except Exception as debug_exc:
            validation_log.append(f"Debug cycle {cycle}: debugger crashed — {debug_exc}")
            continue

    # All cycles exhausted — save the last code anyway
    if code:
        svc_update_session(db, session_id, code_text=code)
        logger.warning(
            "Code validation failed after %d debug cycles, but saving last code. "
            "Last error: %s", max_debug_cycles, last_error,
        )
        return GenerateCodeResponse(
            code=code,
            validation_status="failed",
            validation_attempts=max_debug_cycles + 1,
            validation_log=validation_log,
        )

    # Unreachable: if code is None after generate, we return early above.
    # If code is set, the debug loop either passes or saves code anyway.
    # This is a safety net in case the logic changes.
    return GenerateCodeResponse(
        code=code or "",
        validation_status="failed",
        validation_attempts=max_generate_attempts,
        validation_log=validation_log + ["Unexpected state — no code and no error"],
    )


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
        logger.error("Refine diff generation failed: %s", err)
        return RefineCodeResponse(diff="", summary="", error=err or "LLM returned no diff")
    return RefineCodeResponse(diff=diff, summary=diff_summary(diff))


@router.post("/sessions/{session_id}/apply-diff")
def post_apply_diff(
    session_id: uuid.UUID,
    body: RefineCodeRequest,
    db: Session = Depends(get_db),
):
    """Apply a refine diff to the session's code and persist the result.

    If the diff doesn't apply cleanly (e.g. the code has drifted), the LLM
    is called automatically to produce a complete fixed file instead.
    """
    from app.services.strategy_lab_diff import apply_diff as apply_diff_fn
    from app.services.strategy_lab_llm import debug_code
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    current = body.current_code or sess.code_text
    if not current:
        raise HTTPException(status_code=400, detail="no code_text available")
    try:
        new_code = apply_diff_fn(current, body.instruction)
    except ValueError as e:
        # Diff failed to apply — call the LLM to produce a complete fixed file
        logger.info("Diff apply failed (%s), calling LLM to produce fixed code", str(e)[:80])
        try:
            fixed, debug_err = debug_code(current, f"Diff apply failed: {e}", model=body.model)
            if debug_err or fixed is None:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "diff_apply_failed", "details": f"Diff failed: {e}. Auto-fix also failed: {debug_err}"},
                )
            new_code = fixed
        except HTTPException:
            raise
        except Exception as auto_fix_err:
            raise HTTPException(
                status_code=400,
                detail={"error": "diff_apply_failed", "details": f"Diff failed: {e}. Auto-fix crashed: {auto_fix_err}"},
            )
    svc_update_session(db, session_id, code_text=new_code)
    return {"code": new_code}


class RefineDirectRequest(BaseModel):
    instruction: str = Field(..., min_length=1)
    model: Optional[str] = None


class RefineDirectResponse(BaseModel):
    code: str = ""
    summary: str = ""
    validation_status: str = "unknown"
    validation_log: List[str] = Field(default_factory=list)


@router.post("/sessions/{session_id}/refine-direct", response_model=RefineDirectResponse)
def post_refine_direct(
    session_id: uuid.UUID,
    body: RefineDirectRequest,
    db: Session = Depends(get_db),
):
    """Modify strategy code per a natural language instruction.

    The LLM produces the complete modified file directly (no diff).
    Validates with a backtest — if it fails, debug loop up to 3 cycles.
    """
    from app.services.strategy_lab_llm import refine_code_direct, debug_code
    from app.services.strategy_lab_orchestrator import _run_one
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    current = sess.code_text
    if not current:
        raise HTTPException(status_code=400, detail="no code_text available — generate code first")

    max_debug_cycles = 3
    validation_log = []
    code = current

    # Step 1: LLM modifies the code
    modified, err = refine_code_direct(code, body.instruction, model=body.model)
    if err or modified is None:
        logger.error("Refine direct failed: %s", err)
        return RefineDirectResponse(
            code=code, summary="", validation_status="failed",
            validation_log=[f"LLM refine failed: {err}"],
        )
    code = modified
    validation_log.append(f"Code modified ({len(code)} chars)")

    # Step 2: Validate + debug loop
    for cycle in range(max_debug_cycles + 1):
        try:
            result = _run_one(
                code_text=code,
                session_id=str(session_id),
                as_of="2022-01-01",
                end_date="2024-01-01",
                run_index=0,
            )
        except Exception as validate_err:
            result = {"status": "failed", "error_message": f"{type(validate_err).__name__}: {validate_err}"}

        if result["status"] == "completed":
            k = result.get("kpis", {})
            logger.info("Refine validation passed on cycle %d: ret=%.2f%%", cycle, k.get("total_return_pct", 0))
            svc_update_session(db, session_id, code_text=code)
            return RefineDirectResponse(
                code=code,
                summary=f"Applied: {body.instruction[:120]}",
                validation_status="passed",
                validation_log=validation_log,
            )

        last_error = result.get("error_message", "unknown error")
        validation_log.append(f"Debug cycle {cycle}: backtest failed — {last_error}")

        if cycle >= max_debug_cycles:
            break

        # Debug: call LLM to fix
        try:
            fixed, debug_err = debug_code(code, last_error, model=body.model)
            if debug_err or fixed is None:
                validation_log.append(f"Debug cycle {cycle}: debugger failed — {debug_err}")
                continue
            code = fixed
            validation_log.append(f"Debug cycle {cycle}: debugger produced fix ({len(fixed)} chars)")
        except Exception as debug_exc:
            validation_log.append(f"Debug cycle {cycle}: debugger crashed — {debug_exc}")
            continue

    # Save code anyway
    svc_update_session(db, session_id, code_text=code)
    return RefineDirectResponse(
        code=code,
        summary=f"Applied (with fixes): {body.instruction[:120]}",
        validation_status="failed",
        validation_log=validation_log,
    )


# ── Experiment endpoints (Phase 3) ────────────────────────────────────────

class ExperimentRequest(BaseModel):
    n_runs: int = Field(10, ge=1, le=500)
    end_date: str = Field(..., description="YYYY-MM-DD, e.g. '2024-12-31'")
    start_date_min: str = Field("2002-01-01", description="Earliest random start date")
    start_date_max: str = Field("2024-01-01", description="Latest random start date")
    model: Optional[str] = None  # currently unused, kept for future per-run model selection


class ExperimentStartResponse(BaseModel):
    batch_id: str


class ExperimentRow(BaseModel):
    id: str
    session_id: str
    batch_id: str
    run_index: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    kpis: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class BatchStats(BaseModel):
    n_total: int
    n_completed: int
    n_failed: int
    mean_sharpe: Optional[float] = None
    best_sharpe: Optional[float] = None
    best_experiment_id: Optional[str] = None
    top_3: List[Dict[str, Any]] = []
    worst_3: List[Dict[str, Any]] = []


@router.post("/sessions/{session_id}/experiments", response_model=ExperimentStartResponse, status_code=202)
def start_experiments(
    session_id: uuid.UUID,
    body: ExperimentRequest,
    db: Session = Depends(get_db),
):
    """Kick off a batch of N backtest runs with random as_of_date windows."""
    from app.services.strategy_lab_orchestrator import run_batch
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not sess.code_text:
        raise HTTPException(status_code=400, detail="no code_text — generate code first")
    batch_id = run_batch(
        session_id=str(session_id),
        n_runs=body.n_runs,
        code_text=sess.code_text,
        end_date=body.end_date,
        start_date_min=body.start_date_min,
        start_date_max=body.start_date_max,
    )
    return ExperimentStartResponse(batch_id=batch_id)


@router.get("/sessions/{session_id}/experiments", response_model=List[ExperimentRow])
def list_session_experiments(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """List all experiments for a session (across batches), newest first."""
    from app.services.strategy_lab_experiments import list_experiments
    rows = list_experiments(db, session_id=session_id, limit=200)
    return [ExperimentRow(**r.to_dict()) for r in rows]


@router.get("/sessions/{session_id}/batches/{batch_id}/experiments", response_model=List[ExperimentRow])
def list_batch_experiments(
    session_id: uuid.UUID,
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """List experiments in a specific batch."""
    from app.services.strategy_lab_experiments import list_experiments
    rows = list_experiments(db, session_id=session_id, batch_id=batch_id, limit=500)
    return [ExperimentRow(**r.to_dict()) for r in rows]


@router.get("/sessions/{session_id}/batches/{batch_id}/stats", response_model=BatchStats)
def batch_stats(
    session_id: uuid.UUID,
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Summary statistics for a batch (mean Sharpe, top 3, worst 3)."""
    from app.services.strategy_lab_experiments import get_batch_stats
    return BatchStats(**get_batch_stats(db, batch_id))


@router.get("/experiments/{experiment_id}/equity-curve")
def get_equity_curve(
    experiment_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Return the equity curve for a single experiment."""
    from app.models.strategy_lab import StrategyExperiment
    exp = db.get(StrategyExperiment, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"equity_curve": exp.equity_curve or []}


@router.get("/sessions/{session_id}/batches/{batch_id}/events")
async def batch_events(
    session_id: uuid.UUID,
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Server-Sent Events stream for a running batch.

    Polls the in-memory batch queue (thread-safe) every 0.5s and yields
    events until the batch is done.
    """
    from fastapi.responses import StreamingResponse
    from app.services.strategy_lab_orchestrator import get_batch, drain_events
    from app.services.strategy_lab_experiments import create_experiment

    # Verify the session exists
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")

    async def event_generator():
        import time
        try:
            while True:
                # Drain whatever's available right now
                evts = drain_events(batch_id, timeout=0.0)
                for event in evts:
                    if isinstance(event, dict) and event.get("done"):
                        yield f"data: {json.dumps(event)}\n\n"
                        return
                    # Persist this run's result
                    try:
                        exp = create_experiment(
                            db,
                            session_id=session_id,
                            batch_id=uuid.UUID(batch_id),
                            run_index=event["run_index"],
                            start_date=event.get("start_date"),
                            end_date=event.get("end_date"),
                            status=event["status"],
                            kpis=event.get("kpis"),
                            error_message=event.get("error_message"),
                        )
                        yield f"data: {json.dumps({**event, 'id': str(exp.id)})}\n\n"
                    except Exception as persist_err:
                        logger.error("Failed to persist experiment: %s", persist_err)
                        yield f"data: {json.dumps(event)}\n\n"
                # Sleep briefly before next poll
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("Client disconnected from batch %s events", batch_id)
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class SummarizeRequest(BaseModel):
    model: Optional[str] = None


class SummarizeResponse(BaseModel):
    summary_id: str = ""
    summary_text: str = ""
    winner_run_id: Optional[str] = None
    error: Optional[str] = None


@router.post("/sessions/{session_id}/batches/{batch_id}/summarize", response_model=SummarizeResponse)
def summarize_batch(
    session_id: uuid.UUID,
    batch_id: uuid.UUID,
    body: SummarizeRequest,
    db: Session = Depends(get_db),
):
    """LLM analyzes the completed batch and writes a 3-paragraph summary."""
    from app.services.strategy_lab_experiments import list_experiments, get_batch_stats, create_batch_summary
    from app.services.strategy_lab_llm import summarize_batch
    import json

    exps = list_experiments(db, session_id=session_id, batch_id=batch_id, limit=500)
    if not exps:
        raise HTTPException(status_code=400, detail="batch has no experiments yet")
    # Build a compact table
    rows = []
    for e in exps:
        k = e.kpis or {}
        rows.append({
            "run": e.run_index,
            "start": e.start_date.isoformat() if e.start_date else "",
            "ret": k.get("total_return_pct"),
            "wr": k.get("win_rate"),
            "dd": k.get("max_drawdown_pct"),
            "trades": k.get("total_trades"),
            "status": e.status,
        })
    kpis_table = json.dumps(rows, indent=2)
    summary, err = summarize_batch(kpis_table, len(exps), model=body.model)
    if err or summary is None:
        logger.error("Batch summarize failed: %s", err)
        return SummarizeResponse(summary_id="", summary_text="", error=err or "LLM returned no summary")
    stats = get_batch_stats(db, batch_id)
    winner_id = uuid.UUID(stats["best_experiment_id"]) if stats.get("best_experiment_id") else None
    saved = create_batch_summary(
        db,
        session_id=session_id,
        batch_id=batch_id,
        summary_text=summary,
        winner_run_id=winner_id,
        model_id=body.model or "",
    )
    return SummarizeResponse(
        summary_id=str(saved.id),
        summary_text=summary,
        winner_run_id=str(winner_id) if winner_id else None,
    )


class RefineStrategyRequest(BaseModel):
    model: Optional[str] = None


class RefineStrategyResponse(BaseModel):
    diff: str = ""
    summary: str = ""
    rationale: str = ""
    error: Optional[str] = None  # the LLM's reasoning


@router.post("/sessions/{session_id}/batches/{batch_id}/refine", response_model=RefineStrategyResponse)
def refine_strategy_after_batch(
    session_id: uuid.UUID,
    batch_id: uuid.UUID,
    body: RefineStrategyRequest,
    db: Session = Depends(get_db),
):
    """LLM proposes a code change based on the worst-performing runs of a batch."""
    from app.services.strategy_lab_experiments import list_experiments, get_batch_stats, list_batch_summaries
    from app.services.strategy_lab_llm import refine_strategy
    from app.services.strategy_lab_diff import diff_summary
    sess = svc_get_session(db, session_id)
    if sess is None or not sess.code_text:
        raise HTTPException(status_code=400, detail="session has no code_text")
    stats = get_batch_stats(db, batch_id)
    if not stats["worst_3"]:
        raise HTTPException(status_code=400, detail="no completed runs in batch")
    summaries = list_batch_summaries(db, session_id=session_id, batch_id=batch_id)
    summary_text = summaries[0].summary_text if summaries else ""
    worst_table = json.dumps(stats["worst_3"], indent=2, default=str)
    diff, err = refine_strategy(sess.code_text, summary_text, worst_table, model=body.model)
    if err or diff is None:
        logger.error("Refine strategy failed: %s", err)
        return RefineStrategyResponse(diff="", summary="", rationale="", error=err or "LLM returned no diff")
    return RefineStrategyResponse(
        diff=diff,
        summary=diff_summary(diff),
        rationale=summary_text[:200] + "..." if summary_text else "",
    )


# ── Deploy endpoints (Phase 4) ───────────────────────────────────────────

class DeployRequest(BaseModel):
    experiment_id: uuid.UUID
    class_name: Optional[str] = None  # auto-generated if not provided


class DeploymentResponse(BaseModel):
    deployment_id: str
    class_name: str
    class_file_path: str
    is_active: bool
    deployed_at: Optional[str] = None
    rolled_back_at: Optional[str] = None
    experiment_id: Optional[str] = None
    session_id: str
    verification: Dict[str, bool] = {}


class DeploymentListItem(BaseModel):
    deployment_id: str
    class_name: str
    class_file_path: str
    is_active: bool
    deployed_at: Optional[str] = None
    rolled_back_at: Optional[str] = None
    experiment_id: Optional[str] = None
    session_id: str


@router.post("/sessions/{session_id}/deploy", response_model=DeploymentResponse)
def deploy(
    session_id: uuid.UUID,
    body: DeployRequest,
    db: Session = Depends(get_db),
):
    """Generate a pluggable Strategy class from the session's code and deploy to paper."""
    from app.services.strategy_lab_deploy import deploy_strategy
    from app.models.strategy_lab import StrategyExperiment
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    experiment = db.get(StrategyExperiment, body.experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    try:
        result = deploy_strategy(db, sess, experiment, class_name=body.class_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return DeploymentResponse(
        deployment_id=result["deployment_id"],
        class_name=result["class_name"],
        class_file_path=result["class_file_path"],
        is_active=True,
        experiment_id=str(body.experiment_id),
        session_id=str(session_id),
        verification=result["verification"],
    )


@router.get("/deployments", response_model=List[DeploymentListItem])
def list_deployments(
    active_only: bool = Query(False, description="Only return currently-active deployments"),
    db: Session = Depends(get_db),
):
    """List all deployments, newest first."""
    from app.models.strategy_lab import StrategyDeployment
    q = db.query(StrategyDeployment)
    if active_only:
        q = q.filter(StrategyDeployment.is_active == True)
    rows = q.order_by(StrategyDeployment.deployed_at.desc()).all()
    return [
        DeploymentListItem(
            deployment_id=str(r.id),
            class_name=r.class_name,
            class_file_path=r.class_file_path,
            is_active=r.is_active,
            deployed_at=r.deployed_at.isoformat() if r.deployed_at else None,
            rolled_back_at=r.rolled_back_at.isoformat() if r.rolled_back_at else None,
            experiment_id=str(r.experiment_id) if r.experiment_id else None,
            session_id=str(r.session_id),
        )
        for r in rows
    ]


@router.post("/deployments/{deployment_id}/rollback")
def rollback_deployment(
    deployment_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Roll back a deployment and restore the previous one."""
    from app.services.strategy_lab_deploy import rollback_deployment as do_rollback
    try:
        result = do_rollback(db, deployment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


# ── Chat endpoints ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    critique_of: Optional[str] = None


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    model_id: str
    critique_of: Optional[str] = None
    created_at: str


class ChatResponse(BaseModel):
    response: str
    history: List[ChatMessageResponse]


@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
def post_chat(
    session_id: uuid.UUID,
    body: ChatRequest,
    db: Session = Depends(get_db),
):
    """Send a message to the performance chatbot. Returns response + full history."""
    from app.services.strategy_lab_chat import chat_with_llm
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        critique_uuid = uuid.UUID(body.critique_of) if body.critique_of else None
        response_text, history = chat_with_llm(
            db, session_id, body.message,
            model=body.model, critique_of=critique_uuid,
        )
    except (ValueError, RuntimeError) as e:
        logger.error("Chat failed: %s", e)
        return ChatResponse(response=f"Sorry, I encountered an error: {e}", history=[])
    return ChatResponse(
        response=response_text,
        history=[ChatMessageResponse(**h) for h in history],
    )


@router.get("/sessions/{session_id}/chat", response_model=List[ChatMessageResponse])
def get_chat(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Retrieve full chat history for a session."""
    from app.services.strategy_lab_chat import get_chat_history
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    history = get_chat_history(db, session_id, limit=100)
    return [ChatMessageResponse(**h) for h in history]


# ── Library endpoints ───────────────────────────────────────────────────────

class LibrarySaveRequest(BaseModel):
    name: str = Field(..., min_length=1)
    change_description: str = Field(default="")
    model: Optional[str] = None


class LibraryEntryResponse(BaseModel):
    version: int
    strategy_name: str
    created_at: str
    change_description: str
    backtest_kpis: Dict[str, Any] = Field(default_factory=dict)
    code: Optional[str] = None
    folder: Optional[str] = None


class LibraryListResponse(BaseModel):
    name: str
    display_name: str
    version_count: int
    latest_version: LibraryEntryResponse
    versions: List[LibraryEntryResponse]


@router.post("/sessions/{session_id}/library/save", response_model=LibraryEntryResponse)
def save_to_library(
    session_id: uuid.UUID,
    body: LibrarySaveRequest,
    db: Session = Depends(get_db),
):
    """Save the current session's code to the strategy library."""
    from app.services.strategy_lab_library import save_strategy
    from app.services.strategy_lab_experiments import list_experiments
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not sess.code_text:
        raise HTTPException(status_code=400, detail="no code_text to save")

    # Get latest KPIs from most recent completed experiment
    exps = list_experiments(db, session_id=session_id, limit=50)
    best_kpis = {}
    for e in exps:
        if e.status == "completed" and e.kpis:
            best_kpis = e.kpis
            break

    meta = save_strategy(
        name=body.name,
        code=sess.code_text,
        prompt=sess.prompt or "",
        plan=sess.plan_text or "",
        kpis=best_kpis,
        change_description=body.change_description,
        model_id=sess.model_id,
        session_id=str(session_id),
    )
    return LibraryEntryResponse(**meta)


@router.get("/library", response_model=List[LibraryListResponse])
def list_library():
    """List all saved strategies with their version history."""
    from app.services.strategy_lab_library import list_strategies
    strategies = list_strategies()
    result = []
    for s in strategies:
        result.append(LibraryListResponse(
            name=s["name"],
            display_name=s["display_name"],
            version_count=s["version_count"],
            latest_version=LibraryEntryResponse(**s["latest_version"]),
            versions=[LibraryEntryResponse(**v) for v in s["versions"]],
        ))
    return result


@router.get("/library/{name}", response_model=LibraryListResponse)
def get_library_entry(name: str):
    """Get full details for a specific strategy."""
    from app.services.strategy_lab_library import get_strategy
    s = get_strategy(name)
    if s is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    return LibraryListResponse(
        name=s["name"],
        display_name=s["display_name"],
        version_count=len(s["versions"]),
        latest_version=LibraryEntryResponse(**s["versions"][-1]),
        versions=[LibraryEntryResponse(**v) for v in s["versions"]],
    )


class LibraryLoadRequest(BaseModel):
    name: str = Field(..., min_length=1)
    version: Optional[int] = None  # None = latest


@router.post("/library/load", response_model=SessionResponse)
def load_from_library(
    body: LibraryLoadRequest,
    db: Session = Depends(get_db),
):
    """Create a new session from a saved library strategy (skips steps 1-2)."""
    from app.services.strategy_lab_library import get_strategy
    from app.services.strategy_lab_session import create_session
    s = get_strategy(body.name)
    if s is None:
        raise HTTPException(status_code=404, detail="strategy not found")

    # Pick the requested version or latest
    versions = s["versions"]
    if body.version:
        versions = [v for v in versions if v.get("version") == body.version]
    if not versions:
        raise HTTPException(status_code=404, detail="version not found")

    entry = versions[-1]
    code = entry.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="no code found for this version")

    new_sess = create_session(
        db,
        name=f"{entry.get('strategy_name', body.name)} (library)",
        prompt=entry.get("prompt", "Loaded from library"),
        model_id=entry.get("model_id", "kimi-k2.6:cloud"),
    )
    # Set plan and code
    from app.services.strategy_lab_session import update_session
    update_session(db, new_sess.id, plan_text=entry.get("plan", ""), code_text=code)
    return SessionResponse(**new_sess.to_dict())
