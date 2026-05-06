"""
Database configuration and connection pool for TradeCraft.
Shares the sp1500_1d PostgreSQL database with existing applications.
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# Database configuration from environment
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "sarina00")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5431")
DB_NAME = os.getenv("DB_NAME", "sp1500_1d")

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
    {'ticker': 'XLF', 'name': 'Financials'},
    {'ticker': 'XLV', 'name': 'Health Care'},
    {'ticker': 'XLY', 'name': 'Consumer Discretionary'},
    {'ticker': 'XLI', 'name': 'Industrials'},
    {'ticker': 'XLC', 'name': 'Communication Services'},
    {'ticker': 'XLP', 'name': 'Consumer Staples'},
    {'ticker': 'XLB', 'name': 'Materials'},
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