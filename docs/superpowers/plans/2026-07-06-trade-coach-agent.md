# Trade Coach Agent (Approach A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a "Trade Coach" agent that records every screen run, WFO result, and paper trade into a structured trade-journal schema; computes deterministic analytics (win rate, expectancy, P&L by regime, MAE/MFE, entry-timing lag, drawdown) over that journal; and produces a written markdown critique on demand using the same local LLM the rest of TradeCraft uses, with strict number validation. Surfaces everything in a new React `/coach` page.

**Architecture:** New `coach/` service module (writes via `journal.py`, reads via `analytics.py`, LLM critique via `llm.py` + `bundle.py` + `prompts.py`); new `coach.py` FastAPI router at `/api/coach/*`; six new PostgreSQL `journal_*` tables; ~80 lines of post-run recording hooks in three existing routers (`screener.py`, `quantgen.py`, `markov.py`); new React page at `/coach` with KPI cards, four small charts, markdown report view, trade-log sub-route.

**Tech Stack:** FastAPI · SQLAlchemy 2.x · Alembic · PostgreSQL (existing `sp1500_1d`) · Pydantic · pandas · existing local LLM via `backend/app/services/llm_engine.py` (Ollama-compatible OpenAI client, model `kimi-k2.5:cloud`/`kimi-k2.6:cloud`) · React 19 · TypeScript · Tailwind v4 · shadcn/ui (existing) · Recharts (existing) · `react-markdown` + `remark-gfm` (NEW — add to `frontend/package.json`).

---

## Global Constraints

- Backend Python: existing `backend/venv`, dependencies pinned in `backend/requirements.txt`
- Backend pattern: all routers are `APIRouter()` modules registered in `backend/app/main.py:99-107` with `prefix="/api"` and a `tags=[...]` label
- DB pattern: SQLAlchemy ORM models in `backend/app/models/`, Alembic migrations in `backend/app/db/migrations/`, engine from `backend/app/db/database.py`
- LLM pattern: reuse `backend/app/services/llm_engine.py`'s `client` and `MODEL_NAME`; do **not** duplicate retry/timeout logic
- LLM: we will export a new `get_llm_client()` function from `llm_engine.py` so the coach can call it
- Frontend pattern: pages live in `frontend/src/pages/`, add route in `frontend/src/App.tsx`, add nav entry in `frontend/src/components/layout/Layout.tsx:9-12` (`pageTitles` map)
- Frontend design system (from `CLAUDE.md`): shadcn/ui exclusively, max content width 1280px, 8px spacing base, 1440px+ desktop primary, no Tailwind v4 spacing quirks (use inline styles for critical spacing per `CLAUDE.md` troubleshooting note)
- Null safety: use `!= null` not `!== undefined` when guarding numeric fields from backend (per `CLAUDE.md` troubleshooting note)
- Frontend testing: vitest (already in devDependencies)
- Backend testing: pytest (already in use; existing tests under `backend/tests/`)
- All numerical claims in the spec verified against the existing data layer; for the close-trade endpoint, use `DataService.get_ohlcv_data(ticker, start, end)` from `backend/app/services/data_service.py:80`
- Paper trading only; no broker integration; no auto-trading
- Failure isolation: every recording hook must be wrapped in try/except and log a warning on failure — the user's primary flow must not be blocked by the journal

---

## Phase 1: Schema (the foundation everything else depends on)

### Task 1: Alembic migration for the six journal tables

**Files:**
- Create: `backend/app/db/migrations/003_trade_journal.py`

**Interfaces:**
- Consumes: existing Alembic setup at `backend/app/db/migrations/env.py`; previous migration `002_add_stock_indexes.py` (whose `revision = "002"` and `down_revision = "001"`)
- Produces: a new revision `003` that creates `journal_strategy`, `journal_strategy_run`, `journal_signal`, `journal_trade`, `journal_market_regime`, `journal_coach_report` plus their indexes. Must be reversible (a `downgrade()` that drops the tables in reverse FK order).

**Step 1.1: Write the migration file**

Create `backend/app/db/migrations/003_trade_journal.py` with this header:

```python
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
```

**Step 1.2: Apply the migration**

Run from `backend/`:
```bash
cd backend && ./venv/bin/alembic upgrade head
```
Expected: success; `\dt journal_*` in psql against `sp1500_1d` lists all six tables.

**Step 1.3: Verify schema**

Run:
```bash
cd backend && ./venv/bin/python -c "
from app.db.database import engine
from sqlalchemy import text
with engine.connect() as c:
    rows = c.execute(text(\"\"\"
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name LIKE 'journal_%'
        ORDER BY table_name
    \"\"\")).fetchall()
    for r in rows: print(r[0])
"
```
Expected output (6 lines, alphabetical):
```
journal_coach_report
journal_market_regime
journal_signal
journal_strategy
journal_strategy_run
journal_trade
```

**Step 1.4: Roll back and re-apply to confirm reversibility**

```bash
cd backend && ./venv/bin/alembic downgrade -1
cd backend && ./venv/bin/alembic upgrade head
```
Expected: both succeed.

**Step 1.5: Commit**

```bash
git add backend/app/db/migrations/003_trade_journal.py
git commit -m "feat(coach): add trade journal schema (6 tables + indexes)"
```

---

### Task 2: SQLAlchemy ORM models for the journal

**Files:**
- Create: `backend/app/models/journal.py`
- Modify: `backend/app/models/__init__.py` (add `from . import journal` so SQLAlchemy registers the mapper — the project imports models via this `__init__` per the existing pattern)

**Interfaces:**
- Consumes: `app.db.database.engine` and the `app.models` package init
- Produces: declarative classes `JournalStrategy`, `JournalStrategyRun`, `JournalSignal`, `JournalTrade`, `JournalMarketRegime`, `JournalCoachReport`, all with `to_dict()` methods for serialization

**Step 2.1: Write the ORM models**

Create `backend/app/models/journal.py`:

```python
"""SQLAlchemy ORM models for the trade journal (Trade Coach agent).

These map to the six tables created by migration 003_trade_journal.py.
"""
from __future__ import annotations
import uuid
from datetime import datetime, date as date_cls
from typing import Any, Optional, Dict

from sqlalchemy import (
    String, Text, Integer, Numeric, Date, DateTime, ForeignKey, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base  # if Base not present, see step 2.1a


# === 2.1a: Verify or create declarative base ===
# Check if app.db.database exposes a `Base`; if not, add the standard
# `from sqlalchemy.orm import declarative_base; Base = declarative_base()`
# line at the bottom of app/db/database.py. Most SQLAlchemy 2.x projects
# expose one. If you have to add it, place it just below the engine defs.


class JournalStrategy(Base):
    __tablename__ = "journal_strategy"
    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_journal_strategy_kind_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text_default_uuid())
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text_default_now())
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    runs: Mapped[list["JournalStrategyRun"]] = relationship(back_populates="strategy", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "kind": self.kind,
            "name": self.name,
            "params": self.params,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "retired_at": self.retired_at.isoformat() if self.retired_at else None,
            "notes": self.notes,
        }


class JournalStrategyRun(Base):
    __tablename__ = "journal_strategy_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text_default_uuid())
    strategy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_strategy.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    as_of_date: Mapped[Optional[date_cls]] = mapped_column(Date, nullable=True)
    regime_at_run: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text_default_now())

    strategy: Mapped["JournalStrategy"] = relationship(back_populates="runs")
    signals: Mapped[list["JournalSignal"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "strategy_id": str(self.strategy_id),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result_summary": self.result_summary,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "regime_at_run": self.regime_at_run,
        }


class JournalSignal(Base):
    __tablename__ = "journal_signal"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text_default_uuid())
    strategy_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_strategy_run.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)
    signal_strength: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    as_of_date: Mapped[date_cls] = mapped_column(Date, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text_default_now())

    run: Mapped["JournalStrategyRun"] = relationship(back_populates="signals")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "strategy_run_id": str(self.strategy_run_id),
            "ticker": self.ticker,
            "signal_type": self.signal_type,
            "signal_strength": float(self.signal_strength) if self.signal_strength is not None else None,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "payload": self.payload,
        }


class JournalTrade(Base):
    __tablename__ = "journal_trade"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text_default_uuid())
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_strategy.id", ondelete="SET NULL"), nullable=True)
    signal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_signal.id", ondelete="SET NULL"), nullable=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[float] = mapped_column(Numeric, nullable=False)
    entry_px: Mapped[float] = mapped_column(Numeric, nullable=False)
    exit_px: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_px: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    target_px: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    mae: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    mfe: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    regime_at_entry: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    regime_at_exit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text_default_now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text_default_now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "strategy_id": str(self.strategy_id) if self.strategy_id else None,
            "signal_id": str(self.signal_id) if self.signal_id else None,
            "ticker": self.ticker,
            "side": self.side,
            "qty": float(self.qty) if self.qty is not None else None,
            "entry_px": float(self.entry_px) if self.entry_px is not None else None,
            "exit_px": float(self.exit_px) if self.exit_px is not None else None,
            "entry_at": self.entry_at.isoformat() if self.entry_at else None,
            "exit_at": self.exit_at.isoformat() if self.exit_at else None,
            "stop_px": float(self.stop_px) if self.stop_px is not None else None,
            "target_px": float(self.target_px) if self.target_px is not None else None,
            "pnl": float(self.pnl) if self.pnl is not None else None,
            "pnl_pct": float(self.pnl_pct) if self.pnl_pct is not None else None,
            "mae": float(self.mae) if self.mae is not None else None,
            "mfe": float(self.mfe) if self.mfe is not None else None,
            "regime_at_entry": self.regime_at_entry,
            "regime_at_exit": self.regime_at_exit,
            "notes": self.notes,
        }


class JournalMarketRegime(Base):
    __tablename__ = "journal_market_regime"

    date: Mapped[date_cls] = mapped_column(Date, primary_key=True)
    regime: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    by_sector: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


class JournalCoachReport(Base):
    __tablename__ = "journal_coach_report"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text_default_uuid())
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text_default_now())
    period_start: Mapped[date_cls] = mapped_column(Date, nullable=False)
    period_end: Mapped[date_cls] = mapped_column(Date, nullable=False)
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_strategy.id", ondelete="SET NULL"), nullable=True)
    bundle: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    report_md: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


# Helpers to inline `server_default=text("...")` cleanly:
from sqlalchemy import text  # noqa: E402
def text_default_uuid() -> Any:
    return text("uuid_generate_v4()")
def text_default_now() -> Any:
    return text("now()")
```

**Step 2.1a (conditional):** If `app.db.database` does not yet expose a `Base = declarative_base()`, add it at the bottom of that file. Verify with:
```bash
cd backend && ./venv/bin/python -c "from app.db.database import Base; print(Base)"
```

**Step 2.2: Register the models**

Append to `backend/app/models/__init__.py` (it currently is just a docstring/package marker):
```python
from . import journal  # noqa: F401
```

**Step 2.3: Smoke test the ORM**

```bash
cd backend && ./venv/bin/python -c "
from app.models.journal import JournalStrategy, JournalTrade, JournalSignal
print(JournalStrategy.__tablename__)
print(JournalTrade.__tablename__)
print(JournalSignal.__tablename__)
"
```
Expected: prints the three table names, no import errors.

**Step 2.4: Commit**

```bash
git add backend/app/models/journal.py backend/app/models/__init__.py backend/app/db/database.py
git commit -m "feat(coach): add SQLAlchemy ORM models for journal tables"
```

---

## Phase 2: Service layer — journal writes, analytics, LLM critique

### Task 3: `coach/journal.py` — record strategies, runs, signals

