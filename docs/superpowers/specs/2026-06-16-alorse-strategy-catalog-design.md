# Alorse Pine Script → Python Strategy Catalog & Indicator Browser

## Context

TradeCraft is a unified trading platform combining Sector Rotation Scanner, AI Stock Screener, and QuantGen Strategy Builder — all Python/FastAPI/React with VectorBT backtesting.

The Alorse/pinescript-strategies repo contains 74 Pine Script files (19 indicators, 48 strategies, 7 multi-alert systems) that represent proven trading logic. This spec covers translating a curated subset into Python, integrating them as plug-and-play templates in the QuantGen Library, and building a comprehensive Indicator Browser so users can compose custom strategies from a unified indicator palette.

**Why:** Users currently either write strategies from scratch in the Monaco editor or use the LLM generator. Pre-built, tested templates give them a starting point they can load, inspect, modify, and optimize — dramatically lowering the barrier to using QuantGen effectively.

---

## Architecture

```
Frontend (React)                          Backend (FastAPI)
┌──────────────────────┐                  ┌──────────────────────────────┐
│ Library Page         │    GET /api/     │ strategy_catalog.py          │
│  ┌──────────┐        │ ───────────────▶ │  ┌─────────────────────┐    │
│  │Built-in  │        │ ◀─────────────── │  │ strategies/catalog/ │    │
│  │My Saved  │        │                  │  │  trend/*.py + .json │    │
│  └──────────┘        │                  │  │  momentum/*.py+json │    │
│                      │                  │  │  mean-rev/*.py+json │    │
│ Builder Page         │                  │  └─────────────────────┘    │
│  ┌──────────────┐    │                  │                              │
│  │Indicator     │    │    GET /api/     │ indicator_registry.py        │
│  │Browser       │    │ ───────────────▶ │  ┌─────────────────────┐    │
│  │(new panel)   │    │ ◀─────────────── │  │ ta library (~20)    │    │
│  ├──────────────┤    │                  │  │ VectorBT (~7)       │    │
│  │Monaco Editor │    │                  │  │ Alorse (~19)        │    │
│  └──────────────┘    │                  │  │ pandas-ta (~130+)   │    │
│                      │                  │  └─────────────────────┘    │
│ OptimizationConfig   │                  │                              │
│  (params auto-fill)  │                  │ executor.py (unchanged)      │
└──────────────────────┘                  │ vbt_helpers.py (unchanged)   │
                                          └──────────────────────────────┘
```

---

## Strategy Catalog — Backend

### File Layout

```
backend/strategies/catalog/
├── trend/
│   ├── supertrend.py
│   ├── supertrend.json
│   ├── ma_cross_dmi.py
│   ├── ma_cross_dmi.json
│   ├── supertrend_rsi.py
│   ├── supertrend_rsi.json
│   ├── double_supertrend.py
│   └── double_supertrend.json
├── momentum/
│   ├── macd_rsi.py
│   ├── macd_rsi.json
│   ├── stochrsi_supertrend.py
│   ├── stochrsi_supertrend.json
│   ├── ttm_squeeze.py
│   ├── ttm_squeeze.json
│   ├── qqe_signals.py
│   └── qqe_signals.json
└── mean-reversion/
    ├── bb_winner_pro.py
    ├── bb_winner_pro.json
    ├── bollinger_breakout.py
    ├── bollinger_breakout.json
    ├── mema_bb_rsi.py
    ├── mema_bb_rsi.json
    ├── multi_bb.py
    └── multi_bb.json
```

### Metadata JSON Schema

