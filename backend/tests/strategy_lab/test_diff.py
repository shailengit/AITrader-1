"""Tests for the diff parser/apply helper."""
import pytest

from app.services.strategy_lab_diff import apply_diff, parse_unified_diff, fallback_diff, diff_summary


def test_apply_simple_modification():
    src = "line 1\nline 2\nline 3\n"
    diff = "@@ -1,3 +1,3 @@\n line 1\n-line 2\n+LINE 2 MODIFIED\n line 3\n"
    result = apply_diff(src, diff)
    assert result == "line 1\nLINE 2 MODIFIED\nline 3\n"


def test_apply_addition():
    src = "line 1\nline 3\n"
    diff = "@@ -1,2 +1,3 @@\n line 1\n+line 2 inserted\n line 3\n"
    result = apply_diff(src, diff)
    assert "line 2 inserted" in result


def test_apply_deletion():
    src = "line 1\nline 2 TO REMOVE\nline 3\n"
    diff = "@@ -1,3 +1,2 @@\n line 1\n-line 2 TO REMOVE\n line 3\n"
    result = apply_diff(src, diff)
    assert "TO REMOVE" not in result


def test_apply_multiple_hunks():
    src = "a\nb\nc\nd\ne\nf\n"
    # Two separate changes: b -> B, and e -> E
    diff = (
        "@@ -1,2 +1,2 @@\n a\n-b\n+B\n"
        "@@ -5,2 +5,2 @@\n e\n-f\n+F\n"
    )
    result = apply_diff(src, diff)
    # After both changes, the file has: a, B, c, d, e, F
    assert result == "a\nB\nc\nd\ne\nF\n"


def test_apply_fails_on_mismatch():
    src = "actual line 1\nactual line 2\n"
    diff = "@@ -1,2 +1,2 @@\n wrong line 1\n-wrong line 2\n+NEW\n"
    with pytest.raises(ValueError):
        apply_diff(src, diff)


def test_parse_returns_hunks():
    diff = "@@ -1,2 +1,2 @@\n a\n-b\n+B\n@@ -5,2 +5,2 @@\n e\n-f\n+F\n"
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 2
    assert hunks[0].old_start == 1
    assert hunks[1].old_start == 5


def test_fallback_diff_round_trip():
    src = "a\nb\nc\n"
    target = "a\nB modified\nc\n"
    diff = fallback_diff(src, target)
    # Strip --- and +++ headers before applying
    cleaned = "\n".join(
        line for line in diff.splitlines()
        if not line.startswith("---") and not line.startswith("+++")
    )
    result = apply_diff(src, cleaned)
    assert result == target


def test_diff_summary():
    diff = "@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n@@ -5,2 +5,2 @@\n e\n-f\n+F\n"
    summary = diff_summary(diff)
    assert "+2" in summary
    assert "-2" in summary
    assert "2 hunk" in summary
