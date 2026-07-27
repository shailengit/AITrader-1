# Markov Clickable Rows + Stock Detail Drawer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Markov scan results table rows clickable, opening the same right-side drawer as the Custom Screener with candlestick chart, toggleable EMA20/EMA50 overlays, ticker metadata, and export actions. Add state persistence via URL params + sessionStorage. Add full-page chart view at `/markov/chart/:ticker`.

**Architecture:** Reuse existing `TickerDetailDrawer` and `ChartView` components from the Custom Screener. No backend changes. State persistence via URL search params (scan config) + sessionStorage (scan results). New thin wrapper `MarkovChartView` for the full-page chart route.

**Tech Stack:** React 18, TypeScript, React Router v6, lightweight-charts, shadcn/ui

## Global Constraints

- No backend changes — reuse existing `/api/screener/chart-data/{ticker}` and `/api/screener/ticker/{ticker}` endpoints
- No changes to `TickerDetailDrawer.tsx` — it already handles `scoreRow=null` (hides scoring breakdown)
- Follow existing code patterns: inline styles (not Tailwind classes), theme-aware colors via `useTheme()`
- All new files go in `frontend/src/pages/Markov/`

---

### Task 1: Refactor ChartView to accept configurable back-button label and referrer

**Files:**
- Modify: `frontend/src/pages/app/ScreenerBuilder/ChartView.tsx`

**Interfaces:**
- Consumes: existing `ChartView` component (no props currently — reads everything from URL params)
- Produces: `ChartView` with optional `backLabel`, `backPath`, and `referrer` props

**Rationale:** The full-page chart view is currently hardcoded to navigate back to `/screener/build` and show "Back to results" / "Custom Screener". The Markov version needs to navigate back to `/markov` and show "Back to Markov Chain Trader". Making these configurable via props avoids duplicating the entire component.

- [ ] **Step 1: Add props interface to ChartView**

Add at the top of the component function (around line 154), before the existing `const { ticker: tickerParam }` line:

```tsx
interface ChartViewProps {
  /** Label for the back button. Default: "Back to results" */
  backLabel?: string;
  /** Path the back button navigates to. Default: "/screener/build" */
  backPath?: string;
  /** Referrer path for the Layout's back-navigation. Default: "/screener/build" */
  referrerPath?: string;
  /** Referrer label for the Layout's back-navigation. Default: "Custom Screener" */
  referrerLabel?: string;
}

export default function ChartView({
  backLabel = 'Back to results',
  backPath = '/screener/build',
  referrerPath = '/screener/build',
  referrerLabel = 'Custom Screener',
}: ChartViewProps) {
```

- [ ] **Step 2: Use props in the back button**

Replace the hardcoded back button (line 645) and breadcrumb (line 664):

```tsx
<button
  onClick={() => navigate(backPath)}
  aria-label={backLabel}
  style={{
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    borderRadius: 6,
    border: `1px solid ${colors.border}`,
    background: 'none',
    color: colors.muted,
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
  }}
>
  <ArrowLeft size={14} />
  {backLabel}
</button>
<span style={{ fontSize: 12, color: colors.subtle }}>{referrerLabel} ›</span>
```

- [ ] **Step 3: Use props in the referrer effect**

Replace the hardcoded `recordAppReferrer` call (line 222):

```tsx
useEffect(() => {
  recordAppReferrer(referrerPath, referrerLabel);
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

- [ ] **Step 4: Verify no regressions**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors. The default prop values preserve existing behavior for the ScreenerBuilder's ChartView.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/app/ScreenerBuilder/ChartView.tsx
git commit -m "refactor: make ChartView back-button and referrer configurable via props"
```

---

### Task 2: Create MarkovChartView wrapper

**Files:**
- Create: `frontend/src/pages/Markov/MarkovChartView.tsx`

**Interfaces:**
- Consumes: `ChartView` component with props from Task 1
- Produces: Markov-specific chart view component

- [ ] **Step 1: Create MarkovChartView.tsx**

