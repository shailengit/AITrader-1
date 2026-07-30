"""Strategy Agent — a server-side agent loop for generating, validating, and
improving trading strategies.

The agent runs as a background task and streams progress events via an async
queue. It has a structured loop:

  1. Read Context  — load template, learnings, reference strategies
  2. Generate     — LLM produces the 4 strategy functions + CONFIG
  3. Validate     — syntax check, import check, anti-pattern scan
  4. Backtest     — run a single backtest window, collect KPIs
  5. Debug        — if validation/backtest fails, LLM fixes the code (max 3×)
  6. Improve      — if KPIs are poor, LLM improves the code (max 2×)
  7. Return       — final code + KPIs + summary

Every step emits detailed progress events so the frontend can show the user
exactly what's happening.
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
import ast
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator, Tuple

from app.services.strategy_lab_llm import (
    generate_code,
    debug_code,
    _validate_strategy_code,
)
from app.services.strategy_lab_prompts import make_code_prompt

logger = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # repo root
_TEMPLATE_PATH = _BASE_DIR / "strategies" / "_template.py"
_LEARNINGS_PATH = (
    _BASE_DIR / "backend" / "app" / "services" / "strategy_lab_learnings.md"
)
_GENERATED_DIR = _BASE_DIR / "strategies" / "_generated"


# ── Event types ──────────────────────────────────────────────────────────────
class AgentEvent:
    """Typed event emitted by the agent during its lifecycle."""

    def __init__(self, event_type: str, **kwargs):
        self.type = event_type
        self.data = kwargs
        self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        return {"type": self.type, "timestamp": self.timestamp, **self.data}

    def to_sse(self) -> str:
        return f"data: {json.dumps(self.to_dict())}\n\n"


# ── Session store ───────────────────────────────────────────────────────────
class AgentSession:
    """Holds state for one agent generation session."""

    def __init__(self, session_id: str, prompt: str):
        self.session_id = session_id
        self.prompt = prompt
        self.code: Optional[str] = None
        self.kpis: Optional[dict] = None
        self.summary: Optional[str] = None
        self.error: Optional[str] = None
        self.status: str = "pending"  # pending | running | done | failed
        self.events: asyncio.Queue = asyncio.Queue()
        self._work_dir: Optional[Path] = None
        self.debug_attempts = 0
        self.improve_iterations = 0
        self.created_at = datetime.utcnow()

    @property
    def work_dir(self) -> Path:
        if self._work_dir is None:
            self._work_dir = _GENERATED_DIR / self.session_id
            self._work_dir.mkdir(parents=True, exist_ok=True)
        return self._work_dir

    async def emit(self, event_type: str, **kwargs):
        """Emit an event to the SSE stream."""
        event = AgentEvent(event_type, **kwargs)
        await self.events.put(event)

    async def event_stream(self) -> AsyncGenerator[str, None]:
        """Async generator that yields SSE-formatted events."""
        try:
            while True:
                event = await asyncio.wait_for(self.events.get(), timeout=300)
                yield event.to_sse()
                if event.type == "result" or event.type == "error_fatal":
                    break
        except asyncio.TimeoutError:
            yield AgentEvent("error_fatal", detail="Session timed out after 300s").to_sse()


# ── In-memory session registry ───────────────────────────────────────────────
_sessions: Dict[str, AgentSession] = {}


def get_session(session_id: str) -> Optional[AgentSession]:
    return _sessions.get(session_id)


# ── The Agent ───────────────────────────────────────────────────────────────
class StrategyAgent:
    """Main agent loop for strategy generation."""

    def __init__(
        self,
        session: AgentSession,
        model: Optional[str] = None,
        strategy_session_id: Optional[str] = None,
    ):
        self.session = session
        self.model = model
        self.strategy_session_id = strategy_session_id
        self.template_code: str = ""
        self.learnings_text: str = ""
        self.code: Optional[str] = None
        self.kpis: Optional[dict] = None

    # ── Public entry point ──────────────────────────────────────────────

    async def run(self):
        """Run the full agent loop with flat iteration (no recursive calls)."""
        self.session.status = "running"
        try:
            # Step 1: Read context
            await self._step_read_context()

            # Step 2: Generate code
            await self._step_generate()

            # Steps 3-5: Validate → Debug loop (flat, max 3 attempts)
            if self.code:
                for attempt in range(1, 4):
                    self.session.debug_attempts = attempt
                    valid = await self._step_validate()
                    if valid:
                        break
                    await self._step_debug(attempt=attempt, initial_error="Validation checks failed — fix imports, function signatures, and remove anti-patterns")
                    if not self.code:
                        break

            # Step 4: Backtest
            if self.code:
                await self._step_backtest()

            # Step 6: Improve loop (flat, max 2 iterations)
            if self.code and self.kpis:
                for iteration in range(1, 3):
                    self.session.improve_iterations = iteration
                    tr = self.kpis.get("total_return", 0)
                    sh = self.kpis.get("sharpe_ratio", 0)
                    if tr >= 0.10 and sh >= 0.8:
                        await self.session.emit(
                            "step", step="improving", status="skipped",
                            detail=f"Performance is good (Return: {tr*100:.1f}%, Sharpe: {sh:.2f}) — no improvement needed",
                        )
                        break
                    improved = await self._step_improve(iteration=iteration)
                    if not improved:
                        break
                    # Re-backtest after improvement since code changed
                    if self.code:
                        await self._step_backtest()

            # Step 7: Return results
            await self._step_return()
        except Exception as e:
            logger.exception("Agent loop failed")
            self.session.error = f"{type(e).__name__}: {e}"
            self.session.status = "failed"
            await self.session.emit(
                "error_fatal",
                detail=f"Agent loop failed: {e}",
                traceback=getattr(e, "__traceback__", None),
            )
        finally:
            if self.session.status not in ("done", "failed"):
                self.session.status = "done" if self.code else "failed"

    # ── Step implementations ─────────────────────────────────────────────

    async def _step_read_context(self):
        """Step 1: Read template, learnings, and reference strategies."""
        await self.session.emit(
            "step", step="reading_context", status="running",
            detail="Reading template and accumulated learnings...",
        )

        # Read template
        try:
            self.template_code = _TEMPLATE_PATH.read_text()
            template_size = len(self.template_code)
            await self.session.emit(
                "context", item="template", size=f"{template_size/1024:.1f}KB",
                detail=f"Loaded strategy template ({template_size/1024:.1f}KB)",
            )
        except Exception as e:
            logger.warning("Could not read template: %s", e)
            self.template_code = "# (template not found)"
            await self.session.emit(
                "context", item="template", size="0",
                detail=f"Template not found: {e}",
            )

        # Read learnings
        try:
            self.learnings_text = _LEARNINGS_PATH.read_text()
            # Count golden rules and anti-patterns
            golden_rules = len(re.findall(r"^### \d+\.", self.learnings_text, re.MULTILINE))
            anti_patterns = len(re.findall(r"^\|", self.learnings_text, re.MULTILINE))
            await self.session.emit(
                "context", item="learnings", count=golden_rules + anti_patterns,
                detail=f"Loaded {golden_rules} golden rules + {anti_patterns} anti-patterns",
            )
        except Exception as e:
            logger.warning("Could not read learnings: %s", e)
            self.learnings_text = ""
            await self.session.emit(
                "context", item="learnings", count=0,
                detail=f"Learnings not found: {e}",
            )

        # List reference strategies
        try:
            lib_dir = _BASE_DIR / "strategies" / "library"
            if lib_dir.exists():
                ref_strategies = [d.name for d in lib_dir.iterdir() if d.is_dir()]
                await self.session.emit(
                    "context", item="references", count=len(ref_strategies),
                    detail=f"Found {len(ref_strategies)} reference strategies in library",
                )
        except Exception:
            pass

        await self.session.emit(
            "step", step="reading_context", status="done",
            detail="Context loaded successfully",
        )

    async def _step_generate(self):
        """Step 2: Generate strategy code using LLM."""
        await self.session.emit(
            "step", step="generating", status="running",
            detail="Generating strategy code from your prompt...",
        )

        # Build the code prompt with template and learnings
        messages = self._build_generation_prompt()

        await self.session.emit(
            "llm_call", phase="generation", model=self.model or "default",
            max_tokens=32768, detail="Calling LLM to generate strategy code...",
        )

        # Call LLM
        content, finish_reason, err = await self._call_llm(messages, max_tokens=32768)

        if err:
            await self.session.emit(
                "step", step="generating", status="failed",
                detail=f"LLM call failed: {err}",
                finish_reason=finish_reason,
            )
            return

        # Extract code block
        code = self._extract_code_block(content or "")
        if code is None or len(code) < 500:
            # Try to find the longest code block
            all_blocks = re.findall(r"```python\s*\n(.*?)```", content or "", re.DOTALL)
            if not all_blocks:
                all_blocks = re.findall(r"```\s*\n(.*?)```", content or "", re.DOTALL)
            if all_blocks:
                all_blocks.sort(key=len, reverse=True)
                code = textwrap.dedent(all_blocks[0].rstrip()) + "\n"

        if code is None or len(code) < 500:
            preview = (content or "")[:200].replace("\n", " ")
            await self.session.emit(
                "step", step="generating", status="failed",
                detail=f"Response contained no valid code block (first 200 chars: {preview!r})",
                finish_reason=finish_reason,
            )
            return

        # Validate syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            await self.session.emit(
                "step", step="generating", status="failed",
                detail=f"Syntax error: {e}",
                line=e.lineno,
            )
            return

        # Check for anti-patterns
        warnings = _validate_strategy_code(code)
        if warnings:
            for w in warnings:
                await self.session.emit(
                    "validation_warning", detail=w,
                )

        # Write to file
        strategy_path = self.session.work_dir / "strategy.py"
        strategy_path.write_text(code)
        self.code = code

        # Count functions
        funcs = re.findall(r"^def (\w+)", code, re.MULTILINE)
        await self.session.emit(
            "code_generated", size=f"{len(code)/1024:.1f}KB",
            functions=funcs,
            path=str(strategy_path),
            detail=f"Generated {len(funcs)} functions ({len(code)/1024:.1f}KB)",
        )

        await self.session.emit(
            "step", step="generating", status="done",
            detail="Code generated successfully",
        )

    async def _step_validate(self) -> bool:
        """Step 3: Validate the generated code. Returns True if all checks pass."""
        await self.session.emit(
            "step", step="validating", status="running",
            detail="Checking imports and structure...",
        )

        if not self.code:
            return False

        checks = {}

        # 1. Check imports (only in non-comment code)
        has_engine_import = "from app.db.database import engine" in self.code
        has_security_import = "from app.utils.security import get_safe_table_name" in self.code
        # Check create_engine only in non-comment lines
        has_no_create_engine = True
        for line in self.code.split("\n"):
            code_part = line.strip().split("#")[0].strip()
            if "create_engine" in code_part:
                has_no_create_engine = False
                break
        checks["imports"] = has_engine_import and has_security_import and has_no_create_engine

        # 2. Check all 4 functions exist
        has_precompute = "def precompute" in self.code
        has_entry_score = "def entry_score" in self.code
        has_holding_score = "def holding_score" in self.code
        has_exit_check = "def exit_check" in self.code
        checks["functions"] = all([has_precompute, has_entry_score, has_holding_score, has_exit_check])

        # 3. Check CONFIG exists (the class name varies: StrategyConfig, _StrategyEngine, etc.)
        has_config = bool(re.search(r"CONFIG\s*=", self.code))
        checks["config"] = has_config

        # 4. Check for TODO placeholders in function bodies
        has_no_todos = True
        todo_functions = []
        for func_name in ["precompute", "entry_score", "holding_score", "exit_check"]:
            # Find the function body and check for TODO
            func_match = re.search(
                rf'def {func_name}\(.*?\):.*?""".*?""".*?(?=\n\S|\Z)',
                self.code, re.DOTALL
            )
            if func_match:
                func_body = func_match.group(0)
                if "TODO" in func_body or "todo" in func_body:
                    has_no_todos = False
                    todo_functions.append(func_name)
        checks["no_todos"] = has_no_todos

        # 5. Check precompute doesn't just return empty dict
        precompute_returns_empty = False
        pc_match = re.search(
            r'def precompute\(.*?\):.*?""".*?""".*?(?=\n\S|\Z)',
            self.code, re.DOTALL
        )
        if pc_match:
            pc_body = pc_match.group(0)
            if "return {}" in pc_body:
                precompute_returns_empty = True
                checks["precompute_not_empty"] = False
            else:
                checks["precompute_not_empty"] = True
        else:
            checks["precompute_not_empty"] = True  # function not found, handled by functions check

        # 6. Check for anti-patterns (only in non-comment code)
        has_no_anti_patterns = True
        anti_patterns_found = []
        code_lines = self.code.split("\n")
        for i, line in enumerate(code_lines):
            stripped = line.strip()
            # Strip inline comments: only check code before the first #
            code_part = stripped.split("#")[0].strip()
            if not code_part:
                continue
            for pattern in ["create_engine(", "os.environ.setdefault", "YFData.download"]:
                if pattern in code_part:
                    has_no_anti_patterns = False
                    anti_patterns_found.append(f"{pattern} (line {i+1})")
        checks["anti_patterns"] = has_no_anti_patterns

        all_pass = all(checks.values())

        await self.session.emit(
            "validation",
            imports_ok=checks["imports"],
            functions_found=4 if checks["functions"] else sum([has_precompute, has_entry_score, has_holding_score, has_exit_check]),
            config_ok=checks["config"],
            no_todos=checks.get("no_todos", True),
            todo_functions=todo_functions if not has_no_todos else None,
            precompute_not_empty=checks.get("precompute_not_empty", True),
            anti_patterns_ok=checks["anti_patterns"],
            anti_patterns_found=anti_patterns_found if anti_patterns_found else None,
            detail="All checks passed" if all_pass else "Some checks failed",
        )

        if not all_pass:
            failed_checks = [k for k, v in checks.items() if not v]
            await self.session.emit(
                "step", step="validating", status="failed",
                detail=f"Validation failed: {', '.join(failed_checks)}",
                checks=checks,
            )
            return False
        else:
            await self.session.emit(
                "step", step="validating", status="done",
                detail="All validation checks passed",
            )
            return True

    async def _step_backtest(self):
        """Step 4: Run a single backtest window."""
        await self.session.emit(
            "step", step="backtesting", status="running",
            detail="Running single backtest window...",
        )

        if not self.code:
            return

        # Write code to file if not already written
        strategy_path = self.session.work_dir / "strategy.py"
        if not strategy_path.exists():
            strategy_path.write_text(self.code)

        await self.session.emit(
            "llm_call", phase="backtest", detail="Executing backtest...",
        )

        # Run backtest in subprocess
        try:
            kpis, error, stdout = await self._run_backtest_subprocess(strategy_path)
        except Exception as e:
            await self.session.emit(
                "step", step="backtesting", status="failed",
                detail=f"Backtest execution error: {e}",
            )
            return

        if error:
            await self.session.emit(
                "step", step="backtesting", status="failed",
                detail=f"Backtest failed: {error}",
                traceback=stdout,
            )
            return

        self.kpis = kpis

        # Format KPIs for display
        kpi_detail = (
            f"Return: {kpis.get('total_return', 0)*100:.1f}% | "
            f"Sharpe: {kpis.get('sharpe_ratio', 0):.2f} | "
            f"Max DD: {kpis.get('max_drawdown', 0)*100:.1f}% | "
            f"Win Rate: {kpis.get('win_rate', 0)*100:.1f}% | "
            f"Trades: {kpis.get('n_trades', 0)}"
        )

        await self.session.emit(
            "backtest_result",
            kpis=kpis,
            detail=kpi_detail,
        )

        await self.session.emit(
            "step", step="backtesting", status="done",
            detail=kpi_detail,
        )

    async def _step_debug(self, attempt: int = 1, initial_error: str = ""):
        """Step 5: Debug failing code. Returns True if fixed code was produced."""
        max_attempts = 3

        await self.session.emit(
            "step", step="debugging", status="running",
            detail=f"Debugging (attempt {attempt}/{max_attempts}): {initial_error[:200]}",
            attempt=attempt,
            max_attempts=max_attempts,
        )

        await self.session.emit(
            "llm_call", phase="debug", attempt=attempt,
            detail="Calling LLM to fix the error...",
        )

        # Call debug LLM (in thread pool to avoid blocking the event loop)
        current_code = self.code or self.template_code
        loop = asyncio.get_running_loop()
        fixed_code, err = await loop.run_in_executor(
            None,
            lambda: debug_code(current_code, initial_error, model=self.model),
        )

        if err or fixed_code is None:
            await self.session.emit(
                "step", step="debugging", status="failed",
                detail=f"Debug LLM call failed: {err}",
                attempt=attempt,
            )
            return

        # Validate syntax
        try:
            ast.parse(fixed_code)
        except SyntaxError as e:
            await self.session.emit(
                "step", step="debugging", status="failed",
                detail=f"Debug produced invalid syntax: {e}",
                attempt=attempt,
            )
            return

        # Check anti-patterns
        warnings = _validate_strategy_code(fixed_code)
        if warnings:
            for w in warnings:
                await self.session.emit("validation_warning", detail=w)

        # Write fixed code
        self.code = fixed_code
        strategy_path = self.session.work_dir / "strategy.py"
        strategy_path.write_text(fixed_code)

        await self.session.emit(
            "code_generated", size=f"{len(fixed_code)/1024:.1f}KB",
            functions=re.findall(r"^def (\w+)", fixed_code, re.MULTILINE),
            path=str(strategy_path),
            detail=f"Debug attempt {attempt} produced fixed code ({len(fixed_code)/1024:.1f}KB)",
        )

        await self.session.emit(
            "step", step="debugging", status="done",
            detail=f"Debug attempt {attempt} succeeded",
            attempt=attempt,
        )

    async def _step_improve(self, iteration: int = 1) -> bool:
        """Step 6: Improve strategy if KPIs are poor. Returns True if improvement was applied."""
        if not self.kpis:
            return False

        max_iterations = 2

        await self.session.emit(
            "step", step="improving", status="running",
            detail=f"Strategy returned {self.kpis.get('total_return', 0)*100:.1f}% "
                    f"(Sharpe: {self.kpis.get('sharpe_ratio', 0):.2f}). Analyzing and improving...",
            iteration=iteration,
            max_iterations=max_iterations,
            before_kpis=self.kpis,
        )

        # Build improvement prompt
        improve_prompt = self._build_improve_prompt()

        await self.session.emit(
            "llm_call", phase="improvement", iteration=iteration,
            detail="Calling LLM to improve strategy...",
        )

        # Call LLM for improvement
        content, finish_reason, err = await self._call_llm(
            [
                {"role": "system", "content": (
                    "You are a quant strategy optimizer. The strategy below produced poor backtest results. "
                    "Output the COMPLETE modified Python file in a ```python block. "
                    "Keep ALL imports, engine wiring, and CONFIG exactly as they are. "
                    "Only change the strategy logic to improve performance.\n\n"
                    "Common improvements:\n"
                    "- Adjust entry thresholds (e.g., RSI oversold from 30 to 25)\n"
                    "- Widen or narrow stop losses\n"
                    "- Change position sizing\n"
                    "- Add filters (volatility, volume, sector)\n"
                    "- Adjust take profit / time stop levels\n"
                    "- Make holding_score more dynamic\n\n"
                    "CRITICAL: holding_score() MUST return a DYNAMIC score. "
                    "TAKE_PROFIT must be enabled. TIME_STOP_DAYS must be reasonable."
                )},
                {"role": "user", "content": improve_prompt},
            ],
            max_tokens=32768,
        )

        if err or not content:
            await self.session.emit(
                "step", step="improving", status="failed",
                detail=f"Improvement LLM call failed: {err}",
            )
            return False

        # Extract code
        improved_code = self._extract_code_block(content)
        if improved_code is None or len(improved_code) < 500:
            await self.session.emit(
                "step", step="improving", status="failed",
                detail="Improvement response contained no valid code block",
            )
            return False

        # Validate syntax
        try:
            ast.parse(improved_code)
        except SyntaxError as e:
            await self.session.emit(
                "step", step="improving", status="failed",
                detail=f"Improvement produced invalid syntax: {e}",
            )
            return False

        # Save old KPIs for comparison
        old_kpis = dict(self.kpis) if self.kpis else {}

        # Update code
        self.code = improved_code
        strategy_path = self.session.work_dir / "strategy.py"
        strategy_path.write_text(improved_code)

        await self.session.emit(
            "code_generated", size=f"{len(improved_code)/1024:.1f}KB",
            functions=re.findall(r"^def (\w+)", improved_code, re.MULTILINE),
            path=str(strategy_path),
            detail=f"Improvement iteration {iteration} produced updated code",
        )

        # Show improvement comparison
        if self.kpis:
            await self.session.emit(
                "improvement",
                iteration=iteration,
                before=old_kpis,
                after=dict(self.kpis),
                detail=(
                    f"Before: Return {old_kpis.get('total_return', 0)*100:.1f}%, "
                    f"Sharpe {old_kpis.get('sharpe_ratio', 0):.2f} → "
                    f"After: Return {self.kpis.get('total_return', 0)*100:.1f}%, "
                    f"Sharpe {self.kpis.get('sharpe_ratio', 0):.2f}"
                ),
            )

        return True

    async def _step_return(self):
        """Step 7: Return final results. Saves code back to Strategy Lab session if applicable."""
        # Save code to the session so the result endpoint can read it
        self.session.code = self.code
        self.session.kpis = self.kpis
        self.session.summary = self._build_summary() if self.code else None

        # Save code back to the Strategy Lab session
        if self.code and self.strategy_session_id:
            try:
                self._save_to_strategy_session()
            except Exception as e:
                logger.warning("Failed to save code to strategy session %s: %s", self.strategy_session_id, e)

        if self.code and self.kpis:
            self.session.status = "done"
            await self.session.emit(
                "result",
                code=self.code,
                kpis=self.kpis,
                summary=self._build_summary(),
                detail="Strategy generated successfully!",
            )
        elif self.code:
            self.session.status = "done"
            await self.session.emit(
                "result",
                code=self.code,
                kpis=None,
                summary="Strategy code generated (backtest did not complete)",
                detail="Code generated but backtest did not complete",
            )
        else:
            self.session.status = "failed"
            await self.session.emit(
                "error_fatal",
                detail="Failed to generate strategy code",
            )

    def _save_to_strategy_session(self):
        """Save the generated code back to the Strategy Lab session."""
        if not self.strategy_session_id or not self.code:
            return
        try:
            from app.db.database import SessionLocal
            from app.services.strategy_lab_session import update_session as svc_update_session
            db = SessionLocal()
            try:
                svc_update_session(db, self.strategy_session_id, code_text=self.code)
                logger.info(
                    "Saved generated code to strategy session %s (%d chars)",
                    self.strategy_session_id, len(self.code),
                )
            finally:
                db.close()
        except Exception as e:
            logger.warning("Could not save code to strategy session: %s", e)

    # ── Helper methods ──────────────────────────────────────────────────

    def _build_generation_prompt(self) -> List[Dict[str, str]]:
        """Build the LLM prompt for code generation."""
        # Extract golden rules and anti-patterns from learnings
        learnings_sections = []
        capture = False
        for line in self.learnings_text.split("\n"):
            if line.startswith("## Golden Rules") or line.startswith("## Known Anti-Patterns"):
                capture = True
            if line.startswith("## Validation Checklist"):
                capture = False
            if capture:
                learnings_sections.append(line)
        learnings_text = "\n".join(learnings_sections)

        system_prompt = (
            "You are a quant strategy coder. You write the 4 strategy-specific "
            "filter functions for TradeCraft's StrategyEngine.\n\n"
            "OUTPUT FORMAT: a single Python file wrapped in a markdown ```python block. "
            "Do NOT include any prose before or after the code block.\n\n"
            "START FROM THE TEMPLATE below. Keep ALL imports, the engine wiring at "
            "the bottom, and the CONFIG instantiation EXACTLY as they are. "
            "Only fill in the bodies of the 4 functions: precompute, entry_score, "
            "holding_score, exit_check.\n\n"
            "REFERENCE TEMPLATE (fill in the TODO sections):\n"
            f"```python\n{self.template_code}\n```\n\n"
            "ACCUMULATED LEARNINGS (follow these rules):\n"
            f"{learnings_text}\n\n"
            "CRITICAL RULES — violations cause backtest failures:\n"
            "1. IMPORT `get_safe_table_name` from `app.utils.security`, NOT `app.db.database`\n"
            "2. IMPORT `engine` from `app.db.database` — do NOT use `create_engine()`\n"
            "3. `market_cap` can be NULL — always check `if market_cap is None: continue`\n"
            "4. Use single-line f-strings for SQL, NOT triple-quoted f-strings\n"
            "5. Use `np.searchsorted(dates, np.datetime64(date_str))` for date lookups\n"
            "6. Use `pd.Timestamp(x).strftime(\"%Y-%m-%d\")` to convert numpy datetime64 to strings\n"
            "7. Use `float()`, `int()`, or `round()` to convert numpy types before storing in dicts\n"
            "8. Never compare `None` with `>` or `<` — guard all nullable values\n"
            "9. All KPI values must be JSON-safe — no Infinity or NaN\n"
            "10. Wrap `get_safe_table_name(ticker)` in try/except ValueError and `continue`\n"
            "11. Always call `.mean()` on `.ewm()` before accessing `.values`\n"
            "12. ⚠️  holding_score() MUST return a DYNAMIC score based on current indicator values\n"
            "13. ⚠️  TAKE_PROFIT must be enabled at a reasonable level (e.g. 0.20-0.30)\n"
            "14. ⚠️  TIME_STOP_DAYS must be set to a reasonable value (e.g. 60-120)\n"
            "15. ⚠️  MIN_HOLD_DAYS should be >= 7 to prevent excessive churn\n"
        )

        # Load the gold-standard reference strategy
        _gold_path = _BASE_DIR / "strategies" / "golden_cross_rotation.py"
        try:
            gold_code = _gold_path.read_text()
            gold_lines = gold_code.split("\n")
            gold_core = []
            in_main = False
            for line in gold_lines:
                if line.strip().startswith("def main():"):
                    in_main = True
                if not in_main:
                    gold_core.append(line)
            gold_text = "\n".join(gold_core)
            system_prompt += (
                "\nGOLD STANDARD REFERENCE (study these patterns — "
                "your code should follow the same style):\n"
                f"```python\n{gold_text}\n```\n"
            )
        except Exception:
            pass

        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Here is the strategy idea to implement:\n\n{self.session.prompt}\n\n"
                    "Now write the Python code. Fill in the 4 functions in the template. "
                    "Keep all imports and engine wiring unchanged."
                ),
            },
        ]

    def _build_improve_prompt(self) -> str:
        """Build the prompt for strategy improvement."""
        kpis = self.kpis or {}
        return (
            f"The current strategy produced these backtest results:\n\n"
            f"Total Return: {kpis.get('total_return', 0)*100:.2f}%\n"
            f"Sharpe Ratio: {kpis.get('sharpe_ratio', 0):.4f}\n"
            f"Max Drawdown: {kpis.get('max_drawdown', 0)*100:.2f}%\n"
            f"Win Rate: {kpis.get('win_rate', 0)*100:.1f}%\n"
            f"Number of Trades: {kpis.get('n_trades', 0)}\n"
            f"Profit Factor: {kpis.get('profit_factor', 0):.2f}\n\n"
            f"Current code:\n\n```python\n{self.code}\n```\n\n"
            f"Please improve the strategy to get better performance. "
            f"Output the COMPLETE modified Python file in a ```python block."
        )

    async def _call_llm(
        self, messages: List[Dict[str, str]], max_tokens: int = 16384
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Call the LLM and return (content, finish_reason, error).

        Runs the synchronous _chat in a thread pool to avoid blocking
        the asyncio event loop (which would prevent the FastAPI server
        from responding to SSE streams and other requests).
        """
        from app.services.strategy_lab_llm import _chat

        # Run the synchronous _chat in a thread pool so the event loop
        # stays free to serve SSE streams and other concurrent requests.
        loop = asyncio.get_running_loop()
        content, finish_reason, err = await loop.run_in_executor(
            None,
            lambda: _chat(
                messages, model=self.model, max_tokens=max_tokens,
                temperature=0.0, timeout=300,
            ),
        )
        return content, finish_reason, err

    def _extract_code_block(self, text: str) -> Optional[str]:
        """Extract the first ```python ... ``` block from text."""
        m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
        if m:
            return textwrap.dedent(m.group(1).rstrip()) + "\n"
        m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
        if m:
            return textwrap.dedent(m.group(1).rstrip()) + "\n"
        return None

    async def _run_backtest_subprocess(self, strategy_path: Path) -> Tuple[Optional[dict], Optional[str], str]:
        """Run a backtest in a subprocess and return (kpis, error, stdout)."""
        import subprocess

        # Find the Python interpreter
        venv_python = _BASE_DIR / "backend" / "venv" / "bin" / "python"
        python_cmd = str(venv_python) if venv_python.exists() else "python"

        # Build a runner script that imports the strategy and runs the engine
        runner_code = f"""
import sys
import json
import os
sys.path.insert(0, '{_BASE_DIR / "backend"}')
sys.path.insert(0, '{_BASE_DIR}')

try:
    # Import the strategy module
    import importlib.util
    spec = importlib.util.spec_from_file_location("_agent_strategy", "{strategy_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_agent_strategy"] = mod
    spec.loader.exec_module(mod)

    # Load the engine via importlib (strategies/ dir has no __init__.py)
    _engine_path = os.path.join("{_BASE_DIR}", "strategies", "engine.py")
    _engine_spec = importlib.util.spec_from_file_location("strategies_engine", _engine_path)
    _engine_mod = importlib.util.module_from_spec(_engine_spec)
    sys.modules["strategies_engine"] = _engine_mod
    _engine_spec.loader.exec_module(_engine_mod)
    StrategyEngine = _engine_mod.StrategyEngine

    # Set dynamic dates on CONFIG (template has hardcoded defaults)
    from datetime import datetime as _dt
    _now = _dt.now()
    _end = _now.strftime("%Y-%m-%d")
    _start = _dt(_now.year - 3, _now.month, _now.day).strftime("%Y-%m-%d")
    mod.CONFIG.as_of = _start
    mod.CONFIG.end = _end

    # Run the engine
    engine = mod.CONFIG
    eng = StrategyEngine(engine)
    result = eng.run()

    # Extract KPIs
    # NOTE: engine returns total_return_pct (e.g. 47.3 for 47.3%), win_rate as
    #       percentage (e.g. 47.3 for 47.3%), and total_trades (not n_trades).
    #       We normalize to decimal fractions for the agent's internal use.
    summary = result.get("summary", {{}})
    kpis = {{
        "total_return": float(summary.get("total_return_pct", 0)) / 100.0,
        "total_return_pct": float(summary.get("total_return_pct", 0)),
        "sharpe_ratio": float(summary.get("sharpe_ratio", 0)),
        "max_drawdown": float(summary.get("max_drawdown_pct", 0)) / 100.0,
        "win_rate": float(summary.get("win_rate", 0)) / 100.0,
        "n_trades": int(summary.get("total_trades", 0)),
        "profit_factor": float(summary.get("profit_factor", 0)),
    }}
    print("__KPIS__" + json.dumps(kpis))
except Exception as e:
    import traceback
    print("__ERROR__" + str(e))
    print("__TRACEBACK__" + traceback.format_exc())
"""

        try:
            proc = await asyncio.create_subprocess_exec(
                python_cmd, "-c", runner_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_BASE_DIR / "backend"),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""

            # Check for KPIS marker
            kpis_match = re.search(r"__KPIS__(\{.*\})", stdout_str, re.DOTALL)
            if kpis_match:
                kpis = json.loads(kpis_match.group(1))
                return kpis, None, stdout_str

            # Check for error marker
            error_match = re.search(r"__ERROR__(.*)", stdout_str, re.DOTALL)
            if error_match:
                return None, error_match.group(1).strip(), stdout_str

            # Check stderr
            if stderr_str:
                return None, stderr_str[:500], stdout_str + "\n" + stderr_str

            return None, "No KPIs found in output", stdout_str

        except asyncio.TimeoutError:
            return None, "Backtest timed out after 120s", ""
        except Exception as e:
            return None, f"Subprocess error: {e}", ""

    def _build_summary(self) -> str:
        """Build a human-readable summary of the results."""
        if not self.kpis:
            return "Strategy code generated (backtest results not available)"

        k = self.kpis
        return (
            f"Total Return: {k.get('total_return', 0)*100:.1f}%\n"
            f"Sharpe Ratio: {k.get('sharpe_ratio', 0):.2f}\n"
            f"Max Drawdown: {k.get('max_drawdown', 0)*100:.1f}%\n"
            f"Win Rate: {k.get('win_rate', 0)*100:.1f}%\n"
            f"Number of Trades: {k.get('n_trades', 0)}\n"
            f"Profit Factor: {k.get('profit_factor', 0):.2f}"
        )


