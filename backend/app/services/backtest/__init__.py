"""Screener-driven portfolio backtest service.

Owns:
  - exit_engine: per-rule-family exit logic + the simulate_position orchestrator
  - sizing: pure position-sizing helpers
  - portfolio_simulator: the I/O orchestrator that wires sizing + exit engine
    over the existing PortfolioTracker and wfo_metrics.
"""
