"""
DEPRECATED: This module is no longer used by the refine flow.
The refine flow now uses complete-file replacement (refine_code_direct)
instead of unified diffs. Kept for reference only.
"""

"""Parse and apply unified diffs.

Used to apply LLM-generated diffs to user-edited strategy code. Falls back
to a simple line-by-line replacement if the unified diff doesn't apply
cleanly (which can happen if the user's edits drift from what the LLM
expected).
"""
import difflib
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class DiffHunk:
    """A single hunk from a unified diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    old_lines: List[str]      # context (starting with ' ') + removed (starting with '-')
    new_lines: List[str]      # context (starting with ' ') + added (starting with '+')
    raw_old: List[str]        # the raw '-' + ' ' lines
    raw_new: List[str]        # the raw '+' + ' ' lines


def parse_unified_diff(diff_text: str) -> List[DiffHunk]:
    """Parse a unified diff (text without the ```diff fences) into a list of hunks.

    Raises ValueError on malformed input.
    """
    hunks: List[DiffHunk] = []
    lines = diff_text.splitlines()
    i = 0
    # Skip --- and +++ header lines
    while i < len(lines) and (lines[i].startswith("---") or lines[i].startswith("+++")):
        i += 1
    while i < len(lines):
        line = lines[i]
        if not line.startswith("@@"):
            i += 1
            continue
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if not m:
            raise ValueError(f"Malformed hunk header: {line!r}")
        old_start = int(m.group(1))
        old_count = int(m.group(2) or "1")
        new_start = int(m.group(3))
        new_count = int(m.group(4) or "1")
        i += 1
        raw_old: List[str] = []
        raw_new: List[str] = []
        old_lines: List[str] = []
        new_lines: List[str] = []
        # Hunk body: ' context', '- removed', '+ added'
        for _ in range(old_count + new_count + 100):  # generous bound
            if i >= len(lines):
                break
            l = lines[i]
            if l.startswith("@@"):
                break
            if l.startswith(" "):
                content = l[1:]
                old_lines.append(content)
                new_lines.append(content)
                raw_old.append(l)
                raw_new.append(l)
            elif l.startswith("-"):
                content = l[1:]
                old_lines.append(content)
                raw_old.append(l)
            elif l.startswith("+"):
                content = l[1:]
                new_lines.append(content)
                raw_new.append(l)
            else:
                # Unrecognized line ends this hunk
                break
            i += 1
        hunks.append(DiffHunk(
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
            old_lines=old_lines,
            new_lines=new_lines,
            raw_old=raw_old,
            raw_new=raw_new,
        ))
    return hunks


def apply_diff(source: str, diff_text: str) -> str:
    """Apply a unified diff to source. Returns the new code.

    Raises ValueError if the diff doesn't apply cleanly.
    """
    hunks = parse_unified_diff(diff_text)
    source_lines = source.splitlines(keepends=False)
    # Apply hunks in reverse order so line offsets don't shift
    new_lines = list(source_lines)
    for hunk in reversed(hunks):
        # hunk.old_start is 1-indexed
        start_idx = hunk.old_start - 1
        end_idx = start_idx + hunk.old_count
        # The diff's old section should match what we have at that position
        actual_old = new_lines[start_idx:end_idx]
        if actual_old != hunk.old_lines:
            # Try fuzzy match: if 80% of lines match, attempt the replacement
            matches = sum(1 for a, b in zip(actual_old, hunk.old_lines) if a == b)
            if matches < 0.8 * len(hunk.old_lines):
                raise ValueError(
                    f"Hunk at line {hunk.old_start} doesn't match source "
                    f"(only {matches}/{len(hunk.old_lines)} lines match)"
                )
        new_lines[start_idx:end_idx] = hunk.new_lines
    return "\n".join(new_lines) + ("\n" if source.endswith("\n") else "")


def fallback_diff(source: str, target: str) -> str:
    """Generate a unified diff between source and target. Used when the LLM
    fails to produce a parseable diff — we just compute it ourselves."""
    diff = difflib.unified_diff(
        source.splitlines(keepends=False),
        target.splitlines(keepends=False),
        fromfile="strategy.py",
        tofile="strategy.py",
        lineterm="",
    )
    return "\n".join(diff)


def diff_summary(diff_text: str) -> str:
    """One-line summary of a diff: '+N -M in K hunks'."""
    hunks = parse_unified_diff(diff_text)
    adds = 0
    dels = 0
    for h in hunks:
        for l in h.raw_new:
            if l.startswith("+"):
                adds += 1
        for l in h.raw_old:
            if l.startswith("-"):
                dels += 1
    return f"+{adds} -{dels} in {len(hunks)} hunk(s)"
