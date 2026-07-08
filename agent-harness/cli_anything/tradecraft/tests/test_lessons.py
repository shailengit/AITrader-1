"""Tests for lessons learned store."""
import json
import tempfile
from pathlib import Path

import pytest

from cli_anything.tradecraft.core.lessons import LessonsStore


@pytest.fixture
def store(tmp_path: Path) -> LessonsStore:
    """Create a LessonsStore with a temp config dir."""
    import cli_anything.tradecraft.core.config as cfg
    original = cfg.CONFIG_DIR
    cfg.CONFIG_DIR = tmp_path / ".config" / "tradecraft"
    s = LessonsStore()
    yield s
    cfg.CONFIG_DIR = original


def test_default_lessons_exist(store: LessonsStore):
    """Store should have default lessons loaded."""
    all_lessons = store.all()
    assert len(all_lessons) >= 2
    patterns = [l["pattern"] for l in all_lessons]
    assert "vbt_comparison_operators" in patterns
    assert "missing_broadcast_kwargs" in patterns


def test_add_new_lesson(store: LessonsStore):
    """Adding a new lesson should append it."""
    store.add("some new error", "use X instead of Y", "new_pattern", "backtest")
    all_lessons = store.all()
    assert any(l["pattern"] == "new_pattern" for l in all_lessons)
    new = [l for l in all_lessons if l["pattern"] == "new_pattern"][0]
    assert new["count"] == 1
    assert new["first_seen"] == new["last_seen"]


def test_add_existing_lesson_increments_count(store: LessonsStore):
    """Adding a lesson with an existing error_sig should increment count."""
    store.add("cannot join with no overlapping index names", "", "vbt_comparison_operators")
    lesson = store.match("cannot join with no overlapping index names")
    assert lesson is not None
    assert lesson["count"] >= 1


def test_match_finds_lesson(store: LessonsStore):
    """Match should find a lesson by error signature substring."""
    lesson = store.match("cannot join with no overlapping index names")
    assert lesson is not None
    assert lesson["pattern"] == "vbt_comparison_operators"


def test_match_returns_none_for_unknown(store: LessonsStore):
    """Match should return None for unknown errors."""
    lesson = store.match("completely unknown error XYZ123")
    assert lesson is None


def test_to_prompt_empty_when_no_errors(store: LessonsStore):
    """to_prompt should return empty string when no lessons have been seen."""
    # Reset counts to 0
    for l in store.all():
        l["count"] = 0
    prompt = store.to_prompt()
    assert prompt == ""


def test_to_prompt_includes_relevant_lessons(store: LessonsStore):
    """to_prompt should include lessons matching context hint."""
    store.add("cannot join with no overlapping index names", "", "vbt_comparison_operators", "VBT optimization")
    prompt = store.to_prompt("VBT optimization")
    assert "vbt.combine_logic" in prompt
    assert "vbt_comparison_operators" not in prompt  # pattern name not in output


def test_to_prompt_filters_by_context(store: LessonsStore):
    """to_prompt should only include lessons matching context hint."""
    store.add("cannot join with no overlapping index names", "", "vbt_comparison_operators", "VBT optimization")
    prompt = store.to_prompt("screener scan")
    assert prompt == ""  # no match
