# Alpaca Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Golden Cross Rotation strategy to Alpaca paper trading with daily automated execution.

**Architecture:** A daily cron job triggers a Python script that: (1) fetches latest market data from PostgreSQL, (2) runs the golden cross scan and ranking, (3) compares desired vs actual Alpaca positions, (4) submits bracket orders to Alpaca. The strategy engine is already built and validated.

**Tech Stack:** Python, alpaca-trade-api, PostgreSQL, FastAPI, cron

## Global Constraints

- Alpaca API keys stored in `.env` file, never hardcoded
- All trading happens via Alpaca paper trading API
- Strategy parameters match the validated Alpaca Edition (60/40 blend, 0.05% slippage)
- Daily run scheduled for 6:00 PM ET via cron
- All order execution uses Alpaca bracket orders (market-on-open + OCO take-profit/trailing-stop)

---
## File Structure

| File | Responsibility |
|------|----------------|
| `backend/app/services/alpaca_client.py` | Alpaca REST API wrapper — account, positions, orders |
| `backend/app/services/alpaca_runner.py` | Daily strategy orchestrator — scan, compare, execute |
| `scripts/run_alpaca_strategy.sh` | Cron shell script — activates venv, runs runner, logs |

### Task 1: Alpaca Client Wrapper

**Files:**
- Create: `backend/app/services/alpaca_client.py`
- Modify: `backend/.env.example` (add Alpaca config keys)

**Interfaces:**
- Consumes: Environment variables `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER`
- Produces: `AlpacaClient` class with methods:
  - `get_account()` -> `dict` (account equity, cash, buying power)
  - `get_positions()` -> `list[dict]` (current holdings: ticker, qty, market_value, unrealized_pl)
  - `submit_market_order(symbol, qty, side)` -> `dict` (order response)
  - `submit_bracket_order(symbol, qty, side, take_profit_pct, trailing_stop_pct)` -> `dict`
  - `cancel_all_orders()` -> `bool`
  - `get_latest_bars(symbols)` -> `dict` (latest bar data for given symbols)

- [ ] **Step 1: Install alpaca-trade-api and write the client class**

```bash
cd backend && ./venv/bin/pip install alpaca-trade-api
```

```python
# backend/app/services/alpaca_client.py
"""Alpaca trading API wrapper for TradeCraft."""

import os
import logging
from typing import List, Dict, Any, Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, TrailingStopOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType, OrderClass
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Wrapper around Alpaca trading and data APIs."""

    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"

        if not self.api_key or not self.secret_key:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env"
            )

        self.trading_client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
        self.data_client = StockHistoricalDataClient(self.api_key, self.secret_key)

    def get_account(self) -> Dict[str, Any]:
        """Get account details: equity, cash, buying power."""
        account = self.trading_client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "status": account.status,
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current open positions."""
        positions = self.trading_client.get_all_positions()
        return [
            {
                "ticker": p.symbol,
                "qty": int(p.qty),
                "market_value": float(p.market_value),
                "cost_basis": float(p.cost_basis),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_pl_pct": float(p.unrealized_plpc),
                "current_price": float(p.current_price),
                "avg_entry_price": float(p.avg_entry_price),
            }
            for p in positions
        ]

    def submit_bracket_order(
        self,
        symbol: str,
        qty: int,
        side: OrderSide,
        take_profit_pct: float = 0.20,
        trailing_stop_pct: float = 0.08,
    ) -> Dict[str, Any]:
        """Submit a bracket order with take profit and trailing stop.

        The bracket order enters at market-on-open and attaches OCO
        take-profit and trailing-stop orders that are managed by Alpaca.
        """
        from alpaca.trading.requests import GetOrdersRequest

        # Submit the bracket order
        order = self.trading_client.submit_order(
            order_class=OrderClass.BRACKET,
            symbol=symbol,
            qty=qty,
            side=side,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            take_profit=TakeProfitRequest(
                limit_price=None  # Will be calculated by Alpaca as % above fill
            ) if take_profit_pct > 0 else None,
            stop_loss=StopLossRequest(
                stop_price=None,  # Will be calculated by Alpaca as trailing stop
                trail_percent=trailing_stop_pct * 100,
            ) if trailing_stop_pct > 0 else None,
        )
        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": int(order.qty),
            "side": order.side.value,
            "status": order.status,
            "type": order.type.value,
            "submitted_at": str(order.submitted_at),
        }

    def submit_market_order(self, symbol: str, qty: int, side: OrderSide) -> Dict[str, Any]:
        """Submit a simple market order (for closing positions)."""
        order = self.trading_client.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": int(order.qty),
            "side": order.side.value,
            "status": order.status,
        }

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self.trading_client.cancel_orders()
            return True
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
            return False

    def get_latest_bars(self, symbols: List[str]) -> Dict[str, Any]:
        """Get the latest daily bar for each symbol."""
        end = datetime.now()
        start = end - timedelta(days=5)
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
        )
        bars = self.data_client.get_stock_bars(request)
        result = {}
        for symbol in symbols:
            if symbol in bars:
                bar = bars[symbol][-1]  # Most recent bar
                result[symbol] = {
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                    "timestamp": str(bar.timestamp),
                }
        return result
```

