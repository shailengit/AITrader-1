"""Tests for the backtest request/response Pydantic schemas."""
import pytest
from pydantic import ValidationError

from app.services.backtest.schemas import (
    BacktestExitRequest,
    ExitRulesModel,
    SizingModel,
    ScreenerKind,
    BacktestExitResponse,
    PerTradeEntry,
)


def test_request_dormant_giant_minimum():
    req = BacktestExitRequest(
        as_of_date="2024-06-01",
        top_n=20,
        sizing=SizingModel(mode="equal_weight"),
        screener={"kind": "dormant_giant"},
        exit_rules=ExitRulesModel(stop_loss_pct=0.08, take_profit_pct=0.20,
                                  trailing_stop_pct=0.0, trend_break_sma=20,
                                  max_holding_days=0, max_lookback_days=120),
    )
    assert req.screener.kind == ScreenerKind.DORMANT_GIANT
    assert req.top_n == 20
    assert req.exit_rules.stop_loss_pct == 0.08


def test_request_custom_screener_passes_filters():
    req = BacktestExitRequest(
        as_of_date="2024-06-01",
        top_n=10,
        sizing=SizingModel(mode="equal_weight"),
        screener={"kind": "custom", "filters": {"rsi_max": 30}},
        exit_rules=ExitRulesModel(stop_loss_pct=0.05, take_profit_pct=0.15,
                                  trailing_stop_pct=0.0, trend_break_sma=0,
                                  max_holding_days=0, max_lookback_days=60),
    )
    assert req.screener.filters == {"rsi_max": 30}


def test_request_invalid_pct_rejected():
    with pytest.raises(ValidationError):
        ExitRulesModel(stop_loss_pct=-0.05, take_profit_pct=0.20,
                       trailing_stop_pct=0.0, trend_break_sma=0,
                       max_holding_days=0, max_lookback_days=120)


def test_request_max_lookback_capped_at_365():
    with pytest.raises(ValidationError):
        ExitRulesModel(stop_loss_pct=0.08, take_profit_pct=0.20,
                       trailing_stop_pct=0.0, trend_break_sma=20,
                       max_holding_days=0, max_lookback_days=400)


def test_request_top_n_must_be_positive():
    with pytest.raises(ValidationError):
        BacktestExitRequest(
            as_of_date="2024-06-01", top_n=0,
            sizing=SizingModel(mode="equal_weight"),
            screener={"kind": "dormant_giant"},
            exit_rules=ExitRulesModel(stop_loss_pct=0.0, take_profit_pct=0.0,
                                      trailing_stop_pct=0.0, trend_break_sma=0,
                                      max_holding_days=0, max_lookback_days=120),
        )


def test_response_round_trips():
    resp = BacktestExitResponse(
        config={"as_of_date": "2024-06-01", "top_n": 20, "sizing": {"mode": "equal_weight"},
                "exit_rules": {"stop_loss_pct": 0.08}, "total_capital": 100_000.0},
        warnings=[],
        per_trade=[PerTradeEntry(ticker="AAPL", entry_date="2024-06-01",
                                  entry_price=100.0, exit_date="2024-06-15",
                                  exit_price=110.0, exit_reason="take_profit",
                                  holding_days=10, pnl_dollars=500.0, pnl_pct=0.10,
                                  mfe_pct=0.12, mae_pct=-0.02)],
        summary={"total_return_pct": 0.5, "annualized_return_pct": 5.0,
                  "sharpe": 1.2, "sortino": 1.5, "max_drawdown_pct": -3.0,
                  "win_rate_pct": 60.0, "profit_factor": 1.8,
                  "avg_winner_pct": 8.0, "avg_loser_pct": -4.0,
                  "avg_holding_days": 12.0, "n_trades": 20,
                  "n_winners": 12, "n_losers": 8},
        equity_curve=[{"time": 1_700_000_000, "value": 100_000.0}],
        drawdown_curve=[{"time": 1_700_000_000, "dd_pct": 0.0}],
        benchmark={"spy_return_pct": 4.0, "alpha_pct": -3.5,
                    "spy_equity_curve": [{"time": 1_700_000_000, "value": 100_000.0}]},
    )
    dumped = resp.model_dump()
    assert dumped["per_trade"][0]["ticker"] == "AAPL"
