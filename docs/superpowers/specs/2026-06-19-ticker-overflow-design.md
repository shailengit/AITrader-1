# Ticker Overflow Handling — QuantGen Builder

**Date:** 2026-06-19
**Status:** Approved

## Problem

When 200+ tickers are exported from the Markov page into the QuantGen Builder page, every ticker renders as an individual clickable pill button using `flexWrap: 'wrap'` with no height constraint. The pills cascade downward infinitely, pushing the code editor, right-panel components (OptimizationConfig, IndicatorBrowser, console output), and all other UI elements entirely out of the viewport.

## Solution

Collapsible + scrollable pill list with auto-collapse threshold.

## Changes Needed

### File Modified

- `frontend/src/pages/QuantGen/Builder.tsx` — Ticker section only (approximately lines 1202-1281)

### Design

#### Collapse Logic

- **0 imported tickers:** Normal — just the text input as today. No pills, no summary.
- **1–8 imported tickers:** Show all pills inline (no collapse needed). No summary badge, no toggle.
- **8+ imported tickers:** Collapsed by default. Show a summary badge with count + "▼ Show All" toggle. Clicking expands to a 200px max-height scrollable pill container.

#### New State Variables

```tsx
const [showAllTickers, setShowAllTickers] = useState(false);
```

#### Collapsed State (default for 8+)

```
┌──────────────────────────────────────────────────┐
│ Tickers                                          │
│                                                  │
│  [200 tickers imported  ▼ Show All]              │
│                                                  │
│  [ AAPL, MSFT, GOOG, … ]            ← text      │
│                                      input       │
└──────────────────────────────────────────────────┘
```

#### Expanded State

```
┌──────────────────────────────────────────────────┐
│ Tickers                                          │
│                                                  │
│  [AAPL] [MSFT] [GOOGL] [AMZN] [META] [NVDA]     │
│  [BRK.B] [JPM] [V] [TSLA] [UNH] [XOM]           │ max-h-[200px]
│  [AVGO] [ORCL] [COST] [WMT] [JNJ] [PG]          │ overflow-y-auto
│  [▲ Hide]                                        │
│                                                  │
│  [ AAPL, MSFT, GOOG, … ]            ← text      │
│                                      input       │
└──────────────────────────────────────────────────┘
```

#### Interaction Details

- **Clicking a pill** in the scrollable area: Sets `tickers` state to that single ticker (same as current behavior).
- **Clicking ▼ Show All:** Expands to show the scrollable pill list.
- **Clicking ▲ Hide:** Collapses back to summary badge.
- **Searching in text input:** Works independently — user can type any custom ticker list regardless of what pills show.
- **Component re-renders:** Collapsed state resets if `importedTickers` length changes.

#### Memoization / Derived Values

```tsx
const tickerCount = importedTickers.length;
const shouldCollapse = tickerCount > 8;
const visibleTickers = showAllTickers
  ? importedTickers
  : shouldCollapse ? [] : importedTickers; // < 8: show all; > 8 collapsed: show none as pills
```

#### Styling

The summary badge reuses the same pill styling as individual ticker pills (padding, borderRadius, fontSize, border):
- Non-clickable
- `currentTicker`-style highlight to indicate it's the active pool
- Toggle link ("Show All" / "Hide") rendered as a text button styled like the existing UI patterns in Builder.tsx

All inline styles — consistent with the rest of the Builder page.