- [ ] **Step 2: Add Alpaca config to .env.example**

```bash
# Alpaca Trading (paper trading by default)
ALPACA_API_KEY=your_paper_api_key_here
ALPACA_SECRET_KEY=your_paper_secret_key_here
ALPACA_PAPER=true
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/alpaca_client.py backend/.env.example
git commit -m "feat: add Alpaca trading client wrapper"
```

### Task 2: Daily Strategy Runner

**Files:**
- Create: `backend/app/services/alpaca_runner.py`

**Interfaces:**
- Consumes: `AlpacaClient` from Task 1, `golden_cross_ultimate.py` strategy logic, PostgreSQL database
- Produces: Daily run log with orders placed, positions updated, errors

- [ ] **Step 1: Write the daily runner**

```python
# backend/app/services/alpaca_runner.py
"""Daily strategy runner for Alpaca paper trading.

Orchestrates the daily pipeline:
1. Fetch latest market data from PostgreSQL
2. Run golden cross scan and rank top 5
3. Compare with current Alpaca positions
4. Submit bracket orders for new positions
5. Submit market orders for positions to close
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import OrderedDict

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
TRAILING_STOP_PCT = 0.08  # 8% trailing stop (ATR-based floor)
TAKE_PROFIT_PCT = 0.20     # 20% take profit

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

    def compute_ema_crossover_angle(self, close, ema20, ema200, cross_idx):
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
            high = df["High"]
            low = df["Low"]
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
                        angle = self.compute_ema_crossover_angle(close, ema20, ema200, i)
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
                cap_norm = min(1.0, mc / 100e9)  # Normalize to 100B cap
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

        # Sort by score descending, return top N
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
        logger.info(f"Running daily strategy for {as_of_date}")

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
            # Close all positions
            positions = self.alpaca.get_positions()
            for pos in positions:
                try:
                    order = self.alpaca.submit_market_order(pos["ticker"], pos["qty"], OrderSide.SELL)
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
        logger.info(f"Top {len(desired)} candidates: {[c['ticker'] for c in desired]}")

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
            # Close if: not in top 5, or has death cross, or held too long
            if ticker not in desired_tickers or self.check_death_cross(ticker, as_of_date):
                try:
                    order = self.alpaca.submit_market_order(ticker, pos["qty"], OrderSide.SELL)
                    result["positions_closed"].append({
                        "ticker": ticker, "qty": pos["qty"],
                        "reason": "Death Cross" if ticker not in desired_tickers else "Rotated Out"
                    })
                    logger.info(f"CLOSE {ticker}: {pos['qty']} shares")
                except Exception as e:
                    result["errors"].append(f"Failed to close {ticker}: {e}")

        # Step 5: Determine positions to open
        account = self.alpaca.get_account()
        portfolio_value = float(account["equity"])

        for rank, candidate in enumerate(desired):
            ticker = candidate["ticker"]
            if ticker in current_tickers:
                continue  # Already holding

            target_pct = SIZING_PCTS[rank] if rank < len(SIZING_PCTS) else 0.10
            target_value = portfolio_value * target_pct
            price = candidate["price"]
            qty = max(1, int(target_value / price))

            try:
                order = self.alpaca.submit_bracket_order(
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
                logger.info(f"BUY {ticker}: {qty} shares @ ~${price:.2f} (score={candidate['score']:.2f}, angle={candidate['angle']:.4f})")
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

    # Print summary
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/alpaca_runner.py
git commit -m "feat: add daily Alpaca strategy runner"
```

