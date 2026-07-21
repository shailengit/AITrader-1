"""Orchestrator for batch backtest runs of a single strategy.

For each run in a batch:
  1. Pick a random as_of_date from the configured range
  2. Write the session's code_text to a temp .py file
  3. safe_import_strategy it (via file path, NOT package import — there's
     a name collision with backend/strategies/ the strategy catalog)
  4. Build a fresh StrategyConfig with the random as_of
  5. Call StrategyEngine.run()
  6. Push a result event to the per-batch queue (and persist to DB)

Concurrency: ThreadPoolExecutor with max 4 workers (limits DB pressure).
"""
import importlib.util
import logging
import queue as thread_queue
import random
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Where generated strategy files live
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GENERATED_ROOT = REPO_ROOT / "strategies" / "_generated"
SAFE_IMPORT_PATH = REPO_ROOT / "strategies" / "_safe_import.py"
ENGINE_PATH = REPO_ROOT / "strategies" / "engine.py"


@dataclass
class ExperimentEvent:
    """One event in the orchestrator's stream."""
    run_index: int
    status: str  # "running" | "completed" | "failed"
    kpis: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@dataclass
class ExperimentBatch:
    """In-memory state for one running batch."""
    batch_id: str
    session_id: str
    n_runs: int
    end_date: str
    start_date_min: str
    start_date_max: str
    code_text: str
    # Thread-safe queue (not asyncio.Queue — we run from worker threads)
    queue: thread_queue.Queue = field(default_factory=thread_queue.Queue)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_done: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


# In-memory store of running batches (one entry per batch_id)
_RUNNING_BATCHES: Dict[str, ExperimentBatch] = {}


def get_batch(batch_id: str) -> Optional[ExperimentBatch]:
    return _RUNNING_BATCHES.get(batch_id)


def _write_strategy_file(session_id: str, code_text: str) -> Path:
    """Write the LLM-generated strategy code to a deterministic path."""
    session_dir = GENERATED_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    strategy_path = session_dir / "strategy.py"
    strategy_path.write_text(code_text)
    return strategy_path


def _random_date_in_range(min_date: str, max_date: str) -> str:
    """Pick a random date between min_date and max_date, inclusive."""
    start = datetime.strptime(min_date, "%Y-%m-%d")
    end = datetime.strptime(max_date, "%Y-%m-%d")
    delta_days = (end - start).days
    if delta_days <= 0:
        return min_date
    return (start + timedelta(days=random.randint(0, delta_days))).strftime("%Y-%m-%d")


def _run_one(
    code_text: str,
    session_id: str,
    as_of: str,
    end_date: str,
    run_index: int,
) -> Dict[str, Any]:
    """Run a single backtest. Returns a dict with status/kpis/error/start_date/end_date.

    Runs synchronously (intended to be called from a worker thread).
    """
    import importlib.util
    started_at = datetime.now().isoformat()
    # Write the file
    try:
        strategy_path = _write_strategy_file(session_id, code_text)
    except Exception as e:
        return {
            "run_index": run_index,
            "status": "failed",
            "error_message": f"Failed to write strategy file: {e}",
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "start_date": as_of,
            "end_date": end_date,
        }

    # safe-import via file path (avoids name collision with backend/strategies/)
    def _safe_import(path: str):
        spec = importlib.util.spec_from_file_location("_safe_imp_orchestrator", path)
        if spec is None or spec.loader is None:
            return type("R", (), {"error": f"Could not create spec for {path}", "module": None})()
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_safe_imp_orchestrator"] = mod
        try:
            spec.loader.exec_module(mod)
            return type("R", (), {"error": None, "module": mod})()
        except Exception as e:
            sys.modules.pop("_safe_imp_orchestrator", None)
            return type("R", (), {"error": f"{type(e).__name__}: {e}", "module": None})()

    result = _safe_import(str(strategy_path))
    if result.error or result.module is None:
        return {
            "run_index": run_index,
            "status": "failed",
            "error_message": f"Import error: {result.error}",
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "start_date": as_of,
            "end_date": end_date,
        }

    # Build a fresh StrategyConfig. The module may have:
    #   - a build_config(as_of, end, capital) function (golden_cross style)
    #   - a top-level CONFIG = StrategyConfig(...) instance
    mod = result.module
    try:
        cfg = None
        if hasattr(mod, "build_config") and callable(mod.build_config):
            cfg = mod.build_config(as_of=as_of, end=end_date)
        elif hasattr(mod, "CONFIG") and mod.CONFIG is not None:
            # Mutate the existing CONFIG
            mod.CONFIG.as_of = as_of
            mod.CONFIG.end = end_date
            cfg = mod.CONFIG
        else:
            return {
                "run_index": run_index,
                "status": "failed",
                "error_message": "Module has no build_config() function and no CONFIG attribute",
                "started_at": started_at,
                "completed_at": datetime.now().isoformat(),
                "start_date": as_of,
                "end_date": end_date,
            }

        # Load engine via file path (avoids name collision with backend/strategies/)
        engine_spec = importlib.util.spec_from_file_location(
            "engine_for_orchestrator",
            str(ENGINE_PATH),
        )
        engine_mod = importlib.util.module_from_spec(engine_spec)
        sys.modules["engine_for_orchestrator"] = engine_mod
        engine_spec.loader.exec_module(engine_mod)

        result_data = engine_mod.StrategyEngine(cfg).run()
        summary = result_data["summary"]

        return {
            "run_index": run_index,
            "status": "completed",
            "kpis": summary,
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "start_date": as_of,
            "end_date": end_date,
        }
    except Exception as e:
        return {
            "run_index": run_index,
            "status": "failed",
            "error_message": f"{type(e).__name__}: {e}",
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "start_date": as_of,
            "end_date": end_date,
        }


