# TradeCraft - Stitch Redesign Input Document

This document contains everything Google Stitch needs to redesign and rebuild the TradeCraft frontend while preserving all API contracts, data flows, state management, and functionality.

---

## 1. Project Overview

**TradeCraft** is a unified trading platform combining three tools:
1. **Sector Rotation Scanner** - Analyze sector ETF momentum and find leading stocks
2. **AI Stock Screener** - Multi-agent technical and fundamental stock screening
3. **QuantGen Strategy Builder** - AI-powered quantitative strategy generation with VectorBT backtesting

**Target Users**: Quantitative traders, technical analysts, and retail investors who want data-driven stock selection and strategy backtesting.

**Current Stack**: React 19 + TypeScript + Vite + Tailwind CSS v4 + Framer Motion + Recharts + lightweight-charts + Monaco Editor

---

## 2. Tech Stack & Dependencies

### package.json
```json
{
  "name": "tradecraft-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "preview": "vite preview"
  },
  "dependencies": {
    "@monaco-editor/react": "^4.7.0",
    "axios": "^1.13.4",
    "clsx": "^2.1.1",
    "framer-motion": "^12.31.0",
    "lightweight-charts": "^5.1.0",
    "lucide-react": "^0.563.0",
    "react": "^19.2.0",
    "react-dom": "^19.2.0",
    "react-router-dom": "^7.13.0",
    "recharts": "^3.7.0",
    "tailwind-merge": "^3.4.0"
  },
  "devDependencies": {
    "@eslint/js": "^9.39.1",
    "@tailwindcss/vite": "^4.1.14",
    "@types/react": "^19.2.5",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^5.1.1",
    "autoprefixer": "^10.4.24",
    "eslint": "^9.39.1",
    "eslint-plugin-react": "^7.37.5",
    "eslint-plugin-react-hooks": "^7.0.1",
    "eslint-plugin-react-refresh": "^0.4.24",
    "globals": "^16.5.0",
    "postcss": "^8.5.6",
    "tailwindcss": "^4.1.14",
    "typescript": "~5.8.2",
    "vite": "^7.2.4"
  }
}
```

### Critical: Vite Proxy Config
The frontend relies on this proxy configuration. Any replacement build tool MUST preserve this:

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

---

## 3. Routing Architecture

```
/                     → Landing (dashboard with 3 tool cards)
/sectors              → SectorRotation (sector ETF analysis)
/screener             → StockScreener (AI-powered screening)
/quantgen/*           → QuantGen (sub-router)
  /quantgen           → QuantGenHome (builder landing)
  /quantgen/build     → Builder (code editor + chat)
  /quantgen/dashboard → Dashboard (backtest results)
  /quantgen/library   → Library (strategy management)
```

All pages are wrapped in a `Layout` component that provides:
- Top navigation bar with dynamic page title
- Theme toggle button
- Outlet for page content

---

## 4. Complete API Contract

All API calls use relative paths (e.g., `/api/sectors`) which are proxied to `http://localhost:8000`.

### 4.1 Sector Rotation

#### GET `/api/sectors`
Response: `SectorPerformance[]`
```typescript
interface SectorPerformance {
  ticker: string
  name: string
  perf_3m: number
  perf_6m: number
  spread: number
  is_real_data: boolean
}
```

#### GET `/api/stocks/{sector}`
Response: `StockLeader[]`
```typescript
interface StockLeader {
  ticker: string
  name: string | null
  price: number
  perf_3m: number
  sector_perf_3m: number
  volume_today: number
  volume_avg_20d: number
  high_10d: number
  bb_expanding: boolean
  bb_upper: number
  bb_middle: number
  bb_lower: number
  sma50: number | null
  sma200: number | null
  is_real_data: boolean
}
```

### 4.2 AI Stock Screener

#### GET `/api/screener/modes`
Response:
```typescript
{
  modes: Array<{
    id: string
    name: string
    description: string
    use_ai_options: boolean[]
    supports_backtesting: boolean
    agents: string[]
  }>
}
```