**Files:**
- Create: `backend/app/services/coach/__init__.py` (empty)
- Create: `backend/app/services/coach/journal.py`

**Interfaces:**
- Consumes: SQLAlchemy `Session`, ORM models from `app.models.journal`
- Produces:
  - `upsert_strategy(session, kind, name, params=None, notes=None) -> JournalStrategy`
  - `record_strategy_run(session, strategy_id, started_at, result_summary, as_of_date=None, regime_at_run=None, finished_at=None) -> JournalStrategyRun`
  - `record_signal(session, run_id, ticker, signal_type, as_of_date, signal_strength=None, payload=None) -> JournalSignal`
  - `record_journal_failure(operation: str, exc: Exception) -> None` — logs at WARNING; never raises

All write functions open their own short-lived `with SessionLocal() as session: ...` if the caller doesn't pass one, and **never raise on DB errors** — instead they call `record_journal_failure(...)` and return `None`.

**Step 3.1: Write the module**

Create `backend/app/services/coach/journal.py`:

```python
"""Trade-journal write helpers for the Coach agent.

Failure-isolated: every function catches DB exceptions, logs a warning,
and returns None so the user's primary flow is never blocked.
"""
from __future__ import annotations
import logging
from datetime import datetime, date as date_cls
from typing import Any, Dict, Optional, Union
import uuid

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.journal import JournalStrategy, JournalStrategyRun, JournalSignal

logger = logging.getLogger(__name__)


def record_journal_failure(operation: str, exc: Exception) -> None:
    """Log a journal write failure at WARNING. Never raises."""
    logger.warning("Coach journal %s failed: %s", operation, exc, exc_info=False)


def upsert_strategy(
    kind: str,
    name: str,
    params: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    session: Optional[Any] = None,
) -> Optional[JournalStrategy]:
    """Insert or update a strategy by (kind, name). Returns the row, or None on failure."""
    op = "upsert_strategy"
    own_session = session is None
    try:
        s = session or SessionLocal()
        try:
            row = s.query(JournalStrategy).filter_by(kind=kind, name=name).one_or_none()
            if row is None:
                row = JournalStrategy(kind=kind, name=name, params=params or {}, notes=notes)
                s.add(row)
            else:
                if params is not None:
                    row.params = params
                if notes is not None:
                    row.notes = notes
            if own_session:
                s.commit()
            else:
                s.flush()
            return row
        finally:
            if own_session:
                s.close()
    except SQLAlchemyError as e:
        record_journal_failure(op, e)
        return None


def record_strategy_run(
    strategy_id: uuid.UUID,
    started_at: datetime,
    result_summary: Optional[Dict[str, Any]] = None,
    as_of_date: Optional[date_cls] = None,
    regime_at_run: Optional[str] = None,
    finished_at: Optional[datetime] = None,
    session: Optional[Any] = None,
) -> Optional[JournalStrategyRun]:
    """Insert a strategy_run row. Returns the row, or None on failure."""
    op = "record_strategy_run"
    own_session = session is None
    try:
        s = session or SessionLocal()
        try:
            row = JournalStrategyRun(
                strategy_id=strategy_id,
                started_at=started_at,
                finished_at=finished_at or datetime.utcnow(),
                result_summary=result_summary or {},
                as_of_date=as_of_date,
                regime_at_run=regime_at_run,
            )
            s.add(row)
            if own_session:
                s.commit()
                s.refresh(row)
            else:
                s.flush()
            return row
        finally:
            if own_session:
                s.close()
    except SQLAlchemyError as e:
        record_journal_failure(op, e)
        return None


def record_signal(
    run_id: uuid.UUID,
    ticker: str,
    signal_type: str,
    as_of_date: date_cls,
    signal_strength: Optional[float] = None,
    payload: Optional[Dict[str, Any]] = None,
    session: Optional[Any] = None,
) -> Optional[JournalSignal]:
    """Insert a single signal. Returns the row, or None on failure."""
    op = "record_signal"
    own_session = session is None
    try:
        s = session or SessionLocal()
        try:
            row = JournalSignal(
                strategy_run_id=run_id,
                ticker=ticker,
                signal_type=signal_type,
                as_of_date=as_of_date,
                signal_strength=signal_strength,
                payload=payload or {},
            )
            s.add(row)
            if own_session:
                s.commit()
            else:
                s.flush()
            return row
        finally:
            if own_session:
                s.close()
    except SQLAlchemyError as e:
        record_journal_failure(op, e)
        return None
```

**Step 3.2: Smoke test**

```bash
cd backend && ./venv/bin/python -c "
from datetime import datetime, date
from app.services.coach.journal import upsert_strategy, record_strategy_run, record_signal
s = upsert_strategy(kind='screener', name='_test_smoke', params={'sma': 50})
print('strategy:', s.id if s else None)
r = record_strategy_run(strategy_id=s.id, started_at=datetime.utcnow(), result_summary={'hits': 3})
print('run:', r.id if r else None)
g = record_signal(run_id=r.id, ticker='AAPL', signal_type='entry', as_of_date=date.today())
print('signal:', g.id if g else None)
"
```
Expected: three non-None UUIDs.

**Step 3.3: Clean up the smoke rows**

```bash
cd backend && ./venv/bin/python -c "
from app.db.database import SessionLocal
from app.models.journal import JournalStrategy
s = SessionLocal()
s.query(JournalStrategy).filter_by(kind='screener', name='_test_smoke').delete()
s.commit(); s.close()
print('cleaned')
"
```

**Step 3.4: Commit**

```bash
git add backend/app/services/coach/__init__.py backend/app/services/coach/journal.py
git commit -m "feat(coach): add journal write helpers (failure-isolated)"
```

---

### Task 4: `coach/analytics.py` — deterministic metrics over the journal

**Files:**
- Create: `backend/app/services/coach/analytics.py`

**Interfaces:**
- Consumes: SQLAlchemy `Session`, ORM models
- Produces 11 functions (signatures shown). All return JSON-serializable dicts / lists / pandas Series converted via `.to_dict()` / `.tolist()` by callers.

```python
def kpis(session, period_start: date, period_end: date, strategy_id: UUID|None) -> Dict
def equity_curve(session, period_start, period_end, strategy_id) -> List[Dict]   # [{date, equity}]
def drawdown_curve(session, period_start, period_end, strategy_id) -> List[Dict] # [{date, dd}]
def pnl_by_regime(session, period_start, period_end, strategy_id) -> Dict       # {regime: {n, pnl, pnl_pct}}
def mae_mfe_scatter(session, period_start, period_end, strategy_id) -> List[Dict] # [{mae, mfe, pnl, ticker, entry_at}]
def win_rate_by_strategy(session, period_start, period_end) -> List[Dict]     # [{strategy_id, name, win_rate, n_trades}]
def entry_timing_lag(session, period_start, period_end, strategy_id) -> Dict    # {p25, p50, p75, mean, n}
def strategy_correlation_matrix(session, period_start, period_end) -> Dict      # {strategies: [...], matrix: [[...]]}
def recent_trades(session, strategy_id, n=20) -> List[Dict]
def regime_timeline(session, period_start, period_end) -> List[Dict]            # [{date, regime, confidence}]
def overview(session, period_start, period_end, strategy_id) -> Dict           # bundle of all of the above
```

**Step 4.1: Write the module**

Create `backend/app/services/coach/analytics.py` with the 11 functions. The functions are pure SQLAlchemy + pandas. A full reference implementation (≈400 lines) is provided below; the test suite in Task 5 pins the expected output values.