```tsx
import ChartView from '../app/ScreenerBuilder/ChartView';

/**
 * Markov-specific full-page chart view.
 * Wraps the shared ChartView with Markov-specific back-button and referrer labels.
 */
export default function MarkovChartView() {
  return (
    <ChartView
      backLabel="Back to Markov Chain Trader"
      backPath="/markov"
      referrerPath="/markov"
      referrerLabel="Markov Chain Trader"
    />
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Markov/MarkovChartView.tsx
git commit -m "feat: add MarkovChartView wrapper for full-page chart"
```

---

### Task 3: Add route for `/markov/chart/:ticker`

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `MarkovChartView` component from Task 2
- Produces: New route accessible at `/markov/chart/:ticker`

- [ ] **Step 1: Add import for MarkovChartView**

Add after the existing Markov import (line 11):

```tsx
import MarkovChartView from './pages/Markov/MarkovChartView'
```

- [ ] **Step 2: Add route after the existing markov route**

Add after line 58 (the closing `/>` of the markov route):

```tsx
<Route path="markov/chart/:ticker" element={
  <ErrorBoundary>
    <MarkovChartView />
  </ErrorBoundary>
} />
```

- [ ] **Step 3: Verify route is registered**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add /markov/chart/:ticker route for full-page chart view"
```

---

### Task 4: Add clickable rows to SignalsTable

**Files:**
- Modify: `frontend/src/pages/Markov/components/SignalsTable.tsx`

**Interfaces:**
- Consumes: `onTickerClick: (ticker: string) => void` prop from parent
- Produces: Clickable table rows that call `onTickerClick(ticker)` on click/Enter/Space

- [ ] **Step 1: Add onTickerClick to the props interface**

Add to `SignalsTableProps`:

```tsx
interface SignalsTableProps {
  signals: Signal[];
  totalScanned: number;
  loading: boolean;
  isDarkMode: boolean;
  minConviction?: number;
  asOfDate?: string;
  /** Called when the user clicks a row. */
  onTickerClick: (ticker: string) => void;
}
```

- [ ] **Step 2: Make rows clickable**

Replace the `<tr>` in the `display.map` callback (line 127) with:

```tsx
<tr
  key={`${s.ticker}-${i}`}
  role="button"
  tabIndex={0}
  aria-label={`Open detail for ${s.ticker}`}
  onClick={() => onTickerClick(s.ticker)}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onTickerClick(s.ticker);
    }
  }}
  style={{
    borderBottom: `1px solid ${rowBorder}`,
    cursor: 'pointer',
    transition: 'background-color 150ms ease',
  }}
  onMouseEnter={(e) => {
    e.currentTarget.style.backgroundColor = isDarkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)';
  }}
  onMouseLeave={(e) => {
    e.currentTarget.style.backgroundColor = 'transparent';
  }}
>
```

- [ ] **Step 3: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Markov/components/SignalsTable.tsx
git commit -m "feat: add clickable rows to Markov SignalsTable"
```

---

### Task 5: Add state persistence and drawer to MarkovPage

**Files:**
- Modify: `frontend/src/pages/Markov/index.tsx`

**Interfaces:**
- Consumes: `SignalsTable` with `onTickerClick` prop (Task 4), `TickerDetailDrawer` from `ScreenerBuilder/TickerDetailDrawer`
- Produces: Markov page with URL-synced drawer state, sessionStorage-backed scan results, and rendered TickerDetailDrawer

- [ ] **Step 1: Add imports**

Add after the existing imports (line 5):

```tsx
import { useSearchParams, useNavigate } from 'react-router-dom';
import TickerDetailDrawer from '../app/ScreenerBuilder/TickerDetailDrawer';
import { recordAppReferrer } from '../../components/layout/Layout';
import type { IndicatorDescriptor } from '../../types/indicators';
```

- [ ] **Step 2: Add state and hooks inside the component**

Add after `const { isDarkMode } = useTheme();` (line 39):

```tsx
const [searchParams, setSearchParams] = useSearchParams();
const navigate = useNavigate();
const [drawerTicker, setDrawerTicker] = useState<string | null>(() => searchParams.get('ticker')?.toUpperCase() ?? null);
```

