"""Alpaca trading API wrapper for TradeCraft."""

import os
import logging
from typing import List, Dict, Any

import alpaca_trade_api as tradeapi

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

        base_url = "https://paper-api.alpaca.markets" if self.paper else "https://api.alpaca.markets"
        self.api = tradeapi.REST(self.api_key, self.secret_key, base_url=base_url)

    def get_account(self) -> Dict[str, Any]:
        """Get account details: equity, cash, buying power."""
        account = self.api.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "status": account.status,
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current open positions."""
        positions = self.api.list_positions()
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
        side: str,
        take_profit_pct: float = 0.20,
        trailing_stop_pct: float = 0.08,
        entry_price: float = 0.0,
    ) -> Dict[str, Any]:
        """Submit a bracket order with take profit and trailing stop.

        The bracket order enters at market-on-open and attaches OCO
        take-profit and trailing-stop orders managed by Alpaca.
        """
        order_kwargs = {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "order_class": "bracket",
        }

        # Add take profit if specified (must be a valid price)
        if take_profit_pct > 0 and entry_price > 0:
            tp_price = round(entry_price * (1 + take_profit_pct), 2)
            order_kwargs["take_profit"] = {"limit_price": str(tp_price)}

        # Add trailing stop loss (requires both stop_price and trail_percent for bracket orders)
        if trailing_stop_pct > 0 and entry_price > 0:
            stop_price = round(entry_price * (1 - trailing_stop_pct), 2)
            order_kwargs["stop_loss"] = {
                "stop_price": str(stop_price),
                "trail_percent": str(trailing_stop_pct * 100),
            }

        order = self.api.submit_order(**order_kwargs)
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "qty": int(order.qty),
            "side": order.side,
            "status": order.status,
            "type": order.type,
            "submitted_at": str(order.submitted_at),
        }

    def submit_market_order(self, symbol: str, qty: int, side: str) -> Dict[str, Any]:
        """Submit a simple market order (for closing positions)."""
        order = self.api.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type="market",
            time_in_force="day",
        )
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "qty": int(order.qty),
            "side": order.side,
            "status": order.status,
        }

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self.api.cancel_all_orders()
            return True
        except Exception as e:
            logger.error("Failed to cancel orders: %s", e)
            return False
