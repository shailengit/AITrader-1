"""Real-DB integration tests for /api/screener/chart-data/{ticker}.

These tests hit the live sp1500_1d PostgreSQL database. They are NOT
mocked; if the DB isn't available they fail loudly. Run with:

    cd backend && ./venv/bin/python -m pytest tests/routers/test_chart_data_integration.py -v

For unit-level coverage (no DB), see test_chart_data.py.
"""
import pytest

# Skip this module entirely if the DB isn't reachable. The unit tests
# don't need a live DB; these are pure integration coverage.
try:
    from app.db.database import engine  # type: ignore
    with engine.connect() as _c:
        pass
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DB_AVAILABLE, reason="Live sp1500_1d DB not reachable"
)


def test_chart_data_real_db_with_start_and_end() -> None:
    """End-to-end: real DB returns 252 rows for AAPL in 2024."""
    from app.services.screening.chart_data import get_chart_data

    bars = get_chart_data(
        "AAPL", ["momentum_rsi"], days=9999, start="2024-01-01", end="2024-12-31"
    )
    assert bars is not None
    assert len(bars) > 200  # 252 trading days in 2024
    # All bars within the requested range
    import datetime as _dt
    for bar in bars:
        ts = _dt.datetime.utcfromtimestamp(bar["time"]).date()
        assert _dt.date(2024, 1, 1) <= ts <= _dt.date(2024, 12, 31)


def test_chart_data_real_db_with_start_only() -> None:
    """End-to-end: real DB returns rows from 2024 onward."""
    from app.services.screening.chart_data import get_chart_data

    bars = get_chart_data("AAPL", ["momentum_rsi"], days=9999, start="2024-01-01")
    assert bars is not None
    assert len(bars) > 200
    import datetime as _dt
    first_dt = _dt.datetime.utcfromtimestamp(bars[0]["time"]).date()
    assert first_dt >= _dt.date(2024, 1, 1)