```json
{
  "name": "string — human-readable title",
  "slug": "string — URL-safe identifier, matches filename",
  "category": "trend | momentum | mean-reversion",
  "description": "string — 1-2 sentence summary",
  "version": "string — semantic version",
  "source": "Alorse/pinescript-strategies",
  "original_file": "string — original .pine filename for reference",
  "parameters": {
    "<param_name>": {
      "type": "int | float | bool",
      "default": "<number or bool>",
      "min": "<number>",
      "max": "<number>",
      "description": "string"
    }
  },
  "indicators_used": ["string — indicator names"],
  "timeframes": ["1d", "4h", "1h"],
  "signals": {
    "entry_long": "string — description of long entry condition",
    "entry_short": "string — description of short entry condition",
    "exit_long": "string — description of long exit condition",
    "exit_short": "string — description of short exit condition"
  }
}
```

### Translated Strategy Python Pattern

Every translated `.py` file must follow these rules:

```python
"""
Supertrend Strategy [Alorse] — Python translation
Original: strategies/trend/Supertrend.pine
"""
import numpy as np
import pandas as pd
import vectorbt as vbt
from numba import njit  # or use vbt's jitted indicators

# ── Parameters (tunable by QuantGen optimizer) ──────────────────────────
period = 10          # ATR period
multiplier = 3.7     # ATR multiplier
use_stop_loss = True
stop_loss_pct = 0.05

# ── Data Loading ────────────────────────────────────────────────────────
# TradeCraft pattern: DataService provides the DataFrame
# For backtesting: data is passed in as `ohlcv` (multi-index for multi-ticker)
# ohlcv.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
# For multi-ticker: ohlcv has a MultiIndex with ticker as level 1

close = ohlcv['Close']
high = ohlcv['High']
low = ohlcv['Low']

# ── Indicator Computation ───────────────────────────────────────────────
# Use pandas-ta or ta library for indicators
import pandas_ta as ta

# Supertrend via pandas-ta
st = ta.supertrend(high, low, close, length=period, multiplier=multiplier)
trend = st[f'SUPERTd_{period}_{multiplier}']  # 1 = uptrend, -1 = downtrend
supertrend_line = st[f'SUPERT_{period}_{multiplier}']

# ── Signal Generation (VectorBT-compatible) ─────────────────────────────
# CRITICAL: Use .vbt.gt(), .vbt.lt(), vbt.combine_logic() for VectorBT compatibility
# This ensures both single-ticker (Series) and multi-ticker (DataFrame) work

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
    broadcast_kwargs={'keep_pd': True},  # Required for multi-ticker
    jitted=True,
    direction='both',  # or 'longonly' depending on strategy
)
```

**Key rules:**
1. Every indicator computation uses `pandas_ta` or `ta` library — never raw math where a library function exists
2. All signal comparisons use `.vbt.gt()`, `.vbt.lt()`, `.vbt.eq()`, `vbt.combine_logic()` — never `>`, `<`, `&`, `|`
3. `broadcast_kwargs={'keep_pd': True}` and `jitted=True` on every `Portfolio.from_signals()` call
4. Data is always expected as a DataFrame with columns `['Open', 'High', 'Low', 'Close', 'Volume']`
5. For multi-ticker, the code works automatically thanks to VectorBT's column broadcasting
6. Each strategy ends with `pf` being the last variable (executor reads it)

### New Route: `backend/app/routers/quantgen.py` additions

```python
@router.get("/strategy-catalog")
async def list_strategy_catalog():
    """List all built-in strategies with metadata."""
    # Scans backend/strategies/catalog/**/*.json
    # Returns grouped by category

@router.get("/strategy-catalog/{slug}")
async def get_strategy_code(slug: str):
    """Get a specific strategy's Python code."""
    # Reads the .py file and its .json metadata
```

---

## Indicator Registry — Backend

### New Module: `backend/app/services/indicator_registry.py`

Aggregates indicators from all sources into a unified catalog:

```python
def get_indicator_catalog() -> List[dict]:
    """
    Returns all available indicators grouped by source and category.
    Sources:
    1. ta library (from screener's INDICATOR_CONFIG)
    2. VectorBT built-in (from vbt_helpers.py)
    3. Alorse translated indicators (from strategies/catalog/indicators/)
    4. pandas-ta indicators (reference from skill documentation)
    """

def get_indicators_by_category(category: str) -> List[dict]:
    """Filter indicators by category: momentum, trend, volatility, volume, pattern, custom."""

def search_indicators(query: str) -> List[dict]:
    """Search indicators by name or description."""
```