# ── Public API ──────────────────────────────────────────────────────────────

async def start_agent(prompt: str, model: Optional[str] = None) -> str:
    """Start a new agent session. Returns the session_id."""
    import uuid
    session_id = uuid.uuid4().hex[:12]
    session = AgentSession(session_id, prompt)
    _sessions[session_id] = session

    agent = StrategyAgent(session, model=model)

    # Run the agent loop in a background task
    asyncio.create_task(agent.run())

    logger.info("Started agent session %s: prompt=%s...", session_id, prompt[:80])
    return session_id


async def start_agent_with_plan(
    plan_text: str,
    strategy_session_id: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Start an agent session using a pre-generated plan (from Strategy Lab Step 2).

    The agent uses the plan to generate code, validates it, backtests it,
    and saves the result back to the Strategy Lab session.

    Args:
        plan_text: The structured plan from Step 2.
        strategy_session_id: The Strategy Lab session ID to save code back to.
        model: Optional model override.

    Returns:
        The agent session ID for SSE streaming.
    """
    import uuid
    session_id = uuid.uuid4().hex[:12]
    session = AgentSession(session_id, plan_text)
    _sessions[session_id] = session

    agent = StrategyAgent(
        session,
        model=model,
        strategy_session_id=strategy_session_id,
    )

    # Run the agent loop in a background task
    asyncio.create_task(agent.run())

    logger.info(
        "Started agent with plan for strategy session %s: agent_session=%s",
        strategy_session_id, session_id,
    )
    return session_id


def cleanup_old_sessions(max_age_minutes: int = 30):
    """Remove sessions older than max_age_minutes."""
    now = datetime.utcnow()
    stale = [
        sid for sid, s in _sessions.items()
        if (now - s.created_at).total_seconds() > max_age_minutes * 60
    ]
    for sid in stale:
        del _sessions[sid]
    if stale:
        logger.info("Cleaned up %d stale agent sessions", len(stale))
