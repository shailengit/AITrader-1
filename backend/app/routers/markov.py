"""Markov Chain Trader API router."""
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/markov", tags=["markov"])


@router.get("/status")
async def markov_status():
    """Return model health and cache freshness."""
    return {
        "status": "ok",
        "message": "Markov Chain Trader module loaded",
        "models": {"xgboost": "not_trained", "lstm": "not_trained"},
        "etf_count": 11,
        "tickers_covered": 0,
    }