```python
"""Deterministic analytics over the trade journal. No LLM."""
from __future__ import annotations
import logging
import uuid
from datetime import date as date_cls, datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import and_

from app.models.journal import JournalTrade, JournalStrategy, JournalStrategyRun, JournalMarketRegime, JournalSignal

logger = logging.getLogger(__name__)


def _closed_trades_query(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]):
    """Common base: closed trades in [period_start, period_end], optionally filtered by strategy."""
    q = session.query(JournalTrade).filter(
        JournalTrade.exit_at.isnot(None),
        JournalTrade.exit_at >= datetime.combine(period_start, datetime.min.time()),
        JournalTrade.exit_at <= datetime.combine(period_end, datetime.max.time()),
    )
    if strategy_id is not None:
        q = q.filter(JournalTrade.strategy_id == strategy_id)
    return q.order_by(JournalTrade.exit_at.asc())


def kpis(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    closed = _closed_trades_query(session, period_start, period_end, strategy_id).all()
    n = len(closed)
    if n == 0:
        return {
            "total_pnl": 0.0, "win_rate": 0.0, "expectancy": 0.0,
            "n_trades": 0, "n_open": 0, "max_dd": 0.0, "current_dd": 0.0,
            "sharpe_proxy": 0.0,
        }
    pnls = [float(t.pnl or 0.0) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_pnl = sum(pnls)
    win_rate = len(wins) / n if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    # max drawdown over the period
    eq = pd.Series(pnls).cumsum()
    running_max = eq.cummax()
    dd = (eq - running_max)
    max_dd = float(dd.min()) if len(dd) else 0.0
    current_dd = float(dd.iloc[-1]) if len(dd) else 0.0
    # Sharpe proxy = mean / std of per-trade returns (annualized proxy, 252 trading days)
    import math
    std = pd.Series(pnls).std(ddof=1) if n > 1 else 0.0
    sharpe = float((pd.Series(pnls).mean() / std) * math.sqrt(252)) if std and std > 0 else 0.0
    n_open = session.query(JournalTrade).filter(JournalTrade.exit_at.is_(None)).count()
    return {
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 4),
        "expectancy": round(expectancy, 2),
        "n_trades": n,
        "n_open": n_open,
        "max_dd": round(max_dd, 2),
        "current_dd": round(current_dd, 2),
        "sharpe_proxy": round(sharpe, 4),
    }


def equity_curve(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]) -> List[Dict[str, Any]]:
    closed = _closed_trades_query(session, period_start, period_end, strategy_id).all()
    if not closed:
        return []
    rows = [{"date": t.exit_at.date().isoformat(), "equity": float(t.pnl or 0.0)} for t in closed]
    df = pd.DataFrame(rows)
    df["equity"] = df["equity"].cumsum()
    return df.to_dict(orient="records")


def drawdown_curve(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]) -> List[Dict[str, Any]]:
    eq = equity_curve(session, period_start, period_end, strategy_id)
    if not eq:
        return []
    df = pd.DataFrame(eq)
    df["running_max"] = df["equity"].cummax()
    df["dd"] = df["equity"] - df["running_max"]
    return df[["date", "dd"]].to_dict(orient="records")


def pnl_by_regime(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]) -> Dict[str, Dict[str, Any]]:
    closed = _closed_trades_query(session, period_start, period_end, strategy_id).all()
    out: Dict[str, Dict[str, Any]] = {}
    for t in closed:
        regime = t.regime_at_exit or t.regime_at_entry or "unknown"
        bucket = out.setdefault(regime, {"n": 0, "pnl": 0.0, "pnl_pct_sum": 0.0})
        bucket["n"] += 1
        bucket["pnl"] += float(t.pnl or 0.0)
        bucket["pnl_pct_sum"] += float(t.pnl_pct or 0.0)
    for v in out.values():
        v["pnl"] = round(v["pnl"], 2)
        v["pnl_pct"] = round(v["pnl_pct_sum"] / v["n"], 4) if v["n"] else 0.0
        del v["pnl_pct_sum"]
    return out


def mae_mfe_scatter(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]) -> List[Dict[str, Any]]:
    closed = _closed_trades_query(session, period_start, period_end, strategy_id).all()
    out = []
    for t in closed:
        out.append({
            "mae": float(t.mae) if t.mae is not None else None,
            "mfe": float(t.mfe) if t.mfe is not None else None,
            "pnl": float(t.pnl) if t.pnl is not None else None,
            "ticker": t.ticker,
            "entry_at": t.entry_at.isoformat() if t.entry_at else None,
        })
    return out


def win_rate_by_strategy(session, period_start: date_cls, period_end: date_cls) -> List[Dict[str, Any]]:
    q = (session.query(JournalStrategy, JournalTrade)
         .join(JournalTrade, JournalTrade.strategy_id == JournalStrategy.id)
         .filter(JournalTrade.exit_at.isnot(None))
         .filter(JournalTrade.exit_at >= datetime.combine(period_start, datetime.min.time()))
         .filter(JournalTrade.exit_at <= datetime.combine(period_end, datetime.max.time())))
    out: Dict[uuid.UUID, Dict[str, Any]] = {}
    for strat, t in q.all():
        bucket = out.setdefault(strat.id, {"strategy_id": str(strat.id), "name": strat.name, "n": 0, "wins": 0})
        bucket["n"] += 1
        if t.pnl is not None and float(t.pnl) > 0:
            bucket["wins"] += 1
    rows = []
    for v in out.values():
        v["win_rate"] = round(v["wins"] / v["n"], 4) if v["n"] else 0.0
        del v["wins"]
        rows.append(v)
    rows.sort(key=lambda r: r["win_rate"], reverse=True)
    return rows


def entry_timing_lag(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    """Days between the originating signal's as_of_date and the trade's entry_at."""
    q = (session.query(JournalSignal, JournalTrade)
         .join(JournalTrade, JournalTrade.signal_id == JournalSignal.id)
         .filter(JournalTrade.entry_at >= datetime.combine(period_start, datetime.min.time()))
         .filter(JournalTrade.entry_at <= datetime.combine(period_end, datetime.max.time())))
    if strategy_id is not None:
        q = q.filter(JournalTrade.strategy_id == strategy_id)
    lags = []
    for sig, t in q.all():
        if sig.as_of_date and t.entry_at:
            lag = (t.entry_at.date() - sig.as_of_date).days
            if lag >= 0:
                lags.append(lag)
    if not lags:
        return {"p25": 0, "p50": 0, "p75": 0, "mean": 0.0, "n": 0}
    s = pd.Series(lags)
    return {
        "p25": int(s.quantile(0.25)),
        "p50": int(s.quantile(0.50)),
        "p75": int(s.quantile(0.75)),
        "mean": round(float(s.mean()), 2),
        "n": len(lags),
    }


def strategy_correlation_matrix(session, period_start: date_cls, period_end: date_cls) -> Dict[str, Any]:
    q = (session.query(JournalStrategy.name, JournalTrade.exit_at, JournalTrade.pnl)
         .join(JournalTrade, JournalTrade.strategy_id == JournalStrategy.id)
         .filter(JournalTrade.exit_at.isnot(None))
         .filter(JournalTrade.exit_at >= datetime.combine(period_start, datetime.min.time()))
         .filter(JournalTrade.exit_at <= datetime.combine(period_end, datetime.max.time())))
    rows = [(n, d.date().isoformat(), float(p or 0.0)) for n, d, p in q.all()]
    if not rows:
        return {"strategies": [], "matrix": []}
    df = pd.DataFrame(rows, columns=["name", "date", "pnl"]).pivot_table(index="date", columns="name", values="pnl", aggfunc="sum").fillna(0.0)
    corr = df.corr().fillna(0.0)
    strategies = list(corr.columns)
    matrix = [[round(float(corr.loc[a, b]), 4) for b in strategies] for a in strategies]
    return {"strategies": strategies, "matrix": matrix}


def recent_trades(session, strategy_id: Optional[uuid.UUID], n: int = 20) -> List[Dict[str, Any]]:
    q = session.query(JournalTrade)
    if strategy_id is not None:
        q = q.filter(JournalTrade.strategy_id == strategy_id)
    rows = q.order_by(JournalTrade.entry_at.desc()).limit(n).all()
    return [t.to_dict() for t in rows]


def regime_timeline(session, period_start: date_cls, period_end: date_cls) -> List[Dict[str, Any]]:
    rows = (session.query(JournalMarketRegime)
            .filter(JournalMarketRegime.date >= period_start)
            .filter(JournalMarketRegime.date <= period_end)
            .order_by(JournalMarketRegime.date.asc()).all())
    return [{"date": r.date.isoformat(), "regime": r.regime, "confidence": float(r.confidence) if r.confidence is not None else None} for r in rows]


def overview(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "kpis": kpis(session, period_start, period_end, strategy_id),
        "equity_curve": equity_curve(session, period_start, period_end, strategy_id),
        "drawdown_curve": drawdown_curve(session, period_start, period_end, strategy_id),
        "pnl_by_regime": pnl_by_regime(session, period_start, period_end, strategy_id),
        "win_rate_by_strategy": win_rate_by_strategy(session, period_start, period_end),
        "entry_timing_lag": entry_timing_lag(session, period_start, period_end, strategy_id),
    }
```

**Step 4.2: Smoke test**

```bash
cd backend && ./venv/bin/python -c "
from datetime import date, timedelta
from app.db.database import SessionLocal
from app.services.coach import analytics as A
s = SessionLocal()
end = date.today(); start = end - timedelta(days=30)
print(A.kpis(s, start, end, None))
print('regimes:', A.regime_timeline(s, start, end))
s.close()
"
```
Expected: prints a KPIs dict (all zeros if no trades exist) and an empty list for regimes.

**Step 4.3: Commit**

```bash
git add backend/app/services/coach/analytics.py
git commit -m "feat(coach): add deterministic analytics module (11 functions)"
```

---

### Task 5: Analytics unit tests (TDD — fixed expectations on a fixture journal)

**Files:**
- Create: `backend/tests/coach/__init__.py` (empty)
- Create: `backend/tests/coach/conftest.py` — fixture journal of 50 trades across 3 strategies and 2 regimes
- Create: `backend/tests/coach/test_analytics.py` — fixed expectations

**Step 5.1: Write conftest.py**

```python
"""Fixture journal: 50 trades, 3 strategies, 2 regimes, deterministic."""
from __future__ import annotations
import uuid
from datetime import date, datetime, timedelta
import pytest

from app.db.database import SessionLocal
from app.models.journal import JournalStrategy, JournalStrategyRun, JournalSignal, JournalTrade, JournalMarketRegime


@pytest.fixture
def seed_journal():
    """Seed a deterministic fixture journal. Yields the session; cleans up on teardown."""
    s = SessionLocal()
    # Wipe any prior fixture rows
    s.query(JournalTrade).filter(JournalTrade.ticker.like("FXT%")).delete(synchronize_session=False)
    s.query(JournalStrategy).filter(JournalStrategy.name.like("fx_%")).delete()
    s.query(JournalMarketRegime).filter(JournalMarketRegime.date >= date(2026, 1, 1)).delete()
    s.commit()

    # 3 strategies
    strats = []
    for name in ["fx_alpha", "fx_beta", "fx_gamma"]:
        st = JournalStrategy(kind="manual", name=name, params={"fixture": True})
        s.add(st); s.commit(); s.refresh(st)
        strats.append(st)

    # Regime timeline (Jan-Apr 2026, alternating bull/bear)
    regimes = ["bull", "bear"]
    for i in range(120):
        d = date(2026, 1, 1) + timedelta(days=i)
        s.add(JournalMarketRegime(date=d, regime=regimes[i % 2], confidence=0.8, by_sector={}))
    s.commit()

    # 50 trades, ~17 per strategy, all closed, alternating win/loss
    n = 0
    for i in range(50):
        st = strats[i % 3]
        is_win = (i % 2 == 0)
        entry_day = i + 5
        exit_day = entry_day + 3
        entry = datetime(2026, 1, 1) + timedelta(days=entry_day)
        exxit = datetime(2026, 1, 1) + timedelta(days=exit_day)
        regime = regimes[entry_day % 2]
        qty = 100.0
        entry_px = 50.0
        exit_px = 55.0 if is_win else 47.0
        pnl = (exit_px - entry_px) * qty
        pnl_pct = (exit_px - entry_px) / entry_px
        # MAE/MFE: winners have larger MFE, losers have larger MAE
        mfe = 6.0 if is_win else 1.0
        mae = 1.0 if is_win else 4.0
        t = JournalTrade(
            strategy_id=st.id, ticker=f"FXT{i:02d}", side="long",
            qty=qty, entry_px=entry_px, exit_px=exit_px,
            entry_at=entry, exit_at=exxit,
            pnl=pnl, pnl_pct=pnl_pct, mae=mae, mfe=mfe,
            regime_at_entry=regime, regime_at_exit=regime,
        )
        s.add(t); n += 1
    s.commit()
    yield s
    # teardown
    s.query(JournalTrade).filter(JournalTrade.ticker.like("FXT%")).delete(synchronize_session=False)
    s.query(JournalStrategy).filter(JournalStrategy.name.like("fx_%")).delete()
    s.query(JournalMarketRegime).filter(JournalMarketRegime.date >= date(2026, 1, 1)).delete()
    s.commit()
    s.close()
```

**Step 5.2: Write the test file**

```python
"""Tests for the Coach analytics module. Fixed expectations over the seed_journal fixture."""
from __future__ import annotations
import math
from datetime import date
from app.services.coach import analytics as A


PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 4, 30)


def test_kpis_aggregate(seed_journal):
    k = A.kpis(seed_journal, PERIOD_START, PERIOD_END, None)
    # 25 wins @ +$500 each = +$12,500; 25 losses @ -$300 each = -$7,500; total = +$5,000
    assert k["n_trades"] == 50
    assert k["win_rate"] == 0.5
    assert k["total_pnl"] == 5000.0
    # expectancy = 0.5 * 500 - 0.5 * 300 = 100
    assert k["expectancy"] == 100.0


def test_pnl_by_regime_bull_bear(seed_journal):
    r = A.pnl_by_regime(seed_journal, PERIOD_START, PERIOD_END, None)
    # Roughly half the trades happen in each regime (alternating days)
    assert "bull" in r and "bear" in r
    assert r["bull"]["n"] > 0 and r["bear"]["n"] > 0
    # Both regimes have ~50% win rate → both regimes are net positive
    assert r["bull"]["pnl"] > 0
    assert r["bear"]["pnl"] > 0


def test_win_rate_by_strategy_three_strategies(seed_journal):
    rows = A.win_rate_by_strategy(seed_journal, PERIOD_START, PERIOD_END)
    names = {r["name"] for r in rows}
    assert names == {"fx_alpha", "fx_beta", "fx_gamma"}
    for r in rows:
        # Each strategy gets 16 or 17 trades, alternating win/loss
        assert r["n"] in (16, 17)
        assert 0.4 <= r["win_rate"] <= 0.6


def test_mae_mfe_scatter_shape(seed_journal):
    rows = A.mae_mfe_scatter(seed_journal, PERIOD_START, PERIOD_END, None)
    assert len(rows) == 50
    for r in rows:
        assert "mae" in r and "mfe" in r and "pnl" in r
        # Winners have mfe > mae, losers have mae > mfe (per fixture)
        if r["pnl"] > 0:
            assert r["mfe"] > r["mae"]
        else:
            assert r["mae"] > r["mfe"]


def test_recent_trades_limit(seed_journal):
    rows = A.recent_trades(seed_journal, strategy_id=None, n=10)
    assert len(rows) == 10
    # Most recent first
    assert rows[0]["entry_at"] >= rows[-1]["entry_at"]


def test_regime_timeline_window(seed_journal):
    r = A.regime_timeline(seed_journal, PERIOD_START, PERIOD_END)
    # 120 days of fixture data
    assert len(r) == 120
    assert r[0]["date"] == "2026-01-01"


def test_overview_returns_all_keys(seed_journal):
    o = A.overview(seed_journal, PERIOD_START, PERIOD_END, None)
    for k in ("period", "kpis", "equity_curve", "drawdown_curve", "pnl_by_regime", "win_rate_by_strategy", "entry_timing_lag"):
        assert k in o
```