def run_batch(
    session_id: str,
    n_runs: int,
    code_text: str,
    end_date: str,
    start_date_min: str,
    start_date_max: str,
) -> str:
    """Start a batch of n_runs backtests in a background thread.

    Returns the batch_id immediately. The actual runs execute in a thread
    pool; each result is persisted to the DB and pushed to the in-memory
    queue (so SSE consumers can stream them).
    """
    batch_id = str(uuid.uuid4())
    batch = ExperimentBatch(
        batch_id=batch_id,
        session_id=session_id,
        n_runs=n_runs,
        end_date=end_date,
        start_date_min=start_date_min,
        start_date_max=start_date_max,
        code_text=code_text,
    )
    _RUNNING_BATCHES[batch_id] = batch

    def _persist_event(event: Dict[str, Any]):
        """Persist one run's result to the DB. Called from worker threads."""
        try:
            from app.db.database import SessionLocal
            from app.models.strategy_lab import StrategyExperiment
            with SessionLocal() as db:
                exp = StrategyExperiment(
                    session_id=uuid.UUID(session_id),
                    batch_id=uuid.UUID(batch_id),
                    run_index=event["run_index"],
                    start_date=event.get("start_date"),
                    end_date=event.get("end_date"),
                    status=event["status"],
                    kpis=event.get("kpis"),
                    error_message=event.get("error_message"),
                )
                db.add(exp)
                db.commit()
        except Exception as e:
            logger.exception("Failed to persist experiment: %s", e)

    def _worker():
        try:
            with ThreadPoolExecutor(max_workers=min(4, n_runs)) as ex:
                futures = []
                for i in range(n_runs):
                    as_of = _random_date_in_range(start_date_min, start_date_max)
                    fut = ex.submit(_run_one, code_text, session_id, as_of, end_date, i + 1)
                    futures.append(fut)

                for fut in as_completed(futures):
                    result = fut.result()
                    # Persist to DB (durable, survives SSE disconnects)
                    _persist_event(result)
                    # Push to in-memory queue (SSE stream)
                    batch.queue.put(result)
        except Exception as e:
            logger.exception("Batch %s failed: %s", batch_id, e)
        finally:
            # Mark done and push sentinel
            with batch.lock:
                batch.is_done = True
            batch.queue.put(None)  # sentinel
            # Schedule cleanup after 5 minutes (give the SSE consumer time)
            def _cleanup():
                _RUNNING_BATCHES.pop(batch_id, None)
            threading.Timer(300.0, _cleanup).start()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return batch_id


def drain_events(batch_id: str, timeout: float = 0.5):
    """Drain all currently-available events from a batch's queue.

    Used by the SSE consumer. Returns a list of events. If the batch is
    done and the queue is empty, returns a list with a single sentinel dict.
    """
    batch = _RUNNING_BATCHES.get(batch_id)
    if batch is None:
        return [{"done": True, "batch_id": batch_id, "error": "batch not found"}]
    events_out = []
    while True:
        try:
            item = batch.queue.get(timeout=timeout)
        except thread_queue.Empty:
            break
        if item is None:
            # sentinel
            events_out.append({"done": True, "batch_id": batch_id, "n_runs": batch.n_runs})
            return events_out
        events_out.append(item)
    # If we got nothing and the batch is done, emit a sentinel
    with batch.lock:
        done = batch.is_done
    if not events_out and done:
        events_out.append({"done": True, "batch_id": batch_id, "n_runs": batch.n_runs})
    return events_out


def is_batch_done(batch_id: str) -> bool:
    batch = _RUNNING_BATCHES.get(batch_id)
    if batch is None:
        return True
    with batch.lock:
        return batch.is_done
