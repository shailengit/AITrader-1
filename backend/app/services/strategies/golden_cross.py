"""Golden Cross Rotation Strategy — pluggable Strategy implementation.

Scans 1500 stocks daily for EMA20/200 golden cross (Entry A) or
momentum continuation (Entry B). Ranks by 60% crossover angle + 40% market cap.
Holds top 5, exits on death cross or rotation.
"""

import logging
from typing import List, Dict, Any

import pandas as pd
import numpy as np
from sqlalchemy import Engine, text

from app.services.strategy_base import Strategy, Signal, ExitCheck, get_all_tickers

logger = logging.getLogger(__name__)

# ── Strategy Parameters ───────────────────────────────────────────────
ANGLE_WEIGHT = 0.60
CAP_WEIGHT = 0.40
MAX_HOLDINGS = 5
SIZING_PCTS = [0.30, 0.25, 0.20, 0.15, 0.10]


class GoldenCrossStrategy(Strategy):
    """Golden cross rotation with momentum continuation entry."""

    def get_name(self) -> str:
        return "Golden Cross Rotation"

    @property
    def max_holdings(self) -> int:
        return MAX_HOLDINGS

    @property
    def sizing_pcts(self) -> List[float]:
        return SIZING_PCTS

    # ── Signal Generation ──────────────────────────────────────────────

    def get_signals(self, as_of_date: str, engine: Engine) -> List[Signal]:
        """Scan all stocks for golden cross + Entry B signals, rank by score."""
        from app.utils.security import get_safe_table_name

        tickers = get_all_tickers(engine)
        candidates: List[Signal] = []

        for ticker in tickers:
            try:
                safe = get_safe_table_name(ticker)
            except ValueError:
                continue

            try:
                with engine.connect() as conn:
                    df = pd.read_sql(
                        f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" FROM "{safe}" '
                        f'WHERE "Date" <= \'{as_of_date}\' ORDER BY "Date" DESC LIMIT 300',
                        conn,
                    )
            except Exception:
                continue

            if df.empty or len(df) < 250:
                continue

            df = df.sort_values("Date").reset_index(drop=True)
            close = df["Close"]
            volume = df["Volume"]
            ema20 = close.ewm(span=20, adjust=False).mean()
            ema200 = close.rolling(window=200).mean()
            ema50 = close.ewm(span=50, adjust=False).mean()

            # RSI(14)
            delta = close.diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / (avg_loss + 1e-9)
            rsi = 100 - (100 / (1 + rs))

            vol_ma50 = volume.rolling(50).mean()

            # Entry A: EMA20/200 golden cross on the most recent trading day
            entry_a = None
            i = len(df) - 1
            if (pd.notna(ema20.iloc[i]) and pd.notna(ema200.iloc[i]) and
                    pd.notna(ema20.iloc[i - 1]) and pd.notna(ema200.iloc[i - 1])):
                if ema20.iloc[i - 1] <= ema200.iloc[i - 1] and ema20.iloc[i] > ema200.iloc[i]:
                    angle = self._compute_crossover_angle(close, ema20, ema200, i)
                    entry_a = {
                        "angle": angle,
                        "price": float(close.iloc[i]),
                        "date": str(df["Date"].iloc[i])[:10],
                    }

            # Entry B: Price > EMA50 > EMA200 AND RSI > 60 AND volume > 1.2x avg
            entry_b = None
            last = df.iloc[-1]
            if (pd.notna(ema50.iloc[-1]) and pd.notna(ema200.iloc[-1]) and
                    pd.notna(rsi.iloc[-1]) and pd.notna(vol_ma50.iloc[-1]) and vol_ma50.iloc[-1] > 0):
                if (last["Close"] > ema50.iloc[-1] and ema50.iloc[-1] > ema200.iloc[-1] and
                        rsi.iloc[-1] > 60 and last["Volume"] > vol_ma50.iloc[-1] * 1.2):
                    slope = (ema50.iloc[-1] - ema50.iloc[-5]) / ema50.iloc[-5] if len(df) >= 5 else 0
                    entry_b = {
                        "angle": float(slope * 100),
                        "price": float(last["Close"]),
                        "date": str(last["Date"])[:10],
                    }

            if not (entry_a or entry_b):
                continue

            # Market cap for scoring
            mc = 0.0
            try:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT market_cap FROM stock_metadata WHERE ticker = :t"),
                        {"t": ticker.upper()},
                    ).fetchone()
                if row and row[0] is not None:
                    mc = float(row[0])
            except Exception:
                pass

            entry = entry_a or entry_b
            angle_norm = 1 / (1 + np.exp(-entry["angle"] * 100))
            cap_norm = min(1.0, mc / 100e9)
            score = ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm

            candidates.append(Signal(
                ticker=ticker.upper(),
                side="long",
                score=round(score, 4),
                angle=round(entry["angle"], 4),
                price=entry["price"],
                entry_date=entry["date"],
                entry_type="A" if entry_a else "B",
            ))

        candidates.sort(key=lambda s: s.score, reverse=True)
        return candidates[:MAX_HOLDINGS]

    # ── Exit Logic ────────────────────────────────────────────────────

    def should_exit(self, ticker: str, as_of_date: str,
                    engine: Engine, side: str = "long") -> ExitCheck:
        """Check for death cross — exit if EMA20 crossed below EMA200."""
        if side != "long":
            return ExitCheck()  # Only handles long exits

        try:
            from app.utils.security import get_safe_table_name
            safe = get_safe_table_name(ticker)
            with engine.connect() as conn:
                df = pd.read_sql(
                    f'SELECT "Date", "Close" FROM "{safe}" '
                    f'WHERE "Date" <= \'{as_of_date}\' ORDER BY "Date" DESC LIMIT 250',
                    conn,
                )
            if df.empty or len(df) < 50:
                return ExitCheck()
            df = df.sort_values("Date").reset_index(drop=True)
            ema20 = df["Close"].ewm(span=20, adjust=False).mean()
            ema200 = df["Close"].rolling(window=200).mean()
            if pd.notna(ema20.iloc[-1]) and pd.notna(ema200.iloc[-1]):
                if ema20.iloc[-1] < ema200.iloc[-1]:
                    return ExitCheck(should_close=True, reason="Death Cross")
        except Exception:
            pass
        return ExitCheck()

    # ── Internal Helpers ──────────────────────────────────────────────

    @staticmethod
    def _compute_crossover_angle(close, ema20, ema200, cross_idx):
        """Compute the angle between EMA20 and EMA200 at crossover.

        Uses the rate of change of the spread over lookback*2 bars
        centered on the crossover. Falls back to the spread itself
        when future data is unavailable (latest bar).
        """
        lookback = 3
        if cross_idx < lookback:
            return 0.0

        end = min(cross_idx + lookback, len(close) - 1)
        start = max(0, cross_idx - lookback)

        if end == start:
            return 0.0

        spread_before = (ema20.iloc[start] - ema200.iloc[start])
        spread_after = (ema20.iloc[end] - ema200.iloc[end])
        angle = (spread_after - spread_before) / (end - start)
        return float(angle) if pd.notna(angle) else 0.0