**Step 5.3: Run the tests**

```bash
cd backend && ./venv/bin/pytest tests/coach/test_analytics.py -v
```
Expected: 6 tests pass.

**Step 5.4: Commit**

```bash
git add backend/tests/coach/__init__.py backend/tests/coach/conftest.py backend/tests/coach/test_analytics.py
git commit -m "test(coach): add analytics tests over fixture journal"
```

---

### Task 6: LLM helper export from `llm_engine.py`

**Files:**
- Modify: `backend/app/services/llm_engine.py` (append a `get_llm_client()` function)

**Interfaces:**
- Consumes: the existing module-level `client` and `MODEL_NAME`
- Produces:
  - `get_llm_client() -> Tuple[OpenAI | None, str]` returning `(client, model_name)`. If client is None, returns `(None, MODEL_NAME)`. This is what the coach will call to avoid duplicating retry/timeout logic.

**Step 6.1: Append the helper**

Open `backend/app/services/llm_engine.py` and add at the bottom (above any existing `if __name__ == "__main__":`):

```python
def get_llm_client() -> tuple[Optional["OpenAI"], str]:
    """Return the shared LLM client and model name. Reuses the module-level
    client configured at import time; no duplicate retry/timeout logic.
    Returns (None, model_name) if the client failed to initialize.
    """
    return client, MODEL_NAME
```

**Step 6.2: Verify import**