#### POST `/api/screener/scan`
Body:
```typescript
{
  mode: "dormant_giant" | "quant_strategy"
  use_ai: boolean
  cutoff_date?: string
  prompt?: string
  max_results: number
  filters?: {
    squeeze_threshold: number
    accumulation_threshold: number
    volume_threshold: number
  }
}
```
Response:
```typescript
{
  scan_id: string
  mode: string
  use_ai: boolean
  status: string
  message: string
}
```

#### GET `/api/screener/status/{scan_id}`
Response:
```typescript
{
  scan_id: string
  mode: string
  status: "pending" | "running" | "completed" | "failed"
  progress: number
  use_ai: boolean
  results_count: number
  has_ai_report: boolean
  error?: string
  logs: Array<{
    agent: string
    message: string
    type: string
    color: string
  }>
}
```

#### GET `/api/screener/results/{scan_id}`
Response:
```typescript
{
  scan_id: string
  mode: string
  status: string
  use_ai: boolean
  results_count: number
  results: Array<{
    ticker: string
    signal?: string
    fundamental_catalyst?: string
    close?: number
    data_date?: string
    sma_20?: number
    sma_50?: number
    rsi?: number
    macd?: number
    volume?: number
  }>
  ai_report?: string
}
```

#### GET `/api/screener/ai-report/{scan_id}`
Response: `{ scan_id, mode, ai_report }`

#### GET `/api/screener/health`
Response: `{ status, active_scans, modes_available }`

### 4.3 QuantGen Strategy Builder

#### GET `/api/health`
Response: `{ status, module, llm_model, features }`

#### POST `/api/generate`
Body: `{ prompt, tickers[], start_date, end_date }`
Response:
```typescript
{
  success: boolean
  data: {
    code: string
    output: string
    validation: object
  }
  attempts?: number
  message?: string
  error?: { type, message, details }
}
```

#### POST `/api/run`
Body: `{ code, use_database }`
Response:
```typescript
{
  success: boolean
  data: {
    output: string
    stats: Record<string, number | string>
    equity: Array<{ time: number, value: number }>
    ohlcv: Array<{ time, open, high, low, close, volume }>
    drawdown: Record<string, number>
    benchmark_drawdown: Record<string, number>
    trades: Array<{
      time: number
      price: number
      type: 'buy' | 'sell'
      size?: number
      pnl?: number
    }>
    indicators: Array<{
      name: string
      type: string
      params: Record<string, string | number>
    }>
  }
  message?: string
  error?: { type, message, details }
}
```

#### POST `/api/optimize`
Body: `{ code, strategy_params, config }`
Response:
```typescript
{
  success: boolean
  data: {
    stats: Record<string, number | string>
    equity: Array<{ time, value }>
    heatmap?: Array<Record<string, number | string>>
    windows?: Array<{
      window: number
      train_start: string
      train_end: string
      best_param: string
      train_metric: number
      test_metric?: number
    }>
    mode: string
    best_equity?: Array<{ time, value }>
    oos_equity?: Array<{ time, value }>
    benchmark_equity?: Array<{ time, value }>
  }
  message?: string
  error?: { type, message, details }
}
```

#### POST `/api/true-wfo`
Deprecated. Routes to `/api/optimize` with `mode: "true_wfo"`.

#### POST `/api/chat`
Body: `{ code, messages[] }`
Response: `{ success, data: { response } }`

#### GET `/api/strategies`
Response: `{ success, data: { strategies[], count } }`

#### POST `/api/strategies`
Body: `{ name, code }`
Response: `{ success, data: { path, filename, backup_created } }`

#### GET `/api/strategies/{name}`
Response: `{ success, data: { name, code, filename, size } }`

#### DELETE `/api/strategies/{name}`
Response: `{ success, data: { filename, backup_path } }`

#### GET `/api/indicators`
Response: `{ success, data: { indicators[], count } }`

### 4.4 Health

#### GET `/api/health`
Response: `{ status, version, timestamp, services }`

