"""Tests for the Coach analytics module. Fixed expectations over the seed_journal fixture."""
from __future__ import annotations
import math
from datetime import date
from app.services.coach import analytics as A


PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 4, 30)


def test_kpis_aggregate(seed_journal):
    k = A.kpis(seed_journal, PERIOD_START, PERIOD_END, None)
    # 25 wins @ +$500 each = +$12,500; 25 losses @ -$300 each = -$7,500; total = +$5,000
    assert k["n_trades"] == 50
    assert k["win_rate"] == 0.5
    assert k["total_pnl"] == 5000.0
    # expectancy = 0.5 * 500 - 0.5 * 300 = 100
    assert k["expectancy"] == 100.0


def test_pnl_by_regime_bull_bear(seed_journal):
    r = A.pnl_by_regime(seed_journal, PERIOD_START, PERIOD_END, None)
    # Roughly half the trades happen in each regime (alternating days)
    assert "bull" in r and "bear" in r
    assert r["bull"]["n"] > 0 and r["bear"]["n"] > 0
    # In the fixture, win/loss is coupled to entry_day % 2 which is the same
    # offset as the regime. So even-i (wins) -> bear, odd-i (losses) -> bull.
    # Therefore bear is net positive and bull is net negative.
    assert r["bear"]["pnl"] > 0
    assert r["bull"]["pnl"] < 0


def test_win_rate_by_strategy_three_strategies(seed_journal):
    rows = A.win_rate_by_strategy(seed_journal, PERIOD_START, PERIOD_END)
    names = {r["name"] for r in rows}
    assert names == {"fx_alpha", "fx_beta", "fx_gamma"}
    for r in rows:
        # Each strategy gets 16 or 17 trades, alternating win/loss
        assert r["n"] in (16, 17)
        assert 0.4 <= r["win_rate"] <= 0.6


def test_mae_mfe_scatter_shape(seed_journal):
    rows = A.mae_mfe_scatter(seed_journal, PERIOD_START, PERIOD_END, None)
    assert len(rows) == 50
    for r in rows:
        assert "mae" in r and "mfe" in r and "pnl" in r
        # Winners have mfe > mae, losers have mae > mfe (per fixture)
        if r["pnl"] > 0:
            assert r["mfe"] > r["mae"]
        else:
            assert r["mae"] > r["mfe"]


def test_recent_trades_limit(seed_journal):
    rows = A.recent_trades(seed_journal, strategy_id=None, n=10)
    assert len(rows) == 10
    # Most recent first
    assert rows[0]["entry_at"] >= rows[-1]["entry_at"]


def test_regime_timeline_window(seed_journal):
    r = A.regime_timeline(seed_journal, PERIOD_START, PERIOD_END)
    # 120 days of fixture data
    assert len(r) == 120
    assert r[0]["date"] == "2026-01-01"


def test_overview_returns_all_keys(seed_journal):
    o = A.overview(seed_journal, PERIOD_START, PERIOD_END, None)
    for k in ("period", "kpis", "equity_curve", "drawdown_curve", "pnl_by_regime", "win_rate_by_strategy", "entry_timing_lag"):
        assert k in o