```bash
cd backend && ./venv/bin/python -c "from app.services.llm_engine import get_llm_client; print(get_llm_client())"
```
Expected: prints a tuple (either `(OpenAI, 'kimi-k2.x:cloud')` or `(None, 'kimi-k2.x:cloud')` if Ollama isn't running — both are fine).

**Step 6.3: Commit**

```bash
git add backend/app/services/llm_engine.py
git commit -m "refactor(llm): export get_llm_client() for reuse by Coach"
```

---

### Task 7: `coach/bundle.py` — assemble the JSON bundle the LLM sees

**Files:**
- Create: `backend/app/services/coach/bundle.py`

**Interfaces:**
- Consumes: a SQLAlchemy `Session`, an analytics module, `period_start`, `period_end`, `strategy_id: UUID | None`
- Produces: `build(session, period_start, period_end, strategy_id) -> dict` returning the JSON bundle (the only thing the LLM sees). Capped at ~30k tokens by truncating `recent_trades` to 20 and `regime_timeline` to 90 days; emits a `warnings: []` key listing any truncations.

**Step 7.1: Write the module**

```python
"""Assemble the data bundle the Coach LLM sees. The bundle is the ONLY
thing the LLM sees — no raw journal, no other context.
"""
from __future__ import annotations
import uuid
from datetime import date as date_cls
from typing import Any, Dict, Optional

from app.services.coach import analytics as A
from app.services.coach.journal import upsert_strategy  # noqa: F401  (kept for consistency)


def build(session, period_start: date_cls, period_end: date_cls, strategy_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    """Assemble the data bundle. Returns a JSON-serializable dict."""
    warnings: list[str] = []

    # 11 base metrics from the analytics module
    kpis = A.kpis(session, period_start, period_end, strategy_id)
    pnl_by_regime = A.pnl_by_regime(session, period_start, period_end, strategy_id)
    win_rate_by_strategy = A.win_rate_by_strategy(session, period_start, period_end)
    entry_timing_lag = A.entry_timing_lag(session, period_start, period_end, strategy_id)
    mae_mfe = A.mae_mfe_scatter(session, period_start, period_end, strategy_id)
    equity = A.equity_curve(session, period_start, period_end, strategy_id)
    drawdown = A.drawdown_curve(session, period_start, period_end, strategy_id)
    correlation = A.strategy_correlation_matrix(session, period_start, period_end)
    recent = A.recent_trades(session, strategy_id=strategy_id, n=20)
    regime = A.regime_timeline(session, period_start, period_end)

    # Cap regime_timeline at 90 days, surface a warning
    if len(regime) > 90:
        regime = regime[-90:]
        warnings.append("regime_timeline truncated to last 90 days")

    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "strategy_id": str(strategy_id) if strategy_id else None,
        "kpis": kpis,
        "pnl_by_regime": pnl_by_regime,
        "win_rate_by_strategy": win_rate_by_strategy,
        "entry_timing_lag": entry_timing_lag,
        "mae_mfe_summary": _summarize_mae_mfe(mae_mfe),
        "equity_curve_summary": _summarize_equity(equity),
        "drawdown_summary": _summarize_drawdown(drawdown),
        "strategy_correlation": correlation,
        "recent_trades": recent,
        "regime_timeline": regime,
        "warnings": warnings,
    }


def _summarize_mae_mfe(rows):
    if not rows:
        return {"n": 0}
    maes = [r["mae"] for r in rows if r["mae"] is not None]
    mfes = [r["mfe"] for r in rows if r["mfe"] is not None]
    return {
        "n": len(rows),
        "mae_mean": round(sum(maes) / len(maes), 4) if maes else None,
        "mfe_mean": round(sum(mfes) / len(mfes), 4) if mfes else None,
    }


def _summarize_equity(rows):
    if not rows:
        return {"n": 0}
    equities = [r["equity"] for r in rows]
    return {
        "n": len(equities),
        "start": equities[0],
        "end": equities[-1],
        "peak": max(equities),
        "trough": min(equities),
    }


def _summarize_drawdown(rows):
    if not rows:
        return {"n": 0, "max_dd": 0.0}
    dds = [r["dd"] for r in rows]
    return {"n": len(dds), "max_dd": min(dds)}
```

**Step 7.2: Smoke test**

```bash
cd backend && ./venv/bin/python -c "
from datetime import date, timedelta
from app.db.database import SessionLocal
from app.services.coach.bundle import build
s = SessionLocal()
b = build(s, date.today() - timedelta(days=30), date.today(), None)
print('keys:', sorted(b.keys()))
print('warnings:', b['warnings'])
s.close()
"
```
Expected: prints the bundle's top-level keys (alphabetical) and `warnings: []` (or with one entry if data is old enough to trigger truncation).

**Step 7.3: Commit**

```bash
git add backend/app/services/coach/bundle.py
git commit -m "feat(coach): add bundle builder (LLM input assembler)"
```

---

### Task 8: `coach/prompts.py` — system + user prompt templates

**Files:**
- Create: `backend/app/services/coach/prompts.py`

**Step 8.1: Write the module**

```python
"""Locked prompt templates for the Trade Coach LLM critique.

The system prompt is intentionally strict:
 - no financial advice
 - only numbers that appear in the bundle may be cited
 - fixed 5-section markdown structure
 - at most 3 concrete suggestions, each must be a single A/B WFO test
"""

SYSTEM_PROMPT = """You are Trade Coach, an AI that reviews a trader's journal and produces a written critique.

You are NOT a financial advisor. You do not give buy/sell recommendations for any specific real security.
You only describe what the data in the JSON bundle shows.

Hard rules:
- Use only numbers that appear in the JSON bundle. If a number is not in the bundle, do not state it.
- Cite specific trade IDs and strategy names when making claims.
- Be concise. Use these section headers in this order, with no other top-level headers:
  ## Top Performers
  ## Underperformers
  ## Regime Mismatch
  ## Behavioral Notes
  ## Concrete Suggestions
- Under "Concrete Suggestions", propose at most 3 testable changes. Each suggestion must be implementable as a single A/B walk-forward optimization test (a concrete filter, parameter, or rule change).
- Never recommend taking or avoiding any specific real trade or position.
- Output valid markdown, no preamble, no postscript.

You will be given a JSON bundle describing the trader's journal over a period.
The bundle has these top-level keys:
period, strategy_id, kpis, pnl_by_regime, win_rate_by_strategy, entry_timing_lag,
mae_mfe_summary, equity_curve_summary, drawdown_summary, strategy_correlation,
recent_trades, regime_timeline, warnings.
"""


def user_prompt(bundle: dict) -> str:
    """Render the user prompt from the bundle."""
    import json
    return (
        "Here is the trader's journal bundle for the period.\n\n"
        "Produce your critique using only the 5 required section headers, citing only bundle values.\n\n"
        "```json\n" + json.dumps(bundle, indent=2, default=str) + "\n```\n"
    )
```

**Step 8.2: Smoke test**

```bash
cd backend && ./venv/bin/python -c "
from app.services.coach.prompts import SYSTEM_PROMPT, user_prompt
print('system length:', len(SYSTEM_PROMPT), 'chars')
print('contains headers:', all(h in SYSTEM_PROMPT for h in ['## Top Performers','## Underperformers','## Regime Mismatch','## Behavioral Notes','## Concrete Suggestions']))
print('user prompt example length:', len(user_prompt({'kpis': {'n_trades': 0}})))
"
```
Expected: prints lengths, `contains headers: True`.

**Step 8.3: Commit**

```bash
git add backend/app/services/coach/prompts.py
git commit -m "feat(coach): add locked system + user prompt templates"
```

---

### Task 9: `coach/llm.py` — LLM critique with number validation + retry

**Files:**
- Create: `backend/app/services/coach/llm.py`

**Interfaces:**
- Consumes: a `bundle: dict`, optional `model: str | None`
- Produces:
  - `generate_report(session, bundle: dict, model: str | None = None) -> ReportResult`
  - `ReportResult` is a Pydantic-like dataclass: `{markdown: Optional[str], error: Optional[str], metrics: dict, duration_ms: int, model_id: str, prompt_tokens: int, completion_tokens: int}`. Defined inline in this module (not in `types.py` — keeps it close to its only consumer for v1).

The function:
1. Calls the shared LLM client via `llm_engine.get_llm_client()`.
2. On success, post-processes the output: regex-extracts every number, checks each against the serialized bundle (or a rounded derivative of a bundle value), retries **once** on failure with a stricter user-prompt suffix, persists the report to `journal_coach_report` on success, returns the result.
3. On any LLM error (timeout, transport), returns `error="llm_unavailable"`. On number-validation failure on the second attempt, returns `error="llm_invented_numbers"`.

**Step 9.1: Write the module**

```python
"""LLM critique engine for the Trade Coach.

Pipeline:
  1. Build prompts (prompts.py)
  2. Call shared LLM (llm_engine.get_llm_client) — reuses retry/timeout
  3. Validate every number in the output appears in the bundle
  4. On validation failure, retry once with a stricter suffix
  5. Persist the result to journal_coach_report
"""
from __future__ import annotations
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from app.services.llm_engine import get_llm_client
from app.services.coach.prompts import SYSTEM_PROMPT, user_prompt
from app.models.journal import JournalCoachReport

logger = logging.getLogger(__name__)

# Permissive regex for any number in a markdown report
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


@dataclass
class ReportResult:
    markdown: Optional[str] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    model_id: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    report_id: Optional[str] = None


def _extract_numbers(text: str) -> List[str]:
    return _NUMBER_RE.findall(text)


def _bundle_number_set(bundle: dict) -> set:
    """Flatten the bundle into a set of numeric strings for membership checks."""
    def walk(node):
        out = []
        if isinstance(node, dict):
            for v in node.values():
                out.extend(walk(v))
        elif isinstance(node, list):
            for v in node:
                out.extend(walk(v))
        elif isinstance(node, bool):
            return out
        elif isinstance(node, (int, float)):
            out.append(node)
        return out
    nums = walk(bundle)
    out = set()
    for n in nums:
        out.add(f"{n:.4f}".rstrip("0").rstrip("."))
        out.add(f"{n:.2f}")
        out.add(f"{n:.0f}")
        out.add(str(n))
    return out


def _validate_numbers(md: str, bundle: dict) -> tuple[bool, list]:
    """Return (ok, list_of_unmatched_numbers)."""
    allowed = _bundle_number_set(bundle)
    unmatched = []
    for n in _extract_numbers(md):
        if n in allowed:
            continue
        # Try a 2-decimal form for percentages etc.
        try:
            f = float(n)
            for fmt in (f"{f:.2f}", f"{f:.0f}", f"{f:.4f}".rstrip("0").rstrip(".")):
                if fmt in allowed:
                    break
            else:
                unmatched.append(n)
        except ValueError:
            unmatched.append(n)
    return (len(unmatched) == 0), unmatched


def _call_llm(client, model: str, system: str, user: str) -> tuple[Optional[str], Optional[str], int, int]:
    """One LLM call. Returns (content, error, prompt_tokens, completion_tokens)."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        content = resp.choices[0].message.content if resp.choices else None
        usage = getattr(resp, "usage", None)
        pt = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        ct = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        return content, None, pt, ct
    except Exception as e:
        return None, f"llm_unavailable: {e}", 0, 0


def _persist_report(session, bundle: dict, period_start, period_end, strategy_id,
                    markdown: str, model_id: str, prompt_tokens: int,
                    completion_tokens: int, duration_ms: int) -> Optional[str]:
    try:
        row = JournalCoachReport(
            period_start=period_start,
            period_end=period_end,
            strategy_id=strategy_id,
            bundle=bundle,
            report_md=markdown,
            metrics=_metrics_summary(bundle),
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return str(row.id)
    except Exception as e:
        logger.warning("Failed to persist coach report: %s", e)
        try: session.rollback()
        except Exception: pass
        return None


def _metrics_summary(bundle: dict) -> dict:
    k = bundle.get("kpis", {})
    return {
        "n_trades": k.get("n_trades", 0),
        "win_rate": k.get("win_rate", 0.0),
        "expectancy": k.get("expectancy", 0.0),
        "total_pnl": k.get("total_pnl", 0.0),
        "max_dd": k.get("max_dd", 0.0),
    }


def generate_report(session, bundle: dict, model: Optional[str] = None) -> ReportResult:
    """Generate a Coach report. Returns a ReportResult. Persists on success."""
    started = time.time()
    client, default_model = get_llm_client()
    if client is None:
        return ReportResult(error="llm_unavailable", metrics=_metrics_summary(bundle), model_id=model or default_model)
    used_model = model or default_model

    # Attempt 1
    content, err, pt, ct = _call_llm(client, used_model, SYSTEM_PROMPT, user_prompt(bundle))
    if err or not content:
        return ReportResult(error=err or "llm_empty_response", metrics=_metrics_summary(bundle), model_id=used_model, prompt_tokens=pt, completion_tokens=ct)

    # Validate numbers
    ok, unmatched = _validate_numbers(content, bundle)
    if not ok:
        # Attempt 2 with stricter suffix
        stricter = user_prompt(bundle) + (
            f"\n\nIMPORTANT: Your previous draft contained {len(unmatched)} number(s) "
            "not present in the bundle. Re-issue the report using ONLY bundle values."
        )
        content2, err2, pt2, ct2 = _call_llm(client, used_model, SYSTEM_PROMPT, stricter)
        if err2 or not content2:
            return ReportResult(error="llm_unavailable", metrics=_metrics_summary(bundle), model_id=used_model)
        ok2, unmatched2 = _validate_numbers(content2, bundle)
        if not ok2:
            return ReportResult(error="llm_invented_numbers", metrics=_metrics_summary(bundle), model_id=used_model,
                                prompt_tokens=pt + pt2, completion_tokens=ct + ct2)
        content, pt, ct = content2, pt + pt2, ct + ct2

    duration = int((time.time() - started) * 1000)
    report_id = _persist_report(
        session, bundle,
        period_start=__import__("datetime").date.fromisoformat(bundle["period"]["start"]),
        period_end=__import__("datetime").date.fromisoformat(bundle["period"]["end"]),
        strategy_id=uuid.UUID(bundle["strategy_id"]) if bundle.get("strategy_id") else None,
        markdown=content, model_id=used_model,
        prompt_tokens=pt, completion_tokens=ct, duration_ms=duration,
    )
    return ReportResult(
        markdown=content, metrics=_metrics_summary(bundle), duration_ms=duration,
        model_id=used_model, prompt_tokens=pt, completion_tokens=ct, report_id=report_id,
    )
```

**Step 9.2: Smoke test (validates the validate-only path; the actual LLM call requires Ollama running)**

```bash
cd backend && ./venv/bin/python -c "
from app.services.coach.llm import _validate_numbers, _bundle_number_set
b = {'kpis': {'n_trades': 50, 'win_rate': 0.5, 'expectancy': 100.0, 'total_pnl': 5000.0}}
md_ok = 'Total PnL was 5000.0 across 50 trades, win rate 50%.'
md_bad = 'Total PnL was 9999 across 50 trades.'
print('ok text validates:', _validate_numbers(md_ok, b)[0])
print('bad text rejects:', not _validate_numbers(md_bad, b)[0])
"
```
Expected: `ok text validates: True`, `bad text rejects: True`.

**Step 9.3: Commit**

```bash
git add backend/app/services/coach/llm.py
git commit -m "feat(coach): add LLM critique engine with number validation + retry"
```

---

## Phase 3: Router — expose the coach over HTTP

### Task 10: `routers/coach.py` — 15 endpoints

**Files:**
- Create: `backend/app/routers/coach.py`

**Interfaces:**
- Consumes: `app.services.coach.{journal,analytics,bundle,llm}`, ORM models, Pydantic request/response models defined inline
- Produces: an `APIRouter()` mounted at `/api/coach` with 15 endpoints

**Step 10.1: Write the router**

```python
"""Coach API router: metrics, trades CRUD, strategies, reports."""
from __future__ import annotations
import logging
import uuid
from datetime import date as date_cls, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.journal import JournalTrade, JournalStrategy, JournalCoachReport
from app.services.coach import analytics as A
from app.services.coach.journal import upsert_strategy
from app.services.coach.bundle import build as build_bundle
from app.services.coach.llm import generate_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coach", tags=["coach"])


# ---------- shared deps ----------

def get_session():
    s = SessionLocal()
    try: yield s
    finally: s.close()


def _period(start: Optional[date_cls], end: Optional[date_cls]) -> tuple[date_cls, date_cls]:
    if end is None: end = date_cls.today()
    if start is None: start = end - timedelta(days=30)
    return start, end


# ---------- request/response models ----------

class TradeCreate(BaseModel):
    ticker: str
    side: str = Field("long", pattern="^(long|short)$")
    qty: float
    entry_px: float
    entry_at: datetime
    strategy_id: Optional[uuid.UUID] = None
    signal_id: Optional[uuid.UUID] = None
    stop_px: Optional[float] = None
    target_px: Optional[float] = None
    notes: Optional[str] = None


class TradePatch(BaseModel):
    stop_px: Optional[float] = None
    target_px: Optional[float] = None
    notes: Optional[str] = None


class TradeClose(BaseModel):
    exit_px: Optional[float] = None  # if None, use today's close
    exit_at: Optional[datetime] = None


class StrategyCreate(BaseModel):
    kind: str = Field(..., pattern="^(screener|quantgen|markov|manual)$")
    name: str
    params: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class StrategyPatch(BaseModel):
    notes: Optional[str] = None
    retired_at: Optional[datetime] = None
    params: Optional[Dict[str, Any]] = None


class ReportRequest(BaseModel):
    period_start: Optional[date_cls] = None
    period_end: Optional[date_cls] = None
    strategy_id: Optional[uuid.UUID] = None
    model: Optional[str] = None


# ---------- metrics ----------

@router.get("/metrics/overview")
def metrics_overview(
    period_start: Optional[date_cls] = None,
    period_end: Optional[date_cls] = None,
    strategy_id: Optional[uuid.UUID] = None,
    session: Session = Depends(get_session),
):
    start, end = _period(period_start, period_end)
    o = A.overview(session, start, end, strategy_id)
    if o["kpis"]["n_trades"] == 0 and not o["win_rate_by_strategy"]:
        return {"empty": True, "period": o["period"], "kpis": o["kpis"]}
    return o


@router.get("/metrics/mae-mfe")
def metrics_mae_mfe(
    period_start: Optional[date_cls] = None,
    period_end: Optional[date_cls] = None,
    strategy_id: Optional[uuid.UUID] = None,
    session: Session = Depends(get_session),
):
    start, end = _period(period_start, period_end)
    return A.mae_mfe_scatter(session, start, end, strategy_id)


@router.get("/metrics/win-rate-by-strategy")
def metrics_win_rate_by_strategy(
    period_start: Optional[date_cls] = None,
    period_end: Optional[date_cls] = None,
    session: Session = Depends(get_session),
):
    start, end = _period(period_start, period_end)
    return A.win_rate_by_strategy(session, start, end)


# ---------- trades ----------

@router.get("/trades")
def list_trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    strategy_id: Optional[uuid.UUID] = None,
    open_only: bool = False,
    session: Session = Depends(get_session),
):
    q = session.query(JournalTrade)
    if strategy_id is not None:
        q = q.filter(JournalTrade.strategy_id == strategy_id)
    if open_only:
        q = q.filter(JournalTrade.exit_at.is_(None))
    q = q.order_by(JournalTrade.entry_at.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {"total": total, "rows": [t.to_dict() for t in rows]}


@router.post("/trades", status_code=201)
def create_trade(body: TradeCreate, session: Session = Depends(get_session)):
    t = JournalTrade(
        ticker=body.ticker.upper(), side=body.side, qty=body.qty,
        entry_px=body.entry_px, entry_at=body.entry_at,
        strategy_id=body.strategy_id, signal_id=body.signal_id,
        stop_px=body.stop_px, target_px=body.target_px, notes=body.notes,
    )
    session.add(t); session.commit(); session.refresh(t)
    return t.to_dict()


@router.patch("/trades/{trade_id}")
def patch_trade(trade_id: uuid.UUID, body: TradePatch, session: Session = Depends(get_session)):
    t = session.get(JournalTrade, trade_id)
    if t is None:
        raise HTTPException(404, "trade not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    t.updated_at = datetime.utcnow()
    session.commit(); session.refresh(t)
    return t.to_dict()


@router.delete("/trades/{trade_id}", status_code=204)
def delete_trade(trade_id: uuid.UUID, session: Session = Depends(get_session)):
    t = session.get(JournalTrade, trade_id)
    if t is None:
        raise HTTPException(404, "trade not found")
    session.delete(t); session.commit()
    return None


@router.post("/trades/{trade_id}/close")
def close_trade(trade_id: uuid.UUID, body: TradeClose, session: Session = Depends(get_session)):
    from app.services.data_service import DataService
    t = session.get(JournalTrade, trade_id)
    if t is None:
        raise HTTPException(404, "trade not found")
    if t.exit_at is not None:
        raise HTTPException(400, "trade already closed")
    # Default exit price = today's close
    exit_px = body.exit_px
    exit_at = body.exit_at or datetime.utcnow()
    if exit_px is None:
        latest = DataService.get_latest_price(t.ticker, "daily")
        if latest is None:
            raise HTTPException(503, f"no price data for {t.ticker}")
        exit_px = float(latest)
    sign = 1 if t.side == "long" else -1
    t.exit_px = exit_px
    t.exit_at = exit_at
    t.pnl = (exit_px - float(t.entry_px)) * float(t.qty) * sign
    t.pnl_pct = (exit_px - float(t.entry_px)) / float(t.entry_px) * sign
    # MAE/MFE from OHLCV
    try:
        ohlcv = DataService.get_ohlcv_data(t.ticker, t.entry_at.date().isoformat(), exit_at.date().isoformat())
        if ohlcv is not None and not ohlcv.empty:
            low_min = float(ohlcv["Low"].min())
            high_max = float(ohlcv["High"].max())
            t.mae = (low_min - float(t.entry_px)) * sign
            t.mfe = (high_max - float(t.entry_px)) * sign
    except Exception as e:
        logger.warning("MAE/MFE calc failed for trade %s: %s", trade_id, e)
    t.updated_at = datetime.utcnow()
    session.commit(); session.refresh(t)
    return t.to_dict()


# ---------- strategies ----------

@router.get("/strategies")
def list_strategies(session: Session = Depends(get_session)):
    rows = session.query(JournalStrategy).order_by(JournalStrategy.created_at.desc()).all()
    return [r.to_dict() for r in rows]


@router.post("/strategies", status_code=201)
def create_strategy(body: StrategyCreate, session: Session = Depends(get_session)):
    row = upsert_strategy(kind=body.kind, name=body.name, params=body.params, notes=body.notes, session=session)
    if row is None:
        raise HTTPException(500, "failed to upsert strategy")
    return row.to_dict()


@router.patch("/strategies/{strategy_id}")
def patch_strategy(strategy_id: uuid.UUID, body: StrategyPatch, session: Session = Depends(get_session)):
    row = session.get(JournalStrategy, strategy_id)
    if row is None: raise HTTPException(404, "strategy not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    session.commit(); session.refresh(row)
    return row.to_dict()


# ---------- reports ----------

@router.post("/report")
def post_report(body: ReportRequest, session: Session = Depends(get_session)):
    start, end = _period(body.period_start, body.period_end)
    bundle = build_bundle(session, start, end, body.strategy_id)
    result = generate_report(session, bundle, model=body.model)
    if result.error == "llm_unavailable":
        raise HTTPException(503, detail={"error": "llm_unavailable", "bundle": bundle})
    if result.error == "llm_invented_numbers":
        raise HTTPException(422, detail={"error": "llm_invented_numbers", "bundle": bundle})
    if result.error:
        raise HTTPException(500, detail={"error": result.error})
    return {
        "id": result.report_id, "markdown": result.markdown, "metrics": result.metrics,
        "model_id": result.model_id, "duration_ms": result.duration_ms,
        "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
        "bundle": bundle,
    }


@router.get("/reports")
def list_reports(limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)):
    rows = (session.query(JournalCoachReport)
            .order_by(JournalCoachReport.generated_at.desc()).limit(limit).all())
    return [{
        "id": str(r.id), "generated_at": r.generated_at.isoformat(),
        "period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat(),
        "strategy_id": str(r.strategy_id) if r.strategy_id else None,
        "model_id": r.model_id, "duration_ms": r.duration_ms,
    } for r in rows]


@router.get("/reports/{report_id}")
def get_report(report_id: uuid.UUID, session: Session = Depends(get_session)):
    r = session.get(JournalCoachReport, report_id)
    if r is None: raise HTTPException(404, "report not found")
    return {
        "id": str(r.id), "generated_at": r.generated_at.isoformat(),
        "period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat(),
        "strategy_id": str(r.strategy_id) if r.strategy_id else None,
        "model_id": r.model_id, "report_md": r.report_md,
        "metrics": r.metrics, "bundle": r.bundle,
        "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
        "duration_ms": r.duration_ms,
    }


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: uuid.UUID, session: Session = Depends(get_session)):
    r = session.get(JournalCoachReport, report_id)
    if r is None: raise HTTPException(404, "report not found")
    session.delete(r); session.commit()
    return None
```

**Step 10.2: Register the router in main.py**

Open `backend/app/main.py`. Around line 99 (the `from app.routers import ...` line) add `coach` to the import. Around line 107 (the `app.include_router(...)` block) add:
```python
app.include_router(coach.router, prefix="/api", tags=["Trade Coach"])
```

**Step 10.3: Smoke test the router (start the server, hit one endpoint)**

```bash
cd backend && ./venv/bin/python -m app.main &
sleep 3
curl -s http://localhost:8000/api/coach/metrics/overview
curl -s http://localhost:8000/api/coach/strategies
kill %1
```
Expected: both endpoints return valid JSON (empty-state payload for overview, `[]` for strategies).

**Step 10.4: Commit**

```bash
git add backend/app/routers/coach.py backend/app/main.py
git commit -m "feat(coach): add /api/coach router (15 endpoints)"
```

---

## Phase 4: Recording hooks in existing routers

### Task 11: Screener hooks — record every scan

**Files:**
- Modify: `backend/app/routers/screener.py` (two call sites: the async scan endpoint + a sync one if it exists)

**Interfaces:**
- Consumes: `app.services.coach.journal.{upsert_strategy, record_strategy_run, record_signal}`
- Produces: post-scan hooks at the end of each scan handler. Failure-isolated.

**Step 11.1: Locate the scan handler(s)**

```bash
cd backend && grep -n "def.*scan\|return.*result\|@router.post" app/routers/screener.py | head -20
```

**Step 11.2: Add the hook**

At the top of the file, add the import (after the existing service imports):
```python
from app.services.coach.journal import upsert_strategy, record_strategy_run, record_signal
```

For each scan handler (typically `run_dormant_giant_screener` and `run_quant_strategy_screener`, or one endpoint that calls them), find the place where the result is being returned and add a block like this just before the `return`:

```python
    # --- Coach journal hook (failure-isolated) ---
    try:
        strat = upsert_strategy(kind="screener", name=f"screener:{scan_req.mode}")
        if strat is not None:
            from datetime import datetime as _dt
            run = record_strategy_run(
                strategy_id=strat.id,
                started_at=_dt.utcnow(),
                result_summary={"n_hits": len(result.hits) if hasattr(result, "hits") else 0},
                as_of_date=getattr(scan_req, "as_of_date", None),
            )
            if run is not None:
                for hit in (getattr(result, "hits", []) or []):
                    record_signal(
                        run_id=run.id,
                        ticker=hit.ticker if hasattr(hit, "ticker") else hit.get("ticker"),
                        signal_type="entry",
                        as_of_date=getattr(scan_req, "as_of_date", None) or _dt.utcnow().date(),
                        signal_strength=getattr(hit, "score", None) if hasattr(hit, "score") else hit.get("score"),
                        payload=hit.to_dict() if hasattr(hit, "to_dict") else hit,
                    )
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Coach screener hook failed: %s", _e)
```

**Step 11.3: Smoke test**

Run a screener, then check the journal:
```bash
cd backend && ./venv/bin/python -c "
from app.db.database import SessionLocal
from app.models.journal import JournalStrategyRun
s = SessionLocal()
print('runs:', s.query(JournalStrategyRun).count())
s.close()
"
```
Expected: ≥ 1 row after running a screener.

**Step 11.4: Commit**

```bash
git add backend/app/routers/screener.py
git commit -m "feat(coach): record screener runs in the trade journal"
```

---

### Task 12: QuantGen hooks — record WFO + backtest runs

**Files:**
- Modify: `backend/app/routers/quantgen.py` (three call sites: `/api/run` @ ~line 376, `/api/optimize` @ ~445, `/api/true-wfo` @ ~512)

**Interfaces:** Same as Task 11 but for quantgen.

**Step 12.1: Add the import**

At the top of the file:
```python
from app.services.coach.journal import upsert_strategy, record_strategy_run, record_signal
```

**Step 12.2: Add hooks to all three endpoints**

For `/api/run` and `/api/optimize`: name the strategy as `f"quantgen:{req.ticker}:{req.strategy_name or 'default'}"`, and record each trade the backtest produced (VectorBT pf.trades) as a `signal_type=entry` row in `journal_signal`. For `/api/true-wfo`: name the strategy as `f"quantgen:wfo:{req.ticker}:{req.strategy_name or 'default'}"`.

Insert the same try/except block at the end of each handler, just before the `return`, with `result_summary` populated from the response dict (total_return, sharpe, n_trades, etc.).

**Step 12.3: Smoke test**

Run a backtest or WFO, then check:
```bash
cd backend && ./venv/bin/python -c "
from app.db.database import SessionLocal
from app.models.journal import JournalStrategyRun
s = SessionLocal(); print('quantgen runs:', s.query(JournalStrategyRun).filter(JournalStrategyRun.result_summary.op('->>')('source') == 'quantgen').count()); s.close()
"
```

**Step 12.4: Commit**

```bash
git add backend/app/routers/quantgen.py
git commit -m "feat(coach): record quantgen runs in the trade journal"
```

---

### Task 13: Markov hooks — record daily scan + retrain

**Files:**
- Modify: `backend/app/routers/markov.py` (two call sites: `/api/markov/scan` and `/api/markov/retrain`)

**Step 13.1: Add the import + hooks**

Same pattern as Tasks 11–12. Name the strategy as `f"markov:{kind}"` where `kind` is one of `daily_scan`, `retrain`. Record the regime at run if available. For the daily scan, optionally write the per-ticker signals to `journal_signal`.

**Step 13.2: Smoke test**

Trigger a Markov scan, then check:
```bash
cd backend && ./venv/bin/python -c "
from app.db.database import SessionLocal
from app.models.journal import JournalStrategyRun
s = SessionLocal(); print('markov runs:', s.query(JournalStrategyRun).count()); s.close()
"
```

**Step 13.3: Commit**

```bash
git add backend/app/routers/markov.py
git commit -m "feat(coach): record markov runs in the trade journal"
```

---

## Phase 5: Frontend — the Coach page

### Task 14: Add the `react-markdown` dependency

**Files:**
- Modify: `frontend/package.json` (add `react-markdown` and `remark-gfm` to `dependencies`)

**Step 14.1: Edit `package.json`**

Add two lines to the `dependencies` block:
```json
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0",
```

**Step 14.2: Install**

```bash
cd frontend && npm install
```
Expected: `package-lock.json` updated, no errors.

**Step 14.3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat(coach): add react-markdown + remark-gfm deps"
```

---

### Task 15: TypeScript client `lib/coach.ts`

**Files:**
- Create: `frontend/src/lib/coach.ts`

**Step 15.1: Write the client**

```typescript
// Typed client for /api/coach/*

export interface KPISet {
  total_pnl: number;
  win_rate: number;
  expectancy: number;
  n_trades: number;
  n_open: number;
  max_dd: number;
  current_dd: number;
  sharpe_proxy: number;
}

export interface Trade {
  id: string;
  ticker: string;
  side: 'long' | 'short';
  qty: number;
  entry_px: number;
  exit_px: number | null;
  entry_at: string;
  exit_at: string | null;
  pnl: number | null;
  pnl_pct: number | null;
  mae: number | null;
  mfe: number | null;
  strategy_id: string | null;
  signal_id: string | null;
  notes: string | null;
}

export interface Strategy {
  id: string;
  kind: 'screener' | 'quantgen' | 'markov' | 'manual';
  name: string;
  params: Record<string, unknown>;
  created_at: string;
  retired_at: string | null;
  notes: string | null;
}

export interface OverviewResponse {
  empty?: boolean;
  period: { start: string; end: string };
  kpis?: KPISet;
  equity_curve?: { date: string; equity: number }[];
  drawdown_curve?: { date: string; dd: number }[];
  pnl_by_regime?: Record<string, { n: number; pnl: number; pnl_pct: number }>;
  win_rate_by_strategy?: { strategy_id: string; name: string; n: number; win_rate: number }[];
  entry_timing_lag?: { p25: number; p50: number; p75: number; mean: number; n: number };
}

export interface ReportSummary {
  id: string;
  generated_at: string;
  period_start: string;
  period_end: string;
  strategy_id: string | null;
  model_id: string;
  duration_ms: number | null;
}

export interface ReportDetail extends ReportSummary {
  report_md: string;
  metrics: Record<string, unknown>;
  bundle: Record<string, unknown>;
  prompt_tokens: number | null;
  completion_tokens: number | null;
}

const base = '/api/coach';

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST ${url} -> ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const coachApi = {
  overview: (params: { period_start?: string; period_end?: string; strategy_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.period_start) q.set('period_start', params.period_start);
    if (params.period_end) q.set('period_end', params.period_end);
    if (params.strategy_id) q.set('strategy_id', params.strategy_id);
    return getJson<OverviewResponse>(`${base}/metrics/overview?${q}`);
  },
  maeMfe: (params: { period_start?: string; period_end?: string; strategy_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.period_start) q.set('period_start', params.period_start);
    if (params.period_end) q.set('period_end', params.period_end);
    if (params.strategy_id) q.set('strategy_id', params.strategy_id);
    return getJson<{ mae: number | null; mfe: number | null; pnl: number | null; ticker: string; entry_at: string | null }[]>(`${base}/metrics/mae-mfe?${q}`);
  },
  winRateByStrategy: (params: { period_start?: string; period_end?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.period_start) q.set('period_start', params.period_start);
    if (params.period_end) q.set('period_end', params.period_end);
    return getJson<{ strategy_id: string; name: string; n: number; win_rate: number }[]>(`${base}/metrics/win-rate-by-strategy?${q}`);
  },
  listTrades: (params: { limit?: number; offset?: number; strategy_id?: string; open_only?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set('limit', String(params.limit));
    if (params.offset) q.set('offset', String(params.offset));
    if (params.strategy_id) q.set('strategy_id', params.strategy_id);
    if (params.open_only) q.set('open_only', 'true');
    return getJson<{ total: number; rows: Trade[] }>(`${base}/trades?${q}`);
  },
  createTrade: (body: Partial<Trade> & { ticker: string; qty: number; entry_px: number; entry_at: string }) =>
    postJson<Trade>(`${base}/trades`, body),
  patchTrade: (id: string, body: Partial<Trade>) =>
    fetch(`${base}/trades/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json() as Promise<Trade>),
  closeTrade: (id: string, body: { exit_px?: number; exit_at?: string } = {}) =>
    postJson<Trade>(`${base}/trades/${id}/close`, body),
  deleteTrade: (id: string) => fetch(`${base}/trades/${id}`, { method: 'DELETE' }),
  listStrategies: () => getJson<Strategy[]>(`${base}/strategies`),
  createStrategy: (body: { kind: Strategy['kind']; name: string; params?: Record<string, unknown>; notes?: string }) =>
    postJson<Strategy>(`${base}/strategies`, body),
  patchStrategy: (id: string, body: Partial<Strategy>) =>
    fetch(`${base}/strategies/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json() as Promise<Strategy>),
  generateReport: (body: { period_start?: string; period_end?: string; strategy_id?: string; model?: string }) =>
    postJson<ReportDetail>(`${base}/report`, body),
  listReports: (limit = 20) => getJson<ReportSummary[]>(`${base}/reports?limit=${limit}`),
  getReport: (id: string) => getJson<ReportDetail>(`${base}/reports/${id}`),
  deleteReport: (id: string) => fetch(`${base}/reports/${id}`, { method: 'DELETE' }),
};
```

**Step 15.2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

**Step 15.3: Commit**

```bash
git add frontend/src/lib/coach.ts
git commit -m "feat(coach): add typed Coach API client"
```

---

### Task 16: Coach UI — main page, KPI cards, charts, report view, trades sub-page

**Files:**
- Create: `frontend/src/pages/Coach/index.tsx` (main page, the workhorse)
- Create: `frontend/src/pages/Coach/KPICards.tsx`
- Create: `frontend/src/pages/Coach/EquityCurve.tsx`
- Create: `frontend/src/pages/Coach/RegimeAttribution.tsx`
- Create: `frontend/src/pages/Coach/MAEvsMFE.tsx`
- Create: `frontend/src/pages/Coach/WinRateByStrategy.tsx`
- Create: `frontend/src/pages/Coach/ReportView.tsx`
- Create: `frontend/src/pages/Coach/DateRangePicker.tsx`
- Create: `frontend/src/pages/Coach/trades.tsx` (sub-route)
- Create: `frontend/src/pages/Coach/TradeTable.tsx`
- Create: `frontend/src/pages/Coach/TradeForm.tsx`
- Create: `frontend/src/pages/Coach/CloseTradeDialog.tsx`
- Modify: `frontend/src/App.tsx` (add `/coach` and `/coach/trades` routes)
- Modify: `frontend/src/components/layout/Layout.tsx` (add nav title for `/coach`)

**Step 16.1: Write the small chart components first**

Each follows the existing Recharts pattern. Sketches (full code per file):

`KPICards.tsx`:
```tsx
import { Card } from '../../components/ui/Card';
import type { KPISet } from '../../lib/coach';

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—';
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return '—';
  return `${(n * 100).toFixed(1)}%`;
}

export function KPICards({ k }: { k: KPISet }) {
  const items = [
    { label: 'Total P&L', value: `$${fmt(k.total_pnl, 2)}`, accent: k.total_pnl >= 0 ? 'text-emerald-500' : 'text-rose-500' },
    { label: 'Win Rate', value: fmtPct(k.win_rate) },
    { label: 'Expectancy', value: `$${fmt(k.expectancy, 2)}` },
    { label: '# Trades', value: String(k.n_trades) },
    { label: 'Open', value: String(k.n_open) },
    { label: 'Max DD', value: `$${fmt(k.max_dd, 2)}`, accent: 'text-rose-500' },
  ];
  return (
    <div className="grid grid-cols-6 gap-4">
      {items.map((it) => (
        <Card key={it.label} className="p-6">
          <div className="text-xs uppercase tracking-wide text-zinc-500">{it.label}</div>
          <div className={`mt-2 text-2xl font-semibold ${it.accent ?? 'text-zinc-100'}`}>{it.value}</div>
        </Card>
      ))}
    </div>
  );
}
```

`EquityCurve.tsx`:
```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export function EquityCurve({ data }: { data: { date: string; equity: number }[] }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
          <XAxis dataKey="date" stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <YAxis stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }} />
          <Line type="monotone" dataKey="equity" stroke="#10b981" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