#### GET `/api/db-status`
Response: `{ connected, status }`

---

## 5. Page-by-Page Breakdown

### 5.1 Landing Page (`/`)
**Purpose**: Dashboard showing 3 tool cards and platform stats.

**Content**:
- Hero section with "TradeCraft" title (80px), PostgreSQL badge, description, CTA buttons
- Stats row (4 cards): S&P 1500 Coverage, 11 Sector ETFs, Daily OHLCV, Agno + Ollama
- 3 Feature Cards linking to tools:
  - **Sector Rotation Scanner** (emerald accent): Sector acceleration, momentum leaders, Bollinger squeeze, 3M/6M spread
  - **AI Stock Screener** (blue accent): Volatility contraction, OBV accumulation, EPS inflection, AI workflow
  - **QuantGen Strategy Builder** (purple accent): AI code generation, VectorBT backtesting, Walk-forward optimization, Strategy management
- Footer text

**Data Flow**: Static content, no API calls.

### 5.2 Sector Rotation Scanner (`/sectors`)
**Purpose**: Analyze sector ETF momentum and find outperforming stocks.

**Content**:
- Header with database connection status badge + refresh button
- Two-column layout:
  - Left (2/3): Bar chart of sector acceleration spread (Recharts), click to select sector
  - Right (1/3): Selected sector detail card with 3M/6M performance, spread, momentum indicator
- Stock grid (3 columns): Cards showing top stocks in selected sector with:
  - Ticker, name, current price
  - 3M outperformance vs sector
  - Signal grid: Price breakout, Volume spike, Bollinger Bands expanding
  - "Analyze Setup" button opens modal
- Analysis Modal: Bollinger Bands detail, SMA50/200 comparison, setup strength score (0-100%)

**Data Flow**:
1. On mount: `GET /api/db-status` + `GET /api/sectors`
2. Auto-select first sector
3. On sector change: `GET /api/stocks/{sector}`
4. Refresh button re-fetches both

### 5.3 AI Stock Screener (`/screener`)
**Purpose**: Multi-agent AI stock screening with two modes.

**Content**:
- Hero: "AI Stock Screener" title with "Multi-Agent Intelligence" badge
- Mode Selection (2 cards):
  - Dormant Giant: Bollinger squeeze + OBV + EPS acceleration
  - Quant Strategy: TA + fundamentals + optional backtesting
- Configuration area:
  - AI Analysis toggle + custom prompt textarea
  - Progress bar during scanning
  - Filters sidebar (sensitivity sliders for squeeze, accumulation, volume)
  - Backtest cutoff date (for quant_strategy mode)
- "Start AI Scan" button
- Results section (appears after scan):
  - AI Analysis Report (collapsible)
  - Results grid (5 columns): Ticker cards with signal, price, catalyst, SMA20, RSI
- Error toast at bottom

**Data Flow**:
1. On mount: `GET /api/screener/modes`
2. Start scan: `POST /api/screener/scan` → get scan_id
3. Poll every 1s: `GET /api/screener/status/{scan_id}`
4. On complete: `GET /api/screener/results/{scan_id}` + optional `GET /api/screener/ai-report/{scan_id}`

### 5.4 QuantGen Home (`/quantgen`)
**Purpose**: Landing page for strategy builder with 3 action cards.

**Content**:
- Hero: "Generate Trading Strategies with Natural Language"
- 3 action cards:
  - Strategy Builder (emerald): Natural language to VectorBT code
  - Dashboard: View backtest results and equity curves
  - Library: Manage saved strategies
- Features grid (4 items): AI Generation, VectorBT, Optimization, PostgreSQL
- Stats row: Strategies Created, Backtests Run, Avg Return, Avg Sharpe

**Data Flow**: Reads `localStorage.getItem('builderState')` for stats.

### 5.5 QuantGen Builder (`/quantgen/build`)
**Purpose**: AI strategy generation, code editing, backtesting, and optimization.

