"""
Database configuration and connection pool for TradeCraft.
Shares the sp1500_1d PostgreSQL database with existing applications.
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# Declarative base for ORM models (added for the Trade Coach agent)
Base = declarative_base()

# Database configuration from environment (no hardcoded defaults for sensitive values)
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5431")
DB_NAME = os.getenv("DB_NAME", "sp1500_1d")

# Fail fast if password is not set
if not DB_PASSWORD:
    raise ValueError(
        "DB_PASSWORD environment variable is required. "
        "Please set it in your .env file. See .env.example for reference."
    )

# Connection URLs
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
ASYNC_DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Synchronous engine for blocking operations
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False  # Set to True for SQL debugging
)

# Async engine for FastAPI async endpoints
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    echo=False
)

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)  # type: ignore[call-overload]


def get_db():
    """Dependency for synchronous database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """Dependency for async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def test_connection():
    """Test database connection."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Successfully connected to database: %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Database connection failed: %s", e)
        return False


# ETF and Sector mappings (shared across apps)
SECTOR_ETFS = [
    {'ticker': 'XLK', 'name': 'Technology'},
    {'ticker': 'XLE', 'name': 'Energy'},
    {'ticker': 'XLF', 'name': 'Financial Services'},
    {'ticker': 'XLV', 'name': 'Healthcare'},
    {'ticker': 'XLY', 'name': 'Consumer Cyclical'},
    {'ticker': 'XLI', 'name': 'Industrials'},
    {'ticker': 'XLC', 'name': 'Communication Services'},
    {'ticker': 'XLP', 'name': 'Consumer Defensive'},
    {'ticker': 'XLB', 'name': 'Basic Materials'},
    {'ticker': 'XLRE', 'name': 'Real Estate'},
    {'ticker': 'XLU', 'name': 'Utilities'},
]

# ETF ticker to sector name mapping
SECTOR_NAME_MAP = {
    'xlk': 'Technology',
    'xle': 'Energy',
    'xlf': 'Financial Services',
    'xlv': 'Healthcare',
    'xly': 'Consumer Cyclical',
    'xli': 'Industrials',
    'xlc': 'Communication Services',
    'xlp': 'Consumer Defensive',
    'xlb': 'Basic Materials',
    'xlre': 'Real Estate',
    'xlu': 'Utilities',
}

# Database connection status (set during startup)
db_connected = False


def set_db_connected(connected: bool):
    """Set the database connection status."""
    global db_connected  # pylint: disable=global-statement
    db_connected = connected


def create_earnings_calendar_table():
    """Create the earnings_calendar table if it does not exist."""
    from sqlalchemy import text
    ddl = """
    CREATE TABLE IF NOT EXISTS earnings_calendar (
        ticker VARCHAR(10) NOT NULL,
        report_date DATE NOT NULL,
        fiscal_year INT,
        fiscal_quarter INT,
        eps_estimate NUMERIC(12, 4),
        revenue_estimate NUMERIC(20, 2),
        eps_actual NUMERIC(12, 4),
        revenue_actual NUMERIC(20, 2),
        time_of_day VARCHAR(10) DEFAULT 'tns',
        source VARCHAR(20) DEFAULT 'finnhub',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (ticker, report_date)
    );

    CREATE INDEX IF NOT EXISTS idx_earnings_report_date ON earnings_calendar(report_date);
    CREATE INDEX IF NOT EXISTS idx_earnings_ticker ON earnings_calendar(ticker);

    CREATE OR REPLACE FUNCTION update_earnings_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_earnings_updated_at ON earnings_calendar;
    CREATE TRIGGER trg_earnings_updated_at
        BEFORE UPDATE ON earnings_calendar
        FOR EACH ROW
        EXECUTE FUNCTION update_earnings_updated_at();
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(ddl))
        logger.info("earnings_calendar table created/verified.")
        return True
    except Exception as e:
        logger.error("Failed to create earnings_calendar table: %s", e)
        return False
