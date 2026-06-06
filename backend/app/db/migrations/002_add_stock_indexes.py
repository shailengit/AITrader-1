"""Add indexes to stock price tables for performance.

Revision ID: 002
Revises: 001
Create Date: 2026-06-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add indexes to stock tables for common query patterns."""
    op.execute("""
        -- Create a function to add indexes to all stock tables
        DO $$
        DECLARE
            tbl_name text;
        BEGIN
            FOR tbl_name IN 
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name NOT IN (
                    'stock_metadata', 
                    'stock_financials_quarterly', 
                    'stock_financials_yearly',
                    'earnings_calendar',
                    'alembic_version'
                )
            LOOP
                -- Index on Date for time-series queries
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS idx_%s_date ON %I ("Date")',
                    tbl_name, tbl_name
                );
                
                -- Index on Date + Close for latest price queries
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS idx_%s_date_close ON %I ("Date", "Close")',
                    tbl_name, tbl_name
                );
                
                -- Index on Volume for volume analysis
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS idx_%s_volume ON %I ("Volume")',
                    tbl_name, tbl_name
                );
            END LOOP;
        END $$;
    """)
    
    # Add indexes to metadata tables
    op.create_index(
        'idx_stock_metadata_sector',
        'stock_metadata',
        ['sector']
    )
    op.create_index(
        'idx_stock_metadata_ticker',
        'stock_metadata',
        ['ticker']
    )
    op.create_index(
        'idx_stock_financials_quarterly_ticker',
        'stock_financials_quarterly',
        ['ticker']
    )


def downgrade() -> None:
    """Remove indexes."""
    op.execute("""
        DO $$
        DECLARE
            tbl_name text;
        BEGIN
            FOR tbl_name IN 
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name NOT IN (
                    'stock_metadata', 
                    'stock_financials_quarterly', 
                    'stock_financials_yearly',
                    'earnings_calendar',
                    'alembic_version'
                )
            LOOP
                EXECUTE format(
                    'DROP INDEX IF EXISTS idx_%s_date',
                    tbl_name
                );
                EXECUTE format(
                    'DROP INDEX IF EXISTS idx_%s_date_close',
                    tbl_name
                );
                EXECUTE format(
                    'DROP INDEX IF EXISTS idx_%s_volume',
                    tbl_name
                );
            END LOOP;
        END $$;
    """)
    
    op.drop_index('idx_stock_metadata_sector', 'stock_metadata')
    op.drop_index('idx_stock_metadata_ticker', 'stock_metadata')
    op.drop_index('idx_stock_financials_quarterly_ticker', 'stock_financials_quarterly')