**Content**:
- Input area: Strategy description textarea + tickers input + Generate button
- Workspace (2 columns):
  - Left (editor):
    - Monaco Editor (Python) for strategy code
    - AI Chat assistant (collapsible)
    - Optimization Config panel (collapsible, shown in optimize mode)
  - Right (controls):
    - Mode toggle: Backtest / Optimize
    - Run button
    - Save / Save As buttons
    - Strategy library list (click to load)
    - Console output panel

**State Persistence**:
```typescript
localStorage.setItem('builderState', JSON.stringify({
  code,
  strategyPrompt,
  currentFilename,
  runMode,
  optConfig,
  optParams,
  tickers,
}))
```

**Data Flow**:
1. Generate: `POST /api/generate` → sets code in editor
2. Run Backtest: `POST /api/run` → saves results → navigate to Dashboard
3. Run Optimize: `POST /api/optimize` → saves results → navigate to Dashboard
4. Save: `POST /api/strategies`
5. Load: `GET /api/strategies/{name}`
6. Chat: `POST /api/chat`

### 5.6 QuantGen Dashboard (`/quantgen/dashboard`)
**Purpose**: Display backtest/optimization results with charts and metrics.

**Content**:
- Header: Period dates, strategy type badge, Clear button
- Optimization Results (top priority if available):
  - Walk-Forward Analysis heading
  - Out-of-Sample Equity curve (AreaChart)
  - Window stats table (with virtual scrolling for large datasets)
  - Parameter heatmap (sorted best → worst)
- Metrics Grid (4 cards): Total Return, Sharpe Ratio, Max Drawdown, Win Rate
- Two-column layout:
  - Left (2/3):
    - Candlestick chart with trade markers (lightweight-charts)
    - Technical indicator toggle panel
    - Equity curve (AreaChart with benchmark comparison)
    - Max Drawdown chart (AreaChart)
  - Right (1/3):
    - Detailed statistics table
    - Raw data / execution logs (collapsible)

**Data Flow**:
- Reads from `localStorage.getItem('lastRunData')` on mount
- Format:
```typescript
interface DashboardData {
  stats: Record<string, number | string>
  equity: Array<{ time: number, value: number }>
  ohlcv: Array<{ time, open, high, low, close, volume }>
  optimization: OptimizationData | null
  output: string
  drawdownData: Array<{ time: string, drawdown: number, bench_drawdown: number }>
  trades: Array<{ time, price, type, size?, pnl? }>
  indicators: Array<{ name, type, params }>
}
```

### 5.7 QuantGen Library (`/quantgen/library`)
**Purpose**: Manage saved strategies with search, filter, and sort.

**Content**:
- Header with "New Strategy" button
- Search input + status filter dropdown
- Sortable table headers: Name, Status, Return, Metrics, Updated
- Strategy rows (expandable):
  - Name, description, status badge, return %, metrics (SR, WR, DD), date
  - Expanded: Description, performance metrics grid, code preview, Edit/View buttons
- Empty state with CTA

**Data Flow**: Reads strategies from `localStorage.getItem('builderState').strategies`.

---

## 6. Complete TypeScript Interface Definitions

