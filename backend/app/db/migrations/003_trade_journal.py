"""Create the trade journal schema for the Trade Coach agent.

Revision ID: 003
Revises: 002
Create Date: 2026-07-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, NUMERIC

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the six journal_* tables + indexes."""
    # Enable required extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # journal_strategy
    op.execute("""
        CREATE TABLE journal_strategy (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            kind TEXT NOT NULL CHECK (kind IN ('screener', 'quantgen', 'markov', 'manual')),
            name TEXT NOT NULL,
            params JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            retired_at TIMESTAMPTZ NULL,
            notes TEXT NULL,
            UNIQUE (kind, name)
        )
    """)

    # journal_strategy_run
    op.execute("""
        CREATE TABLE journal_strategy_run (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            strategy_id UUID NOT NULL REFERENCES journal_strategy(id) ON DELETE CASCADE,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ NULL,
            result_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            as_of_date DATE NULL,
            regime_at_run TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_journal_strategy_run_strategy_id ON journal_strategy_run(strategy_id)")
    op.execute("CREATE INDEX idx_journal_strategy_run_finished_at ON journal_strategy_run(finished_at)")

    # journal_signal
    op.execute("""
        CREATE TABLE journal_signal (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            strategy_run_id UUID NOT NULL REFERENCES journal_strategy_run(id) ON DELETE CASCADE,
            ticker TEXT NOT NULL,
            signal_type TEXT NOT NULL CHECK (signal_type IN ('entry', 'exit', 'buy', 'sell', 'hold')),
            signal_strength NUMERIC NULL,
            as_of_date DATE NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_journal_signal_ticker_date ON journal_signal(ticker, as_of_date)")
    op.execute("CREATE INDEX idx_journal_signal_run ON journal_signal(strategy_run_id)")

    # journal_trade
    op.execute("""
        CREATE TABLE journal_trade (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            strategy_id UUID NULL REFERENCES journal_strategy(id) ON DELETE SET NULL,
            signal_id UUID NULL REFERENCES journal_signal(id) ON DELETE SET NULL,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('long', 'short')),
            qty NUMERIC NOT NULL CHECK (qty > 0),
            entry_px NUMERIC NOT NULL CHECK (entry_px > 0),
            exit_px NUMERIC NULL CHECK (exit_px IS NULL OR exit_px > 0),
            entry_at TIMESTAMPTZ NOT NULL,
            exit_at TIMESTAMPTZ NULL,
            stop_px NUMERIC NULL,
            target_px NUMERIC NULL,
            pnl NUMERIC NULL,
            pnl_pct NUMERIC NULL,
            mae NUMERIC NULL,
            mfe NUMERIC NULL,
            regime_at_entry TEXT NULL,
            regime_at_exit TEXT NULL,
            notes TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_journal_trade_ticker ON journal_trade(ticker)")
    op.execute("CREATE INDEX idx_journal_trade_strategy_entry ON journal_trade(strategy_id, entry_at)")
    op.execute("CREATE INDEX idx_journal_trade_open ON journal_trade(exit_at) WHERE exit_at IS NULL")

    # journal_market_regime
    op.execute("""
        CREATE TABLE journal_market_regime (
            date DATE PRIMARY KEY,
            regime TEXT NOT NULL CHECK (regime IN ('bull', 'bear', 'sideways', 'high_vol')),
            confidence NUMERIC NULL,
            by_sector JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)

    # journal_coach_report
    op.execute("""
        CREATE TABLE journal_coach_report (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            strategy_id UUID NULL REFERENCES journal_strategy(id) ON DELETE SET NULL,
            bundle JSONB NOT NULL,
            report_md TEXT NOT NULL,
            metrics JSONB NOT NULL,
            model_id TEXT NOT NULL,
            prompt_tokens INT NULL,
            completion_tokens INT NULL,
            duration_ms INT NULL
        )
    """)
    op.execute("CREATE INDEX idx_journal_coach_report_generated_at ON journal_coach_report(generated_at DESC)")


def downgrade() -> None:
    """Drop tables in reverse FK order."""
    op.execute("DROP TABLE IF EXISTS journal_coach_report")
    op.execute("DROP TABLE IF EXISTS journal_market_regime")
    op.execute("DROP TABLE IF EXISTS journal_trade")
    op.execute("DROP TABLE IF EXISTS journal_signal")
    op.execute("DROP TABLE IF EXISTS journal_strategy_run")
    op.execute("DROP TABLE IF EXISTS journal_strategy")