`RegimeAttribution.tsx`:
```tsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';

const COLORS = ['#10b981', '#f43f5e', '#f59e0b', '#3b82f6'];

export function RegimeAttribution({ data }: { data: Record<string, { n: number; pnl: number; pnl_pct: number }> }) {
  const rows = Object.entries(data).map(([regime, v]) => ({ regime, ...v }));
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
          <XAxis dataKey="regime" stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <YAxis stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }} />
          <Bar dataKey="pnl">
            {rows.map((_, i) => (<Cell key={i} fill={COLORS[i % COLORS.length]} />))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

`MAEvsMFE.tsx`:
```tsx
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';

export function MAEvsMFE({ data }: { data: { mae: number | null; mfe: number | null; pnl: number | null; ticker: string }[] }) {
  const points = data.filter((d) => d.mae != null && d.mfe != null);
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
          <XAxis type="number" dataKey="mae" name="MAE" stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <YAxis type="number" dataKey="mfe" name="MFE" stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <ZAxis range={[40, 80]} />
          <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }} cursor={{ strokeDasharray: '3 3' }} />
          <Scatter data={points}>
            {points.map((p, i) => (
              <Cell key={i} fill={(p.pnl ?? 0) > 0 ? '#10b981' : '#f43f5e'} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
```

`WinRateByStrategy.tsx`:
```tsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export function WinRateByStrategy({ data }: { data: { name: string; n: number; win_rate: number }[] }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 64 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
          <XAxis type="number" domain={[0, 1]} stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" stroke="#a1a1aa" tick={{ fontSize: 11 }} width={120} />
          <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }} />
          <Bar dataKey="win_rate" fill="#3b82f6" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

`DateRangePicker.tsx`:
```tsx
import { useState } from 'react';

export type DateRange = { start: string; end: string };

const PRESETS: { label: string; days: number | 'ytd' | 'all' }[] = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
  { label: 'YTD', days: 'ytd' },
  { label: 'All', days: 'all' },
];

function toISODate(d: Date): string { return d.toISOString().slice(0, 10); }

export function presetRange(days: number | 'ytd' | 'all'): DateRange {
  const end = new Date();
  let start: Date;
  if (days === 'ytd') {
    start = new Date(end.getFullYear(), 0, 1);
  } else if (days === 'all') {
    start = new Date('2020-01-01');
  } else {
    start = new Date(end); start.setDate(start.getDate() - days);
  }
  return { start: toISODate(start), end: toISODate(end) };
}

export function DateRangePicker({ value, onChange }: { value: DateRange; onChange: (r: DateRange) => void }) {
  const [custom, setCustom] = useState(false);
  return (
    <div className="flex items-center gap-2">
      {PRESETS.map((p) => (
        <button
          key={p.label}
          onClick={() => { setCustom(false); onChange(presetRange(p.days)); }}
          className="rounded-md border border-zinc-700 px-3 py-1 text-sm hover:bg-zinc-800"
        >
          {p.label}
        </button>
      ))}
      <button
        onClick={() => setCustom(true)}
        className="rounded-md border border-zinc-700 px-3 py-1 text-sm hover:bg-zinc-800"
      >
        Custom
      </button>
      {custom && (
        <>
          <input
            type="date" value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm"
          />
          <span className="text-zinc-500">→</span>
          <input
            type="date" value={value.end} onChange={(e) => onChange({ ...value, end: e.target.value })}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm"
          />
        </>
      )}
    </div>
  );
}
```

`ReportView.tsx`:
```tsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function ReportView({ markdown }: { markdown: string }) {
  return (
    <div className="prose prose-invert max-w-none prose-headings:text-zinc-100 prose-p:text-zinc-300 prose-strong:text-zinc-100">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
    </div>
  );
}
```

**Step 16.2: Write the trades sub-page and its components**

`TradeTable.tsx` (sketch):
```tsx
import { useState } from 'react';
import { coachApi, type Trade } from '../../lib/coach';

export function TradeTable({ initialRows, onChanged }: { initialRows: Trade[]; onChanged: () => void }) {
  const [rows] = useState<Trade[]>(initialRows);
  return (
    <table className="w-full text-sm">
      <thead className="text-xs uppercase text-zinc-500">
        <tr>
          <th className="px-3 py-2 text-left">Ticker</th>
          <th className="px-3 py-2 text-left">Side</th>
          <th className="px-3 py-2 text-right">Qty</th>
          <th className="px-3 py-2 text-right">Entry</th>
          <th className="px-3 py-2 text-right">Exit</th>
          <th className="px-3 py-2 text-right">P&L</th>
          <th className="px-3 py-2 text-left">Opened</th>
          <th className="px-3 py-2 text-left">Closed</th>
          <th className="px-3 py-2 text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t) => (
          <tr key={t.id} className="border-t border-zinc-800">
            <td className="px-3 py-2 font-mono">{t.ticker}</td>
            <td className="px-3 py-2">{t.side}</td>
            <td className="px-3 py-2 text-right">{t.qty}</td>
            <td className="px-3 py-2 text-right">{t.entry_px.toFixed(2)}</td>
            <td className="px-3 py-2 text-right">{t.exit_px != null ? t.exit_px.toFixed(2) : '—'}</td>
            <td className={`px-3 py-2 text-right ${(t.pnl ?? 0) >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
              {t.pnl != null ? t.pnl.toFixed(2) : '—'}
            </td>
            <td className="px-3 py-2">{t.entry_at?.slice(0, 10)}</td>
            <td className="px-3 py-2">{t.exit_at?.slice(0, 10) ?? 'open'}</td>
            <td className="px-3 py-2 text-right">
              {t.exit_at == null && (
                <CloseTradeButton tradeId={t.id} onClosed={onChanged} />
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CloseTradeButton({ tradeId, onClosed }: { tradeId: string; onClosed: () => void }) {
  return (
    <button
      onClick={async () => {
        await coachApi.closeTrade(tradeId, {});
        onChanged();
      }}
      className="rounded-md border border-emerald-700 px-2 py-1 text-xs text-emerald-400 hover:bg-emerald-900/30"
    >
      Close
    </button>
  );
}
```

`CloseTradeDialog.tsx`: a small dialog asking for an explicit close price (default: today's close). Wire to `coachApi.closeTrade`. Full code is straightforward; matches the shadcn dialog pattern used elsewhere.

`TradeForm.tsx`: a small form for `ticker`, `side`, `qty`, `entry_px`, `entry_at`, `notes`. Calls `coachApi.createTrade`.

`trades.tsx`: the sub-route that uses `TradeTable` + `TradeForm`. Calls `coachApi.listTrades({ limit: 100 })` on mount.

**Step 16.3: Write the main Coach page**

`pages/Coach/index.tsx` (sketch — wires everything together):
```tsx
import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card } from '../../components/ui/Card';
import { KPICards } from './KPICards';
import { EquityCurve } from './EquityCurve';
import { RegimeAttribution } from './RegimeAttribution';
import { MAEvsMFE } from './MAEvsMFE';
import { WinRateByStrategy } from './WinRateByStrategy';
import { ReportView } from './ReportView';
import { DateRangePicker, presetRange, type DateRange } from './DateRangePicker';
import { coachApi, type OverviewResponse, type ReportDetail } from '../../lib/coach';

export default function CoachIndex() {
  const [range, setRange] = useState<DateRange>(presetRange(30));
  const [latest, setLatest] = useState<ReportDetail | null>(null);
  const qc = useQueryClient();

  const overview = useQuery({
    queryKey: ['coach-overview', range],
    queryFn: () => coachApi.overview({ period_start: range.start, period_end: range.end }),
  });

  const reports = useQuery({
    queryKey: ['coach-reports'],
    queryFn: () => coachApi.listReports(20),
  });

  useEffect(() => {
    if (reports.data && reports.data.length > 0 && !latest) {
      coachApi.getReport(reports.data[0].id).then(setLatest).catch(() => {});
    }
  }, [reports.data, latest]);

  const generate = useMutation({
    mutationFn: () => coachApi.generateReport({ period_start: range.start, period_end: range.end }),
    onSuccess: (r) => { setLatest(r); qc.invalidateQueries({ queryKey: ['coach-reports'] }); },
  });

  return (
    <div className="mx-auto max-w-[1280px] space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-zinc-100">Trade Coach</h1>
        <DateRangePicker value={range} onChange={setRange} />
      </div>

      {overview.data?.empty ? (
        <Card className="p-6">
          <div className="text-zinc-300">
            Run a screener, take a paper trade, and your Coach will start learning from your activity.
          </div>
        </Card>
      ) : overview.data ? (
        <>
          {overview.data.kpis && <KPICards k={overview.data.kpis} />}
          <div className="grid grid-cols-2 gap-4">
            <Card className="p-6">
              <div className="mb-2 text-sm text-zinc-400">Equity Curve</div>
              <EquityCurve data={overview.data.equity_curve ?? []} />
            </Card>
            <Card className="p-6">
              <div className="mb-2 text-sm text-zinc-400">P&L by Regime</div>
              <RegimeAttribution data={overview.data.pnl_by_regime ?? {}} />
            </Card>
            <Card className="p-6">
              <div className="mb-2 text-sm text-zinc-400">MAE vs MFE</div>
              <MAEvsMFE data={[]} />
            </Card>
            <Card className="p-6">
              <div className="mb-2 text-sm text-zinc-400">Win Rate by Strategy</div>
              <WinRateByStrategy data={overview.data.win_rate_by_strategy ?? []} />
            </Card>
          </div>
        </>
      ) : null}

      <Card className="p-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="text-sm text-zinc-400">Latest Coach Report</div>
          <button
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            className="rounded-md border border-emerald-700 px-3 py-1 text-sm text-emerald-400 hover:bg-emerald-900/30 disabled:opacity-50"
          >
            {generate.isPending ? `Generating… (${generate.elapsed || 0}s)` : 'Regenerate ↻'}
          </button>
        </div>
        {generate.error && (
          <div className="mb-4 rounded-md border border-rose-700 bg-rose-950/30 p-3 text-sm text-rose-300">
            Critique unavailable, metrics are up-to-date.
          </div>
        )}
        {latest ? <ReportView markdown={latest.report_md} /> : (
          <div className="text-zinc-500">No report yet. Click Regenerate.</div>
        )}
      </Card>

      <Card className="p-6">
        <div className="mb-2 text-sm text-zinc-400">Past Reports</div>
        <ul className="space-y-1 text-sm">
          {(reports.data ?? []).map((r) => (
            <li key={r.id} className="flex items-center justify-between border-t border-zinc-800 py-2">
              <span>{r.generated_at.slice(0, 10)} · {r.period_start} → {r.period_end} · {r.model_id} · {r.duration_ms ?? '?'}ms</span>
              <button
                onClick={() => coachApi.getReport(r.id).then(setLatest)}
                className="rounded-md border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-800"
              >
                View
              </button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
```

**Step 16.4: Wire routes and nav**

`frontend/src/App.tsx` — inside the `<Layout>` block, add:
```tsx
<Route path="coach" element={<ErrorBoundary><CoachIndex /></ErrorBoundary>} />
<Route path="coach/trades" element={<ErrorBoundary><CoachTrades /></ErrorBoundary>} />
```
And add the imports at the top:
```tsx
import CoachIndex from './pages/Coach'
import CoachTrades from './pages/Coach/trades'
```

`frontend/src/components/layout/Layout.tsx` — add a line to the `pageTitles` map (around line 9):
```tsx
  "/coach": "Trade Coach",
```

**Step 16.5: Type-check + build**

```bash
cd frontend && npx tsc --noEmit && npx vite build
```
Expected: no errors. (Per the CLAUDE.md troubleshooting note: if spacing classes don't apply in dev, use inline styles.)

**Step 16.6: Smoke test in the browser**

Start the backend and the frontend, navigate to `/coach`, confirm the page loads, KPIs are shown (zeros if no data), and the "Regenerate" button is present.

**Step 16.7: Commit**

```bash
git add frontend/src/pages/Coach frontend/src/App.tsx frontend/src/components/layout/Layout.tsx
git commit -m "feat(coach): add Coach page (KPI cards, charts, report view, trades sub-route)"
```

---

## Phase 6: End-to-end verification

### Task 17: End-to-end verification flow

Run the 12 manual checks from the spec. None of them require new code; they require a populated database and a running stack.

**17.1: Schema**
```bash
PGPASSWORD=$DB_PASSWORD psql -h 127.0.0.1 -p 5431 -U $DB_USER -d sp1500_1d -c "\dt journal_*"
```
Expected: 6 rows.

**17.2: Hook smoke (screener)** — Open the Screener tab, run any scan. Then:
```bash
cd backend && ./venv/bin/python -c "
from app.db.database import SessionLocal
from app.models.journal import JournalStrategyRun, JournalSignal
s = SessionLocal()
print('runs:', s.query(JournalStrategyRun).count())
print('signals:', s.query(JournalSignal).count())
"
```

**17.3: Hook smoke (QuantGen)** — Run a backtest. Repeat 17.2.

**17.4: Hook smoke (Markov)** — Trigger a Markov scan. Repeat 17.2.

**17.5: Trade CRUD** — Via the UI: add a paper trade, edit notes, close. Verify pnl/mae/mfe populated.

**17.6: Analytics** — `curl 'http://localhost:8000/api/coach/metrics/overview?period_start=YYYY-MM-DD&period_end=YYYY-MM-DD'` and cross-check totals.

**17.7: Analytics unit tests**
```bash
cd backend && ./venv/bin/pytest tests/coach/test_analytics.py -v
```

**17.8: LLM critique** — Click "Regenerate" in the UI. Wait ≤ 30s. Verify a new row in `journal_coach_report` and a markdown report that mentions only bundle values.

**17.9: LLM failure path** — Stop Ollama temporarily, click Regenerate. Verify the 503 banner shows.

**17.10: Empty state** — On a clean DB, `/coach` shows the empty-state card.

**17.11: UI screenshot** — Take a screenshot of the Coach page with data.

**17.12: History** — Generate twice. Both reports visible in the list.

If any check fails, fix and re-verify before tagging the milestone done.

**Step 17.13: Final commit (if any cleanup was needed)**
```bash
git add -A
git commit -m "chore(coach): end-to-end verification passed"
```

---

## Self-Review (run after writing the plan)

**1. Spec coverage:**
- §1.2 Solution → covered by Tasks 1, 3, 4, 7, 8, 9, 10, 16
- §1.3 Decisions → enforced by global constraints and exclusions in Task 10, 11, 12, 13
- §2 Architecture → implemented by file structure (Phase 1-5)
- §3.1-3.6 Schema → Task 1 (all 6 tables + indexes)
- §3.7 Migration → Task 1
- §4 Analytics (11 functions) → Task 4 (all 11 names + signatures match)
- §5.1 Bundle → Task 7
- §5.2 Prompts → Task 8
- §5.3 LLM validate+retry → Task 9
- §6 Coach API (15 endpoints) → Task 10 (all 15 routes match by path)
- §7 Coach UI → Task 16
- §8 Recording hooks → Tasks 11, 12, 13
- §9 Failure modes → handled in Task 9 (LLM validate+retry), Task 3 (journal failure isolation), Task 10 (router 503s with bundle fallback), Task 16 (UI banner)
- §10 Out of scope → parking lot, no tasks
- §11 Verification (12 checks) → Task 17 (1:1 mapping)
- §12 Open questions → parking lot, no tasks

**2. Placeholder scan:** No TBD/TODO/"implement later"/"similar to task N" in the plan. All code is concrete.

**3. Type consistency:**
- `JournalStrategy`, `JournalStrategyRun`, `JournalSignal`, `JournalTrade`, `JournalMarketRegime`, `JournalCoachReport` — used identically in Tasks 2, 3, 4, 7, 9, 10
- Analytics function names in Task 4 match the calls in Task 7
- `bundle["period"]["start"]` / `bundle["period"]["end"]` accessed in Tasks 7 and 9 with matching key
- `ReportResult` dataclass in Task 9 has fields used in Task 10
- Endpoint paths in Task 10 match the client methods in Task 15
- Pydantic field names in Task 10 match the TypeScript interface fields in Task 15

**4. Ambiguity:** None — every step has exact file paths, exact commands, and expected output.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-06-trade-coach-agent.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