```typescript
// ============================================
// Core Data Models
// ============================================

interface Sector {
  ticker: string
  name: string
  perf_3m: number
  perf_6m: number
  spread: number
  is_real_data: boolean
}

interface Stock {
  ticker: string
  name: string
  price: number
  perf_3m: number
  sector_perf_3m: number
  volume_today: number
  volume_avg_20d: number
  high_10d: number
  bb_expanding: boolean
  bb_upper: number
  bb_middle: number
  bb_lower: number
  sma50: number | null
  sma200: number | null
  is_real_data: boolean
}

interface ScanResult {
  ticker: string
  signal?: string
  fundamental_catalyst?: string
  close?: number
  data_date?: string
  sma_20?: number
  sma_50?: number
  rsi?: number
  macd?: number
  volume?: number
}

interface ScanStatus {
  scan_id: string
  mode: string
  status: "pending" | "running" | "completed" | "failed"
  progress: number
  use_ai: boolean
  results_count: number
  has_ai_report: boolean
  error?: string
}

interface ScreenerMode {
  id: string
  name: string
  description: string
  agents: string[]
  supports_backtesting: boolean
}

// ============================================
// QuantGen Models
// ============================================

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface ParamRange {
  name: string
  start: number
  stop: number
  step: number
}

interface WFOConfig {
  type: 'rolling' | 'expanding'
  windows: number
  ratio: number
  splitMethod: 'ratio' | 'fixed'
  train_days: number
  test_days: number
  start_date: string
  end_date: string
}

interface OptimizationConfigData {
  mode: 'simple' | 'wfo' | 'true_wfo'
  metric: 'total_return' | 'sharpe' | 'sortino' | 'max_dd'
  wfo: WFOConfig
}

interface Trade {
  time: number
  price: number
  type: 'buy' | 'sell'
  size?: number
  pnl?: number
}

interface OHLCV {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface EquityPoint {
  time: number
  value: number
}

interface ChartIndicator {
  name: string
  type: string
  data: Array<{ time: number, value: number }>
  color?: string
}

interface PanelIndicator {
  name: string
  type: string
  params: Record<string, string | number>
}

interface HeatmapRow {
  metric: number
  [key: string]: number | string
}

interface WFOWindow {
  window: number
  train_start: string
  train_end: string
  test_start?: string
  test_end?: string
  test_date?: string
  best_param: string
  train_metric: number
  test_metric?: number
  signal?: 'BUY' | 'SELL' | 'HOLD'
}

interface OptimizationData {
  mode: 'simple' | 'wfo' | 'true_wfo'
  heatmap?: HeatmapRow[]
  windows?: WFOWindow[]
  oos_equity?: EquityPoint[]
  max_windows?: number
  stats?: Record<string, number | string>
  trades?: Trade[]
}

interface DashboardData {
  stats: Record<string, number | string>
  equity: EquityPoint[]
  ohlcv: OHLCV[]
  optimization: OptimizationData | null
  output: string
  drawdownData: Array<{ time: string, drawdown: number, bench_drawdown: number }>
  trades: Trade[]
  indicators: PanelIndicator[]
}

interface Strategy {
  id: string
  name: string
  description: string
  code?: string
  createdAt: string
  updatedAt: string
  status: 'draft' | 'backtested' | 'optimized' | 'live'
  metrics?: {
    totalReturn?: number
    sharpeRatio?: number
    maxDrawdown?: number
    winRate?: number
    trades?: number
  }
}
```

---

## 7. Design System Tokens

### 7.1 Color Palette

The app uses a **manual theme system** (NOT Tailwind dark: prefix). Colors are computed inline based on `isDarkMode` from `ThemeContext`.

#### Dark Mode
| Token | Value | Usage |
|-------|-------|-------|
| Canvas | `#09090B` | Page background |
| Surface | `#27272A` | Cards, panels |
| Surface Alt | `#1A1A1D` | Alternate surface |
| Text Primary | `#FAFAFA` | Headings, primary text |
| Text Muted | `#A1A1AA` | Descriptions, labels |
| Text Subtle | `#52525B` | Secondary info |
| Border | `#27272A` | Default borders |
| Border Light | `#3F3F46` | Input borders, hover |
| Accent | `#10B981` | Primary accent (emerald) |
| Accent Light | `#34D399` | Accent hover, highlights |
| Accent Glow | `rgba(16, 185, 129, 0.1)` | Glow effects |
| Positive | `#34D399` | Gains, positive metrics |
| Negative | `#F43F5E` | Losses, drawdown |
| Warning | `#F59E0B` | Info alerts |

