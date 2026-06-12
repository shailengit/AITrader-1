"""Routers package for TradeCraft API."""
from .health import router as health_router
from .sectors import router as sectors_router
from .screener import router as screener_router
from .quantgen import router as quantgen_router
from .markov import router as markov_router

__all__ = [
    'health_router',
    'sectors_router',
    'screener_router',
    'quantgen_router',
    'markov_router'
]