- [ ] **Step 3: Add sessionStorage restore effect**

Add after the existing `useEffect` for polling (after line 109):

```tsx
// Restore scan results from sessionStorage on mount
useEffect(() => {
  try {
    const cached = sessionStorage.getItem('markov:scan:results');
    if (cached) {
      const parsed = JSON.parse(cached);
      const age = Date.now() - (parsed.timestamp || 0);
      // Only restore if less than 5 minutes old
      if (age < 5 * 60 * 1000 && Array.isArray(parsed.signals)) {
        setSignals(parsed.signals);
        if (parsed.sectors) setSectors(parsed.sectors);
        if (parsed.totalScanned != null) setTotalScanned(parsed.totalScanned);
      } else {
        sessionStorage.removeItem('markov:scan:results');
      }
    }
  } catch {
    sessionStorage.removeItem('markov:scan:results');
  }
}, []);
```

- [ ] **Step 4: Save results to sessionStorage after scan completes**

Add at the end of the `handleScan` callback, inside the `try` block after setting state (after line 137):

```tsx
// Cache results in sessionStorage for navigation persistence
try {
  sessionStorage.setItem('markov:scan:results', JSON.stringify({
    signals: data.signals,
    sectors: data.sector_status,
    totalScanned: data.total_scanned,
    timestamp: Date.now(),
  }));
} catch { /* sessionStorage may be full; ignore */ }
```

- [ ] **Step 5: Sync drawerTicker to URL search params**

Add effect after the sessionStorage restore effect:

```tsx
// Sync drawerTicker to ?ticker= URL param
useEffect(() => {
  if (drawerTicker) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('ticker', drawerTicker);
        return next;
      },
      { replace: true },
    );
  } else {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('ticker');
        return next;
      },
      { replace: true },
    );
  }
}, [drawerTicker, setSearchParams]);
```

- [ ] **Step 6: Define default indicators**

Add before the return statement (before line 153):

```tsx
const defaultIndicators: IndicatorDescriptor[] = useMemo(() => [
  { id: 'ema_20', label: 'EMA 20' },
  { id: 'ema_50', label: 'EMA 50' },
], []);
```

- [ ] **Step 7: Add drawer open/close handlers**

Add after `handleScan`:

```tsx
const openTicker = useCallback((ticker: string) => {
  setDrawerTicker(ticker.toUpperCase());
}, []);

const closeDrawer = useCallback(() => {
  setDrawerTicker(null);
}, []);
```

- [ ] **Step 8: Pass onTickerClick to SignalsTable**

Update the SignalsTable usage (line 267) to include the new prop:

```tsx
<SignalsTable
  signals={signals}
  totalScanned={totalScanned}
  loading={loading}
  isDarkMode={isDarkMode}
  minConviction={lastMinConviction}
  asOfDate={lastAsOfDate}
  onTickerClick={openTicker}
/>
```

- [ ] **Step 9: Render TickerDetailDrawer**

Add after the SignalsTable (after line 267), before the closing `</div>`:

```tsx
<TickerDetailDrawer
  ticker={drawerTicker}
  asOfDate={lastAsOfDate || undefined}
  indicators={defaultIndicators}
  scoreRow={null}
  onClose={closeDrawer}
  onOpenInChart={(ticker) => {
    recordAppReferrer('/markov', 'Markov Chain Trader');
    navigate(`/markov/chart/${encodeURIComponent(ticker)}`);
  }}
  onExportToLab={(ticker) => {
    recordAppReferrer('/markov', 'Markov Chain Trader');
    const fromDate = lastAsOfDate || new Date().toISOString().split('T')[0];
    navigate(`/quantgen/build?tickers=${encodeURIComponent(ticker)}&from_date=${fromDate}`);
  }}
/>
```

