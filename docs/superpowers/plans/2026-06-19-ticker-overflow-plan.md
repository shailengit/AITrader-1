# Ticker Overflow Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent 200+ exported ticker pills from overflowing the QuantGen Builder page by adding auto-collapse and scrollable container.

**Architecture:** Single-file change to `Builder.tsx`. A new state variable (`showAllTickers`) and a memoized `shouldCollapse` flag control whether ticker pills are shown inline (≤8), collapsed to a summary badge (>8), or expanded to a max-h-200px scrollable container. No new components, no CSS changes, no backend changes.

**Tech Stack:** React + TypeScript + inline styles (matching existing Builder.tsx patterns)

**Design doc:** `docs/superpowers/specs/2026-06-19-ticker-overflow-design.md`

---

### Task 1: Add collapse state and derived variables

**Files:**
- Modify: `frontend/src/pages/QuantGen/Builder.tsx:99` (after `importedTickers` computation)

- [ ] **Step 1: Add `showAllTickers` state variable**

Add this right after line 107 (`const importedTickers = ...`):

```typescript
const [showAllTickers, setShowAllTickers] = useState(false);
```

- [ ] **Step 2: Add derived variables**

Add this right after the new state variable (around line 108):

```typescript
const tickerCount = importedTickers.length;
const shouldCollapse = tickerCount > 8;
const visibleTickers = shouldCollapse
  ? importedTickers
  : importedTickers.slice(0, 8);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/QuantGen/Builder.tsx
git commit -m "wip: add ticker collapse state and derived variables"
```

---

### Task 2: Replace inline pills with collapsed/expanded logic

**Files:**
- Modify: `frontend/src/pages/QuantGen/Builder.tsx:1229-1258` (the imported tickers pill rendering block)

- [ ] **Step 1: Replace the pill rendering block**

Replace the entire `{importedTickers.length > 0 && (...)}` block (lines 1229-1258) with this:

```tsx
{importedTickers.length > 0 && (
  <div style={{ marginBottom: '8px' }}>
    {/* Summary badge when collapsed */}
    {shouldCollapse && !showAllTickers ? (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span
          style={{
            padding: '4px 10px',
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 600,
            border: '1px solid var(--border)',
            backgroundColor: 'var(--accent)',
            color: '#000000',
          }}
        >
          {tickerCount} ticker{tickerCount !== 1 ? 's' : ''} imported
        </span>
        <button
          onClick={() => setShowAllTickers(true)}
          style={{
            padding: '4px 10px',
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 600,
            border: '1px solid var(--border)',
            cursor: 'pointer',
            backgroundColor: 'var(--canvas)',
            color: 'var(--foreground)',
          }}
        >
          ▼ Show All
        </button>
      </div>
    ) : null}

    {/* Pill list: expanded or always-visible for small counts */}
    {(showAllTickers || !shouldCollapse) && (
      <div style={{ marginBottom: '8px' }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px',
            maxHeight: shouldCollapse ? '200px' : undefined,
            overflowY: shouldCollapse ? 'auto' : undefined,
            paddingBottom: '4px',
          }}
        >
          {importedTickers.map((t) => (
            <button
              key={t}
              onClick={() => {
                setTickers(t);
                if (code) {
                  let updated = replaceTickerInCode(code, t);
                  updated = replaceDatesInCode(updated, optConfig.wfo.start_date, optConfig.wfo.end_date);
                  setCode(updated);
                }
              }}
              style={{
                padding: '4px 10px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                border: '1px solid var(--border)',
                cursor: 'pointer',
                backgroundColor: tickers === t ? 'var(--accent)' : 'var(--canvas)',
                color: tickers === t ? '#000000' : 'var(--foreground)',
                transition: 'all 0.15s ease',
                flexShrink: 0,
              }}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Hide button (only shown when expanded from collapsed state) */}
        {shouldCollapse && showAllTickers && (
          <button
            onClick={() => setShowAllTickers(false)}
            style={{
              padding: '4px 10px',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 600,
              border: '1px solid var(--border)',
              cursor: 'pointer',
              backgroundColor: 'var(--canvas)',
              color: 'var(--foreground)',
              marginTop: '4px',
            }}
          >
            ▲ Hide
          </button>
        )}
      </div>
    )}
  </div>
)}
```

- [ ] **Step 2: Verify the change compiles**

Run:
```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30
```

Expected: No TypeScript errors related to Builder.tsx.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/QuantGen/Builder.tsx
git commit -m "fix: collapsible ticker list for large exports from Markov page"
```

---

## Verification

1. **Normal state (no exported tickers):** Load Builder page directly (no URL params). Verify ticker input shows normally with no pills or summary badge.

2. **Small export (1-8 tickers):** Navigate with `?tickers=AAPL,MSFT,GOOGL`. Verify all pills shown inline, no summary badge, no toggle.

3. **Large export (200+ tickers):** Navigate with `?tickers=AAPL,MSFT,...,ZZZZ` (200+). Verify:
   - Summary badge shows "200 tickers imported"
   - "▼ Show All" button visible
   - Code editor and right panel components visible (not pushed out)
   - Clicking "▼ Show All" expands to scrollable pill container (max-height ~200px)
   - Clicking a pill selects that ticker (badge highlights)
   - Clicking "▲ Hide" collapses back to summary

4. **Responsive:** Verify the ticker section doesn't overflow on 1280px viewport.

5. **No regression:** Verify all existing buttons (Generate, Backtest/Optimize toggle, Save, Run) still work and the code editor still occupies the left panel properly.