#### Light Mode
| Token | Value | Usage |
|-------|-------|-------|
| Canvas | `#ffffff` | Page background |
| Surface | `#ffffff` | Cards |
| Surface Alt | `#f5f5f7` | Alternate surface |
| Text Primary | `#1d1d1f` | Headings |
| Text Muted | `#6e6e73` | Descriptions |
| Text Subtle | `#86868b` | Secondary info |
| Border | `#d2d2d7` | Default borders |
| Border Light | `#e5e5e7` | Input borders |
| Accent | `#0071e3` / `#059669` | Primary accent (apple blue / emerald) |
| Accent Light | `#2997ff` | Hover |

### 7.2 Typography Scale
| Name | Size | Weight | Line Height | Letter Spacing |
|------|------|--------|-------------|----------------|
| Hero | 80px | 700 | 1.1 | -0.04em |
| Display | 56px | 600 | 1.07 | -0.28px |
| H1 | 40px | 600 | 1.1 | normal |
| H2 | 32px | 600 | 1.2 | normal |
| H3 | 24px | 600 | 1.3 | normal |
| Section | 48px | 700 | 1.1 | normal |
| Body | 16-18px | 400 | 1.6 | normal |
| Caption | 14px | 400 | 1.29 | -0.224px |
| Micro | 12px | 400 | 1.33 | -0.12px |
| Nano | 10px | 400 | 1.47 | -0.08px |

### 7.3 Spacing System
| Token | Value |
|-------|-------|
| Base Unit | 8px |
| Page Padding | 64-80px |
| Card Padding | 24-32px (p-6 to p-8) |
| Grid Gap | 24-48px |
| Section Gap | 80-120px |

### 7.4 Border Radius
| Token | Value |
|-------|-------|
| Small | 8px |
| Standard | 12px |
| Large | 16px |
| Card | 24px |
| Pill | 50px |

### 7.5 Shadows
| Token | Value |
|-------|-------|
| Card | `rgba(0, 0, 0, 0.22) 3px 5px 30px 0px` |
| Hover Lift | `0 8px 25px rgba(0, 0, 0, 0.3)` |
| Accent Glow | `0 0 20px rgba(16, 185, 129, 0.2)` |
| Emerald Button | `0 0 30px rgba(16, 185, 129, 0.25)` |

### 7.6 Animation Tokens
| Animation | Duration | Easing |
|-----------|----------|--------|
| Theme transition | 0.3s | ease |
| Hover lift | 0.2s | ease |
| Card hover border | 0.2s | ease |
| Modal scale-in | 0.3s | ease-out |
| Fade in up | 0.5s | ease-out |
| Stagger children | 0.1s | - |

---

## 8. Component Library

### 8.1 Layout Components

#### Layout (`src/components/layout/Layout.tsx`)
- Top bar: 64px height, dynamic page title, logo icon, theme toggle
- Main content area with `<Outlet />`
- Page titles: Dashboard, Sector Rotation Scanner, AI Stock Screener, QuantGen Strategy Builder

### 8.2 UI Components

#### Card (`src/components/ui/Card.tsx`)
Variants: `base`, `raised`, `overlay`
Props: `variant`, `hover`, `children`
- Base: rounded-xl, theme-aware background
- DataCard: left accent border (apple/white/muted/red)
- StatCard: centered, value + label + optional change indicator
- FeatureCard: Landing page tool cards with gradient backgrounds

#### Badge (`src/components/ui/Badge.tsx`)
Variants: `emerald`, `blue`, `purple`, `red`, `amber`, `zinc`
Sizes: `sm`, `md`
- Standard badge: pill-shaped with colored background/border
- StatusBadge: dot indicator (connected/disconnected/checking)

#### Metric (`src/components/ui/Metric.tsx`)
Sizes: `lg`, `md`, `sm`
Props: `value`, `label`, `change`, `changeType`, `prefix`, `suffix`
- ProgressMetric: value + label + progress bar (0-100%)

#### Button (`src/components/ui/Button.tsx`)
Variants: `primary`, `secondary`, `ghost`, `destructive`
Sizes: `sm`, `md`, `lg`
Props: `leftIcon`, `rightIcon`

#### ThemeToggle (`src/components/ui/ThemeToggle.tsx`)
- Sun/Moon icon with rotation animation
- Sizes: `sm`, `md`, `lg`
- Variants: `default`, `ghost`, `outline`