Each indicator entry includes:
```python
{
    "name": "RSI",
    "source": "ta",  # "ta" | "vectorbt" | "alorse" | "pandas-ta"
    "category": "momentum",
    "description": "Relative Strength Index — measures speed and magnitude of price changes",
    "params": [
        {"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}
    ],
    "code_snippet": "from ta.momentum import RSIIndicator\nrsi = RSIIndicator(close, window=14).rsi()",
    "pine_equivalent": "ta.rsi(src, len)"  # for reference
}
```

### New Route: `backend/app/routers/quantgen.py` addition

```python
@router.get("/indicators/catalog")
async def list_indicator_catalog(category: str = None, search: str = None):
    """List all available indicators with metadata."""
```

---

## Frontend Changes

### Library Page (`Library.tsx`)

**Add tab switcher** at the top of the page:

```tsx
const [activeTab, setActiveTab] = useState<'builtin' | 'saved'>('builtin');
```

- **Built-in tab**: Fetches from `GET /api/quantgen/strategy-catalog`, renders strategy cards grouped by category. Each card shows name, category badge, description, parameter summary, and a "Load into Builder" button.
- **My Strategies tab**: Existing localStorage-based list, unchanged.

**Category filter chips** for the Built-in tab:
```tsx
const categoryFilter = ['All', 'Trend', 'Momentum', 'Mean Reversion'];
```

**Load action**: Clicking "Load" navigates to `/quantgen/build?load=<slug>`.

### Builder Page (`Builder.tsx`)

**1. Auto-load from query param:**
```tsx
const [searchParams] = useSearchParams();
const loadSlug = searchParams.get('load');

useEffect(() => {
  if (loadSlug) {
    fetch(`/api/quantgen/strategy-catalog/${loadSlug}`)
      .then(r => r.json())
      .then(data => {
        setCode(data.code);
        setStrategyMetadata(data.metadata);
        prefillParams(data.metadata.parameters);
      });
  }
}, [loadSlug]);
```

**2. New "Indicator Browser" panel:**
A collapsible panel in the Builder sidebar (next to the editor) with:
- **Search bar** — filters indicators by name
- **Category chips** — Momentum, Trend, Volatility, Volume, Pattern, Custom
- **Source badges** — small tags showing `ta`, `vbt`, `Alorse`, `pandas-ta`
- **Indicator list** — click to expand, showing:
  - Description
  - Parameters with defaults
  - Code snippet (copyable)
  - "Insert at cursor" button that adds the snippet to the Monaco editor

**3. OptimizationConfig auto-fill:**
When a built-in strategy is loaded, parse its metadata parameters and pre-populate the OptimizationConfig panel's parameter ranges (using `computeAutoRange()` logic that already exists).

### New Component: `IndicatorBrowser.tsx`

```tsx
interface IndicatorBrowserProps {
  onInsertSnippet: (snippet: string) => void;
  editorRef: React.MutableRefObject<any>;
}

// Fetches from /api/quantgen/indicators/catalog
// Renders searchable, filterable list
// "Insert at cursor" calls editorRef.current.executeEdits()
```

---

## Curated Subset — First Batch (12 Strategies)

### Trend (4)
| File Slug | Pine Source | Key Concept | Complexity |
|-----------|-------------|-------------|------------|
| `supertrend` | Supertrend [Alorse] | ATR-based trailing stop | Medium |
| `ma_cross_dmi` | MA Cross + DMI | MA crossover with ADX filter | Medium |
| `supertrend_rsi` | Supertrend + RSI | Supertrend with RSI confirmation | Medium |
| `double_supertrend` | Double Supertrend | Two Supertrends for confirmation | Medium+ |