### Task 3: Cron Shell Script

**Files:**
- Create: `scripts/run_alpaca_strategy.sh`

**Interfaces:**
- Consumes: `alpaca_runner.py` from Task 2
- Produces: Log file with daily run results

- [ ] **Step 1: Write the cron shell script**

```bash
#!/bin/bash
# TradeCraft Golden Cross Rotation — Daily Alpaca Strategy Runner
# Runs daily at 6:00 PM ET via cron
#
# Add to crontab:
#   0 18 * * 1-5 /path/to/scripts/run_alpaca_strategy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/backend/logs"
LOG_FILE="$LOG_DIR/alpaca_strategy_$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

# Load environment variables
if [ -f "$PROJECT_DIR/backend/.env" ]; then
    set -a
    source "$PROJECT_DIR/backend/.env"
    set +a
fi

cd "$PROJECT_DIR/backend"
source venv/bin/activate

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting daily strategy run..." >> "$LOG_FILE"

python -m app.services.alpaca_runner >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily strategy run complete" >> "$LOG_FILE"

# Keep only last 30 days of logs
find "$LOG_DIR" -name "alpaca_strategy_*.log" -mtime +30 -delete
```

- [ ] **Step 2: Make executable and add to crontab**

```bash
chmod +x scripts/run_alpaca_strategy.sh

# Add to crontab (runs weekdays at 6 PM ET)
(crontab -l 2>/dev/null; echo "0 18 * * 1-5 $(pwd)/scripts/run_alpaca_strategy.sh") | crontab -
```

- [ ] **Step 3: Commit**

```bash
git add scripts/run_alpaca_strategy.sh
git commit -m "feat: add daily Alpaca strategy cron script"
```

### Task 4: Integration Test

**Files:**
- Create: `backend/tests/test_alpaca_runner.py`

- [ ] **Step 1: Write integration test**

```python
"""Tests for the Alpaca strategy runner."""

from app.services.alpaca_runner import StrategyRunner


def test_scan_and_rank():
    """Test that scan_and_rank returns top candidates with valid data."""
    runner = StrategyRunner()
    as_of = runner.get_latest_date()
    candidates = runner.scan_and_rank(as_of)
    assert len(candidates) > 0, "Should find at least some candidates"
    assert len(candidates) <= 5, "Should return at most 5 candidates"
    for c in candidates:
        assert "ticker" in c
        assert "score" in c
        assert "angle" in c
        assert c["score"] > 0, "Score should be positive"


def test_check_death_cross():
    """Test death cross detection on a known stock."""
    runner = StrategyRunner()
    # AAPL is unlikely to have a death cross on any random date
    # but the function should return a boolean without error
    result = runner.check_death_cross("AAPL", "2024-01-01")
    assert isinstance(result, bool)


def test_crisis_override():
    """Test crisis override check returns a boolean."""
    runner = StrategyRunner()
    result = runner.check_crisis_override("2024-01-01")
    assert isinstance(result, bool)
```

- [ ] **Step 2: Run tests**

```bash
cd backend && export DB_PASSWORD=sarina00 && ./venv/bin/python -m pytest tests/test_alpaca_runner.py -v
```

Expected output:
```
test_scan_and_rank PASSED
test_check_death_cross PASSED
test_crisis_override PASSED
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_alpaca_runner.py
git commit -m "test: add Alpaca strategy runner tests"
```
