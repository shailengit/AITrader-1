"""
Security utilities for ticker validation and SQL injection prevention.
"""
import re
from typing import Optional

# Valid ticker pattern: 1-5 uppercase letters, optionally .A-Z1-3 for class shares
VALID_TICKER_PATTERN = re.compile(r'^[A-Z]{1,5}(\.[A-Z]{1,3})?$')

# Additional safety: reject SQL keywords and special characters in tickers
FORBIDDEN_TICKER_CHARS = re.compile(r'[;\'"\\/*\-{}\[\]()$%@#<>!+=~`^&|]')
FORBIDDEN_SQL_KEYWORDS = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'EXEC', 'EXECUTE', 'UNION', '--', '/*', '*/']


def sanitize_ticker(ticker: str) -> str:
    """
    Validate and sanitize a ticker symbol.
    
    Returns the cleaned uppercase ticker if valid.
    Raises ValueError if the ticker contains suspicious characters or patterns.
    """
    if not ticker or not isinstance(ticker, str):
        raise ValueError("Ticker must be a non-empty string")
    
    cleaned = ticker.strip().upper()
    
    if len(cleaned) > 10:
        raise ValueError(f"Ticker '{ticker}' is too long")
    
    # Check for forbidden characters
    if FORBIDDEN_TICKER_CHARS.search(cleaned):
        raise ValueError(f"Ticker '{ticker}' contains forbidden characters")
    
    # Check for SQL injection keywords
    cleaned_upper = cleaned.upper()
    for keyword in FORBIDDEN_SQL_KEYWORDS:
        if keyword in cleaned_upper:
            raise ValueError(f"Ticker '{ticker}' contains forbidden SQL keyword: {keyword}")
    
    # Final validation against standard pattern
    if not VALID_TICKER_PATTERN.match(cleaned):
        # Allow if it's a known ETF (ETFs sometimes have numbers, e.g., XLK)
        if not re.match(r'^[A-Z]{1,5}$', cleaned):
            raise ValueError(f"Ticker '{ticker}' does not match valid pattern")
    
    return cleaned


def get_safe_table_name(ticker: str) -> str:
    """
    Convert a ticker to a safe PostgreSQL table name.
    
    Validates the ticker first, then returns lowercase version.
    """
    validated = sanitize_ticker(ticker)
    # Replace dots with hyphens for table names (e.g., BRK.A -> brk-a)
    return validated.lower().replace('.', '-')