### 8.3 QuantGen Components

#### CandleStickChart (`src/components/quantgen/CandleStickChart.tsx`)
- Uses `lightweight-charts` library
- Displays OHLCV data with trade markers
- Optional volume histogram
- Optional indicator overlays (line series)
- Props: `data`, `trades`, `indicators`, `height`

#### IndicatorPanel (`src/components/quantgen/IndicatorPanel.tsx`)
- Collapsible panel showing technical indicators
- Toggle buttons to show/hide indicators on chart
- Each indicator has a unique color dot

#### OptimizationConfig (`src/components/quantgen/OptimizationConfig.tsx`)
- Mode selector: simple / wfo / true_wfo
- Metric selector: total_return / sharpe / sortino / max_dd
- Parameter ranges (name, start, stop, step) with add/remove
- WFO settings: window type, split method, train/test days or ratio

#### OptimizationResults (`src/components/quantgen/OptimizationResults.tsx`)
- Out-of-sample equity curve (AreaChart)
- Window stats table (with virtual scrolling)
- Parameter heatmap (sorted best to worst)

---

## 9. State Management

### 9.1 ThemeContext (`src/context/ThemeContext.tsx`)
- Global dark/light mode
- Persisted in `localStorage` key: `tradecraft-theme-preference`
- Listens to system preference if no stored preference
- Applies `apple-light-theme` class to `<html>`

### 9.2 localStorage Keys
| Key | Data | Used By |
|-----|------|---------|
| `tradecraft-theme-preference` | `"dark"` or `"light"` | ThemeContext |
| `builderState` | `{ code, strategyPrompt, currentFilename, runMode, optConfig, optParams, tickers, strategies[] }` | QuantGen Builder, Library |
| `lastRunData` | DashboardData object | QuantGen Dashboard |
| `loadStrategy` | Strategy object (sessionStorage) | Library → Builder transfer |

### 9.3 Page-Level State Patterns

**Screener**:
- Modes fetched once on mount
- Scan triggers POST, then 1-second polling loop
- Results displayed after completion

**Sector Rotation**:
- Sectors fetched on mount
- Stocks fetched when sector changes
- Database status polled on mount + refresh

**QuantGen Builder**:
- All state auto-saved to localStorage on change
- Code execution triggers API call, then navigation to Dashboard
- Chat maintains message history in component state

---

## 10. Animation Specification

All animations use **Framer Motion**.

### Global Patterns
```typescript
const fadeInUp = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 }
}

const staggerContainer = {
  animate: { transition: { staggerChildren: 0.1 } }
}
```

### Page-Specific Animations
- **Landing**: Hero text fade-in-up, cards stagger in, orbs have blur glow
- **Screener**: Mode cards scale in, results stagger grid items (0.05s delay each)
- **Sector Rotation**: Stock cards animate in with `y: 20` on load
- **QuantGen Home**: Cards and features stagger in
- **Dashboard**: Metric cards scale in, charts fade in
- **Modals**: Scale from 0.9 to 1 + opacity, backdrop blur
- **Theme Toggle**: Sun/Moon rotate 90 degrees with opacity/scale crossfade

### CSS Animations (in index.css)
- `fadeInUp`: 0.5s ease-out
- `scaleIn`: 0.3s ease-out
- `pulse-glow`: 2s ease-in-out infinite
- `float`: translateY oscillation

---

## 11. File Inventory

### Entry Points
```
frontend/index.html
frontend/src/main.tsx          (StrictMode + ThemeProvider + App)
frontend/src/App.tsx            (BrowserRouter + Routes)
```

### Pages
```
frontend/src/pages/Landing.tsx
frontend/src/pages/SectorRotation.tsx
frontend/src/pages/StockScreener.tsx
frontend/src/pages/QuantGen/index.tsx      (sub-router)
frontend/src/pages/QuantGen/Home.tsx
frontend/src/pages/QuantGen/Builder.tsx
frontend/src/pages/QuantGen/Dashboard.tsx
frontend/src/pages/QuantGen/Library.tsx
```

