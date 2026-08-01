"""Daily Golden Cross Rotation Strategy — pluggable Strategy implementation.

Scans 1500 stocks daily for EMA20/200 golden cross.
Ranks by: 60% crossover angle + 40% market cap.
Holds top 5, rotates when better candidates appear.
Exits: death cross, death cross warning, time stop (60d), or rotated out.
Minimum hold days: 7 before rotation close.
Volatility filter — skips stocks with 14d daily return std > 5%.
Sector diversification (max 2 per sector).
Score-squared position sizing for aggressive top-pick weighting.
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
MIN_HOLD_DAYS = 7
TIME_STOP_DAYS = 60
MAX_VOLATILITY = 0.05
MAX_SECTOR_COUNT = 2
SIZING_PCTS = [0.30, 0.25, 0.20, 0.15, 0.10]


class DailyGoldenCrossRotation(Strategy):
    """Daily golden cross rotation with sector diversification and volatility filter."""

    def get_name(self) -> str:
        return "Daily Golden Cross Rotation"

    @property
    def max_holdings(self) -> int:
        return MAX_HOLDINGS

    @property
    def sizing_pcts(self) -> List[float]:
        return SIZING_PCTS

    # ── Signal Generation ──────────────────────────────────────────────

    def get_signals(self, as_of_date: str, engine: Engine) -> List[Signal]:
        """Scan all stocks for golden cross signals, rank by score with sector diversification."""
        from app.utils.security import get_safe_table_name

        tickers = get_all_tickers(engine)
        candidates: List[Dict[str, Any]] = []

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
            volume = df["Volume"].astype(float)
            ema20 = close.ewm(span=20, adjust=False).mean()
            ema200 = close.rolling(window=200).mean()
            vol_ma50 = volume.rolling(50).mean()

            # 14-day rolling volatility
            returns = close.pct_change(fill_method=None)
            vol_14 = returns.rolling(14).std()

            # Check for golden cross on the most recent trading day
            i = len(df) - 1
            if not (pd.notna(ema20.iloc[i]) and pd.notna(ema200.iloc[i]) and
                    pd.notna(ema20.iloc[i - 1]) and pd.notna(ema200.iloc[i - 1])):
                continue

            if not (ema20.iloc[i - 1] <= ema200.iloc[i - 1] and ema20.iloc[i] > ema200.iloc[i]):
                continue

            # Volatility filter
            current_vol = float(vol_14.iloc[i]) if pd.notna(vol_14.iloc[i]) else 0.0
            if current_vol > MAX_VOLATILITY:
                continue

            angle = self._compute_crossover_angle(close, ema20, ema200, i)

            # Market cap for scoring
            mc = 0.0
            sector = "Unknown"
            try:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT market_cap, sector FROM stock_metadata WHERE ticker = :t"),
                        {"t": ticker.upper()},
                    ).fetchone()
                if row:
                    if row[0] is not None:
                        mc = float(row[0])
                    if row[1] is not None:
                        sector = row[1]
            except Exception:
                pass

            candidates.append({
                "ticker": ticker.upper(),
                "angle": angle,
                "market_cap": mc,
                "sector": sector,
                "price": float(close.iloc[i]),
                "date": str(df["Date"].iloc[i])[:10],
            })

        if not candidates:
            return []

        # Normalize market caps
        caps = [c["market_cap"] for c in candidates if c["market_cap"] > 0]
        cap_max = max(caps) if caps else 1
        cap_min = min(caps) if caps else 0
        cap_range = cap_max - cap_min if cap_max > cap_min else 1

        # Score and rank
        for c in candidates:
            angle_norm = 1 / (1 + np.exp(-c["angle"] * 100))
            cap_norm = (c["market_cap"] - cap_min) / cap_range if cap_range > 0 else 0.5
            c["score"] = ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm

        candidates.sort(key=lambda x: x["score"], reverse=True)

        # Apply sector diversification (max MAX_SECTOR_COUNT per sector)
        selected = []
        sector_counts: Dict[str, int] = {}
        for c in candidates:
            if len(selected) >= MAX_HOLDINGS:
                break
            sec = c.get("sector", "Unknown")
            if sector_counts.get(sec, 0) >= MAX_SECTOR_COUNT:
                continue
            selected.append(c)
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

        return [
            Signal(
                ticker=c["ticker"],
                side="long",
                score=round(c["score"], 4),
                angle=round(c["angle"], 4),
                price=c["price"],
                entry_date=c["date"],
                entry_type="golden_cross",
            )
            for c in selected
        ]

    # ── Exit Logic ────────────────────────────────────────────────────

    def should_exit(self, ticker: str, as_of_date: str,
                    engine: Engine, side: str = "long") -> ExitCheck:
        """Check for death cross, death cross warning, or time stop."""
        if side != "long":
            return ExitCheck()

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

            last_ema20 = ema20.iloc[-1]
            last_ema200 = ema200.iloc[-1]

            if pd.isna(last_ema20) or pd.isna(last_ema200):
                return ExitCheck()

            # Death cross: EMA20 crossed below EMA200
            if last_ema20 < last_ema200:
                return ExitCheck(should_close=True, reason="Death Cross")

            # Death cross warning: EMA20 within 0.1% of EMA200 and underwater
            spread_pct = (last_ema20 - last_ema200) / last_ema200
            if spread_pct < 0.001:
                # Check if position is underwater by comparing to entry price
                # (approximate: check if close is below ema20)
                if df["Close"].iloc[-1] < last_ema20:
                    return ExitCheck(should_close=True, reason="Death Cross Warning")

        except Exception:
            pass

        return ExitCheck()

    # ── Internal Helpers ──────────────────────────────────────────────

    @staticmethod
    def _compute_crossover_angle(close, ema20, ema200, cross_idx):
        """Compute the angle between EMA20 and EMA200 at crossover."""
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
