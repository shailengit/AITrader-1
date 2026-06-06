"""Tests for security utilities."""

import pytest
from app.utils.security import sanitize_ticker, get_safe_table_name


class TestSanitizeTicker:
    def test_valid_tickers(self):
        assert sanitize_ticker("AAPL") == "AAPL"
        assert sanitize_ticker("brk.a") == "BRK.A"
        assert sanitize_ticker("  MSFT  ") == "MSFT"
        assert sanitize_ticker("xlk") == "XLK"

    def test_rejects_sql_injection(self):
        with pytest.raises(ValueError):
            sanitize_ticker("AAPL; DROP TABLE users")
        with pytest.raises(ValueError):
            sanitize_ticker("AAPL' OR '1'='1")
        with pytest.raises(ValueError):
            sanitize_ticker("AAPL--")

    def test_rejects_sql_keywords(self):
        with pytest.raises(ValueError):
            sanitize_ticker("SELECT")
        with pytest.raises(ValueError):
            sanitize_ticker("DROP")
        with pytest.raises(ValueError):
            sanitize_ticker("UNION")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            sanitize_ticker("")
        with pytest.raises(ValueError):
            sanitize_ticker("   ")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError):
            sanitize_ticker("A" * 20)


class TestGetSafeTableName:
    def test_basic_ticker(self):
        assert get_safe_table_name("AAPL") == "aapl"

    def test_class_shares(self):
        assert get_safe_table_name("BRK.A") == "brk-a"

    def test_lowercase_input(self):
        assert get_safe_table_name("msft") == "msft"