### Layout & Context
```
frontend/src/components/layout/Layout.tsx
frontend/src/context/ThemeContext.tsx
```

### UI Components
```
frontend/src/components/ui/Card.tsx
frontend/src/components/ui/Badge.tsx
frontend/src/components/ui/Metric.tsx
frontend/src/components/ui/Button.tsx
frontend/src/components/ui/Input.tsx
frontend/src/components/ui/ThemeToggle.tsx
frontend/src/components/ui/index.ts
```

### QuantGen Components
```
frontend/src/components/quantgen/CandleStickChart.tsx
frontend/src/components/quantgen/IndicatorPanel.tsx
frontend/src/components/quantgen/OptimizationConfig.tsx
frontend/src/components/quantgen/OptimizationResults.tsx
frontend/src/components/quantgen/index.ts
```

### Styles & Config
```
frontend/src/styles/index.css
frontend/vite.config.ts
frontend/package.json
frontend/tsconfig.json
frontend/tailwind.config.js
```

---

## 12. Critical Constraints for Stitch

### MUST PRESERVE (Non-Negotiable)
1. **API Endpoint URLs**: All `/api/*` paths must remain exactly as documented. The backend is NOT being changed.
2. **Monaco Editor**: Builder page MUST include a Python code editor. Keep `@monaco-editor/react` or provide equivalent.
3. **Chart Libraries**:
   - Recharts for equity curves, drawdown charts, sector bar chart
   - lightweight-charts for candlestick OHLCV visualization
4. **API Proxy**: Any build tool must proxy `/api` to `http://localhost:8000`
5. **React Router**: Must support nested routes (`/quantgen/*`) with `BrowserRouter`
6. **localStorage Keys**: Must use exact keys: `tradecraft-theme-preference`, `builderState`, `lastRunData`

### SHOULD PRESERVE (High Priority)
1. **Theme system**: Manual dark/light toggle with CSS variable switching (not Tailwind dark:)
2. **Framer Motion animations**: Page transitions, card animations, modal effects
3. **Polling pattern**: Screener status polling every 1 second
4. **Lucide React icons**: All icons use this library
5. **Data shapes**: All TypeScript interfaces must remain compatible with backend responses

### CAN CHANGE (Design Freedom)
1. **Visual design**: Colors, spacing, typography, border-radius can all be redesigned
2. **Layout structure**: Page layouts can be reorganized
3. **Component organization**: Files can be split/merged differently
4. **Tailwind classes**: Can switch to different utility approach if desired
5. **Animation details**: Specific easing, duration, effects can change
6. **CSS-in-JS vs Tailwind**: Can switch styling approach

---

## 13. Responsive Requirements

| Breakpoint | Target |
|------------|--------|
| Primary | 1440px - 1728px (MacBook Pro 16") |
| Minimum | 768px (tablet) |
| Large | 1280px+ |

All pages must look intentional at 1440px+. No orphaned whitespace.
- Max content width: 1280px, centered
- Sidebar widths: 240px (nav), 320px (contextual panels)
- Tables: horizontal scroll on mobile
- Cards: stack vertically below 768px

---

## 14. Verification Checklist

After Stitch generates the new frontend, verify:

- [ ] Landing page shows 3 tool cards with working navigation
- [ ] Sector Rotation loads bar chart and stock cards from API
- [ ] Stock Screener can select mode, start scan, poll status, display results
- [ ] QuantGen Home shows 3 action cards navigating correctly
- [ ] Builder page has Python code editor, can generate/run/save strategies
- [ ] Dashboard displays charts from localStorage data
- [ ] Library lists strategies with search/filter/sort
- [ ] Theme toggle works across all pages
- [ ] API proxy correctly forwards `/api` calls to backend
- [ ] All localStorage persistence works (theme, builder state, results)
- [ ] Responsive at 768px, 1280px, 1728px
