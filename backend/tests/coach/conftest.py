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
