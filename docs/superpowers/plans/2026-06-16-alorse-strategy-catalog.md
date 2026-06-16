# Alorse Strategy Catalog & Indicator Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate 12 curated Pine Script strategies from Alorse/pinescript-strategies into VectorBT-compatible Python, expose them as built-in templates in QuantGen's Library, and build a comprehensive Indicator Browser.

**Architecture:** Backend serves strategy files from `backend/strategies/catalog/` and aggregates indicators from `ta` library, VectorBT, and Alorse translations via `indicator_registry.py`. Frontend adds a tab switcher to the Library page for built-in vs saved strategies, an Indicator Browser panel in the Builder, and auto-load from `?load=<slug>`.

**Tech Stack:** Python + FastAPI + VectorBT + ta library + pandas_ta, React + TypeScript + Monaco Editor

---

## File Structure

### New Files
```
backend/
├── app/services/indicator_registry.py     # Indicator aggregator module
└── strategies/catalog/
    ├── trend/
    │   ├── supertrend.py + supertrend.json
    │   ├── ma_cross_dmi.py + ma_cross_dmi.json
    │   ├── supertrend_rsi.py + supertrend_rsi.json
    │   └── double_supertrend.py + double_supertrend.json
    ├── momentum/
    │   ├── macd_rsi.py + macd_rsi.json
    │   ├── stochrsi_supertrend.py + stochrsi_supertrend.json
    │   ├── ttm_squeeze.py + ttm_squeeze.json
    │   └── qqe_signals.py + qqe_signals.json
    └── mean-reversion/
        ├── bb_winner_pro.py + bb_winner_pro.json
        ├── bollinger_breakout.py + bollinger_breakout.json
        ├── mema_bb_rsi.py + mema_bb_rsi.json
        └── multi_bb.py + multi_bb.json

frontend/src/components/quantgen/
└── IndicatorBrowser.tsx                    # New indicator browser panel
```

### Modified Files
```
backend/app/routers/quantgen.py            # +3 endpoints: strategy-catalog, strategy-catalog/{slug}, indicators/catalog
frontend/src/pages/QuantGen/Library.tsx     # +Built-in tab, category filters
frontend/src/pages/QuantGen/Builder.tsx     # +Indicator Browser panel, ?load=<slug> auto-load
```

---

### Task 0: Install pandas_ta

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Add pandas_ta to requirements**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/backend
echo "pandas_ta>=0.3.14b0" >> requirements.txt
```

- [ ] **Install the package**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/backend && ./venv/bin/pip install pandas_ta 2>&1 | tail -5
```

Expected: Successfully installed pandas_ta

- [ ] **Verify it works**

```bash
/Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/backend/venv/bin/python -c "import pandas_ta as ta; print(len(ta.all_indicators), 'indicators'); print(ta.all_indicators[:10])"
```

Expected: Shows 130+ indicators including "supertrend", "kdj", "ttm_squeeze", etc.

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/requirements.txt && git commit -m "chore: add pandas_ta for Pine Script indicator translations"
```

---

### Task 1: Create indicator_registry.py

**Files:**
- Create: `backend/app/services/indicator_registry.py`

- [ ] **Write indicator_registry.py**

```python
"""
Indicator Registry — aggregates indicator metadata from all available sources.

Sources:
1. ta library (Technical Analysis Library, ~30 indicators)
2. VectorBT built-in indicators (~7 indicators)
3. Alorse translated indicators (from strategies/catalog/)
4. pandas-ta (130+ indicators, available but not primary for translations)

Returns unified catalog for the Indicator Browser frontend.
"""

