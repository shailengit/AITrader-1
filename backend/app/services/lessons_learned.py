"""
LessonsLearnedStore - Persistent JSON-based store of past errors and their fixes.

Provides error classification, fuzzy matching, and formatted lesson injection
for LLM system prompts to prevent recurring mistakes in generated strategy code.
"""

import json
import os
import re
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from difflib import SequenceMatcher

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DEFAULT_PATH = os.path.join(DATA_DIR, "lessons_learned.json")

# Error signature categories with matching patterns
ERROR_SIGNATURES: Dict[str, List[str]] = {
    "VBT_COMPARISON_OPERATOR": [
        "cannot join with no overlapping index names",
        "comparison operator",
        "ma_above",
        "ma_below",
        "rsi_above",
        "rsi_below",
        "vbt.and",
        "vbt.or",
    ],
    "MISSING_PF_OBJECT": [
        "must create a 'pf'",
        "must define a 'pf'",
        "portfolio object missing",
        "strategy code must create a 'pf'",
    ],
    "SYNTAX_ERROR": [
        "invalid syntax",
        "unexpected indent",
        "expected an indented block",
        "unexpected eof",
        "eol while scanning string literal",
    ],
    "DATA_LOADING": [
        "yfdata",
        "data download",
        "no data",
        "empty data",
        "failed to download",
    ],
    "PORTFOLIO_EMPTY": [
        "portfolio is empty",
        "no trades",
        "empty portfolio",
        "wrapper.shape[0] == 0",
    ],
    "MISSING_PARAMETERS": [
        "missing required patterns",
        "parameters section",
        "# parameters",
    ],
    "IMPORT_ERROR": [
        "forbidden import",
        "dangerous pattern",
        "no module named",
        "import error",
    ],
    "CONTINUOUS_SIGNALS": [
        "continuous signals",
        "event-driven",
        "crossed_above",
        "crossed_below",
        "true wfo",
    ],
    "TYPE_ERROR": [
        "typeerror",
        "unsupported operand type",
        "cannot concatenate",
    ],
    "ATTRIBUTE_ERROR": [
        "attributeerror",
        "has no attribute",
        "object has no attribute",
    ],
}


class LessonsLearnedStore:
    """Persistent JSON-based store of error -> fix mappings."""

    def __init__(self, filepath: str = DEFAULT_PATH):
        self.filepath = filepath
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self.lessons: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.filepath):
            return []
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self) -> None:
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.lessons, f, indent=2)
        except IOError as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save lessons: {e}")

    def classify_error(self, error_message: str) -> Optional[str]:
        """Classify an error message into a known signature."""
        if not error_message:
            return None
        error_lower = error_message.lower()
        for signature, patterns in ERROR_SIGNATURES.items():
            for pattern in patterns:
                if pattern.lower() in error_lower:
                    return signature
        return None

    def add(
        self,
        error_signature: str,
        error_message: str,
        fix_description: str,
        example_before: str = "",
        example_after: str = "",
    ) -> None:
        """Add or update a lesson."""
        existing = next(
            (l for l in self.lessons if l["error_signature"] == error_signature),
            None,
        )
        if existing:
            existing["frequency"] = existing.get("frequency", 1) + 1
            existing["last_seen"] = datetime.utcnow().isoformat() + "Z"
            if error_message not in existing.get("variations", []):
                existing.setdefault("variations", []).append(error_message)
            # Update the fix if it's more detailed
            if len(fix_description) > len(existing.get("fix_description", "")):
                existing["fix_description"] = fix_description
            if example_before and not existing.get("example_before"):
                existing["example_before"] = example_before
            if example_after and not existing.get("example_after"):
                existing["example_after"] = example_after
        else:
            self.lessons.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "error_signature": error_signature,
                    "error_pattern": error_message[:200],
                    "error_message": error_message[:500],
                    "fix_description": fix_description,
                    "example_before": example_before,
                    "example_after": example_after,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "frequency": 1,
                    "variations": [error_message],
                }
            )
        self._save()

    def get_formatted(self, n_recent: int = 20) -> str:
        """Return markdown-formatted lessons for system prompt injection."""
        if not self.lessons:
            return ""
        lessons = sorted(
            self.lessons, key=lambda x: x.get("frequency", 1), reverse=True
        )[:n_recent]
        lines = ["## Lessons Learned from Previous Mistakes\n"]
        lines.append(
            "The following errors have occurred before. Do NOT repeat them:\n"
        )
        for i, l in enumerate(lessons, 1):
            lines.append(
                f"{i}. **{l['error_signature']}** (seen {l.get('frequency', 1)}x)"
            )
            lines.append(f"   - Symptom: {l['error_pattern'][:120]}")
            lines.append(f"   - Fix: {l['fix_description'][:200]}")
            if l.get("example_before") and l.get("example_after"):
                lines.append(
                    f"   - Example: `{l['example_before']}` -> `{l['example_after']}`"
                )
            lines.append("")
        return "\n".join(lines)

    def find_match(self, error_message: str) -> Optional[Dict[str, Any]]:
        """Find the best matching lesson for an error message."""
        if not error_message:
            return None

        # First try signature classification
        signature = self.classify_error(error_message)
        if signature:
            match = next(
                (l for l in self.lessons if l["error_signature"] == signature), None
            )
            if match:
                return match

        # Fuzzy match against stored patterns
        best_score = 0.55
        best_match = None
        error_lower = error_message.lower()
        for l in self.lessons:
            score = SequenceMatcher(
                None, error_lower, l["error_message"].lower()
            ).ratio()
            if score > best_score:
                best_score = score
                best_match = l

        return best_match

    def get_lesson_by_id(self, lesson_id: str) -> Optional[Dict[str, Any]]:
        """Get a lesson by its ID."""
        return next((l for l in self.lessons if l["id"] == lesson_id), None)

    def prune(self, max_lessons: int = 100, keep_top: int = 30) -> int:
        """Prune old lessons, keeping the most frequent ones."""
        if len(self.lessons) <= max_lessons:
            return 0
        sorted_lessons = sorted(
            self.lessons, key=lambda x: x.get("frequency", 1), reverse=True
        )
        self.lessons = sorted_lessons[:keep_top]
        self._save()
        return len(sorted_lessons) - keep_top
