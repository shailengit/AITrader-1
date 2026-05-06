"""
Portfolio state tracker for continuous True WFO.
Maintains positions, cash, and P&L across walk-forward windows.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd


@dataclass
class Position:
    """Represents a holding in a specific ticker."""
    ticker: str
    shares: float
    entry_price: float
    entry_date: datetime
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.shares * (self.current_price - self.entry_price)


@dataclass
class Trade:
    """Records a single trade execution."""
    date: datetime
    ticker: str
    action: str  # 'BUY' or 'SELL'
    shares: float
    price: float
    value: float
    realized_pnl: Optional[float] = None  # For sells


@dataclass
class PortfolioState:
    """Complete portfolio state for continuous WFO."""
    date: datetime
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    trade_history: List[Trade] = field(default_factory=list)

    @property
    def total_value(self) -> float:
        """Total portfolio value (cash + positions)."""
        position_value = sum(p.market_value for p in self.positions.values())
        return self.cash + position_value

    def execute_buy(self, ticker: str, shares: float, price: float,
                    date: datetime) -> bool:
        """Execute a buy order. Returns True if successful."""
        value = shares * price
        if value > self.cash:
            return False  # Insufficient funds

        self.cash -= value

        if ticker in self.positions:
            # Average down/up existing position
            pos = self.positions[ticker]
            total_shares = pos.shares + shares
            total_cost = (pos.shares * pos.entry_price) + value
            pos.shares = total_shares
            pos.entry_price = total_cost / total_shares
        else:
            self.positions[ticker] = Position(
                ticker=ticker,
                shares=shares,
                entry_price=price,
                entry_date=date,
                current_price=price
            )

        self.trade_history.append(Trade(
            date=date, ticker=ticker, action='BUY',
            shares=shares, price=price, value=value
        ))
        return True

    def execute_sell(self, ticker: str, shares: float, price: float,
                     date: datetime) -> bool:
        """Execute a sell order. Returns True if successful."""
        if ticker not in self.positions:
            return False  # No position to sell

        pos = self.positions[ticker]
        if shares > pos.shares:
            shares = pos.shares  # Sell all we have

        value = shares * price
        realized_pnl = shares * (price - pos.entry_price)

        self.cash += value
        pos.shares -= shares

        if pos.shares <= 0:
            del self.positions[ticker]

        self.trade_history.append(Trade(
            date=date, ticker=ticker, action='SELL',
            shares=shares, price=price, value=value,
            realized_pnl=realized_pnl
        ))
        return True

    def update_prices(self, price_data: Dict[str, float], date: datetime):
        """Update current prices for all positions."""
        self.date = date
        for ticker, price in price_data.items():
            if ticker in self.positions:
                self.positions[ticker].current_price = price

    def to_dict(self) -> dict:
        """Serialize state for JSON response."""
        return {
            'date': self.date.isoformat(),
            'cash': self.cash,
            'total_value': self.total_value,
            'positions': {
                t: {
                    'shares': p.shares,
                    'entry_price': p.entry_price,
                    'current_price': p.current_price,
                    'market_value': p.market_value,
                    'unrealized_pnl': p.unrealized_pnl
                }
                for t, p in self.positions.items()
            },
            'trade_count': len(self.trade_history)
        }


class PortfolioTracker:
    """Manages portfolio state across True WFO windows."""

    def __init__(self, initial_cash: float = 100000.0):
        self.initial_cash = initial_cash
        self.states: List[PortfolioState] = []
        self.current_state: Optional[PortfolioState] = None
        self.equity_curve: List[Dict] = []

    def initialize(self, start_date: datetime):
        """Initialize portfolio at start of True WFO."""
        self.current_state = PortfolioState(
            date=start_date,
            cash=self.initial_cash,
            positions={},
            trade_history=[]
        )
        self.record_state()

    def record_state(self):
        """Record current state to equity curve."""
        if self.current_state:
            self.states.append(self.current_state)
            self.equity_curve.append({
                'time': self.current_state.date.timestamp(),
                'value': self.current_state.total_value,
                'cash': self.current_state.cash,
                'position_value': self.current_state.total_value - self.current_state.cash
            })

    def process_signal(self, ticker: str, signal: str,
                       price: float, date: datetime,
                       size_pct: float = 1.0) -> Optional[Trade]:
        """
        Process a trading signal for a single day.

        Args:
            ticker: Stock symbol
            signal: 'BUY', 'SELL', or 'HOLD'
            price: Current price
            date: Trading date
            size_pct: Position size as % of available capital (1.0 = 100%)

        Returns:
            Trade object if executed, None otherwise
        """
        state = self.current_state
        if state is None:
            return None

        if signal == 'BUY' and ticker not in state.positions:
            # Buy with specified % of available cash
            buy_value = state.cash * size_pct
            shares = buy_value / price
            if state.execute_buy(ticker, shares, price, date):
                return state.trade_history[-1]

        elif signal == 'SELL' and ticker in state.positions:
            # Sell entire position
            pos = state.positions[ticker]
            if state.execute_sell(ticker, pos.shares, price, date):
                return state.trade_history[-1]

        # HOLD or no action - just update prices
        return None

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics for the walk-forward run."""
        if not self.states:
            return {}

        start_value = self.initial_cash
        end_value = self.states[-1].total_value
        total_return = (end_value - start_value) / start_value

        # Deduplicate trades - same object is recorded in multiple states
        seen = set()
        trades = []
        for state in self.states:
            for t in state.trade_history:
                # Use int(timestamp) to match get_trade_history() deduplication
                trade_key = (int(t.date.timestamp()), t.action, t.ticker)
                if trade_key in seen:
                    continue
                seen.add(trade_key)
                trades.append(t)

        winning_trades = [t for t in trades
                         if t.action == 'SELL' and t.realized_pnl and t.realized_pnl > 0]
        losing_trades = [t for t in trades
                        if t.action == 'SELL' and t.realized_pnl and t.realized_pnl < 0]

        realized_wins = [t.realized_pnl for t in winning_trades if t.realized_pnl]
        realized_losses = [t.realized_pnl for t in losing_trades if t.realized_pnl]

        total_sells = len([t for t in trades if t.action == 'SELL'])

        return {
            'initial_value': start_value,
            'final_value': end_value,
            'total_return': total_return,
            'total_trades': len(trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / total_sells if total_sells > 0 else 0,
            'avg_win': sum(realized_wins) / len(realized_wins) if realized_wins else 0,
            'avg_loss': sum(realized_losses) / len(realized_losses) if realized_losses else 0,
        }

    def get_trade_history(self) -> List[Dict]:
        """Get complete trade history as list of dicts."""
        seen = set()  # Track unique trades by (timestamp, action) to avoid duplicates
        trades = []
        for state in self.states:
            for t in state.trade_history:
                # Convert datetime to Unix timestamp for chart compatibility
                ts = t.date.timestamp() if hasattr(t.date, 'timestamp') else pd.Timestamp(t.date).timestamp()
                # Create unique key for deduplication
                trade_key = (int(ts), t.action)
                if trade_key in seen:
                    continue
                seen.add(trade_key)
                trades.append({
                    'time': int(ts),
                    'date': t.date.isoformat(),
                    'ticker': t.ticker,
                    'action': t.action,
                    'shares': t.shares,
                    'price': t.price,
                    'value': t.value,
                    'realized_pnl': t.realized_pnl
                })
        return trades

    def get_daily_returns(self) -> pd.Series:
        """Return daily returns as a pandas Series, suitable for stats computation."""
        if len(self.equity_curve) < 2:
            return pd.Series(dtype=float)

        dates = [datetime.fromtimestamp(p['time']) for p in self.equity_curve]
        values = pd.Series(
            [p['value'] for p in self.equity_curve],
            index=pd.DatetimeIndex(dates),
            dtype=float
        )
        return values.pct_change().dropna()
