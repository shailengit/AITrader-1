"""Lessons learned store for code generation quality.

Captures strategy code generation errors and prevents repeats by
injecting relevant lessons into future LLM prompts.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from cli_anything.tradecraft.core.config import CONFIG_DIR

LESSONS_FILE = CONFIG_DIR / "lessons.json"

DEFAULT_LESSONS = [
    {
        "pattern": "vbt_comparison_operators",
        "error_sig": "cannot join with no overlapping index names",
        "fix": "Use .vbt.gt() / .vbt.lt() instead of > / <, and vbt.combine_logic instead of &",
        "trigger_hint": "VBT optimization",
        "count": 0,
        "first_seen": "",
        "last_seen": "",
    },
    {
        "pattern": "missing_broadcast_kwargs",
        "error_sig": "Portfolio.from_signals shape mismatch",
        "fix": "Add broadcast_kwargs={'keep_pd': True} to Portfolio.from_signals",
        "trigger_hint": "multi-ticker backtest",
        "count": 0,
        "first_seen": "",
        "last_seen": "",
    },
]


class LessonsStore:
    """Persistent store for code generation lessons learned."""

    def __init__(self):
        self._lessons: List[Dict[str, Any]] = []
        self._load()

    def _path(self) -> Path:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return LESSONS_FILE

    def _load(self) -> None:
        path = self._path()
        if path.exists():
            try:
                self._lessons = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._lessons = list(DEFAULT_LESSONS)
        else:
            self._lessons = list(DEFAULT_LESSONS)
            self._save()

    def _save(self) -> None:
        self._path().write_text(
            json.dumps(self._lessons, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add(self, error_sig: str, fix: str, pattern: str, trigger_hint: str = "") -> None:
        """Add or update a lesson. If error_sig matches an existing lesson, increment count."""
        now = datetime.now().isoformat()
        for lesson in self._lessons:
            if lesson["error_sig"] == error_sig or lesson["pattern"] == pattern:
                lesson["count"] += 1
                lesson["last_seen"] = now
                if fix:
                    lesson["fix"] = fix
                if trigger_hint:
                    lesson["trigger_hint"] = trigger_hint
                self._save()
                return
        self._lessons.append({
            "pattern": pattern,
            "error_sig": error_sig,
            "fix": fix,
            "trigger_hint": trigger_hint,
            "count": 1,
            "first_seen": now,
            "last_seen": now,
        })
        self._save()

    def match(self, error_text: str) -> Optional[Dict[str, Any]]:
        """Find a lesson whose error_sig appears in the error text."""
        error_lower = error_text.lower()
        for lesson in self._lessons:
            if lesson["error_sig"].lower() in error_lower:
                return lesson
        return None

    def all(self) -> List[Dict[str, Any]]:
        return list(self._lessons)

    def to_prompt(self, context_hint: str = "") -> str:
        """Generate a prompt suffix with relevant lessons.

        If context_hint is provided, only include lessons whose trigger_hint
        matches. Otherwise include all lessons with count > 0.
        """
        context_lower = context_hint.lower()
        relevant = []
        for lesson in self._lessons:
            if lesson["count"] == 0:
                continue
            if context_hint and lesson["trigger_hint"].lower() not in context_lower:
                continue
            relevant.append(lesson)

        if not relevant:
            return ""

        lines = ["\n## Known Pitfalls (from lessons learned)"]
        for lesson in relevant:
            lines.append(f"- {lesson['fix']}  (seen {lesson['count']}x)")
        return "\n".join(lines)
