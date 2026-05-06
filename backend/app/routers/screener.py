"""
AI Stock Screener router for TradeCraft API.
Supports two screening modes:
1. Dormant Giant (agnoMultiAgentTrader_3) - Bollinger squeeze + EPS acceleration
2. Quant Strategy (agnoMultiAgentTrader_2) - TA-based with backtesting

Includes real-time SSE streaming of agent logs and progress.
"""

import uuid
import json
import logging
import asyncio
from typing import List, Optional, Dict, Any, Literal
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.services.agno_screener import (
    run_dormant_giant_screener,
    run_dormant_giant_screener_with_ai,
    run_quant_strategy_screener,
    run_quant_strategy_screener_with_ai,
    parse_quant_filters
)
from app.services.pdf_generator import generate_screener_report

logger = logging.getLogger(__name__)

router = APIRouter()

# =============================================================================
# In-memory state
# =============================================================================

scan_status: Dict[str, Dict[str, Any]] = {}
scan_queues: Dict[str, asyncio.Queue] = {}


# =============================================================================
# Models
# =============================================================================

class ScanRequest(BaseModel):
    """Scan request model."""
    mode: Literal["dormant_giant", "quant_strategy"] = "dormant_giant"
    use_ai: bool = True
    cutoff_date: Optional[str] = None  # For quant_strategy mode backtesting
    prompt: Optional[str] = None  # Custom prompt for AI analysis
    max_results: int = 50
    filters: Optional[Dict[str, Any]] = None


class ScanResult(BaseModel):
    """Stock scan result model."""
    ticker: str
    signal: Optional[str] = None
    fundamental_catalyst: Optional[str] = None
    close: Optional[float] = None
    data_date: Optional[str] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    volume: Optional[int] = None


class ScanStatus(BaseModel):
    """Scan status model."""
    scan_id: str
    mode: str
    status: str  # 'pending', 'running', 'completed', 'failed'
    progress: int  # 0-100
    use_ai: bool
    results: Optional[List[Dict]] = None
    ai_report: Optional[str] = None
    error: Optional[str] = None


class ParseFiltersRequest(BaseModel):
    """Request to parse a natural language prompt into structured filters."""
    prompt: str


class ParseFiltersResponse(BaseModel):
    """Response containing parsed QuantFilters."""
    filters: Dict[str, Any]
    raw_prompt: str


# =============================================================================
# Helpers
# =============================================================================

def _create_event(event_type: str, data: Dict[str, Any]) -> str:
    """Format a Server-Sent Event payload."""
    payload = json.dumps({"type": event_type, "data": data})
    return f"data: {payload}\n\n"


def _push_event(scan_id: str, event_type: str, data: Dict[str, Any]):
    """Push an event into the scan's SSE queue if it exists."""
    q = scan_queues.get(scan_id)
    if q is not None:
        try:
            q.put_nowait(_create_event(event_type, data))
        except asyncio.QueueFull:
            pass


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/modes")
async def get_screener_modes():
    """Get available screening modes with descriptions."""
    return {
        "modes": [
            {
                "id": "dormant_giant",
                "name": "Dormant Giant Screener",
                "description": "Identifies stocks with Bollinger Band squeeze, OBV hidden accumulation, or resistance breakouts. Verifies with EPS acceleration as catalyst.",
                "use_ai_options": [True, False],
                "supports_backtesting": False,
                "agents": ["Technical Specialist", "Fundamental Specialist", "Risk Manager"]
            },
            {
                "id": "quant_strategy",
                "name": "Quant Strategy Screener",
                "description": "Technical analysis screening with fundamental health verification, risk assessment, and optional historical backtesting.",
                "use_ai_options": [True, False],
                "supports_backtesting": True,
                "agents": ["Technical Specialist", "Fundamental Specialist", "Risk Manager", "Performance Analyst"]
            }
        ]
    }


