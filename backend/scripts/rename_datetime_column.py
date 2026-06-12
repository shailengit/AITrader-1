"""
Rename "Datetime" column to "Date" on all stock tables in sp1500_1m.
This makes the schema match sp1500_1d so both databases can use the same queries.
"""
import os
import time
import logging

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Load credentials same way as database.py
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5431")

if not DB_PASSWORD:
    raise ValueError("DB_PASSWORD environment variable is required.")

# Connect to sp1500_1m (the minute database)
url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/sp1500_1m"
engine = create_engine(url)


def main():
    with engine.connect() as conn:
        # Get all stock tables (exclude non-stock tables)
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name NOT IN ('stock_metadata', 'stock_financials_quarterly',
                                   'stock_financials_yearly', 'earnings_calendar', 'alembic_version')
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        logger.info(f"Found {len(tables)} tables to process")

        # First verify which tables still need the rename
        to_rename = []
        for t in tables:
            row = conn.execute(
                text(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}' AND column_name='Datetime'")
            ).fetchone()
            has_datetime = row is not None
            has_date = conn.execute(
                text(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}' AND column_name='Date'")
            ).fetchone() is not None

            if has_datetime and has_date:
                logger.warning(f"{t}: has BOTH Datetime AND Date — skipping")
            elif has_datetime:
                to_rename.append(t)
            elif has_date:
                pass  # already renamed
            else:
                logger.warning(f"{t}: has neither Datetime nor Date column — skipping")

        logger.info(f"{len(to_rename)} tables need rename, {len(tables) - len(to_rename)} already done or skipped")

        if not to_rename:
            logger.info("Nothing to rename!")
            return

        # Ask for confirmation
        logger.info(f"Starting rename of {len(to_rename)} tables...")

        t0 = time.time()
        errors = []
        for i, table in enumerate(to_rename, 1):
            try:
                conn.execute(text(f'ALTER TABLE "{table}" RENAME COLUMN "Datetime" TO "Date"'))
                if i % 100 == 0:
                    conn.commit()
                    elapsed = time.time() - t0
                    logger.info(f"Progress: {i}/{len(to_rename)} ({elapsed:.1f}s elapsed)")
            except Exception as e:
                errors.append((table, str(e)))
                logger.error(f"Failed on {table}: {e}")

        conn.commit()
        elapsed = time.time() - t0
        logger.info(f"Renamed {len(to_rename) - len(errors)}/{len(to_rename)} tables in {elapsed:.1f}s")

        if errors:
            logger.error(f"Errors ({len(errors)}):")
            for table, err in errors:
                logger.error(f"  {table}: {err}")

        # Verify: check a sample table
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='aapl' AND column_name='Date'"))
        if result.fetchone():
            logger.info("✅ Verification: aapl table has 'Date' column")
        else:
            logger.error("❌ Verification FAILED: aapl table still doesn't have 'Date' column")

        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='aapl' AND column_name='Datetime'"))
        if result.fetchone():
            logger.error("❌ Verification: aapl table still has 'Datetime' column!")
        else:
            logger.info("✅ Verification: aapl table no longer has 'Datetime' column")


if __name__ == "__main__":
    main()