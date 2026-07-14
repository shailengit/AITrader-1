"""Daily strategy runner for Alpaca paper trading.

Orchestrates the daily pipeline:
1. Fetch latest market data from PostgreSQL
2. Run golden cross scan and rank top 5
3. Compare with current Alpaca positions
4. Submit bracket orders for new positions
5. Submit market orders for positions to close
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from alpaca.trading.enums import OrderSide

from app.services.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)

# Strategy parameters (from validated Alpaca Edition)
ANGLE_WEIGHT = 0.60
CAP_WEIGHT = 0.40
MAX_HOLDINGS = 5
MIN_HOLD_DAYS = 10
SIZING_PCTS = [0.30, 0.25, 0.20, 0.15, 0.10]
TRAILING_STOP_PCT = 0.08
TAKE_PROFIT_PCT = 0.20

# Crisis override
CRISIS_DRAWDOWN = 0.20
CRISIS_RECOVERY = 0.10


class StrategyRunner:
    """Daily strategy runner that connects the scan engine to Alpaca."""

    def __init__(self):
        self.alpaca = AlpacaClient()
        self.db_url = (
            f"postgresql://{os.getenv('DB_USER', 'postgres')}:"
            f"{os.getenv('DB_PASSWORD')}@"
            f"{os.getenv('DB_HOST', '127.0.0.1')}:"
            f"{os.getenv('DB_PORT', '5431')}/"
            f"{os.getenv('DB_NAME', 'sp1500_1d')}"
        )
        self.engine = create_engine(self.db_url)

    def get_all_tickers(self) -> List[str]:
        """Get all stock tickers from the database."""
        skip = {'stock_metadata', 'stock_financials_quarterly', 'stock_financials_yearly',
                'xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly', 'vix'}
        with self.engine.connect() as conn:
            res = conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ))
            return [row[0] for row in res if row[0] not in skip]

    def get_latest_date(self) -> str:
        """Get the latest trading date from the database."""
        with self.engine.connect() as conn:
            result = conn.execute(text('SELECT MAX("Date") FROM aapl')).scalar()
            return str(result)[:10] if result else datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def compute_ema_crossover_angle(close, ema20, ema200, cross_idx):
        """Compute the angle between EMA20 and EMA200 at crossover."""
        lookback = 3
        if cross_idx < lookback or cross_idx + lookback >= len(close):
            return 0.0
        spread_before = (ema20.iloc[cross_idx - lookback] - ema200.iloc[cross_idx - lookback])
        spread_after = (ema20.iloc[cross_idx + lookback] - ema200.iloc[cross_idx + lookback])
        angle = (spread_after - spread_before) / (lookback * 2)
        return float(angle) if pd.notna(angle) else 0.0

    def scan_and_rank(self, as_of_date: str) -> List[Dict[str, Any]]:
        """Scan all stocks for golden cross + Entry B signals, rank by score.

        Returns top MAX_HOLDINGS candidates with scores and metadata.
        """
        from app.utils.security import get_safe_table_name

        tickers = self.get_all_tickers()
        candidates = []

        for ticker in tickers:
            try:
                safe = get_safe_table_name(ticker)
            except ValueError:
                continue

            try:
                with self.engine.connect() as conn:
                    df = pd.read_sql(
                        f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" FROM "{safe}" '
                        f'WHERE "Date" <= \'{as_of_date}\' ORDER BY "Date" DESC LIMIT 300',
                        conn
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

            # Check Entry A: EMA20/200 golden cross in last 5 days
            entry_a = None
            for i in range(len(df) - 5, len(df)):
                if (pd.notna(ema20.iloc[i]) and pd.notna(ema200.iloc[i]) and
                    pd.notna(ema20.iloc[i-1]) and pd.notna(ema200.iloc[i-1])):
                    if ema20.iloc[i-1] <= ema200.iloc[i-1] and ema20.iloc[i] > ema200.iloc[i]:
                        angle = StrategyRunner.compute_ema_crossover_angle(close, ema20, ema200, i)
                        entry_a = {
                            "angle": angle,
                            "price": float(close.iloc[i]),
                            "date": str(df["Date"].iloc[i])[:10],
                        }
                        break

            # Check Entry B: Price > EMA50 > EMA200 AND RSI > 60 AND volume > 1.2x avg
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

            if entry_a or entry_b:
                # Get market cap
                mc = 0.0
                try:
                    with self.engine.connect() as conn:
                        row = conn.execute(
                            text("SELECT market_cap FROM stock_metadata WHERE ticker = :t"),
                            {"t": ticker.upper()}
                        ).fetchone()
                    if row and row[0] is not None:
                        mc = float(row[0])
                except Exception:
                    pass

                entry = entry_a or entry_b
                angle_norm = 1 / (1 + np.exp(-entry["angle"] * 100))
                cap_norm = min(1.0, mc / 100e9)
                score = ANGLE_WEIGHT * angle_norm + CAP_WEIGHT * cap_norm

                candidates.append({
                    "ticker": ticker.upper(),
                    "score": round(score, 4),
                    "angle": round(entry["angle"], 4),
                    "price": entry["price"],
                    "entry_date": entry["date"],
                    "entry_type": "A" if entry_a else "B",
                    "market_cap": mc,
                })

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:MAX_HOLDINGS]

    def check_crisis_override(self, as_of_date: str) -> bool:
        """Check if SPY has dropped >20% from its 200-day high."""
        try:
            with self.engine.connect() as conn:
                spy = pd.read_sql(
                    f'SELECT "Date", "Close" FROM spy WHERE "Date" <= \'{as_of_date}\' ORDER BY "Date" DESC LIMIT 200',
                    conn
                )
            if spy.empty or len(spy) < 200:
                return False
            spy = spy.sort_values("Date")
            spy_high = spy["Close"].max()
            spy_current = spy["Close"].iloc[-1]
            drawdown = (spy_high - spy_current) / spy_high
            return drawdown >= CRISIS_DRAWDOWN
        except Exception:
            return False

    def check_death_cross(self, ticker: str, as_of_date: str) -> bool:
        """Check if a stock has a death cross (EMA20 below EMA200)."""
        try:
            from app.utils.security import get_safe_table_name
            safe = get_safe_table_name(ticker)
            with self.engine.connect() as conn:
                df = pd.read_sql(
                    f'SELECT "Date", "Close" FROM "{safe}" WHERE "Date" <= \'{as_of_date}\' ORDER BY "Date" DESC LIMIT 250',
                    conn
                )
            if df.empty or len(df) < 50:
                return False
            df = df.sort_values("Date").reset_index(drop=True)
            ema20 = df["Close"].ewm(span=20, adjust=False).mean()
            ema200 = df["Close"].rolling(window=200).mean()
            return bool(ema20.iloc[-1] < ema200.iloc[-1]) if pd.notna(ema20.iloc[-1]) and pd.notna(ema200.iloc[-1]) else False
        except Exception:
            return False

    def run_daily(self) -> Dict[str, Any]:
        """Execute the daily strategy pipeline."""
        as_of_date = self.get_latest_date()
        logger.info("Running daily strategy for %s", as_of_date)

        result = {
            "date": as_of_date,
            "status": "running",
            "orders_placed": [],
            "positions_closed": [],
            "errors": [],
            "crisis_mode": False,
        }

        # Step 1: Check crisis override
        if self.check_crisis_override(as_of_date):
            logger.warning("CRISIS OVERRIDE ACTIVE — going to cash")
            result["crisis_mode"] = True
            positions = self.alpaca.get_positions()
            for pos in positions:
                try:
                    self.alpaca.submit_market_order(pos["ticker"], pos["qty"], OrderSide.SELL)
                    result["positions_closed"].append({
                        "ticker": pos["ticker"], "qty": pos["qty"], "reason": "Crisis Override"
                    })
                except Exception as e:
                    result["errors"].append(f"Failed to close {pos['ticker']}: {e}")
            result["status"] = "completed_crisis"
            return result

        # Step 2: Scan and rank
        logger.info("Scanning 1500 stocks for golden cross signals...")
        desired = self.scan_and_rank(as_of_date)
        logger.info("Top %d candidates: %s", len(desired), [c["ticker"] for c in desired])

        if not desired:
            result["status"] = "no_candidates"
            return result

        # Step 3: Get current positions
        current_positions = self.alpaca.get_positions()
        current_tickers = {p["ticker"] for p in current_positions}
        desired_tickers = {c["ticker"] for c in desired}

        # Step 4: Determine positions to close
        for pos in current_positions:
            ticker = pos["ticker"]
            if ticker not in desired_tickers or self.check_death_cross(ticker, as_of_date):
                try:
                    self.alpaca.submit_market_order(ticker, pos["qty"], OrderSide.SELL)
                    result["positions_closed"].append({
                        "ticker": ticker, "qty": pos["qty"],
                        "reason": "Death Cross" if self.check_death_cross(ticker, as_of_date) else "Rotated Out"
                    })
                    logger.info("CLOSE %s: %d shares", ticker, pos["qty"])
                except Exception as e:
                    result["errors"].append(f"Failed to close {ticker}: {e}")

        # Step 5: Determine positions to open
        account = self.alpaca.get_account()
        portfolio_value = float(account["equity"])

        for rank, candidate in enumerate(desired):
            ticker = candidate["ticker"]
            if ticker in current_tickers:
                continue

            target_pct = SIZING_PCTS[rank] if rank < len(SIZING_PCTS) else 0.10
            target_value = portfolio_value * target_pct
            price = candidate["price"]
            qty = max(1, int(target_value / price))

            try:
                self.alpaca.submit_bracket_order(
                    symbol=ticker,
                    qty=qty,
                    side=OrderSide.BUY,
                    take_profit_pct=TAKE_PROFIT_PCT,
                    trailing_stop_pct=TRAILING_STOP_PCT,
                )
                result["orders_placed"].append({
                    "ticker": ticker, "qty": qty, "price": price,
                    "score": candidate["score"], "angle": candidate["angle"],
                    "entry_type": candidate["entry_type"],
                })
                logger.info(
                    "BUY %s: %d shares @ ~$%.2f (score=%.2f, angle=%.4f)",
                    ticker, qty, price, candidate["score"], candidate["angle"],
                )
            except Exception as e:
                result["errors"].append(f"Failed to buy {ticker}: {e}")

        result["status"] = "completed"
        return result


def main():
    """Entry point for the daily strategy run."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    runner = StrategyRunner()
    result = runner.run_daily()

    print(f"\n{'='*60}")
    print(f"  GOLDEN CROSS ROTATION — DAILY RUN")
    print(f"  Date: {result['date']}")
    print(f"  Status: {result['status']}")
    print("=" * 60)

    if result.get("crisis_mode"):
        print("  🛑 CRISIS OVERRIDE — All positions closed, staying in cash")
    else:
        print(f"  Orders placed: {len(result['orders_placed'])}")
        for o in result["orders_placed"]:
            print(f"    BUY  {o['ticker']:>6}  {o['qty']:>4} shares  "
                  f"score={o['score']:.2f}  angle={o['angle']:.4f}")

        print(f"  Positions closed: {len(result['positions_closed'])}")
        for c in result["positions_closed"]:
            print(f"    SELL {c['ticker']:>6}  {c['qty']:>4} shares  reason={c['reason']}")

    if result["errors"]:
        print(f"  Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"    ❌ {e}")

    print("=" * 60)
    return result


if __name__ == "__main__":
    main()
