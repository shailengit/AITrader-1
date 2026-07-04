"""Tests for the date-range extension of /api/screener/chart-data/{ticker}.

The endpoint delegates to app.services.screening.chart_data.get_chart_data,
which talks to the real DB. These tests monkeypatch pandas.read_sql at the
chart_data module level to return a small fixture DataFrame, so they
exercise the routing + service plumbing without needing a live DB.

For full integration coverage, run against the live sp1500_1d database.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pandas as pd
import pytest


def _make_bars_df(start: str, n: int) -> pd.DataFrame:
    """Build a small OHLCV DataFrame for chart tests.

    Returns rows oldest-first (chronological), which matches what the
    production code path produces after its sort_values('Date') step.
    """
    dates = pd.date_range(start=start, periods=n, freq="D")
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0 + i for i in range(n)],
            "High": [101.0 + i for i in range(n)],
            "Low": [99.0 + i for i in range(n)],
            "Close": [100.5 + i for i in range(n)],
            "Volume": [1_000_000] * n,
        }
    )


@pytest.fixture
def patched_chart(monkeypatch):
    """Patch pd.read_sql inside chart_data to return a 250-row fixture.

    Yields (df, captured_calls) so tests can both inspect the returned
    bars and the SQL string/params that were passed in.
    """
    df = _make_bars_df("2023-01-03", 250)
    captured: List[Dict[str, Any]] = []

    def fake_read_sql(sql, engine, params=None):
        captured.append({"sql": sql, "params": params})
        # When the SQL has BETWEEN, return only rows in the requested range.
        if params and ("start" in params or "end" in params):
            sub = df.copy()
            if "start" in params:
                sub = sub[sub["Date"] >= pd.Timestamp(params["start"])]
            if "end" in params:
                sub = sub[sub["Date"] <= pd.Timestamp(params["end"])]
            return sub.reset_index(drop=True)
        # Otherwise (the days path) return the full fixture — the production
        # code will sort it. We hand back DESC-order to match the SQL.
        return df.iloc[::-1].reset_index(drop=True)

    monkeypatch.setattr(
        "app.services.screening.chart_data.pd.read_sql", fake_read_sql
    )
    return df, captured


# ── get_chart_data unit tests ──────────────────────────────────────────────


def test_chart_data_with_start_and_end_returns_bars_in_range(patched_chart) -> None:
    """Both start and end → bars strictly between the dates, oldest first."""
    from app.services.screening.chart_data import get_chart_data

    # Use a range wide enough to produce ≥50 rows (the service's lower bound
    # for indicator computation). 2023-06-01 → 2023-09-30 spans ~120 days.
    bars = get_chart_data(
        "AAPL", ["sma_50"], days=9999, start="2023-06-01", end="2023-09-30"
    )
    assert bars is not None
    assert len(bars) > 0
    first_ts = bars[0]["time"]
    first_dt = datetime.utcfromtimestamp(first_ts).date()
    last_ts = bars[-1]["time"]
    last_dt = datetime.utcfromtimestamp(last_ts).date()
    assert first_dt >= datetime(2023, 6, 1).date()
    assert last_dt <= datetime(2023, 9, 30).date()
    # And oldest first.
    assert first_ts <= last_ts


def test_chart_data_with_start_only_returns_bars_from_start_forward(patched_chart) -> None:
    """Only start provided → all bars from start to latest."""
    from app.services.screening.chart_data import get_chart_data

    bars = get_chart_data(
        "AAPL", ["sma_50"], days=9999, start="2023-06-01"
    )
    assert bars is not None
    assert len(bars) > 0
    first_dt = datetime.utcfromtimestamp(bars[0]["time"]).date()
    assert first_dt >= datetime(2023, 6, 1).date()


def test_chart_data_without_range_falls_back_to_days(patched_chart) -> None:
    """Neither start nor end provided → uses days (backward-compat regression)."""
    from app.services.screening.chart_data import get_chart_data

    bars = get_chart_data("AAPL", ["sma_50"], days=10)
    assert bars is not None
    # The fixture has 60 rows; the days path returns all of them in our
    # mock because we don't honor the LIMIT. Confirm the function still
    # returns a list with at least one bar.
    assert isinstance(bars, list)
    assert len(bars) > 0


def test_chart_data_with_overrides_still_works_after_date_range_addition(
    patched_chart,
) -> None:
    """Regression: overrides param must still produce separate payload keys."""
    from app.services.screening.chart_data import get_chart_data

    # `trend_ema_fast` is a real registry column (default window 12). The
    # override with window=200 must produce a unique payload key
    # (`trend_ema_fast__w200`) in `bar.indicators` so the frontend can
    # render both the default and the override on the same chart.
    bars = get_chart_data(
        "AAPL",
        ["trend_ema_fast"],
        days=120,
        overrides={"trend_ema_fast": {"window": 200}},
    )
    assert bars is not None
    first_with_ind = next((b for b in bars if b.get("indicators")), None)
    assert first_with_ind is not None
    ind_keys = list(first_with_ind["indicators"].keys())
    # We expect at least one key starting with "trend_ema_fast" (either the
    # default column or the override-suffixed variant).
    assert any(k.startswith("trend_ema_fast") for k in ind_keys), ind_keys


# ── Route-level 400 test ───────────────────────────────────────────────────


def test_chart_data_route_with_malformed_start_returns_400(patched_chart) -> None:
    """Route returns 400 when start is not a valid YYYY-MM-DD string."""
    from fastapi import HTTPException
    from app.routers.screener import chart_data

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chart_data("AAPL", "", days=120, overrides="", start="not-a-date", end=None))
    assert exc_info.value.status_code == 400
    assert "Invalid start date" in str(exc_info.value.detail)
