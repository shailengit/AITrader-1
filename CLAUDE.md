# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradeCraft is a unified trading platform combining three tools:
1. **Sector Rotation Scanner** - Analyze sector ETF momentum and find leading stocks
2. **AI Stock Screener** - Multi-agent technical and fundamental stock screening
3. **QuantGen Strategy Builder** - AI-powered quantitative strategy generation with VectorBT

## Architecture

```
TradeCraft/
├── backend/                 # FastAPI Python backend
│   ├── app/
│   │   ├── main.py          # FastAPI entry point with CORS, security headers
│   │   ├── routers/         # API endpoints
│   │   │   ├── sectors.py    # Sector rotation: /api/sectors, /api/stocks/:sector
│   │   │   ├── screener.py  # AI screener: /api/screener/scan, /api/screener/status/:id
│   │   │   ├── quantgen.py  # Strategy builder: /api/generate, /api/run, /api/optimize
│   │   │   └── health.py     # Health check: /api/health, /api/db-status
│   │   ├── services/        # Business logic
│   │   │   ├── agno_screener.py  # Multi-agent AI screener (Dormant Giant, Quant Strategy)
│   │   │   └── data_service.py  # PostgreSQL data access (replaces yfinance)
│   │   └── db/
│   │       └── database.py  # SQLAlchemy connection pool, sector ETF mappings
│   └── requirements.txt
├── frontend/                # React + TypeScript + Tailwind CSS
│   ├── src/
│   │   ├── App.tsx          # React Router with tabs
│   │   ├── components/layout/Layout.tsx  # Sidebar navigation
│   │   ├── pages/
│   │   │   ├── Landing.tsx        # Dashboard with three app cards
│   │   │   ├── SectorRotation.tsx # Sector ETF analysis with Recharts
│   │   │   ├── StockScreener.tsx  # AI screener with mode selection
│   │   │   └── QuantGen.tsx       # Strategy builder with Monaco Editor
│   │   └── styles/index.css # Tailwind + dark theme CSS variables
│   ├── vite.config.ts       # Vite with API proxy to FastAPI
│   └── package.json
└── README.md
```

## Commands

### Backend (from `backend/` directory)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run development server
python -m app.main
# or
uvicorn app.main:app --reload --port 8000
```

**IMPORTANT:** When running any Python script, always use the virtual environment's Python interpreter from the `backend/` folder:
```bash
cd backend && ./venv/bin/python <script_path>
```

### Frontend (from `frontend/` directory)

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

### Database

PostgreSQL database `sp1500_1d` must be running with:
- Individual stock tables (e.g., `aapl`, `msft`) with columns: `Date`, `Open`, `High`, `Low`, `Close`, `Volume`
- `stock_metadata` table with sector info
- `stock_financials_quarterly` table with EPS data

Environment variables (defaults in `database.py`):
- `DB_USER` (default: postgres)
- `DB_PASSWORD` (default: sarina00)
- `DB_HOST` (default: 127.0.0.1)
- `DB_PORT` (default: 5431)
- `DB_NAME` (default: sp1500_1d)

## Key Patterns

### AI Screener Modes

Two screening modes with optional AI multi-agent analysis:

1. **Dormant Giant** (`dormant_giant`): Bollinger squeeze + OBV accumulation + EPS acceleration
2. **Quant Strategy** (`quant_strategy`): TA indicators + fundamental health + optional backtesting

Set `use_ai=true` for Agno multi-agent team analysis with natural language reports.

### Database Access Pattern

```python
from app.db import database

# Use the connection pool
with database.engine.connect() as conn:
    result = conn.execute(text("SELECT * FROM table"))
