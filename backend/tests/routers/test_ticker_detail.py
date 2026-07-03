"""Tests for the per-ticker detail endpoint.

The endpoint delegates to app.services.screening.ticker_detail.get_ticker_detail,
which talks to the real DB. These tests monkeypatch that function so they
exercise the route's request/response plumbing without needing a live DB.

The route uses a late-bound module reference (`_td_module.get_ticker_detail`)
so monkeypatching the source module's attribute is enough to redirect the call.
For full integration coverage run against the live sp1500_1d database.
"""
import pytest


def _make_detail(**overrides):
    """Build a TickerDetail dict with sensible defaults; tests override fields."""
    base = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "close": 187.45,
        "as_of_date": "2026-07-02",
        "fundamentals": {
            "market_cap": 2.91e12,
            "beta": 1.25,
            "peg_ratio": 2.1,
            "eps_growth_qoq": 18.4,
            "revenue_growth_qoq": 9.2,
        },
        "indicators": {
            "rsi": 62.3,
            "macd": 1.42,
            "mfi": 58.1,
            "bbw": 0.04,
            "volume_ratio": 1.4,
            "ath_proximity": 0.94,
            "volume_cluster_count": None,
            "rs_vs_sector": None,
        },
        "earnings_next": {
            "date": "2026-08-01",
            "days_away": 30,
            "eps_estimate": 1.34,
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def patched_detail(monkeypatch):
    """Patch ticker_detail.get_ticker_detail to return a controlled payload."""
    from app.services.screening import ticker_detail

    def _install(return_value=None, side_effect=None):
        if side_effect is not None:
            monkeypatch.setattr(
                ticker_detail,
                "get_ticker_detail",
                lambda ticker, as_of_date=None: (_ for _ in ()).throw(side_effect),
            )
        else:
            monkeypatch.setattr(
                ticker_detail,
                "get_ticker_detail",
                lambda ticker, as_of_date=None: return_value,
            )
    return _install


def test_ticker_detail_happy_path(client, patched_detail):
    """AAPL returns the full TickerDetail schema, all fields populated."""
    from app.exceptions import DataNotFoundError  # noqa: F401  (just verifying import)
    patched_detail(return_value=_make_detail())

    response = client.get("/api/screener/ticker/AAPL")
    assert response.status_code == 200
    data = response.json()

    for key in ("ticker", "company_name", "sector", "close", "as_of_date",
                "fundamentals", "indicators", "earnings_next"):
        assert key in data, f"missing {key}"

    assert data["ticker"] == "AAPL"
    assert data["close"] == 187.45
    assert data["as_of_date"] == "2026-07-02"

    for key in ("market_cap", "beta", "peg_ratio",
                "eps_growth_qoq", "revenue_growth_qoq"):
        assert key in data["fundamentals"]

    for key in ("rsi", "macd", "mfi", "bbw", "volume_ratio", "ath_proximity",
                "volume_cluster_count", "rs_vs_sector"):
        assert key in data["indicators"]


def test_ticker_detail_invalid_ticker(client):
    """A garbage ticker fails sanitize_ticker and returns 400."""
    response = client.get("/api/screener/ticker/!!!not-a-ticker!!!")
    assert response.status_code == 400


def test_ticker_detail_unknown_ticker(client, patched_detail):
    """Service raises DataNotFoundError → route returns 404."""
    from app.exceptions import DataNotFoundError
    patched_detail(side_effect=DataNotFoundError("No data for ticker ZZZZZ"))

    response = client.get("/api/screener/ticker/ZZZZZ")
    assert response.status_code == 404


def test_ticker_detail_as_of_param_forwarded(client):
    """The as_of_date query param is forwarded to the service verbatim."""
    from app.services.screening import ticker_detail
    calls = []

    def fake(ticker, as_of_date=None):
        calls.append((ticker, as_of_date))
        return _make_detail(ticker=ticker, as_of_date=as_of_date or "2026-07-02")

    mp = pytest.MonkeyPatch()
    mp.setattr(ticker_detail, "get_ticker_detail", fake)
    try:
        response = client.get("/api/screener/ticker/AAPL?as_of_date=2024-01-15")
        assert response.status_code == 200
        assert calls == [("AAPL", "2024-01-15")]
    finally:
        mp.undo()


def test_ticker_detail_earnings_nullable(client, patched_detail):
    """When the service returns earnings_next=None, the route returns 200 with null."""
    patched_detail(return_value=_make_detail(earnings_next=None))

    response = client.get("/api/screener/ticker/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert "earnings_next" in data
    assert data["earnings_next"] is None
