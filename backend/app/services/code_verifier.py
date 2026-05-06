"""
CodeVerifier - Encapsulate the verify -> fix -> retry loop in a reusable module.

Provides structured error extraction, enhanced fix prompts with lesson context,
and automatic lesson recording after successful fixes.
"""

import re
import traceback as tb_module
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from app.services.executor import execute_strategy
from app.services.llm_engine import fix_strategy_code
from app.services.lessons_learned import LessonsLearnedStore

import logging

logger = logging.getLogger(__name__)


@dataclass
class ErrorDetails:
    """Structured error information from a failed code execution."""

    type: str
    category: str  # syntax | validation | execution | security
    message: str
    line: Optional[int] = None
    line_content: Optional[str] = None
    traceback: str = ""
    stdout: str = ""
    suggestion: str = ""
    related_lesson: Optional[str] = None


@dataclass
class VerificationResult:
    """Result of a verification attempt, possibly including auto-fixes."""

    success: bool
    code: str
    output: str
    error_details: Optional[ErrorDetails] = None
    fix_attempts: int = 0
    lessons_applied: List[str] = field(default_factory=list)
    execution_time: Optional[float] = None


class CodeVerifier:
    """Reusable verify -> fix -> retry runner with lesson memory."""

    def __init__(self, lessons_store: Optional[LessonsLearnedStore] = None):
        self.lessons = lessons_store or LessonsLearnedStore()

    def verify_and_fix(
        self,
        code: str,
        tickers: Optional[List[str]] = None,
        max_attempts: int = 3,
        record_lessons: bool = True,
    ) -> VerificationResult:
        """
        Run code, auto-fix if failing, record lessons.

        Args:
            code: Python code to verify
            tickers: Optional ticker override
            max_attempts: Maximum verification/fix attempts
            record_lessons: Whether to record lessons after successful fixes

        Returns:
            VerificationResult with success status and error details if failed
        """
        import time

        last_error_details: Optional[ErrorDetails] = None
        lessons_applied: List[str] = []
        original_code = code
        total_start = time.time()

        for attempt in range(max_attempts):
            logger.info(f"Verification attempt {attempt + 1}/{max_attempts}")
            result = execute_strategy(code, tickers=tickers)

            if result.get("success"):
                elapsed = time.time() - total_start
                # Record lesson if we had to fix
                if attempt > 0 and last_error_details and record_lessons:
                    self._record_lesson(last_error_details, code, original_code)
                return VerificationResult(
                    success=True,
                    code=code,
                    output=result.get("output", ""),
                    fix_attempts=attempt,
                    lessons_applied=lessons_applied,
                    execution_time=elapsed,
                )

            # Capture detailed error information
            error_str = result.get("error", "Unknown error")
            stdout = result.get("output", "")
            traceback_str = result.get("traceback", "")

            last_error_details = self._extract_error_details(
                error_str, stdout, traceback_str, code
            )

            # Check for past fix
            lesson = self.lessons.find_match(error_str)
            if lesson:
                lessons_applied.append(lesson["error_signature"])
                last_error_details.suggestion = lesson["fix_description"]
                last_error_details.related_lesson = lesson["id"]
                logger.info(
                    f"Found lesson {lesson['error_signature']} for error"
                )

            # If last attempt, don't try to fix
            if attempt == max_attempts - 1:
                break

            # Build enhanced fix prompt
            fix_context = self._build_fix_context(
                code, last_error_details, lesson
            )
            logger.info(
                f"Attempting fix for {last_error_details.type} "
                f"(line {last_error_details.line})"
            )

            fix_start = time.time()
            fixed_code = fix_strategy_code(code, fix_context)
            fix_elapsed = time.time() - fix_start
            logger.info(f"Fix request took {fix_elapsed:.2f}s")

            if fixed_code and fixed_code != code:
                code = fixed_code
            else:
                logger.warning("Fix returned same code, stopping retries")
                break

        elapsed = time.time() - total_start
        return VerificationResult(
            success=False,
            code=code,
            output=result.get("output", ""),
            error_details=last_error_details,
            fix_attempts=attempt + 1,
            lessons_applied=lessons_applied,
            execution_time=elapsed,
        )

    def _extract_error_details(
        self, error: str, stdout: str, traceback: str, code: str
    ) -> ErrorDetails:
        """Extract structured error details from raw error output."""
        # Extract line number from traceback
        line_match = re.search(r'File "<string>".*line (\d+)', traceback)
        if not line_match:
            line_match = re.search(r"line (\d+)", traceback)
        line_num = int(line_match.group(1)) if line_match else None
        line_content = None
        if line_num:
            lines = code.split("\n")
            if 0 <= line_num - 1 < len(lines):
                line_content = lines[line_num - 1]

        # Classify error category
        category = "execution"
        error_lower = error.lower()
        if "syntax" in error_lower or "invalid syntax" in error_lower:
            category = "syntax"
        elif "validation" in error_lower:
            category = "validation"
        elif "security" in error_lower or "forbidden" in error_lower:
            category = "security"
        elif "timeout" in error_lower:
            category = "timeout"
        elif "import" in error_lower and "no module" in error_lower:
            category = "execution"

        # Get error type from classification
        error_type = self.lessons.classify_error(error) or "UNKNOWN"

        # Build suggestion based on error type
        suggestion = self._get_default_suggestion(error_type, error, line_content)

        return ErrorDetails(
            type=error_type,
            category=category,
            message=error,
            line=line_num,
            line_content=line_content,
            traceback=traceback,
            stdout=stdout,
            suggestion=suggestion,
        )

    def _get_default_suggestion(
        self, error_type: str, error_message: str, line_content: Optional[str]
    ) -> str:
        """Generate a default suggestion based on error type."""
        suggestions = {
            "VBT_COMPARISON_OPERATOR": (
                "Replace comparison operators (>, <, &, |) with VBT methods: "
                "ma_above(), ma_below(), rsi_below(), vbt.And(), vbt.Or()"
            ),
            "MISSING_PF_OBJECT": (
                "Ensure code ends with: pf = vbt.Portfolio.from_signals(...)"
            ),
            "SYNTAX_ERROR": (
                "Check for missing parentheses, quotes, or indentation issues. "
                f"Problematic line: {line_content[:80] if line_content else 'N/A'}"
            ),
            "DATA_LOADING": (
                "Use DataService.get_ohlcv_data(ticker, start, end) to load data. "
                "Ensure ticker exists in database."
            ),
            "PORTFOLIO_EMPTY": (
                "Portfolio has no trades. Check signal generation: "
                "entries/exits must have some True values."
            ),
            "MISSING_PARAMETERS": (
                "Add a '# Parameters' section at the top with tunable numeric variables."
            ),
            "IMPORT_ERROR": (
                "Only standard libraries + pandas/numpy/vectorbt are allowed. "
                "Remove any forbidden imports."
            ),
            "CONTINUOUS_SIGNALS": (
                "For True WFO, use continuous signals (ma_above, ma_below, rsi_below) "
                "instead of event-driven signals (ma_crossed_above, ma_crossed_below)."
            ),
        }
        return suggestions.get(
            error_type,
            f"Review the error message and fix the code. Error: {error_message[:100]}",
        )

    def _build_fix_context(
        self, code: str, error: ErrorDetails, lesson: Optional[Dict[str, Any]]
    ) -> str:
        """Build an enhanced fix prompt with full error context."""
        parts = [
            f"Error: {error.message}",
            f"Category: {error.category}",
            f"Error Type: {error.type}",
        ]
        if error.line:
            parts.append(f"Line {error.line}: {error.line_content}")
        if error.stdout:
            parts.append(f"Stdout before failure:\n{error.stdout[-800:]}")
        if error.traceback:
            parts.append(f"Traceback:\n{error.traceback}")
        if lesson:
            parts.append(
                f"\nPrevious fix for similar error ({lesson['error_signature']}):"
            )
            parts.append(lesson["fix_description"])
            if lesson.get("example_after"):
                parts.append(f"Example fix:\n{lesson['example_after']}")
        return "\n".join(parts)

    def _record_lesson(
        self,
        error_details: ErrorDetails,
        fixed_code: str,
        original_code: str,
    ) -> None:
        """Record a lesson after a successful fix."""
        if error_details.type == "UNKNOWN":
            return

        example_before = error_details.line_content or original_code[:200]
        example_after = fixed_code[:200]

        self.lessons.add(
            error_signature=error_details.type,
            error_message=error_details.message,
            fix_description=error_details.suggestion
            or f"Fixed {error_details.type}",
            example_before=example_before,
            example_after=example_after,
        )
        logger.info(f"Recorded lesson: {error_details.type}")
