"""Router tests for POST /api/screener/backtest-exit.

The endpoint delegates to `app.services.backtest.orchestrator.run_backtest`,
whose I/O wrappers (`run_screener_at_as_of`, `get_ohlcv_for_backtest`,
`get_spy_bars`) are patched in tests so we never touch the real database.
"""
import pytest
from unittest.mock import patch
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _empty_screener(*a, **kw):
    return []


def _spy_bars():
    return pd.DataFrame({
        "Date": pd.date_range("2024-06-01", periods=130, freq="D"),
        "Open": 500.0, "High": 510.0, "Low": 495.0,
        "Close": np.linspace(500.0, 510.0, 130), "Volume": 1_000_000,
    })


def test_backtest_exit_returns_well_formed_response_with_no_candidates(client):
    """When the screener returns no candidates, the response is well-formed
    with empty per_trade, summary zeroed, and a 'no candidates' warning.
    """
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
    with patch("app.services.backtest.orchestrator.run_screener_at_as_of",
               side_effect=_empty_screener), \
         patch("app.services.backtest.orchestrator.get_spy_bars",
               return_value=_spy_bars()):
        r = client.post("/api/screener/backtest-exit", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["config"]["as_of_date"] == "2024-06-01"
    assert body["config"]["top_n"] == 5
    assert body["per_trade"] == []
    assert body["summary"]["n_trades"] == 0
    assert any("no candidates" in w.lower() for w in body["warnings"])


def test_backtest_exit_custom_returns_well_formed_response(client):
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
    with patch("app.services.backtest.orchestrator.run_screener_at_as_of",
               side_effect=_empty_screener), \
         patch("app.services.backtest.orchestrator.get_spy_bars",
               return_value=_spy_bars()):
        r = client.post("/api/screener/backtest-exit", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["sizing"]["mode"] == "equal_weight"
    # The custom screener's filters flow into the config (the orchestrator
    # does not echo them back, but it accepted the request → no 4xx).
    assert body["per_trade"] == []


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


def test_backtest_exit_orchestrator_end_to_end(client):
    """Stub the screener + OHLCV fetch; the real orchestrator must produce
    a non-empty per_trade and a non-zero summary.
    """
    candidates = [
        {"ticker": "AAA", "score": 90.0, "close": 100.0, "sector": "Tech"},
        {"ticker": "BBB", "score": 80.0, "close": 50.0, "sector": "Finance"},
    ]
    # AAA: trend_break fires when close < SMA(20) after the up-then-down
    aaa_bars = pd.DataFrame({
        "Date": pd.date_range("2024-06-01", periods=125, freq="D"),
        "Open": 100.0, "High": 100.0, "Low": 100.0,
        "Close": [100.0] * 20 + [110.0] * 5 + [95.0, 90.0, 85.0] + [90.0] * 97,
        "Volume": 1_000_000,
    })
    # BBB: take_profit fires on +30% (well above 20% threshold)
    bbb_bars = pd.DataFrame({
        "Date": pd.date_range("2024-06-01", periods=125, freq="D"),
        "Open": 50.0, "High": 50.0, "Low": 50.0,
        "Close": [50.0] * 5 + [55.0, 60.0, 65.0] + [65.0] * 117,
        "Volume": 1_000_000,
    })

    def fake_run_screener(req):
        return candidates

    def fake_get_ohlcv(ticker, start, end):
        return aaa_bars if ticker == "AAA" else bbb_bars

    payload = {
        "as_of_date": "2024-06-01",
        "top_n": 2,
        "sizing": {"mode": "equal_weight"},
        "screener": {"kind": "dormant_giant"},
        "exit_rules": {
            "stop_loss_pct": 0.50,      # wide so it doesn't fire
            "take_profit_pct": 0.20,
            "trailing_stop_pct": 0.0,
            "trend_break_sma": 20,
            "max_holding_days": 0,
            "max_lookback_days": 120,
        },
    }
    with patch("app.services.backtest.orchestrator.run_screener_at_as_of", side_effect=fake_run_screener), \
         patch("app.services.backtest.orchestrator.get_ohlcv_for_backtest", side_effect=fake_get_ohlcv), \
         patch("app.services.backtest.orchestrator.get_spy_bars", return_value=_spy_bars()):
        r = client.post("/api/screener/backtest-exit", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["per_trade"]) == 2
    assert {t["ticker"] for t in body["per_trade"]} == {"AAA", "BBB"}
    reasons = {t["ticker"]: t["exit_reason"] for t in body["per_trade"]}
    # BBB: take_profit fires on +30% (well above 20% threshold)
    assert reasons["BBB"] == "take_profit"
    # AAA: trend_break fires when close < SMA(20) after the up-then-down
    assert reasons["AAA"] in ("trend_break", "max_lookback")
    assert body["summary"]["n_trades"] == 2
    assert body["equity_curve"], "equity_curve should not be empty"
    assert body["benchmark"]["spy_equity_curve"], "spy_equity_curve should not be empty"
