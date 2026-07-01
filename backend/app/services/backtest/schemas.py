"""Pydantic request/response models for the screener-exit backtest endpoint."""
from __future__ import annotations
from datetime import date as _date
from enum import Enum
from typing import List, Optional, Dict, Any, Union, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


DEFAULT_TOTAL_CAPITAL = 100_000.0
MAX_LOOKBACK_HARD_CAP = 365


class ScreenerKind(str, Enum):
    DORMANT_GIANT = "dormant_giant"
    CUSTOM = "custom"


class SizingMode(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    INVERSE_VOL = "inverse_vol"
    SCORE_WEIGHTED = "score_weighted"
    CAPITAL_CAPPED = "capital_capped"


class SizingModel(BaseModel):
    mode: SizingMode = SizingMode.EQUAL_WEIGHT
    per_position_cap: Optional[float] = Field(
        default=None, description="Required when mode == capital_capped"
    )

    @model_validator(mode="after")
    def _validate_cap(self):
        if self.mode == SizingMode.CAPITAL_CAPPED and (self.per_position_cap is None or self.per_position_cap <= 0):
            raise ValueError("per_position_cap is required and must be > 0 when mode == capital_capped")
        return self


class ExitRulesModel(BaseModel):
    stop_loss_pct: float = Field(ge=0.0, le=1.0)
    take_profit_pct: float = Field(ge=0.0, le=5.0)
    trailing_stop_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    trend_break_sma: int = Field(default=0, ge=0, le=200,
                                  description="0 disables; otherwise exit when close < SMA(N)")
    max_holding_days: int = Field(default=0, ge=0, le=365)
    max_lookback_days: int = Field(default=120, ge=1, le=MAX_LOOKBACK_HARD_CAP)

    @field_validator("trend_break_sma")
    @classmethod
    def _sma_min_2(cls, v: int) -> int:
        if v not in (0,) and v < 2:
            raise ValueError("trend_break_sma must be 0 (disabled) or >= 2")
        return v


class _DormantGiantScreener(BaseModel):
    kind: Literal[ScreenerKind.DORMANT_GIANT] = ScreenerKind.DORMANT_GIANT


class _CustomScreener(BaseModel):
    kind: Literal[ScreenerKind.CUSTOM] = ScreenerKind.CUSTOM
    filters: Dict[str, Any] = Field(default_factory=dict)


ScreenerConfig = Union[_DormantGiantScreener, _CustomScreener]


class BacktestExitRequest(BaseModel):
    as_of_date: _date
    top_n: int = Field(ge=1, le=200)
    sizing: SizingModel = Field(default_factory=SizingModel)
    screener: ScreenerConfig
    exit_rules: ExitRulesModel


class PerTradeEntry(BaseModel):
    ticker: str
    sector: Optional[str] = None
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    exit_reason: str
    holding_days: int
    pnl_dollars: float
    pnl_pct: float
    mfe_pct: float
    mae_pct: float


class BacktestExitResponse(BaseModel):
    config: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    per_trade: List[PerTradeEntry]
    summary: Dict[str, Any]
    equity_curve: List[Dict[str, Any]]
    drawdown_curve: List[Dict[str, Any]]
    benchmark: Dict[str, Any]
