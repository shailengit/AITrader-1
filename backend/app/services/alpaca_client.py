"""Alpaca trading API wrapper for TradeCraft."""

import os
import logging
from typing import List, Dict, Any

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
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
        take-profit and trailing-stop orders managed by Alpaca.
        """
        order = self.trading_client.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(
                limit_price=None  # Alpaca calculates from fill price
            ) if take_profit_pct > 0 else None,
            stop_loss=StopLossRequest(
                stop_price=None,
                trail_percent=trailing_stop_pct * 100,
            ) if trailing_stop_pct > 0 else None,
        )
        return {
            "id": str(order.id),
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
            "id": str(order.id),
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
            logger.error("Failed to cancel orders: %s", e)
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
                bar = bars[symbol][-1]
                result[symbol] = {
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                    "timestamp": str(bar.timestamp),
                }
        return result