@router.post("/parse-filters", response_model=Dict[str, Any])
async def parse_filters(request: ParseFiltersRequest):
    """
    Parse a natural language prompt into structured QuantFilters.

    Uses a lightweight LLM call to extract filter criteria from the user's directive.
    Returns the parsed filters for frontend review and editing.
    """
    try:
        filters = await run_in_threadpool(lambda: parse_quant_filters(request.prompt))
        return {
            "filters": filters,
            "raw_prompt": request.prompt,
            "message": "Filters parsed successfully. Review and edit before scanning."
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Filter parsing failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Filter parsing failed: {str(e)}") from e


@router.post("/scan", response_model=Dict[str, Any])
async def run_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """
    Run stock screening scan.

    Modes:
    - dormant_giant: Bollinger squeeze + EPS acceleration detection
    - quant_strategy: TA-based with fundamental health and optional backtesting

    Set use_ai=True to get AI-generated analysis report from multi-agent team.
    """
    scan_id = str(uuid.uuid4())

    # Initialize status
    scan_status[scan_id] = {
        "mode": request.mode,
        "status": "pending",
        "progress": 0,
        "use_ai": request.use_ai,
        "results": None,
        "ai_report": None,
        "error": None,
        "logs": []
    }

    # Create SSE queue for this scan
    scan_queues[scan_id] = asyncio.Queue(maxsize=500)

    # Run scan in background
    background_tasks.add_task(run_screening_task, scan_id, request)

    return {
        "scan_id": scan_id,
        "mode": request.mode,
        "use_ai": request.use_ai,
        "status": "pending",
        "message": f"Scan started in {request.mode} mode. Stream /api/screener/stream/{scan_id} for real-time updates."
    }


@router.get("/stream/{scan_id}")
async def stream_scan(scan_id: str):
    """
    Server-Sent Events endpoint for real-time scan progress and agent logs.

    Streams events:
    - log: { agent, message, type, color }
    - progress: { progress }
    - status: { status, error? }
    """
    if scan_id not in scan_status:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    q = scan_queues.get(scan_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Scan queue not found")

    async def event_generator():
        # Send initial state
        yield _create_event("status", {"status": scan_status[scan_id]["status"], "progress": scan_status[scan_id]["progress"]})

        while True:
            # Drain any queued events first (handles fast scans where queue filled before connect)
            drained = False
            while not q.empty():
                try:
                    event = q.get_nowait()
                    yield event
                    drained = True
                except asyncio.QueueEmpty:
                    break

            # After draining, if scan is done, send final status and exit
            if scan_status[scan_id]["status"] in ("completed", "failed"):
                yield _create_event("status", {"status": scan_status[scan_id]["status"], "progress": scan_status[scan_id]["progress"]})
                break

            # If we drained events, loop again immediately to check status
            if drained:
                await asyncio.sleep(0.1)
                continue

            try:
                event = await asyncio.wait_for(q.get(), timeout=5.0)
                yield event
            except asyncio.TimeoutError:
                # Send keep-alive heartbeat
                yield ":heartbeat\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/status/{scan_id}")
async def get_scan_status(scan_id: str):
    """Get status of a running or completed scan (polling fallback)."""
    if scan_id not in scan_status:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    status = scan_status[scan_id]
    logs = status.get("logs", [])

    # Convert legacy string logs to structured format
    structured_logs = []
    for log in logs:
        if isinstance(log, dict):
            structured_logs.append(log)
        else:
            structured_logs.append({
                "agent": "System",
                "message": str(log),
                "type": "system",
                "color": "gray"
            })

    return {
        "scan_id": scan_id,
        "mode": status.get("mode", "unknown"),
        "status": status["status"],
        "progress": status["progress"],
        "use_ai": status.get("use_ai", False),
        "results_count": len(status["results"]) if status.get("results") else 0,
        "has_ai_report": status.get("ai_report") is not None,
        "error": status.get("error"),
        "logs": structured_logs
    }


@router.get("/results/{scan_id}")
async def get_scan_results(scan_id: str):
    """Get final results of a completed scan."""
    if scan_id not in scan_status:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    status = scan_status[scan_id]

    if status["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Scan not completed. Current status: {status['status']}"
        )

    return {
        "scan_id": scan_id,
        "mode": status.get("mode", "unknown"),
        "status": "completed",
        "use_ai": status.get("use_ai", False),
        "results_count": len(status["results"]) if status.get("results") else 0,
        "results": status["results"],
        "ai_report": status.get("ai_report")
    }


@router.get("/ai-report/{scan_id}")
async def get_ai_report(scan_id: str):
    """Get the AI-generated analysis report for a completed scan."""
    if scan_id not in scan_status:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    status = scan_status[scan_id]

    if status["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Scan not completed. Current status: {status['status']}"
        )

    if not status.get("ai_report"):
        raise HTTPException(
            status_code=404,
            detail="No AI report available. This scan was run without AI analysis (use_ai=False)."
        )

    return {
        "scan_id": scan_id,
        "mode": status.get("mode"),
        "ai_report": status["ai_report"]
    }


@router.get("/report/{scan_id}")
async def download_report(scan_id: str):
    """
    Download a professional PDF report for a completed scan.
    """
    if scan_id not in scan_status:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    status = scan_status[scan_id]

    if status["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Scan not completed. Current status: {status['status']}"
        )

    results = status.get("results") or []
    ai_report = status.get("ai_report")
    mode = status.get("mode", "unknown")
    use_ai = status.get("use_ai", False)

    # Build summary text
    summary = status.get("summary", f"Found {len(results)} stocks.")

    # Build stats
    stats = {
        "technical_candidates": status.get("technical_candidates", len(results)),
        "verified_candidates": status.get("verified_candidates", len(results)),
        "results_count": len(results)
    }

    try:
        pdf_bytes = generate_screener_report(
            mode=mode,
            use_ai=use_ai,
            results=results,
            summary=summary,
            ai_report=ai_report,
            stats=stats
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("PDF generation failed for scan %s: %s", scan_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(e)}"
        ) from e

    safe_mode = mode.replace("_", "-")
    filename = f"tradecraft-screener-{safe_mode}-{scan_id[:8]}.pdf"

    from fastapi.responses import Response
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.delete("/scan/{scan_id}")
async def delete_scan(scan_id: str):
    """Delete a scan from memory."""
    if scan_id not in scan_status:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    # Clean up queue
    if scan_id in scan_queues:
        del scan_queues[scan_id]
    del scan_status[scan_id]
    return {"message": f"Scan {scan_id} deleted"}


@router.get("/health")
async def screener_health():
    """Health check for screener service."""
    return {
        "status": "healthy",
        "active_scans": len(scan_status),
        "modes_available": ["dormant_giant", "quant_strategy"]
    }


# =============================================================================
# Background task
# =============================================================================

async def run_screening_task(scan_id: str, request: ScanRequest):
    """Background task to run the screening workflow with real-time event streaming."""

    def update_progress(p: int):
        scan_status[scan_id]["progress"] = p
        _push_event(scan_id, "progress", {"progress": p})

    def update_logs(message: str):
        scan_status[scan_id]["logs"].append(message)
        _push_event(scan_id, "log", {"agent": "System", "message": message, "type": "system", "color": "gray"})

    def update_agent_log(agent: str, message: str, log_type: str = "system", color: str = "gray"):
        entry = {"agent": agent, "message": message, "type": log_type, "color": color}
        scan_status[scan_id]["logs"].append(entry)
        _push_event(scan_id, "log", entry)

    try:
        scan_status[scan_id]["status"] = "running"
        scan_status[scan_id]["progress"] = 0
        _push_event(scan_id, "status", {"status": "running", "progress": 0})
        update_agent_log("System", f"Starting scan {scan_id} in {request.mode} mode")

        mode = request.mode
        use_ai = request.use_ai
        logs_buffer = []

        if mode == "dormant_giant":
            if use_ai:
                result = await run_in_threadpool(
                    lambda: run_dormant_giant_screener_with_ai(
                        prompt=request.prompt,
                        progress_callback=update_progress,
                        log_callback=update_logs,
                        filters=request.filters,
                        logs_buffer=logs_buffer,
                        agent_log_callback=update_agent_log
                    )
                )
            else:
                result = await run_in_threadpool(
                    lambda: run_dormant_giant_screener(
                        prompt=request.prompt,
                        progress_callback=update_progress,
                        log_callback=update_logs,
                        filters=request.filters
                    )
                )

        elif mode == "quant_strategy":
            if use_ai:
                result = await run_in_threadpool(
                    lambda: run_quant_strategy_screener_with_ai(
                        prompt=request.prompt or "Find me candidates for a high-growth breakout. Technically, they should be in a Volatility Squeeze (volatility_bbw). Fundamentally, they must have positive QoQ revenue growth.",
                        cutoff_date=request.cutoff_date,
                        logs_buffer=logs_buffer,
                        progress_callback=update_progress,
                        agent_log_callback=update_agent_log,
                        filters=request.filters
                    )
                )
            else:
                result = await run_in_threadpool(
                    lambda: run_quant_strategy_screener(
                        prompt=request.prompt or "Find me candidates for a high-growth breakout. Technically, they should be in a Volatility Squeeze (volatility_bbw). Fundamentally, they must have positive QoQ revenue growth.",
                        cutoff_date=request.cutoff_date,
                        progress_callback=update_progress,
                        log_callback=update_logs,
                        filters=request.filters
                    )
                )
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Merge any logs from result into logs_buffer
        if result and "logs" in result and isinstance(result["logs"], list):
            logs_buffer.extend(result["logs"])
            for entry in result["logs"]:
                if isinstance(entry, dict):
                    _push_event(scan_id, "log", entry)

        # Limit results
        if "results" in result and isinstance(result["results"], list):
            result["results"] = result["results"][:request.max_results]

        update_progress(100)
        scan_status[scan_id]["status"] = "completed"
        scan_status[scan_id]["progress"] = 100
        scan_status[scan_id]["results"] = result.get("results", [])
        scan_status[scan_id]["ai_report"] = result.get("ai_report")
        scan_status[scan_id]["summary"] = result.get("summary", "")
        scan_status[scan_id]["technical_candidates"] = result.get("technical_candidates", 0)
        scan_status[scan_id]["verified_candidates"] = result.get("verified_candidates", 0)

        _push_event(scan_id, "status", {"status": "completed", "progress": 100})
        update_agent_log("System", f"Scan complete. {len(result.get('results', []))} stocks found.")

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Scan %s failed: %s", scan_id, e)
        scan_status[scan_id]["status"] = "failed"
        scan_status[scan_id]["error"] = str(e)
        _push_event(scan_id, "status", {"status": "failed", "error": str(e)})
        update_agent_log("System", f"Scan failed: {str(e)}", log_type="error", color="red")

    finally:
        # Close the queue gracefully after a short delay
        await asyncio.sleep(2.0)
        if scan_id in scan_queues:
            del scan_queues[scan_id]
