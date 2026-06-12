"""Markov Chain Trader API router."""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import SECTOR_ETFS
from app.services.markov.regime_model import SectorRegimeManager
from app.services.markov.signal_generator import SignalGenerator
from app.services.markov.feature_engineering import DEFAULT_BUY_THRESHOLD

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/markov", tags=["markov"])

# Global instances (initialized on first use)
_regime_manager: Optional[SectorRegimeManager] = None
_signal_generator: Optional[SignalGenerator] = None


def _get_managers():
    global _regime_manager, _signal_generator
    if _regime_manager is None:
        _regime_manager = SectorRegimeManager()
    if _signal_generator is None:
        _signal_generator = SignalGenerator(_regime_manager)
    return _regime_manager, _signal_generator


class ScanRequest(BaseModel):
    tickers: Optional[List[str]] = None  # None = all available
    model: str = "xgboost"
    threshold: float = DEFAULT_BUY_THRESHOLD
    min_conviction: float = 0.6
    max_results: int = 50


class RetrainRequest(BaseModel):
    model: str = "xgboost"  # 'xgboost', 'lstm', or 'all'


@router.get("/status")
async def markov_status():
    """Return model health and cache freshness."""
    rm, sg = _get_managers()
    return {
        "status": "ok",
        "etf_count": len(SECTOR_ETFS),
        "trained_etfs": sum(1 for m in rm.models.values() if m.is_trained),
        "last_updated": rm.last_updated,
        "models": {
            "xgboost": "ready",
            "lstm": "ready",
        },
    }


@router.post("/scan")
async def scan_tickers(request: ScanRequest):
    """Scan tickers and return ranked convergent signals."""
    rm, sg = _get_managers()

    # If no tickers specified, train regimes first
    if rm.last_updated is None:
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=365 * 3)).strftime('%Y-%m-%d')
        rm.train_all(start, end)

    # Build ticker list
    if request.tickers is not None and len(request.tickers) > 0:
        from app.services.data_service import DataService
        ticker_list = []
        for t in request.tickers:
            meta = DataService.get_ticker_metadata(t)
            sector = meta['sector'] if meta else 'Unknown'
            ticker_list.append({'ticker': t.upper(), 'sector': sector})
    else:
        from app.services.data_service import DataService
        all_tickers = DataService.get_available_tickers()
        ticker_list = []
        for t in all_tickers:
            meta = DataService.get_ticker_metadata(t)
            sector = meta['sector'] if meta else 'Unknown'
            ticker_list.append({'ticker': t, 'sector': sector})

    result = sg.scan_tickers(
        ticker_list,
        model=request.model,
        threshold=request.threshold,
        min_conviction=request.min_conviction,
        max_results=request.max_results,
    )

    # Add sector status
    result['sector_status'] = rm.get_all_regimes()

    return result


@router.post("/retrain")
async def retrain_models(request: RetrainRequest):
    """Force retrain models."""
    rm, sg = _get_managers()
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=365 * 3)).strftime('%Y-%m-%d')

    if request.model in ("xgboost", "all"):
        results = rm.train_all(start, end)
        return {"status": "retraining", "model": request.model, "results": results}

    return {"status": "retraining", "model": request.model}


@router.get("/regimes")
async def get_regimes():
    """Get current regime state for all sector ETFs."""
    rm, _ = _get_managers()
    return {"sector_status": rm.get_all_regimes()}