- [ ] **Step 10: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/Markov/index.tsx
git commit -m "feat: add state persistence and TickerDetailDrawer to Markov page"
```

---

### Task 6: Add initial values support to ControlPanel (optional — URL param pre-fill)

**Files:**
- Modify: `frontend/src/pages/Markov/components/ControlPanel.tsx`

**Interfaces:**
- Consumes: `initialValues?: Partial<ScanParams>` prop from parent
- Produces: Control panel pre-filled with values from URL params

**Note:** This task is optional — the ControlPanel already has sensible defaults. URL param pre-fill is a nice-to-have for bookmarking specific scan configurations.

- [ ] **Step 1: Add initialValues prop**

Add to `ControlPanelProps`:

```tsx
interface ControlPanelProps {
  onScan: (params: ScanParams) => void;
  loading: boolean;
  /** Optional initial values to pre-fill the form (from URL params). */
  initialValues?: Partial<ScanParams>;
}
```

- [ ] **Step 2: Apply initial values on mount**

Add after the existing `useState` declarations (after line 37):

```tsx
// Apply initial values from URL params on mount
useEffect(() => {
  if (!initialValues) return;
  if (initialValues.model) setModel(initialValues.model);
  if (initialValues.minConviction != null) setMinConviction(initialValues.minConviction);
  if (initialValues.maxResults != null) setMaxResults(initialValues.maxResults);
  if (initialValues.asOfDate != null) setAsOfDate(initialValues.asOfDate);
  if (initialValues.threshold != null) setThreshold(initialValues.threshold);
  // Only run once on mount
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

- [ ] **Step 3: Pass initialValues from MarkovPage**

In `MarkovPage/index.tsx`, update the ControlPanel usage:

```tsx
<ControlPanel
  onScan={handleScan}
  loading={loading}
  initialValues={{
    model: (searchParams.get('model') as 'xgboost' | 'lstm') || undefined,
    threshold: searchParams.get('threshold') ? parseFloat(searchParams.get('threshold')!) : undefined,
    minConviction: searchParams.get('minConviction') ? parseFloat(searchParams.get('minConviction')!) : undefined,
    maxResults: searchParams.get('maxResults') ? parseInt(searchParams.get('maxResults')!, 10) : undefined,
    asOfDate: searchParams.get('asOfDate') || undefined,
  }}
/>
```

- [ ] **Step 4: Write scan params to URL on scan**

In `MarkovPage/index.tsx`, add to the `handleScan` callback (before the fetch call):

```tsx
// Write scan params to URL for state persistence
setSearchParams(
  (prev) => {
    const next = new URLSearchParams(prev);
    next.set('model', params.model);
    next.set('threshold', String(params.threshold));
    next.set('minConviction', String(params.minConviction));
    next.set('maxResults', String(params.maxResults));
    if (params.asOfDate) next.set('asOfDate', params.asOfDate);
    return next;
  },
  { replace: true },
);
```

- [ ] **Step 5: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Markov/index.tsx frontend/src/pages/Markov/components/ControlPanel.tsx
git commit -m "feat: add URL param pre-fill for Markov scan controls"
```

---

## Verification

After all tasks are complete, verify end-to-end:

1. **Start dev servers:**
   ```bash
   cd backend && ./venv/bin/python -m app.main &
   cd frontend && npm run dev
   ```

2. **Run a Markov scan** → verify results table appears with clickable rows (cursor: pointer, hover effect)

3. **Click a row** → verify right-side drawer opens with:
   - Candlestick chart + volume histogram
   - EMA20 and EMA50 toggleable overlays (both ON by default)
   - Ticker metadata panel (company name, sector)
   - Expand/shrink button works
   - "Open in chart" button works

4. **Toggle EMA20/EMA50 chips** → verify overlays appear/disappear on chart

5. **Click "Open in chart"** → verify navigates to `/markov/chart/:ticker` with:
   - Full indicator picker with ~30 indicators
   - Back button says "Back to Markov Chain Trader"
   - Date range bar, overlays list, metadata rail

6. **Navigate to home and back** → verify scan results and drawer state are restored

7. **Click "Export to Lab"** → verify opens QuantGen builder with the ticker pre-filled

8. **Refresh the page** → verify scan config is preserved in URL params (results may be lost — acceptable)
