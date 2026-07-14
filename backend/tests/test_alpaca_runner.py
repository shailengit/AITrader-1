"""Tests for the Alpaca strategy runner."""

import os
import sys

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Set DB credentials for testing
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")

import pytest
from app.services.alpaca_runner import StrategyRunner


@pytest.fixture
def runner():
    """Create a StrategyRunner instance for testing."""
    return StrategyRunner()


def test_scan_and_rank(runner):
    """Test that scan_and_rank returns top candidates with valid data."""
    as_of = runner.get_latest_date()
    candidates = runner.scan_and_rank(as_of)
    assert len(candidates) > 0, "Should find at least some candidates"
    assert len(candidates) <= 5, "Should return at most 5 candidates"
    for c in candidates:
        assert "ticker" in c
        assert "score" in c
        assert "angle" in c
        assert c["score"] > 0, "Score should be positive"
        assert len(c["ticker"]) > 0, "Ticker should not be empty"


def test_scan_and_rank_sorted(runner):
    """Test that candidates are sorted by score descending."""
    as_of = runner.get_latest_date()
    candidates = runner.scan_and_rank(as_of)
    if len(candidates) >= 2:
        for i in range(len(candidates) - 1):
            assert candidates[i]["score"] >= candidates[i + 1]["score"], \
                f"Candidates not sorted at index {i}: {candidates[i]['score']} < {candidates[i+1]['score']}"


def test_check_death_cross(runner):
    """Test death cross detection returns a boolean or numpy bool."""
    result = runner.check_death_cross("AAPL", "2024-01-01")
    import numpy as np
    assert isinstance(result, (bool, np.bool_))


def test_crisis_override(runner):
    """Test crisis override check returns a boolean or numpy bool."""
    result = runner.check_crisis_override("2024-01-01")
    import numpy as np
    assert isinstance(result, (bool, np.bool_))


def test_get_latest_date(runner):
    """Test that latest date is a valid date string."""
    date = runner.get_latest_date()
    assert len(date) == 10, f"Date should be YYYY-MM-DD format, got {date}"
    parts = date.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # Year
    assert 1 <= int(parts[1]) <= 12  # Month
    assert 1 <= int(parts[2]) <= 31  # Day


def test_get_all_tickers(runner):
    """Test that ticker list is non-empty."""
    tickers = runner.get_all_tickers()
    assert len(tickers) > 0, "Should find tickers in the database"
    assert len(tickers) > 100, "Should find at least 100 tickers"