### Momentum (4)
| File Slug | Pine Source | Key Concept | Complexity |
|-----------|-------------|-------------|------------|
| `macd_rsi` | MACD+RSI | MACD crossover + RSI oversold/overbought | Easy |
| `stochrsi_supertrend` | StochRSI + Supertrend | StochRSI crossover + Supertrend | Medium+ |
| `ttm_squeeze` | TTM Squeeze | Bollinger/Keltner volatility squeeze | Medium+ |
| `qqe_signals` | QQE signals | RSI-based QQE with adaptive signals | Advanced |

### Mean Reversion (4)
| File Slug | Pine Source | Key Concept | Complexity |
|-----------|-------------|-------------|------------|
| `bb_winner_pro` | BB Winner PRO | BB + RSI + Aroon + MA confluence | Advanced |
| `bollinger_breakout` | Bollinger Breakout [kodify] | Classic BB breakout | Easy |
| `mema_bb_rsi` | MEMA + BB + RSI | Multiple EMAs + BB + RSI | Medium+ |
| `multi_bb` | Multi BB | Multiple Bollinger Bands | Medium+ |

---

## Implementation Sequence

| Step | Deliverable | Depends On |
|------|-------------|------------|
| **1** | `indicator_registry.py` — aggregate all indicator sources into one catalog | Nothing |
| **2** | `GET /api/quantgen/indicators/catalog` endpoint | Step 1 |
| **3** | Indicator Browser panel in Builder (frontend) | Step 2 |
| **4** | Translate first 4 strategies (1 per category) as `.py` + `.json` | Nothing (parallel) |
| **5** | `GET /api/quantgen/strategy-catalog` and `/{slug}` endpoints | Step 4 |
| **6** | "Built-in" tab in Library page (frontend) | Step 5 |
| **7** | `?load=<slug>` auto-load in Builder (frontend) | Step 6 |
| **8** | Translate remaining 8 strategies | Step 4 (pattern established) |
| **9** | Translate 19 Alorse indicators, register in `indicator_registry` | Step 1 |
| **10** | E2E testing: Load → Run → Optimize for all 12 strategies | Steps 1-9 |

**Translation process for each strategy:**
1. Read the `.pine` file to understand entry/exit logic
2. Map Pine Script indicators to Python equivalents (`ta`, `pandas-ta`, or `vectorbt`)
3. Write the `.py` file following the VectorBT-compatible pattern
4. Write the `.json` metadata file
5. Test with single ticker
6. Test with multi-ticker (2-3 tickers)
7. Test optimization workflow

---

## Future: Database-Backed Catalog

The file-based approach is intentionally simple for V1. When migrating to DB:

```sql
CREATE TABLE strategy_catalog (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    category VARCHAR(32) NOT NULL,
    description TEXT,
    code TEXT NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}',
    indicators_used TEXT[] DEFAULT '{}',
    source VARCHAR(64) DEFAULT 'Alorse/pinescript-strategies',
    version VARCHAR(16) DEFAULT '1.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    times_loaded INT DEFAULT 0,
    avg_sharpe FLOAT,
    avg_return FLOAT
);

CREATE TABLE indicator_catalog (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    source VARCHAR(32) NOT NULL,
    category VARCHAR(32) NOT NULL,
    description TEXT,
    params JSONB NOT NULL DEFAULT '{}',
    code_snippet TEXT,
    pine_equivalent VARCHAR(128),
    UNIQUE(name, source)
);
```

Migration path: write a one-time script that reads the file catalog and inserts into DB, then swap the API endpoints to query the DB. The frontend API contract stays identical.

---

## Verification

1. **Unit tests**: Each translated strategy gets a test that calls it with known data and asserts expected trade signals
2. **Multi-ticker test**: Run each strategy with 3 tickers, verify it produces per-ticker results
3. **Optimization test**: Run each strategy through the True WFO pipeline, verify parameter optimization works
4. **Indicator API test**: Verify `GET /api/quantgen/indicators/catalog` returns correct count and structure
5. **Frontend integration**: Load a strategy from Library → verify code appears in Builder → Run → verify results render
