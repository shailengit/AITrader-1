"""Router tests for POST /api/screener/backtest-exit.

This task stubs the implementation: the endpoint validates the request
and returns a placeholder response. Task 10 wires the real orchestration.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_backtest_exit_dormant_giant_returns_placeholder(client):
    payload = {
        "as_of_date": "2024-06-01",
        "top_n": 5,
        "sizing": {"mode": "equal_weight"},
        "screener": {"kind": "dormant_giant"},
        "exit_rules": {
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.20,
            "trailing_stop_pct": 0.0,
            "trend_break_sma": 20,
            "max_holding_days": 0,
            "max_lookback_days": 120,
        },
    }
    r = client.post("/api/screener/backtest-exit", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["config"]["as_of_date"] == "2024-06-01"
    assert body["config"]["top_n"] == 5
    # Placeholder: empty per_trade, summary zeroed
    assert body["per_trade"] == []
    assert body["summary"]["n_trades"] == 0


def test_backtest_exit_custom_returns_placeholder(client):
    payload = {
        "as_of_date": "2024-06-01",
        "top_n": 10,
        "sizing": {"mode": "equal_weight"},
        "screener": {"kind": "custom", "filters": {"rsi_max": 30}},
        "exit_rules": {
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.15,
            "trailing_stop_pct": 0.0,
            "trend_break_sma": 0,
            "max_holding_days": 0,
            "max_lookback_days": 60,
        },
    }
    r = client.post("/api/screener/backtest-exit", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["sizing"]["mode"] == "equal_weight"


def test_backtest_exit_invalid_payload_returns_422(client):
    payload = {
        "as_of_date": "2024-06-01",
        "top_n": 0,                          # invalid: must be >= 1
        "sizing": {"mode": "equal_weight"},
        "screener": {"kind": "dormant_giant"},
        "exit_rules": {
            "stop_loss_pct": -0.05,           # invalid: must be >= 0
            "take_profit_pct": 0.20,
            "trailing_stop_pct": 0.0,
            "trend_break_sma": 0,
            "max_holding_days": 0,
            "max_lookback_days": 120,
        },
    }
    r = client.post("/api/screener/backtest-exit", json=payload)
    assert r.status_code == 422
