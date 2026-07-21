"""StrategyEngine — fixed mechanical engine for daily-rotation strategies.

The engine handles everything that doesn't change between strategies:
  - Daily simulation loop
  - Portfolio state (holdings, cash, equity)
  - Position sizing (score-weighted)
  - Sector diversification
  - Markov regime adaptation (bull/bear exposure)
  - Trade logging
  - Reporting (KPIs, monthly returns, top/bottom trades)
  - JSON/CSV export

What changes per strategy is the 4-function config:
  - precompute_fn(tickers, start, end) -> stock_db
  - entry_score_fn(candidate, market_cap_stats) -> float
  - holding_score_fn(ticker, date, holding, market_cap_stats) -> float
  - exit_check_fn(ticker, date, holding, stock_db) -> str | None
"""
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any, List
import pandas as pd
import numpy as np


@dataclass
class StrategyConfig:
    """All knobs for a daily-rotation strategy run."""
    # ── Date range ──
    as_of: str
    end: str

    # ── Capital & sizing ──
    capital: float = 100_000.0
    max_holdings: int = 5
    min_hold_days: int = 7

    # ── Exits ──
    trailing_stop: float = 0.20
    take_profit: float = 0.30
    time_stop_days: int = 60

    # ── Filters ──
    max_volatility: float = 0.05  # skip stocks with 14d return std above this
    max_sector_count: int = 2

    # ── Regime ──
    bull_exposure: float = 1.0
    bear_exposure: float = 0.50

    # ── Scoring weights (used by golden_cross; ignored by others) ──
    angle_weight: float = 0.60
    cap_weight: float = 0.40

    # ── Strategy-specific 4 functions (set by golden_cross.py etc.) ──
    precompute_fn: Optional[Callable] = None
    entry_score_fn: Optional[Callable] = None
    holding_score_fn: Optional[Callable] = None
    exit_check_fn: Optional[Callable] = None

    # ── Optional metadata for reports ──
    name: str = "Unnamed Strategy"
    score_squared_sizing: bool = True  # Golden Cross uses score² weighting