```

### Frontend API Calls

Frontend proxies `/api/*` to backend via Vite config. Use relative paths:

```typescript
const res = await fetch('/api/sectors')
```

### True Walk-Forward Optimization (True WFO)

**Purpose:** Simulates real trading conditions by optimizing on past data only, then trading just one day at a time.

**How It Works:**
1. For each rolling window: optimize parameters on training data (past N days)
2. Pick the best parameters from that training window
3. Generate signal from training window's last day → trade the NEXT day only
4. Position persists across windows (like real trading)
5. Repeat with window shifted forward by 1 day

**Key Differences from Simple WFO:**
- Tests one day at a time vs. multi-day test periods
- Position state carries over between windows
- No future data used in decision-making (avoids curve-fitting)

**Implementation:** `backend/app/services/continuous_wfo.py` — uses `PortfolioTracker` to maintain position state across windows.

## Original Repositories

This unified platform combines code from:
- **StockScreener_2** - Multi-agent AI stock screener with Agno/Ollama
- **Sector-Rotation-Scanner** - React/TypeScript sector analysis dashboard
- **QuantGen** - FastAPI/React quantitative strategy builder with VectorBT

## Design System Rules
- Max content width: 1280px, centered with auto margins
- Base spacing unit: 8px (use multiples: 8, 16, 24, 32, 48, 64)
- Typography scale: 14/16/18/20/24/32/40/48px
- Grid: 12-column, 24px gutters
- Never use raw pixel values — use spacing tokens or Tailwind classes only
- All pages must look intentional at 1440px+ (no orphaned whitespace)

## Frontend Requirements
- Target display: MacBook Pro 16" with 4K display (3456×2234 native, 
- typically rendered at 1728×1117 in the browser at 2x DPR).
- Design for 1440px–1728px as the primary breakpoint.
- Use shadcn/ui components exclusively. Do not invent custom components when a shadcn equivalent exists.

## UI/UX Standards
- Framework: React + Tailwind CSS + shadcn/ui
- Target viewport: 1440px–1728px primary, must also work at 768px and 1280px
- Content max-width: 1280px centered
- Spacing: 8px base unit, Tailwind spacing scale only (no arbitrary values)
- Layout: CSS Grid preferred over flexbox for page-level layouts
- No layout should have unintentional empty space at 1440px+
- Sidebar widths: 240px (nav), 320px (contextual panels)
- All modals/dialogs: max-width 560px or 720px, never full-width

## Component rules
- Use shadcn/ui before building custom components
- Cards: always use consistent padding (p-6), border-radius (rounded-xl)
- Forms: max-width 480px unless explicitly a wide layout
- Tables: always implement horizontal scroll on mobile

## Troubleshooting Learnings (April 2026)

### Tailwind Spacing Classes Not Applied

**Problem:** Tailwind spacing utilities (`mb-8`, `gap-12`, `py-24`, etc.) were not being applied to components even though:
- TypeScript compilation succeeded
- Dev server was running
- File changes were being detected (extreme visual indicators like red borders worked)

**Root Cause:** Unknown - possibly Tailwind v4 + Vite integration issue where certain classes get tree-shaken or not processed correctly in development mode.

**Solution:** Use inline styles for spacing when Tailwind classes fail:
```tsx
// Instead of:
<div className="mb-24">

// Use:
<div style={{ marginBottom: '96px' }}>
```

**Verification Method:**
1. Add extreme visual indicators (red border, blue background) to verify code changes are being served
2. If indicators appear but Tailwind classes don't → use inline styles
3. Check browser DevTools computed styles to confirm what's actually applied

**Lesson:** When spacing/layout changes don't appear despite correct code:
- Don't assume the code is wrong
- Verify the file is actually being served (extreme test styles)
- Fall back to inline styles for reliable spacing
- This project's Tailwind v4 setup has quirks with spacing utilities in dev mode

### True WFO Window Calculation Bug

**Problem:** True WFO was generating only 1 window when using Ratio split method, resulting in no trades and a tiny date range (e.g., 2022-10-18 to 2022-10-20 instead of 2020-01-01 to 2024-01-01).

**Root Cause:** `calculate_window_configs()` used `step = test_len` (438 days with 0.7 ratio) for all modes. With ratio=0.7, train=1022 days, only `(1461-1022)//438 = 1` window fits. True WFO should step 1 day at a time to trade each day.

**Fix:** Added `is_true_wfo` parameter to `calculate_window_configs()` that forces `step=1`:
```python
# In continuous_wfo.py
window_configs = calculate_window_configs(
    start_date, end_date, n_windows,
    wfo_conf.get("type", "rolling"), wfo_conf,
    is_true_wfo=True  # Forces step=1
)
```

**Files Modified:**
- `backend/app/services/true_wfo_implementation.py` - Added `is_true_wfo` parameter
- `backend/app/services/continuous_wfo.py` - Pass `is_true_wfo=True`

**Lesson:** True WFO must always step 1 day at a time regardless of split method. The step calculation that works for standard WFO (step = test_len) breaks True WFO's continuous trading model.

### VectorBT Optimization Requires Special Comparison Syntax

**Problem:** Strategy backtest works fine, but optimization fails with "cannot join with no overlapping index names" error.

**Root Cause:** When using single parameter values, VBT creates simple Series that can be compared with operators (`>`, `<`, `&`). When optimizing with multiple parameter combinations, VBT creates DataFrames with MultiIndex columns that cannot be directly compared with operators.

**Solution:** Use VBT's built-in comparison methods instead of operators:

```python
# WRONG - Works for backtest, fails for optimization:
entries = (fast_ma.ma > slow_ma.ma) & (rsi.rsi < 30)

# CORRECT - Works for both backtest and optimization:
entries = vbt.And(fast_ma.ma_above(slow_ma.ma), rsi.rsi_below(30))

# Available VBT comparison methods:
# - ma_above(), ma_below(), ma_crossed_above(), ma_crossed_below()
# - rsi_above(), rsi_below(), rsi_crossed_above(), rsi_crossed_below()
# - vbt.And(), vbt.Or(), vbt.Not() for combining conditions
```

**Lesson:** 
- Strategy code must use VBT comparison methods to work with optimization
- Single-parameter backtests work with operators because VBT uses simple Series
- Multi-parameter optimization requires DataFrame-aware comparison methods
- The backend now catches this error and provides a helpful message explaining how to fix the code
