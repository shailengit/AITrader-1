"""Position-sizing helpers for screener-driven backtests.

All functions are pure — no I/O, no DB. Inputs are scalars / lists; outputs
are parallel lists of dollar amounts that sum to <= total_capital.

Modes:
  - equal_weight   : uniform split of total_capital across n positions
  - inverse_vol    : weights ∝ 1 / rolling_vol (lower vol → more capital)
  - score_weighted : weights ∝ screener score (higher score → more capital)
  - capital_capped : equal-weight but each position is capped at per_position_cap
"""
from __future__ import annotations
from typing import List, Optional

EQUAL_WEIGHT = "equal_weight"
INVERSE_VOL = "inverse_vol"
SCORE_WEIGHTED = "score_weighted"
CAPITAL_CAPPED = "capital_capped"

VALID_MODES = {EQUAL_WEIGHT, INVERSE_VOL, SCORE_WEIGHTED, CAPITAL_CAPPED}

DEFAULT_TOTAL_CAPITAL = 100_000.0


class SizingError(ValueError):
    """Raised when sizing inputs are invalid or insufficient."""


def _check_n(n: int) -> None:
    if not isinstance(n, int) or n <= 0:
        raise SizingError(f"n must be a positive int, got {n!r}")


def _equal_weight(n: int, total_capital: float) -> List[float]:
    per = total_capital / n
    return [per] * n


def _capital_capped(n: int, total_capital: float, per_position_cap: float) -> List[float]:
    if per_position_cap <= 0:
        raise SizingError(f"per_position_cap must be > 0, got {per_position_cap}")
    per = min(total_capital / n, per_position_cap)
    return [per] * n


def _score_weighted(n: int, scores: List[float], total_capital: float) -> List[float]:
    if scores is None or len(scores) != n:
        raise SizingError(f"score_weighted requires a list of {n} scores, got {scores}")
    total = sum(scores)
    if total <= 0:
        raise SizingError("score_weighted requires positive total score")
    return [total_capital * (s / total) for s in scores]


def _inverse_vol(n: int, vols: List[float], total_capital: float) -> List[float]:
    if vols is None or len(vols) != n:
        raise SizingError(f"inverse_vol requires a list of {n} vols, got {vols}")
    inv = []
    for v in vols:
        if v is None or v <= 0:
            raise SizingError(f"inverse_vol requires positive vol per ticker, got {v}")
        inv.append(1.0 / v)
    total = sum(inv)
    return [total_capital * (x / total) for x in inv]


def compute_position_dollars(
    mode: str,
    n: int,
    scores: Optional[List[float]] = None,
    vols: Optional[List[float]] = None,
    total_capital: float = DEFAULT_TOTAL_CAPITAL,
    per_position_cap: Optional[float] = None,
) -> List[float]:
    """Return a list of n dollar amounts summing to <= total_capital.

    Args:
        mode: one of equal_weight | inverse_vol | score_weighted | capital_capped
        n: number of positions (must be positive int)
        scores: required for score_weighted; one score per position
        vols: required for inverse_vol; one vol per position
        total_capital: pool of capital to allocate (default $100,000)
        per_position_cap: required for capital_capped; per-position upper bound
    """
    _check_n(n)
    if mode not in VALID_MODES:
        raise SizingError(f"unknown mode {mode!r}; valid: {sorted(VALID_MODES)}")
    if total_capital <= 0:
        raise SizingError(f"total_capital must be > 0, got {total_capital}")

    if mode == EQUAL_WEIGHT:
        return _equal_weight(n, total_capital)
    if mode == CAPITAL_CAPPED:
        if per_position_cap is None:
            raise SizingError("capital_capped requires per_position_cap")
        return _capital_capped(n, total_capital, per_position_cap)
    if mode == SCORE_WEIGHTED:
        return _score_weighted(n, scores, total_capital)  # type: ignore[arg-type]
    # INVERSE_VOL
    return _inverse_vol(n, vols, total_capital)  # type: ignore[arg-type]


# Backward-compat alias (older callers may import the class)
SizingMode = VALID_MODES