from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# ── ta library indicators ──────────────────────────────────────────────────
TA_INDICATORS: List[Dict] = [
    # Momentum
    {"name": "RSI", "source": "ta", "category": "momentum",
     "description": "Relative Strength Index — measures speed and magnitude of price changes",
     "params": [{"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}],
     "code_snippet": "from ta.momentum import RSIIndicator\nrsi = RSIIndicator(close, window=14).rsi()",
     "pine_equivalent": "ta.rsi(src, len)"},
    {"name": "StochRSI", "source": "ta", "category": "momentum",
     "description": "Stochastic RSI — RSI-based stochastic oscillator",
     "params": [{"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "RSI period"},
                {"name": "smooth1", "type": "int", "default": 3, "min": 1, "max": 20, "description": "Stochastic %K smoothing"},
                {"name": "smooth2", "type": "int", "default": 3, "min": 1, "max": 20, "description": "Stochastic %D smoothing"}],
     "code_snippet": "from ta.momentum import StochRSIIndicator\nstoch_rsi = StochRSIIndicator(close, window=14, smooth1=3, smooth2=3).stochrsi()",
     "pine_equivalent": "ta.stochrsi(src, len)"},
    {"name": "MACD", "source": "ta", "category": "momentum",
     "description": "Moving Average Convergence Divergence — trend-following momentum indicator",
     "params": [{"name": "window_fast", "type": "int", "default": 12, "min": 2, "max": 50, "description": "Fast EMA period"},
                {"name": "window_slow", "type": "int", "default": 26, "min": 5, "max": 100, "description": "Slow EMA period"},
                {"name": "window_sign", "type": "int", "default": 9, "min": 2, "max": 50, "description": "Signal line period"}],
     "code_snippet": "from ta.trend import MACD\nmacd = MACD(close, window_slow=26, window_fast=12, window_sign=9)\nmacd_line = macd.macd()\nsignal = macd.macd_signal()\nhistogram = macd.macd_diff()",
     "pine_equivalent": "ta.macd(src, fastlen, slowlen, siglen)"},
    {"name": "Williams %R", "source": "ta", "category": "momentum",
     "description": "Williams Percent Range — overbought/oversold indicator",
     "params": [{"name": "lbp", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}],
     "code_snippet": "from ta.momentum import WilliamsRIndicator\nwr = WilliamsRIndicator(high, low, close, lbp=14).williams_r()",
     "pine_equivalent": "ta.wr(src, len)"},
    {"name": "ROC", "source": "ta", "category": "momentum",
     "description": "Rate of Change — price change rate",
     "params": [{"name": "window", "type": "int", "default": 12, "min": 2, "max": 100, "description": "Lookback period"}],
     "code_snippet": "from ta.momentum import ROCIndicator\nroc = ROCIndicator(close, window=12).roc()",
     "pine_equivalent": "ta.roc(src, len)"},
    {"name": "Awesome Oscillator", "source": "ta", "category": "momentum",
     "description": "Awesome Oscillator — midpoint momentum",
     "params": [{"name": "window1", "type": "int", "default": 5, "min": 2, "max": 50, "description": "Fast period"},
                {"name": "window2", "type": "int", "default": 34, "min": 5, "max": 100, "description": "Slow period"}],
     "code_snippet": "from ta.momentum import AwesomeOscillatorIndicator\nao = AwesomeOscillatorIndicator(high, low, window1=5, window2=34).awesome_oscillator()",
     "pine_equivalent": "ta.ao(high, low, fastlen, slowlen)"},
    {"name": "KAMA", "source": "ta", "category": "momentum",
     "description": "Kaufman's Adaptive Moving Average",
     "params": [{"name": "window", "type": "int", "default": 10, "min": 2, "max": 100, "description": "Period"},
                {"name": "pow1", "type": "int", "default": 2, "min": 1, "max": 10, "description": "Fastest EMA constant"},
                {"name": "pow2", "type": "int", "default": 30, "min": 5, "max": 50, "description": "Slowest EMA constant"}],
     "code_snippet": "from ta.momentum import KAMAIndicator\nkama = KAMAIndicator(close, window=10, pow1=2, pow2=30).kama()",
     "pine_equivalent": "ta.kama(src, len)"},
    # Trend
    {"name": "EMA", "source": "ta", "category": "trend",
     "description": "Exponential Moving Average",
     "params": [{"name": "window", "type": "int", "default": 20, "min": 2, "max": 200, "description": "Period"}],
     "code_snippet": "from ta.trend import EMAIndicator\nema = EMAIndicator(close, window=20).ema_indicator()",
     "pine_equivalent": "ta.ema(src, len)"},
    {"name": "SMA", "source": "ta", "category": "trend",
     "description": "Simple Moving Average",
     "params": [{"name": "window", "type": "int", "default": 20, "min": 2, "max": 200, "description": "Period"}],
     "code_snippet": "from ta.trend import SMAIndicator\nsma = SMAIndicator(close, window=20).sma_indicator()",
     "pine_equivalent": "ta.sma(src, len)"},
    {"name": "ADX", "source": "ta", "category": "trend",
     "description": "Average Directional Movement Index — trend strength",
     "params": [{"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Period"}],
     "code_snippet": "from ta.trend import ADXIndicator\nadx = ADXIndicator(high, low, close, window=14)\nadx_val = adx.adx()\nplus_di = adx.adx_pos()\nminus_di = adx.adx_neg()",
     "pine_equivalent": "ta.adx(high, low, close, len)"},
    {"name": "Aroon", "source": "ta", "category": "trend",
     "description": "Aroon Indicator — trend change detection",
     "params": [{"name": "window", "type": "int", "default": 25, "min": 2, "max": 100, "description": "Period"}],
     "code_snippet": "from ta.trend import AroonIndicator\naroon = AroonIndicator(close, window=25)\naroon_up = aroon.aroon_up()\naroon_down = aroon.aroon_down()",
     "pine_equivalent": "ta.aroon(high, low, len)"},
    {"name": "PSAR", "source": "ta", "category": "trend",
     "description": "Parabolic SAR — trend direction and potential reversals",
     "params": [{"name": "step", "type": "float", "default": 0.02, "min": 0.001, "max": 0.1, "description": "Acceleration factor"},
                {"name": "max_step", "type": "float", "default": 0.2, "min": 0.01, "max": 0.5, "description": "Maximum acceleration factor"}],
     "code_snippet": "from ta.trend import PSARIndicator\npsar = PSARIndicator(high, low, close, step=0.02, max_step=0.2).psar()",
     "pine_equivalent": "ta.sar(high, low, step, max)"},
    {"name": "Ichimoku Cloud", "source": "ta", "category": "trend",
     "description": "Ichimoku Kinko Hyo — comprehensive trend/volume/support-resistance",
     "params": [{"name": "window1", "type": "int", "default": 9, "min": 2, "max": 50, "description": "Tenkan-sen period"},
                {"name": "window2", "type": "int", "default": 26, "min": 5, "max": 100, "description": "Kijun-sen period"},
                {"name": "window3", "type": "int", "default": 52, "min": 10, "max": 200, "description": "Senkou Span B period"}],
     "code_snippet": "from ta.trend import IchimokuIndicator\nichimoku = IchimokuIndicator(high, low, window1=9, window2=26, window3=52)\ntenkan = ichimoku.ichimoku_conversion_line()\nkijun = ichimoku.ichimoku_base_line()",
     "pine_equivalent": "ta.ichimoku(high, low, tenkan, kijun, senkou)"},
    {"name": "CCI", "source": "ta", "category": "trend",
     "description": "Commodity Channel Index — cyclical trend detection",
     "params": [{"name": "window", "type": "int", "default": 20, "min": 2, "max": 100, "description": "Period"}],
     "code_snippet": "from ta.trend import CCIIndicator\ncci = CCIIndicator(high, low, close, window=20).cci()",
     "pine_equivalent": "ta.cci(high, low, close, len)"},
    # Volume
    {"name": "OBV", "source": "ta", "category": "volume",
     "description": "On-Balance Volume — volume accumulation/distribution",
     "params": [],
     "code_snippet": "from ta.volume import OnBalanceVolumeIndicator\nobv = OnBalanceVolumeIndicator(close, volume).on_balance_volume()",
     "pine_equivalent": "ta.obv(close, volume)"},
    {"name": "MFI", "source": "ta", "category": "volume",
     "description": "Money Flow Index — volume-weighted RSI",
     "params": [{"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Period"}],
     "code_snippet": "from ta.volume import MFIIndicator\nmfi = MFIIndicator(high, low, close, volume, window=14).money_flow_index()",
     "pine_equivalent": "ta.mfi(high, low, close, volume, len)"},
    {"name": "Chaikin Money Flow", "source": "ta", "category": "volume",
     "description": "Chaikin Money Flow — volume-weighted accumulation/distribution",
     "params": [{"name": "window", "type": "int", "default": 20, "min": 2, "max": 100, "description": "Period"}],
     "code_snippet": "from ta.volume import ChaikinMoneyFlowIndicator\ncmf = ChaikinMoneyFlowIndicator(high, low, close, volume, window=20).chaikin_money_flow()",
     "pine_equivalent": "ta.cmf(high, low, close, volume, len)"},
    {"name": "Volume Price Trend", "source": "ta", "category": "volume",
     "description": "Volume Price Trend — cumulative volume-based trend",
     "params": [],
     "code_snippet": "from ta.volume import VolumePriceTrendIndicator\nvpt = VolumePriceTrendIndicator(close, volume).volume_price_trend()",
     "pine_equivalent": "ta.vpt(close, volume)"},
    # Volatility
    {"name": "Bollinger Bands", "source": "ta", "category": "volatility",
     "description": "Bollinger Bands — volatility bands around moving average",
     "params": [{"name": "window", "type": "int", "default": 20, "min": 2, "max": 100, "description": "Period"},
                {"name": "window_dev", "type": "int", "default": 2, "min": 1, "max": 5, "description": "Standard deviation multiplier"}],
     "code_snippet": "from ta.volatility import BollingerBands\nbb = BollingerBands(close, window=20, window_dev=2)\nbb_upper = bb.bollinger_hband()\nbb_lower = bb.bollinger_lband()\nbb_mid = bb.bollinger_mavg()",
     "pine_equivalent": "ta.bb(src, len, mult)"},
    {"name": "Average True Range", "source": "ta", "category": "volatility",
     "description": "Average True Range — market volatility measure",
     "params": [{"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Period"}],
     "code_snippet": "from ta.volatility import AverageTrueRange\natr = AverageTrueRange(high, low, close, window=14).average_true_range()",
     "pine_equivalent": "ta.atr(high, low, close, len)"},
]

# ── VectorBT built-in indicators ────────────────────────────────────────────
VBT_INDICATORS: List[Dict] = [
    {"name": "VBT MA", "source": "vectorbt", "category": "trend",
     "description": "Moving Average (VectorBT) — simple/weighted/exponential",
     "params": [{"name": "window", "type": "int", "default": 10, "min": 2, "max": 200, "description": "Period"}],
     "code_snippet": "ma = vbt.MA.run(close, window=10).ma",
     "pine_equivalent": "ta.sma(src, len) / ta.ema(src, len)"},
    {"name": "VBT RSI", "source": "vectorbt", "category": "momentum",
     "description": "Relative Strength Index (VectorBT)",
     "params": [{"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Period"}],
     "code_snippet": "rsi = vbt.RSI.run(close, window=14).rsi",
     "pine_equivalent": "ta.rsi(src, len)"},
    {"name": "VBT BBANDS", "source": "vectorbt", "category": "volatility",
     "description": "Bollinger Bands (VectorBT)",
     "params": [{"name": "window", "type": "int", "default": 20, "min": 2, "max": 100, "description": "Period"},
                {"name": "alpha", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "description": "Standard deviation multiplier"}],
     "code_snippet": "bb = vbt.BBANDS.run(close, window=20, alpha=2.0)\nbb_upper = bb.upper\nbb_lower = bb.lower\nbb_mid = bb.middle",
     "pine_equivalent": "ta.bb(src, len, mult)"},
    {"name": "VBT MACD", "source": "vectorbt", "category": "momentum",
     "description": "MACD (VectorBT)",
     "params": [{"name": "fast_window", "type": "int", "default": 12, "min": 2, "max": 50, "description": "Fast EMA period"},
                {"name": "slow_window", "type": "int", "default": 26, "min": 5, "max": 100, "description": "Slow EMA period"},
                {"name": "signal_window", "type": "int", "default": 9, "min": 2, "max": 50, "description": "Signal line period"}],
     "code_snippet": "macd = vbt.MACD.run(close, fast_window=12, slow_window=26, signal_window=9)\nmacd_line = macd.macd\nsignal = macd.signal\nhistogram = macd.histogram",
     "pine_equivalent": "ta.macd(src, fastlen, slowlen, siglen)"},
    {"name": "VBT STOCH", "source": "vectorbt", "category": "momentum",
     "description": "Stochastic Oscillator (VectorBT)",
     "params": [{"name": "k_window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "%K period"},
                {"name": "d_window", "type": "int", "default": 3, "min": 1, "max": 20, "description": "%D smoothing"}],
     "code_snippet": "stoch = vbt.STOCH.run(high, low, close, k_window=14, d_window=3)\nstoch_k = stoch.percent_k\nstoch_d = stoch.percent_d",
     "pine_equivalent": "ta.stoch(high, low, close, k, d)"},
    {"name": "VBT ATR", "source": "vectorbt", "category": "volatility",
     "description": "Average True Range (VectorBT)",
     "params": [{"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Period"}],
     "code_snippet": "atr = vbt.ATR.run(high, low, close, window=14).atr",
     "pine_equivalent": "ta.atr(high, low, close, len)"},
    {"name": "VBT OBV", "source": "vectorbt", "category": "volume",
     "description": "On-Balance Volume (VectorBT)",
     "params": [],
     "code_snippet": "obv = vbt.OBV.run(close, volume).obv",
     "pine_equivalent": "ta.obv(close, volume)"},
]

# ── pandas-ta indicators (subset useful for translations) ────────────────────
PANDAS_TA_INDICATORS: List[Dict] = [
    {"name": "Supertrend", "source": "pandas-ta", "category": "trend",
     "description": "Supertrend — ATR-based trailing stop indicator",
     "params": [{"name": "length", "type": "int", "default": 10, "min": 2, "max": 100, "description": "ATR period"},
                {"name": "multiplier", "type": "float", "default": 3.0, "min": 0.5, "max": 10.0, "description": "ATR multiplier"}],
     "code_snippet": "import pandas_ta as ta\nst = ta.supertrend(high, low, close, length=10, multiplier=3.0)\ntrend = st[f'SUPERTd_{10}_{3.0}']\nline = st[f'SUPERT_{10}_{3.0}']",
     "pine_equivalent": "ta.supertrend(high, low, close, length, mult)"},
    {"name": "TTM Squeeze", "source": "pandas-ta", "category": "volatility",
     "description": "TTM Squeeze — Bollinger Bands / Keltner Channel volatility squeeze",
     "params": [{"name": "length", "type": "int", "default": 20, "min": 5, "max": 50, "description": "BB/KC period"},
                {"name": "bb_mult", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "description": "BB standard deviation multiplier"},
                {"name": "kc_mult", "type": "float", "default": 1.5, "min": 0.5, "max": 5.0, "description": "KC ATR multiplier"}],
     "code_snippet": "import pandas_ta as ta\nttm = ta.ttm_squeeze(high, low, close, length=20, bb_mult=2.0, kc_mult=1.5)\nsqueeze_on = ttm['SQZ_20_2.0_1.5']",
     "pine_equivalent": "ttm_squeeze(high, low, close, length, bb_mult, kc_mult)"},
    {"name": "KDJ", "source": "pandas-ta", "category": "momentum",
     "description": "KDJ Indicator — derivative of Stochastic Oscillator with smoothed lines",
     "params": [{"name": "length", "type": "int", "default": 9, "min": 2, "max": 50, "description": "RSV period"},
                {"name": "signal_length", "type": "int", "default": 3, "min": 1, "max": 20, "description": "K/D smoothing"}],
     "code_snippet": "import pandas_ta as ta\nkdj = ta.kdj(high, low, close, length=9, signal_length=3)\nk = kdj['K_9_3']\nd = kdj['D_9_3']\nj = kdj['J_9_3']",
     "pine_equivalent": "ta.kdj(high, low, close, k, d)"},
]


def get_indicator_catalog(
    category: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict]:
    """
    Return unified indicator catalog from all sources.
    Optionally filter by category or search query.
    """
    all_indicators = TA_INDICATORS + VBT_INDICATORS + PANDAS_TA_INDICATORS

    if category and category != "all":
        all_indicators = [i for i in all_indicators if i["category"] == category]

    if search:
        search_lower = search.lower()
        all_indicators = [
            i for i in all_indicators
            if search_lower in i["name"].lower()
            or search_lower in i["description"].lower()
        ]

    return all_indicators


def get_indicator_sources() -> List[str]:
    """Return list of available indicator sources."""
    return ["ta", "vectorbt", "pandas-ta"]


def get_indicator_categories() -> List[str]:
    """Return list of available indicator categories."""
    return ["momentum", "trend", "volatility", "volume"]
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/app/services/indicator_registry.py && git commit -m "feat: add indicator_registry module aggregating ta, vbt, pandas-ta"
```

---

### Task 2: Add /indicators/catalog endpoint

**Files:**
- Modify: `backend/app/routers/quantgen.py`

- [ ] **Add import and endpoint to quantgen.py** (after the last import, before `router = APIRouter()`)

```python
from app.services.indicator_registry import get_indicator_catalog
```

- [ ] **Add the indicators/catalog route** (after the existing `/indicators` route around line 765)

```python
@router.get("/indicators/catalog")
async def list_indicator_catalog(
    category: Optional[str] = Query(None, description="Filter by category: momentum, trend, volatility, volume"),
    search: Optional[str] = Query(None, description="Search by name or description"),
):
    """
    List all available indicators with metadata from all sources.
    Sources: ta library, VectorBT, pandas-ta.
    """
    try:
        indicators = get_indicator_catalog(category=category, search=search)
        categories = get_indicator_categories()

        # Build a source count summary
        from collections import Counter
        source_counts = Counter(i["source"] for i in indicators)

        return {
            "success": True,
            "data": {
                "indicators": indicators,
                "count": len(indicators),
                "categories": categories,
                "source_counts": dict(source_counts),
            },
            "message": f"Found {len(indicators)} indicators"
        }
    except Exception as e:
        logger.error("Error listing indicator catalog: %s", e)
        return {
            "success": False,
            "error": str(e),
            "data": {"indicators": [], "count": 0}
        }
```

Need to add the import for `Query` and `Optional` at the top of the file:

```python
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
```

Also add imports for the helper functions:
```python
from app.services.indicator_registry import get_indicator_catalog, get_indicator_categories
```

- [ ] **Test the endpoint**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1
source backend/venv/bin/activate
python -c "
from backend.app.services.indicator_registry import get_indicator_catalog
indicators = get_indicator_catalog()
print(f'Total indicators: {len(indicators)}')
cats = set(i['category'] for i in indicators)
print(f'Categories: {cats}')
srcs = set(i['source'] for i in indicators)
print(f'Sources: {srcs}')
"
```

Expected: Total ~30+ indicators, categories momentum/trend/volatility/volume, sources ta/vectorbt/pandas-ta

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/app/routers/quantgen.py && git commit -m "feat: add /api/quantgen/indicators/catalog endpoint"
```

---

### Task 3: Create IndicatorBrowser.tsx component

**Files:**
- Create: `frontend/src/components/quantgen/IndicatorBrowser.tsx`

- [ ] **Write IndicatorBrowser.tsx**

```tsx
import { useState, useEffect, useCallback } from 'react';
import { Search, Plus, ChevronDown, ChevronRight, Code2, Box } from 'lucide-react';

interface IndicatorParam {
  name: string;
  type: string;
  default: number | string;
  min?: number;
  max?: number;
  description?: string;
}

interface Indicator {
  name: string;
  source: string;
  category: string;
  description: string;
  params: IndicatorParam[];
  code_snippet: string;
  pine_equivalent?: string;
}

interface IndicatorBrowserProps {
  onInsertSnippet: (snippet: string) => void;
}

const SOURCE_BADGE_COLORS: Record<string, string> = {
  ta: 'rgba(59, 130, 246, 0.12)',
  vectorbt: 'rgba(139, 92, 246, 0.12)',
  'pandas-ta': 'rgba(16, 185, 129, 0.12)',
};

const SOURCE_TEXT_COLORS: Record<string, string> = {
  ta: '#3b82f6',
  vectorbt: '#8b5cf6',
  'pandas-ta': '#10b981',
};

const CATEGORY_CHIPS = ['all', 'momentum', 'trend', 'volatility', 'volume'];

export function IndicatorBrowser({ onInsertSnippet }: IndicatorBrowserProps) {
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [filtered, setFiltered] = useState<Indicator[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [expandedIndices, setExpandedIndices] = useState<Set<number>>(new Set());
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    fetch('/api/quantgen/indicators/catalog')
      .then(r => r.json())
      .then(data => {
        if (data.success && data.data?.indicators) {
          setIndicators(data.data.indicators);
          setFiltered(data.data.indicators);
        }
      })
      .catch(() => {})
      .finally(() => setIsLoaded(true));
  }, []);

  useEffect(() => {
    let result = indicators;
    if (activeCategory !== 'all') {
      result = result.filter(i => i.category === activeCategory);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        i => i.name.toLowerCase().includes(q) || i.description.toLowerCase().includes(q)
      );
    }
    setFiltered(result);
    setExpandedIndices(new Set());
  }, [searchQuery, activeCategory, indicators]);

  const toggleExpand = (idx: number) => {
    setExpandedIndices(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const handleInsert = useCallback((snippet: string) => {
    onInsertSnippet(snippet);
  }, [onInsertSnippet]);

  if (!isLoaded) {
    return (
      <div style={{ padding: '16px', color: 'var(--muted)', fontSize: '13px', textAlign: 'center' }}>
        Loading indicators...
      </div>
    );
  }

  return (
    <div>
      {/* Search */}
      <div style={{ position: 'relative', marginBottom: '12px' }}>
        <Search size={13} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--subtle)' }} />
        <input
          type="text"
          placeholder="Search indicators..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: '100%',
            padding: '7px 10px 7px 30px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            backgroundColor: 'var(--canvas)',
            color: 'var(--foreground)',
            fontSize: '12px',
            outline: 'none',
          }}
        />
      </div>

      {/* Category chips */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap' }}>
        {CATEGORY_CHIPS.map(cat => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            style={{
              padding: '4px 10px',
              borderRadius: '999px',
              fontSize: '11px',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              backgroundColor: activeCategory === cat ? 'var(--accent)' : 'var(--surface)',
              color: activeCategory === cat ? '#000000' : 'var(--subtle)',
              textTransform: 'capitalize',
            }}
          >
            {cat === 'all' ? 'All' : cat}
          </button>
        ))}
      </div>

      {/* Results count */}
      <div style={{ fontSize: '11px', color: 'var(--subtle)', marginBottom: '8px', padding: '0 4px' }}>
        {filtered.length} indicator{filtered.length !== 1 ? 's' : ''}
      </div>

      {/* Indicator list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {filtered.map((indicator, idx) => {
          const isExpanded = expandedIndices.has(idx);
          const sourceColor = SOURCE_BADGE_COLORS[indicator.source] || 'var(--surface)';
          const sourceTextColor = SOURCE_TEXT_COLORS[indicator.source] || 'var(--muted)';

          return (
            <div key={idx} style={{
              borderRadius: '8px',
              border: `1px solid ${isExpanded ? 'var(--accent)' : 'var(--border)'}`,
              overflow: 'hidden',
              transition: 'border-color 0.1s',
            }}>
              {/* Header row */}
              <div
                onClick={() => toggleExpand(idx)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 10px',
                  cursor: 'pointer',
                  backgroundColor: 'var(--surface)',
                }}
              >
                {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <span style={{ flex: 1, fontSize: '12px', fontWeight: 600, color: 'var(--foreground)' }}>
                  {indicator.name}
                </span>
                <span style={{
                  padding: '2px 6px',
                  borderRadius: '4px',
                  fontSize: '10px',
                  fontWeight: 600,
                  backgroundColor: sourceColor,
                  color: sourceTextColor,
                }}>
                  {indicator.source}
                </span>
              </div>

              {/* Expanded content */}
              {isExpanded && (
                <div style={{
                  padding: '8px 10px 10px',
                  borderTop: '1px solid var(--border)',
                  backgroundColor: 'var(--canvas)',
                }}>
                  <p style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px', lineHeight: 1.5 }}>
                    {indicator.description}
                  </p>

                  {indicator.params.length > 0 && (
                    <div style={{ marginBottom: '8px' }}>
                      <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--subtle)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Parameters
                      </div>
                      {indicator.params.map((p, pi) => (
                        <div key={pi} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', padding: '2px 0', color: 'var(--muted)' }}>
                          <span>{p.name}</span>
                          <span style={{ color: 'var(--subtle)' }}>
                            {p.type}={p.default}
                            {p.min != null && p.max != null ? ` [${p.min}-${p.max}]` : ''}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {indicator.code_snippet && (
                    <div style={{ marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px', fontWeight: 600, color: 'var(--subtle)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        <Code2 size={10} />
                        Code
                      </div>
                      <pre style={{
                        margin: 0,
                        padding: '8px',
                        borderRadius: '6px',
                        fontSize: '10px',
                        lineHeight: 1.4,
                        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                        backgroundColor: 'var(--surface)',
                        color: 'var(--foreground)',
                        overflowX: 'auto',
                        whiteSpace: 'pre-wrap',
                      }}>
                        {indicator.code_snippet}
                      </pre>
                    </div>
                  )}

                  <button
                    onClick={() => handleInsert(indicator.code_snippet)}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '11px',
                      fontWeight: 600,
                      border: 'none',
                      cursor: 'pointer',
                      backgroundColor: 'var(--accent)',
                      color: '#000000',
                    }}
                  >
                    <Plus size={11} />
                    Insert at Cursor
                  </button>
                </div>
              )}
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: '24px 16px', color: 'var(--muted)', fontSize: '12px' }}>
            No indicators match your search.
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add frontend/src/components/quantgen/IndicatorBrowser.tsx && git commit -m "feat: add IndicatorBrowser component with search, categories, snippet insert"
```

---

### Task 4: Integrate IndicatorBrowser into Builder.tsx

**Files:**
- Modify: `frontend/src/pages/QuantGen/Builder.tsx`

- [ ] **Add import and state for the IndicatorBrowser** (alongside existing imports at the top)

```tsx
import { IndicatorBrowser } from '@/components/quantgen/IndicatorBrowser';
import { useRef } from 'react';  // Already imported - verify
```

- [ ] **Add editor ref for Monaco** (declare alongside other refs around line 122)

```tsx
const editorRef = useRef<any>(null);
```

- [ ] **Add handleInsertSnippet callback** (after `replaceDatesInCode` around line 168)

```tsx
const handleInsertSnippet = useCallback((snippet: string) => {
  const editor = editorRef.current;
  if (editor) {
    const position = editor.getPosition();
    editor.executeEdits('indicator-browser', [
      {
        range: {
          startLineNumber: position.lineNumber,
          startColumn: position.column,
          endLineNumber: position.lineNumber,
          endColumn: position.column,
        },
        text: snippet + '\n',
      },
    ]);
    editor.focus();
  } else {
    // Fallback: append to code
    setCode(prev => prev + '\n' + snippet + '\n');
  }
}, []);
```

- [ ] **Pass editorRef to Monaco Editor's onMount** (find the Monaco Editor render and add onMount)

Find the `<Editor` component in the Builder's JSX and add `onMount`:

```tsx
<Editor
  // ... existing props
  onMount={(editor) => { editorRef.current = editor; }}
/>
```

- [ ] **Add the IndicatorBrowser panel to the sidebar** (find the right location in the JSX, likely near the existing indicator panel or chat panel)

Add a collapsible section, for example after the chat panel or as a new sidebar section:

```tsx
{/* Indicator Browser */}
<div style={{ marginBottom: '12px' }}>
  <button
    onClick={() => setIsIndicatorBrowserOpen(!isIndicatorBrowserOpen)}
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      width: '100%',
      padding: '8px 12px',
      borderRadius: '8px',
      border: 'none',
      backgroundColor: 'var(--surface)',
      color: 'var(--foreground)',
      fontSize: '12px',
      fontWeight: 600,
      cursor: 'pointer',
      textAlign: 'left',
    }}
  >
    <Box size={14} />
    Indicator Browser
    <span style={{ marginLeft: 'auto' }}>
      {isIndicatorBrowserOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
    </span>
  </button>
  {isIndicatorBrowserOpen && (
    <div style={{
      marginTop: '8px',
      padding: '12px',
      borderRadius: '8px',
      backgroundColor: 'var(--surface)',
      border: '1px solid var(--border)',
      maxHeight: '400px',
      overflowY: 'auto',
    }}>
      <IndicatorBrowser onInsertSnippet={handleInsertSnippet} />
    </div>
  )}
</div>
```

- [ ] **Add state for the panel visibility** (declare alongside other states around line 124)

```tsx
const [isIndicatorBrowserOpen, setIsIndicatorBrowserOpen] = useState(false);
```

Also import `Box` from lucide-react if not already imported:
```tsx
import { ..., Box, ... } from "lucide-react";
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add frontend/src/pages/QuantGen/Builder.tsx && git commit -m "feat: integrate IndicatorBrowser panel into Builder"
```

---

### Task 5: Create strategy catalog infrastructure + route

**Files:**
- Create: `backend/strategies/catalog/` (directory structure)
- Modify: `backend/app/routers/quantgen.py`

- [ ] **Create directory structure**

```bash
mkdir -p /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/backend/strategies/catalog/{trend,momentum,mean-reversion}
touch /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/backend/strategies/__init__.py
touch /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/backend/strategies/catalog/__init__.py
```

- [ ] **Add strategy catalog route to quantgen.py**

```python
import json
from pathlib import Path

STRATEGY_CATALOG_DIR = Path(__file__).resolve().parent.parent.parent / "strategies" / "catalog"


@router.get("/strategy-catalog")
async def list_strategy_catalog():
    """
    List all built-in strategies from the catalog, grouped by category.
    """
    try:
        catalog_dir = STRATEGY_CATALOG_DIR
        if not catalog_dir.exists():
            return {
                "success": True,
                "data": {"categories": [], "strategies": [], "count": 0},
                "message": "No strategies in catalog"
            }

        strategies = []
        for category_dir in sorted(catalog_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            category = category_dir.name
            for json_file in sorted(category_dir.glob("*.json")):
                with open(json_file) as f:
                    meta = json.load(f)
                strategies.append(meta)

        # Group by category
        categories = {}
        for s in strategies:
            cat = s.get("category", "other")
            if cat not in categories:
                categories[cat] = []
            # Return metadata without the full code
            categories[cat].append({k: v for k, v in s.items() if k != "code"})

        return {
            "success": True,
            "data": {
                "categories": list(categories.keys()),
                "strategies_by_category": categories,
                "count": len(strategies),
            },
            "message": f"Found {len(strategies)} strategies"
        }
    except Exception as e:
        logger.error("Error listing strategy catalog: %s", e)
        return {"success": False, "error": str(e)}


@router.get("/strategy-catalog/{slug}")
async def get_strategy_code(slug: str):
    """
    Get a specific strategy's Python code and metadata.
    """
    try:
        # Search all category directories for the matching slug
        catalog_dir = STRATEGY_CATALOG_DIR
        for json_file in catalog_dir.rglob(f"{slug}.json"):
            py_file = json_file.with_suffix(".py")
            if not py_file.exists():
                return {"success": False, "error": "Strategy code file not found"}

            with open(json_file) as f:
                metadata = json.load(f)
            with open(py_file) as f:
                code = f.read()

            return {
                "success": True,
                "data": {
                    "metadata": metadata,
                    "code": code,
                },
                "message": f"Loaded strategy: {metadata.get('name', slug)}"
            }

        return {"success": False, "error": f"Strategy '{slug}' not found"}
    except Exception as e:
        logger.error("Error loading strategy %s: %s", slug, e)
        return {"success": False, "error": str(e)}
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/strategies/ backend/app/routers/quantgen.py && git commit -m "feat: add strategy catalog infrastructure and API routes"
```

---

### Task 6: Translate macd_rsi.py (Momentum — pattern establisher)

**Files:**
- Create: `backend/strategies/catalog/momentum/macd_rsi.py`
- Create: `backend/strategies/catalog/momentum/macd_rsi.json`

This is the first and simplest translation. It establishes the pattern all others will follow.

Original Pine Script logic:
- MACD line (fast_ma - slow_ma) with signal line
- Crossover(bull) = macd crosses above signal AND RSI was recently oversold (< 30)
- Crossunder(bear) = macd crosses below signal AND RSI was recently overbought (> 70)
- Entry on bull_cross (long only)
- Exit on bear_cross
- Stop loss at entry_price * (1 - SL%)

- [ ] **Read the original Pine Script to confirm logic**

```bash
cat /tmp/pinescript-strategies/strategies/momentum/MACD+RSI.pine
```

- [ ] **Write macd_rsi.py**

```python
"""
MACD + RSI Strategy [Alorse] — Python translation
Original: strategies/momentum/MACD+RSI.pine

Entry: MACD crosses above signal line AND RSI was < oversold_level in last N candles
Exit: MACD crosses below signal line AND RSI was > overbought_level in last N candles
Stop: Fixed percentage stop loss from entry price
"""
import numpy as np
import vectorbt as vbt

# ── Parameters (tunable by QuantGen optimizer) ──────────────────────────
fast_length = 12          # MACD fast EMA period
slow_length = 26          # MACD slow EMA period
signal_length = 9         # MACD signal line period
rsi_length = 14           # RSI period
rsi_oversold = 30         # RSI oversold threshold
rsi_overbought = 70       # RSI overbought threshold
rsi_lookback = 5          # Check RSI condition over last N candles
stop_loss_pct = 0.01      # 1% stop loss (Pine default: 0.99 meaning 1%)

# ── Data Loading ────────────────────────────────────────────────────────
# ohlcv: DataFrame with columns ['Open', 'High', 'Low', 'Close', 'Volume']
# For multi-ticker: MultiIndex with ticker level 1

close = ohlcv['Close']

# ── Indicator Computation ───────────────────────────────────────────────
from ta.trend import MACD
from ta.momentum import RSIIndicator

macd = MACD(close, window_slow=slow_length, window_fast=fast_length, window_sign=signal_length)
macd_line = macd.macd()
signal_line = macd.macd_signal()

rsi = RSIIndicator(close, window=rsi_length).rsi()

# ── Signal Generation (VectorBT-compatible) ─────────────────────────────
# MACD crossover / crossunder
bull_cross = vbt.combine_logic(
    macd_line.vbt.gt(signal_line),
    macd_line.shift(1).vbt.lt(signal_line.shift(1)),
    combine_func=np.logical_and
)

bear_cross = vbt.combine_logic(
    macd_line.vbt.lt(signal_line),
    macd_line.shift(1).vbt.gt(signal_line.shift(1)),
    combine_func=np.logical_and
)

# RSI condition: was RSI below oversold in lookback period?
# Using rolling min: if min RSI over last N periods <= oversold level
rsi_was_oversold = rsi.rolling(rsi_lookback).min().vbt.lt(rsi_oversold)
rsi_was_overbought = rsi.rolling(rsi_lookback).max().vbt.gt(rsi_overbought)

# Entry: MACD bull cross AND RSI was recently oversold
entries = vbt.combine_logic(
    bull_cross,
    rsi_was_oversold,
    combine_func=np.logical_and
)

# Exit: MACD bear cross (OR stop loss — handled by Portfolio)
exits = bear_cross

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    sl_stop=stop_loss_pct,       # VectorBT handles stop loss natively
    broadcast_kwargs={'keep_pd': True},
    jitted=True,
    direction='longonly',
)
```

- [ ] **Write macd_rsi.json**

```json
{
  "name": "MACD + RSI Strategy",
  "slug": "macd_rsi",
  "category": "momentum",
  "description": "MACD crossover with RSI oversold/overbought confirmation. Enters long when MACD crosses above signal line after RSI was recently oversold. Exits on bearish MACD cross.",
  "version": "1.0.0",
  "source": "Alorse/pinescript-strategies",
  "original_file": "strategies/momentum/MACD+RSI.pine",
  "parameters": {
    "fast_length": {"type": "int", "default": 12, "min": 5, "max": 50, "description": "MACD fast EMA period"},
    "slow_length": {"type": "int", "default": 26, "min": 10, "max": 100, "description": "MACD slow EMA period"},
    "signal_length": {"type": "int", "default": 9, "min": 3, "max": 30, "description": "MACD signal line period"},
    "rsi_length": {"type": "int", "default": 14, "min": 5, "max": 50, "description": "RSI period"},
    "rsi_oversold": {"type": "int", "default": 30, "min": 10, "max": 50, "description": "RSI oversold level"},
    "rsi_overbought": {"type": "int", "default": 70, "min": 50, "max": 90, "description": "RSI overbought level"},
    "rsi_lookback": {"type": "int", "default": 5, "min": 1, "max": 20, "description": "Candles to check RSI condition"},
    "stop_loss_pct": {"type": "float", "default": 0.01, "min": 0.001, "max": 0.10, "description": "Stop loss as fraction of entry price"}
  },
  "indicators_used": ["MACD", "RSI"],
  "timeframes": ["1d", "4h", "1h"],
  "signals": {
    "entry_long": "MACD crosses above signal line AND RSI was < oversold level in last N candles",
    "exit_long": "MACD crosses below signal line OR stop loss hit",
    "entry_short": "Not supported (long-only)",
    "exit_short": "Not supported (long-only)"
  }
}
```

- [ ] **Test the strategy with VectorBT**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && backend/venv/bin/python -c "
import pandas as pd
import numpy as np
import vectorbt as vbt

# Generate test OHLCV data
dates = pd.date_range('2023-01-01', '2023-06-30', freq='B')
np.random.seed(42)
close = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
high = close * (1 + np.abs(np.random.randn(len(dates)) * 0.01))
low = close * (1 - np.abs(np.random.randn(len(dates)) * 0.01))
open_p = close.shift(1).fillna(close[0]) * (1 + np.random.randn(len(dates)) * 0.005)
volume = np.random.randint(1000000, 10000000, len(dates))

ohlcv = pd.DataFrame({
    'Open': open_p, 'High': high, 'Low': low, 'Close': close, 'Volume': volume
}, index=dates)

# Run the strategy
exec(open('backend/strategies/catalog/momentum/macd_rsi.py').read())
print(f'Total return: {pf.total_return():.2%}')
print(f'Sharpe ratio: {pf.sharpe_ratio():.2f}')
print(f'Max drawdown: {pf.max_drawdown():.2%}')
print(f'Number of trades: {len(pf.trades())}')
print('macd_rsi.py translation: OK')
" 2>&1
```

Expected: Strategy runs without errors, shows some trades and metrics.

- [ ] **Test with multi-ticker**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && backend/venv/bin/python -c "
import pandas as pd
import numpy as np
import vectorbt as vbt

# Generate multi-ticker OHLCV (3 tickers)
dates = pd.date_range('2023-01-01', '2023-06-30', freq='B')
tickers = ['AAPL', 'MSFT', 'GOOG']
np.random.seed(42)
data = {}
for t in tickers:
    close = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
    data[(t, 'Close')] = close
    data[(t, 'High')] = close * (1 + np.abs(np.random.randn(len(dates)) * 0.01))
    data[(t, 'Low')] = close * (1 - np.abs(np.random.randn(len(dates)) * 0.01))
    data[(t, 'Open')] = close.shift(1).fillna(close[0]) * (1 + np.random.randn(len(dates)) * 0.005)
    data[(t, 'Volume')] = np.random.randint(1000000, 10000000, len(dates))

ohlcv = pd.DataFrame(data, index=dates)
ohlcv.columns = pd.MultiIndex.from_tuples(ohlcv.columns, names=['ticker', 'field'])

exec(open('backend/strategies/catalog/momentum/macd_rsi.py').read())
print(f'Multi-ticker total return: {pf.total_return()}')
print(f'Multi-ticker trades per ticker: {pf.trades().count()}')
print('Multi-ticker test: OK')
" 2>&1
```

Expected: Returns per-ticker results

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/strategies/catalog/momentum/macd_rsi.py backend/strategies/catalog/momentum/macd_rsi.json && git commit -m "feat: translate MACD+RSI strategy (momentum, pattern establisher)"
```

---

### Task 7: Translate supertrend.py (Trend)

**Files:**
- Create: `backend/strategies/catalog/trend/supertrend.py`
- Create: `backend/strategies/catalog/trend/supertrend.json`

Use `pandas_ta` for Supertrend computation. Signal: trend flips from -1 to 1 → buy, 1 to -1 → sell.

- [ ] **Read original Pine Script**

```bash
cat /tmp/pinescript-strategies/strategies/trend/Supertrend.pine
```

- [ ] **Write supertrend.py**

```python
"""
Supertrend Strategy [Alorse] — Python translation
Original: strategies/trend/Supertrend.pine

Entry: Supertrend flips from downtrend to uptrend (trend goes from -1 to +1)
Exit: Supertrend flips from uptrend to downtrend (trend goes from +1 to -1)
Stop: Lowest price over last N bars for long, highest for short
Take profit: Entry + (entry - stop) * tp_factor
"""
import numpy as np
import vectorbt as vbt
import pandas_ta as ta

# ── Parameters ─────────────────────────────────────────────────────────
period = 10               # ATR period
multiplier = 3.7          # ATR multiplier
bars_back = 2             # Bars to look back for stop loss
tp_factor = 1.5           # Take profit multiplier

# ── Data Loading ────────────────────────────────────────────────────────
close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

# ── Indicator Computation ───────────────────────────────────────────────
st = ta.supertrend(high, low, close, length=period, multiplier=multiplier)
col_trend = f'SUPERTd_{period}_{multiplier}'
col_line = f'SUPERT_{period}_{multiplier}'
trend = st[col_trend]        # 1 = uptrend, -1 = downtrend
supertrend_line = st[col_line]

# ── Signal Generation (VectorBT-compatible) ─────────────────────────────
entries = vbt.combine_logic(
    trend.vbt.eq(1),
    trend.shift(1).vbt.eq(-1),
    combine_func=np.logical_and
)

exits = vbt.combine_logic(
    trend.vbt.eq(-1),
    trend.shift(1).vbt.eq(1),
    combine_func=np.logical_and
)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    broadcast_kwargs={'keep_pd': True},
    jitted=True,
    direction='longonly',
    sl_stop=multiplier * ta.atr(high, low, close, length=period).iloc[-1] / close.iloc[-1] if hasattr(ta, 'atr') else None,
)
```

- [ ] **Write supertrend.json**

```json
{
  "name": "Supertrend Strategy",
  "slug": "supertrend",
  "category": "trend",
  "description": "ATR-based trailing stop trend following. Enters long when Supertrend flips to uptrend, exits when it flips to downtrend. Uses ATR-period and multiplier for sensitivity control.",
  "version": "1.0.0",
  "source": "Alorse/pinescript-strategies",
  "original_file": "strategies/trend/Supertrend.pine",
  "parameters": {
    "period": {"type": "int", "default": 10, "min": 5, "max": 50, "description": "ATR period"},
    "multiplier": {"type": "float", "default": 3.7, "min": 1.0, "max": 10.0, "step": 0.1, "description": "ATR multiplier"},
    "bars_back": {"type": "int", "default": 2, "min": 1, "max": 20, "description": "Bars for stop loss calculation"},
    "tp_factor": {"type": "float", "default": 1.5, "min": 0.5, "max": 5.0, "step": 0.1, "description": "Take profit multiplier"}
  },
  "indicators_used": ["Supertrend", "ATR"],
  "timeframes": ["1d", "4h", "1h"],
  "signals": {
    "entry_long": "Supertrend flips from -1 (downtrend) to +1 (uptrend)",
    "exit_long": "Supertrend flips from +1 to -1 || stop loss hit || take profit hit",
    "entry_short": "Not supported (long-only)",
    "exit_short": "Not supported (long-only)"
  }
}
```

- [ ] **Test with VectorBT**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && backend/venv/bin/python -c "
import pandas as pd, numpy as np, vectorbt as vbt
dates = pd.date_range('2023-01-01', '2023-06-30', freq='B')
np.random.seed(42)
close = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
high = close * 1.02; low = close * 0.98; open_p = close.shift(1).fillna(100) * 1.001
volume = np.random.randint(1000000, 10000000, len(dates))
ohlcv = pd.DataFrame({'Open': open_p, 'High': high, 'Low': low, 'Close': close, 'Volume': volume}, index=dates)
exec(open('backend/strategies/catalog/trend/supertrend.py').read())
print(f'Total return: {pf.total_return():.2%}, Sharpe: {pf.sharpe_ratio():.2f}, Trades: {len(pf.trades())}')
print('supertrend.py: OK')
" 2>&1
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/strategies/catalog/trend/supertrend.py backend/strategies/catalog/trend/supertrend.json && git commit -m "feat: translate Supertrend strategy (trend)"
```

---

### Task 8: Translate bollinger_breakout.py (Mean Reversion)

**Files:**
- Create: `backend/strategies/catalog/mean-reversion/bollinger_breakout.py`
- Create: `backend/strategies/catalog/mean-reversion/bollinger_breakout.json`

Original Pine: Bollinger Breakout [kodify]. Enters when close touches lower band (long) or upper band (short), exits at middle band or opposite band.

- [ ] **Read the original Pine Script**

```bash
cat /tmp/pinescript-strategies/strategies/mean-reversion/Bollinger\ Breakout\ \[kodify\].pine
```

- [ ] **Write bollinger_breakout.py**

```python
"""
Bollinger Breakout Strategy [kodify] — Python translation
Original: strategies/mean-reversion/Bollinger Breakout [kodify].pine

Entry (long): Close touches or crosses below lower Bollinger Band
Entry (short): Close touches or crosses above upper Bollinger Band
Exit: Close crosses back above/below the middle band (SMA)
"""
import numpy as np
import vectorbt as vbt

# ── Parameters ─────────────────────────────────────────────────────────
bb_length = 20            # Bollinger Bands SMA period
bb_std = 2.0              # Standard deviation multiplier

# ── Data Loading ────────────────────────────────────────────────────────
close = ohlcv['Close']

# ── Indicator Computation ───────────────────────────────────────────────
from ta.volatility import BollingerBands

bb = BollingerBands(close, window=bb_length, window_dev=bb_std)
bb_upper = bb.bollinger_hband()
bb_lower = bb.bollinger_lband()
bb_mid = bb.bollinger_mavg()

# ── Signal Generation ───────────────────────────────────────────────────
# Long entry: close was above lower band, now at/below it
long_entries = vbt.combine_logic(
    close.vbt.lte(bb_lower),
    close.shift(1).vbt.gt(bb_lower.shift(1)),
    combine_func=np.logical_and
)

# Short entry: close was below upper band, now at/above it
short_entries = vbt.combine_logic(
    close.vbt.gte(bb_upper),
    close.shift(1).vbt.lt(bb_upper.shift(1)),
    combine_func=np.logical_and
)

# Entry: combine long and short
entries = np.where(long_entries, True, np.where(short_entries, True, False))

# Exit: close crosses back to middle band
long_exits = close.vbt.gte(bb_mid)
short_exits = close.vbt.lte(bb_mid)
exits = np.where(long_exits | short_exits, True, False)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    broadcast_kwargs={'keep_pd': True},
    jitted=True,
    direction='both',
)
```

- [ ] **Write bollinger_breakout.json**

```json
{
  "name": "Bollinger Breakout",
  "slug": "bollinger_breakout",
  "category": "mean-reversion",
  "description": "Mean reversion using Bollinger Bands. Buys when price touches lower band, sells short when price touches upper band. Exits at the middle SMA line.",
  "version": "1.0.0",
  "source": "Alorse/pinescript-strategies",
  "original_file": "strategies/mean-reversion/Bollinger Breakout [kodify].pine",
  "parameters": {
    "bb_length": {"type": "int", "default": 20, "min": 5, "max": 100, "description": "Bollinger Bands SMA period"},
    "bb_std": {"type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1, "description": "Standard deviation multiplier"}
  },
  "indicators_used": ["Bollinger Bands"],
  "timeframes": ["1d", "4h", "1h"],
  "signals": {
    "entry_long": "Close crosses below lower Bollinger Band",
    "exit_long": "Close crosses back above middle Bollinger Band",
    "entry_short": "Close crosses above upper Bollinger Band",
    "exit_short": "Close crosses back below middle Bollinger Band"
  }
}
```

- [ ] **Test with VectorBT**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && backend/venv/bin/python -c "
import pandas as pd, numpy as np, vectorbt as vbt
dates = pd.date_range('2023-01-01', '2023-06-30', freq='B')
np.random.seed(42)
close = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
high = close * 1.02; low = close * 0.98; open_p = close.shift(1).fillna(100) * 1.001
volume = np.random.randint(1000000, 10000000, len(dates))
ohlcv = pd.DataFrame({'Open': open_p, 'High': high, 'Low': low, 'Close': close, 'Volume': volume}, index=dates)
exec(open('backend/strategies/catalog/mean-reversion/bollinger_breakout.py').read())
print(f'Total return: {pf.total_return():.2%}, Sharpe: {pf.sharpe_ratio():.2f}, Trades: {len(pf.trades())}')
print('bollinger_breakout.py: OK')
" 2>&1
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/strategies/catalog/mean-reversion/bollinger_breakout.py backend/strategies/catalog/mean-reversion/bollinger_breakout.json && git commit -m "feat: translate Bollinger Breakout strategy (mean-reversion)"
```

---

### Task 9: Translate bb_winner_pro.py (Mean Reversion — Advanced)

**Files:**
- Create: `backend/strategies/catalog/mean-reversion/bb_winner_pro.py`
- Create: `backend/strategies/catalog/mean-reversion/bb_winner_pro.json`

This is the most complex strategy. Combines BB + RSI + Aroon + MA filters. Original is at `strategies/mean-reversion/BB Winner PRO.pine`.

- [ ] **Read the original Pine Script**

```bash
cat /tmp/pinescript-strategies/strategies/mean-reversion/BB\ Winner\ PRO.pine
```

- [ ] **Write bb_winner_pro.py**

```python
"""
BB Winner PRO [Alorse] — Python translation
Original: strategies/mean-reversion/BB Winner PRO.pine

A multi-filter mean reversion strategy combining:
1. Bollinger Bands — entry when candle body passes through band
2. RSI filter — long only when RSI < aboveRSI level
3. Aroon filter — uptrend confirmation (optional)
4. MA filter — close above/below 200 EMA/SMA (optional)
5. Early close — close when price touches opposite band in profit
"""
import numpy as np
import vectorbt as vbt

# ── Parameters ─────────────────────────────────────────────────────────

# Bollinger Bands
bb_length = 20
bb_mult = 2.0

# RSI Filter
use_rsi = True
rsi_above = 45        # Long only when RSI < this level
rsi_length = 14

# Moving Average Filter
use_ma = True
ma_type = 'EMA'       # 'EMA' or 'SMA'
ma_length = 200

# Aroon Filter
use_aroon = False
aroon_length = 288
aroon_confirmation = 90
aroon_stop = 70

# Strategy
candle_pct = 0.30     # Candle must penetrate band by this %
close_early = True
use_stop_loss = True
sl_percent = 0.07     # 7% stop loss

# ── Data Loading ────────────────────────────────────────────────────────
close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']
open_p = ohlcv['Open']

# ── Indicator Computation ───────────────────────────────────────────────
from ta.volatility import BollingerBands
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, SMAIndicator, AroonIndicator

# Bollinger Bands
bb = BollingerBands(close, window=bb_length, window_dev=bb_mult)
bb_upper = bb.bollinger_hband()
bb_lower = bb.bollinger_lband()
bb_mid = bb.bollinger_mavg()

# RSI
rsi = RSIIndicator(close, window=rsi_length).rsi()

# Moving Average
if ma_type == 'EMA':
    ma = EMAIndicator(close, window=ma_length).ema_indicator()
else:
    ma = SMAIndicator(close, window=ma_length).sma_indicator()

# ── Signal Generation ───────────────────────────────────────────────────

# Candle body size and penetration zones
candle_body = (close - open_p).abs()
body_low = np.where(close > open_p, open_p, close)      # bottom of body
body_high = np.where(close > open_p, close, open_p)     # top of body
penetration_zone_low = body_low - (candle_body * candle_pct)
penetration_zone_high = body_high + (candle_body * candle_pct)

# Long condition: candle body passes below lower band (bearish candle)
long_candle = vbt.combine_logic(
    penetration_zone_low.vbt.lt(bb_lower),
    close.vbt.lt(open_p),
    combine_func=np.logical_and
)

# Short condition: candle body passes above upper band (bullish candle)
short_candle = vbt.combine_logic(
    penetration_zone_high.vbt.gt(bb_upper),
    close.vbt.gt(open_p),
    combine_func=np.logical_and
)

# RSI filter
rsi_filter_long = rsi.vbt.lt(rsi_above) if use_rsi else True
rsi_filter_short = rsi.vbt.gt(100 - rsi_above) if use_rsi else True

# MA filter
ma_filter_long = close.vbt.gt(ma) if use_ma else True
ma_filter_short = close.vbt.lt(ma) if use_ma else True

# Combined entries
entries_long = vbt.combine_logic(
    long_candle, rsi_filter_long, ma_filter_long,
    combine_func=np.logical_and
)

entries_short = vbt.combine_logic(
    short_candle, rsi_filter_short, ma_filter_short,
    combine_func=np.logical_and
)

# Combined entries (both directions)
entries = np.where(entries_long, True, np.where(entries_short, True, False))

# Exits: close when price touches opposite band (early close)
long_exits = close_early & (close.vbt.gte(bb_upper)) if close_early else entries_short
short_exits = close_early & (close.vbt.lte(bb_lower)) if close_early else entries_long
exits = np.where(long_exits | short_exits, True, False)

# ── Portfolio ───────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    sl_stop=sl_percent if use_stop_loss else None,
    broadcast_kwargs={'keep_pd': True},
    jitted=True,
    direction='both',
)
```

- [ ] **Write bb_winner_pro.json**

```json
{
  "name": "BB Winner PRO",
  "slug": "bb_winner_pro",
  "category": "mean-reversion",
  "description": "Advanced multi-filter mean reversion strategy combining Bollinger Bands penetration, RSI filter, optional Aroon trend confirmation, and optional MA trend filter. Version 2.0.8 from Alorse.",
  "version": "1.0.0",
  "source": "Alorse/pinescript-strategies",
  "original_file": "strategies/mean-reversion/BB Winner PRO.pine",
  "parameters": {
    "bb_length": {"type": "int", "default": 20, "min": 5, "max": 100, "description": "Bollinger Bands period"},
    "bb_mult": {"type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1, "description": "Bollinger Bands std dev multiplier"},
    "use_rsi": {"type": "bool", "default": true, "description": "Enable RSI filter"},
    "rsi_above": {"type": "int", "default": 45, "min": 20, "max": 60, "description": "RSI threshold for long entries"},
    "rsi_length": {"type": "int", "default": 14, "min": 5, "max": 50, "description": "RSI period"},
    "use_ma": {"type": "bool", "default": true, "description": "Enable MA trend filter"},
    "ma_type": {"type": "string", "default": "EMA", "description": "MA type (EMA or SMA)"},
    "ma_length": {"type": "int", "default": 200, "min": 20, "max": 500, "description": "MA period"},
    "candle_pct": {"type": "float", "default": 0.30, "min": 0.05, "max": 1.0, "step": 0.05, "description": "Candle penetration percentage"},
    "close_early": {"type": "bool", "default": true, "description": "Close position early on opposite band touch"},
    "use_stop_loss": {"type": "bool", "default": true, "description": "Enable stop loss"},
    "sl_percent": {"type": "float", "default": 0.07, "min": 0.01, "max": 0.20, "step": 0.01, "description": "Stop loss percentage"}
  },
  "indicators_used": ["Bollinger Bands", "RSI", "EMA", "SMA"],
  "timeframes": ["1d", "4h", "1h"],
  "signals": {
    "entry_long": "Bearish candle body penetrates below lower BB with RSI < threshold and close > MA",
    "exit_long": "Price touches upper BB (early close) or stop loss",
    "entry_short": "Bullish candle body penetrates above upper BB with RSI > threshold and close < MA",
    "exit_short": "Price touches lower BB (early close) or stop loss"
  }
}
```

- [ ] **Test with VectorBT**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && backend/venv/bin/python -c "
import pandas as pd, numpy as np, vectorbt as vbt
dates = pd.date_range('2023-01-01', '2023-06-30', freq='B')
np.random.seed(42)
close = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
high = close * 1.02; low = close * 0.98
open_p = close.shift(1).fillna(100) * (1 + np.random.randn(len(dates)) * 0.005)
volume = np.random.randint(1000000, 10000000, len(dates))
ohlcv = pd.DataFrame({'Open': open_p, 'High': high, 'Low': low, 'Close': close, 'Volume': volume}, index=dates)
exec(open('backend/strategies/catalog/mean-reversion/bb_winner_pro.py').read())
print(f'Total return: {pf.total_return():.2%}, Sharpe: {pf.sharpe_ratio():.2f}, Trades: {len(pf.trades())}')
print('bb_winner_pro.py: OK')
" 2>&1
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/strategies/catalog/mean-reversion/bb_winner_pro.py backend/strategies/catalog/mean-reversion/bb_winner_pro.json && git commit -m "feat: translate BB Winner PRO strategy (mean-reversion, advanced)"
```

---

### Task 10: Add "Built-in" tab to Library.tsx

**Files:**
- Modify: `frontend/src/pages/QuantGen/Library.tsx`

- [ ] **Add tab switcher state and fetch logic**

Add after existing state declarations (around line 49):
```tsx
const [activeTab, setActiveTab] = useState<'builtin' | 'saved'>('builtin');
const [builtinStrategies, setBuiltinStrategies] = useState<Record<string, any[]>>({});
const [builtinCategories, setBuiltinCategories] = useState<string[]>([]);
const [categoryFilter, setCategoryFilter] = useState('all');
const [isLoadingBuiltin, setIsLoadingBuiltin] = useState(false);
```

- [ ] **Add built-in strategies fetch**

Add after the existing useEffect (around line 57):
```tsx
useEffect(() => {
  if (activeTab !== 'builtin') return;
  setIsLoadingBuiltin(true);
  fetch('/api/quantgen/strategy-catalog')
    .then(r => r.json())
    .then(data => {
      if (data.success && data.data) {
        setBuiltinStrategies(data.data.strategies_by_category || {});
        setBuiltinCategories(data.data.categories || []);
      }
    })
    .catch(() => {})
    .finally(() => setIsLoadingBuiltin(false));
}, [activeTab]);
```

- [ ] **Add tab switcher UI** (after the Header section, around line 127)

```tsx
{/* Tab Switcher */}
<div style={{ display: 'flex', gap: '4px', marginBottom: '20px', padding: '4px', borderRadius: '12px', backgroundColor: 'var(--surface)', border: '1px solid var(--border)', width: 'fit-content' }}>
  <button
    onClick={() => setActiveTab('builtin')}
    style={{
      padding: '8px 20px',
      borderRadius: '8px',
      fontSize: '13px',
      fontWeight: 600,
      border: 'none',
      cursor: 'pointer',
      backgroundColor: activeTab === 'builtin' ? 'var(--accent)' : 'transparent',
      color: activeTab === 'builtin' ? '#000000' : 'var(--subtle)',
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
    }}
  >
    <Library size={14} />
    Built-in
  </button>
  <button
    onClick={() => setActiveTab('saved')}
    style={{
      padding: '8px 20px',
      borderRadius: '8px',
      fontSize: '13px',
      fontWeight: 600,
      border: 'none',
      cursor: 'pointer',
      backgroundColor: activeTab === 'saved' ? 'var(--accent)' : 'transparent',
      color: activeTab === 'saved' ? '#000000' : 'var(--subtle)',
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
    }}
  >
    <Edit3 size={14} />
    My Strategies
  </button>
</div>
```

- [ ] **Add built-in strategies grid view** (when activeTab === 'builtin')

Replace the main content area to conditionally render based on activeTab:

```tsx
{activeTab === 'builtin' ? (
  <div>
    {isLoadingBuiltin ? (
      <div style={{ textAlign: 'center', padding: '48px', color: 'var(--muted)', fontSize: '13px' }}>
        Loading strategies...
      </div>
    ) : (
      <>
        {/* Category filter chips */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
          {['all', ...builtinCategories].map(cat => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              style={{
                padding: '6px 14px',
                borderRadius: '999px',
                fontSize: '12px',
                fontWeight: 600,
                border: 'none',
                cursor: 'pointer',
                backgroundColor: categoryFilter === cat ? 'var(--accent)' : 'var(--surface)',
                color: categoryFilter === cat ? '#000000' : 'var(--subtle)',
                textTransform: 'capitalize',
                border: categoryFilter !== cat ? '1px solid var(--border)' : 'none',
              }}
            >
              {cat === 'all' ? 'All' : `${cat} (${(builtinStrategies[cat] || []).length})`}
            </button>
          ))}
        </div>

        {/* Strategy cards grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '12px' }}>
          {Object.entries(builtinStrategies)
            .filter(([cat]) => categoryFilter === 'all' || cat === categoryFilter)
            .map(([category, strategies]) =>
              strategies.map((strategy: any, idx: number) => (
                <div key={`${category}-${idx}`} style={{
                  padding: '20px',
                  borderRadius: '14px',
                  backgroundColor: 'var(--surface)',
                  border: '1px solid var(--border)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <div>
                      <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--foreground)' }}>
                        {strategy.name}
                      </span>
                      <span style={{
                        display: 'inline-block',
                        marginLeft: '8px',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '10px',
                        fontWeight: 600,
                        backgroundColor: 'rgba(16,185,129,0.1)',
                        color: '#10b981',
                        textTransform: 'capitalize',
                      }}>
                        {strategy.category}
                      </span>
                    </div>
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.5, marginBottom: '12px' }}>
                    {strategy.description}
                  </p>
                  {strategy.parameters && (
                    <div style={{ marginBottom: '12px' }}>
                      <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>
                        Parameters
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {Object.entries(strategy.parameters).slice(0, 4).map(([key, val]: [string, any]) => (
                          <span key={key} style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '4px', backgroundColor: 'var(--canvas)', color: 'var(--muted)' }}>
                            {key}={val.default}
                          </span>
                        ))}
                        {Object.keys(strategy.parameters).length > 4 && (
                          <span style={{ fontSize: '11px', color: 'var(--subtle)' }}>
                            +{Object.keys(strategy.parameters).length - 4} more
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                  <button
                    onClick={() => {
                      window.location.href = `/quantgen/build?load=${strategy.slug}`;
                    }}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 16px',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: 600,
                      border: 'none',
                      cursor: 'pointer',
                      backgroundColor: 'var(--accent)',
                      color: '#000000',
                    }}
                  >
                    <Edit3 size={13} />
                    Load into Builder
                  </button>
                </div>
              ))
            )}
        </div>

        {Object.keys(builtinStrategies).length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px', color: 'var(--muted)', fontSize: '13px' }}>
            No built-in strategies available.
          </div>
        )}
      </>
    )}
  </div>
) : (
  /* ---- Existing "My Strategies" content ---- */
  // Keep all the existing code for the saved strategies view
  // Just wrap it in this else block
  <>{/* existing saved strategies JSX */}</>
)}
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add frontend/src/pages/QuantGen/Library.tsx && git commit -m "feat: add Built-in tab to Library page with strategy catalog"
```

---

### Task 11: Add auto-load from slug in Builder.tsx

**Files:**
- Modify: `frontend/src/pages/QuantGen/Builder.tsx`

- [ ] **Add state for loading slug and metadata**

Add alongside existing state declarations (around line 117):
```tsx
const loadSlug = searchParams.get('load');
const [strategyMetadata, setStrategyMetadata] = useState<any>(null);
const [isLoadingStrategy, setIsLoadingStrategy] = useState(false);
```

- [ ] **Add auto-load effect**

Add after the existing useEffect hooks (around line 590):
```tsx
// Auto-load strategy from ?load=<slug>
useEffect(() => {
  if (!loadSlug) return;
  setIsLoadingStrategy(true);
  fetch(`/api/quantgen/strategy-catalog/${loadSlug}`)
    .then(r => r.json())
    .then(data => {
      if (data.success && data.data) {
        setCode(data.data.code);
        setStrategyMetadata(data.data.metadata);
        // Pre-fill optimization params from metadata
        if (data.data.metadata?.parameters) {
          const params = data.data.metadata.parameters;
          const ranges: ParamRange[] = Object.entries(params).map(([name, conf]: [string, any]) => ({
            name,
            start: conf.min ?? Math.max(1, Math.round(conf.default * 0.5)),
            stop: conf.max ?? Math.max(2, Math.round(conf.default * 1.5)),
            step: conf.step ?? (conf.type === 'int' ? 1 : 0.5),
            sourceValue: conf.default,
          }));
          setOptParams(ranges);
        }
      }
    })
    .catch(() => {})
    .finally(() => setIsLoadingStrategy(false));
}, [loadSlug]);
```

- [ ] **Add loading indicator to the editor area**

Find the Monaco Editor rendering and add condition:
```tsx
{isLoadingStrategy ? (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--muted)', fontSize: '14px' }}>
    Loading strategy...
  </div>
) : (
  <Editor ... />
)}
```

- [ ] **Commit**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add frontend/src/pages/QuantGen/Builder.tsx && git commit -m "feat: auto-load strategy from ?load=<slug> in Builder"
```

---

### Task 12: Translate remaining 8 strategies

**Files to create — use the same pattern as Tasks 6-9:**

Each strategy follows the same process: read .pine → write .py → write .json → test → commit.

**Sub-task 12a: supertrend_rsi.py** (trend)
- Logic: Supertrend + RSI filter. Entry when Supertrend flips to uptrend AND RSI > 50.
- Parameters: period=10, multiplier=3.0, rsi_length=14, rsi_threshold=50

**Sub-task 12b: double_supertrend.py** (trend)
- Logic: Two Supertrends (fast/slow). Entry when both show uptrend.
- Parameters: fast_period=7, fast_mult=2.0, slow_period=14, slow_mult=3.0

**Sub-task 12c: ma_cross_dmi.py** (trend)
- Logic: MA crossover (20/50) + DMI/ADX filter. Entry when fast MA > slow MA AND ADX > 25.
- Parameters: fast_ma=20, slow_ma=50, adx_period=14, adx_threshold=25

**Sub-task 12d: stochrsi_supertrend.py** (momentum)
- Logic: StochRSI crossover + Supertrend filter. Entry when StochRSI crosses above 20 AND Supertrend is up.
- Parameters: stochrsi_period=14, stochrsi_k=3, stochrsi_d=3, oversold=20, overbought=80, st_period=10, st_mult=3.0

**Sub-task 12e: ttm_squeeze.py** (momentum)
- Logic: TTM Squeeze (BB inside Keltner = squeeze) + momentum. Entry when squeeze fires (BB expand out of Keltner) in direction of momentum.
- Parameters: bb_length=20, bb_mult=2.0, kc_mult=1.5

**Sub-task 12f: qqe_signals.py** (momentum)
- Logic: RSI-based QQE with adaptive signals. Entry on RSI smoothing crossover with volatility-adaptive levels.
- Parameters: rsi_length=14, smooth_length=5, fast_factor=2.0, slow_factor=4.0

**Sub-task 12g: mema_bb_rsi.py** (mean-reversion)
- Logic: Multiple EMAs (10/30/50) + BB band touch + RSI confirmation.
- Parameters: ema_fast=10, ema_mid=30, ema_slow=50, bb_length=20, rsi_length=14

**Sub-task 12h: multi_bb.py** (mean-reversion)
- Logic: Multiple BB periods (20/50/100) confluence. Entry when all 3 bands show oversold/overbought.
- Parameters: bb_periods=[20, 50, 100], bb_std=2.0

- [ ] **Translate remaining 8 strategies**

Each sub-task should be a single commit:
```bash
# For each strategy:
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && git add backend/strategies/catalog/<category>/<slug>.py backend/strategies/catalog/<category>/<slug>.json && git commit -m "feat: translate <name> strategy (<category>)"
```

---

### Task 13: End-to-end testing

- [ ] **Start backend server**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && backend/venv/bin/python -m backend.app.main &
sleep 3
```

- [ ] **Test strategy catalog API**

```bash
curl -s http://localhost:8000/api/quantgen/strategy-catalog | python -m json.tool | head -30
```

Expected: Returns all 12 strategies grouped by category

- [ ] **Test single strategy fetch**

```bash
curl -s http://localhost:8000/api/quantgen/strategy-catalog/macd_rsi | python -m json.tool | head -20
```

Expected: Returns metadata and Python code

- [ ] **Test indicator catalog API**

```bash
curl -s "http://localhost:8000/api/quantgen/indicators/catalog?category=momentum" | python -m json.tool | head -20
```

Expected: Returns momentum indicators sorted by source

- [ ] **Test strategy execution via executor**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1 && backend/venv/bin/python -c "
# Load a strategy, run it with a real ticker via executor
from backend.app.services.executor import execute_strategy
with open('backend/strategies/catalog/momentum/macd_rsi.py') as f:
    code = f.read()
result = execute_strategy(code, tickers=['AAPL'])
print('Success:', result.get('success'))
if result.get('stats'):
    print('Stats keys:', list(result['stats'].keys())[:5])
print('Test: OK')
"
```

Expected: Strategy executes with real data, returns stats

- [ ] **Stop backend server**

```bash
kill %1 2>/dev/null
```

- [ ] **Verify frontend builds without errors**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: No TypeScript errors (or minimal pre-existing ones, none from our changes)

- [ ] **Kill any remaining background processes**

```bash
kill %1 2>/dev/null || true
```

---

## Verification Checklist

- [ ] **12 strategies translated** — all pass single-ticker and multi-ticker VectorBT tests
- [ ] **Indicator catalog** — returns 30+ indicators across 4 categories from 3 sources
- [ ] **Library Built-in tab** — shows strategies grouped by category, "Load" navigates to Builder
- [ ] **Builder auto-load** — `?load=<slug>` pre-fills code and optimization params
- [ ] **Indicator Browser** — searchable, filterable, "Insert at Cursor" works with Monaco
- [ ] **No regressions** — existing QuantGen generate/run/optimize flows still work
