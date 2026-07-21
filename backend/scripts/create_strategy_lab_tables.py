"""One-shot DDL for the AI Strategy Builder tables.

Run once to create the 4 tables in the sp1500_1d database.
Safe to re-run: uses CREATE TABLE IF NOT EXISTS.
Idempotent: drops nothing.

Usage:
  cd backend && ./venv/bin/python scripts/create_strategy_lab_tables.py
"""
import os
import sys

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.database import engine
from sqlalchemy import text

DDL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS strategy_sessions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  prompt      TEXT NOT NULL,
  plan_text   TEXT,
  code_text   TEXT,
  model_id    TEXT NOT NULL,
  tags        TEXT[] NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_strategy_sessions_tags ON strategy_sessions USING gin(tags);

CREATE TABLE IF NOT EXISTS strategy_experiments (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        UUID NOT NULL REFERENCES strategy_sessions(id) ON DELETE CASCADE,
  batch_id          UUID NOT NULL,
  run_index         INT NOT NULL,
  start_date        DATE NOT NULL,
  end_date          DATE NOT NULL,
  status            TEXT NOT NULL,
  error_message     TEXT,
  kpis              JSONB,
  trades_summary    JSONB,
  report_html_path  TEXT,
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_experiments_session_batch ON strategy_experiments(session_id, batch_id);
CREATE INDEX IF NOT EXISTS idx_experiments_kpis ON strategy_experiments USING gin(kpis);

CREATE TABLE IF NOT EXISTS strategy_batch_summaries (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id        UUID NOT NULL,
  session_id      UUID NOT NULL REFERENCES strategy_sessions(id) ON DELETE CASCADE,
  summary_text    TEXT NOT NULL,
  winner_run_id   UUID REFERENCES strategy_experiments(id),
  model_id        TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS strategy_deployments (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      UUID NOT NULL REFERENCES strategy_sessions(id),
  experiment_id   UUID REFERENCES strategy_experiments(id),
  class_name      TEXT NOT NULL,
  class_file_path TEXT NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT FALSE,
  deployed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  rolled_back_at  TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_deployment
  ON strategy_deployments(is_active) WHERE is_active = TRUE;
"""


def main():
    with engine.begin() as conn:
        for stmt in [s.strip() for s in DDL.split(";") if s.strip()]:
            conn.execute(text(stmt))
    print("✅ Created 4 strategy_lab tables (idempotent).")


if __name__ == "__main__":
    main()
