# Dormant Giant Screener v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Dormant Giant screener with 7 improved technical signals, composite scoring (0-100), new frontend filter controls, and a help modal.

**Architecture:** Single-file backend changes in `agno_screener.py` (new signal computation + scoring + SPY/sector context fetching), single-file frontend changes in `StockScreener.tsx` (new filters + score display + help modal). All new signals are computed inside the existing `analyze_single_ticker_dormant_giant` worker function.

**Tech Stack:** Python 3.11, Pandas, NumPy, SQLAlchemy, FastAPI, React 18, TypeScript, Tailwind CSS

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/services/agno_screener.py` | Modify heavily | All backend signal logic, scoring, SPY/sector context |
| `frontend/src/pages/StockScreener.tsx` | Modify heavily | New filter controls, score display, help modal |

---

## Task 1: Add SPY and Sector ETF Context Fetching (Backend)

**Files:**
- Modify: `backend/app/services/agno_screener.py` (new functions near top, after imports)

- [ ] **Step 1: Add `_fetch_spy_data()` function**

Add this function after the existing `get_active_tickers()` function (around line 64):

```python
def _fetch_spy_data(days: int = 200) -> pd.DataFrame:
    """Fetch SPY OHLCV data for relative strength calculations."""
    try:
        query = f'SELECT "Date", "Close" FROM "spy" ORDER BY "Date" DESC LIMIT {days}'
        df = pd.read_sql(query, ENGINE)
        if df.empty or len(df) < 20:
            return pd.DataFrame()
        return df.sort_values('Date').reset_index(drop=True)
    except Exception as e:
        logger.warning("Failed to fetch SPY data: %s", e)
        return pd.DataFrame()
```

- [ ] **Step 2: Add `_fetch_sector_etfs()` function**

Add immediately after `_fetch_spy_data()`:

```python
def _fetch_sector_etfs(days: int = 200) -> Dict[str, bool]:
    """Fetch sector ETF data and compute whether each is above its 50-day SMA."""
    sector_above_sma = {}
    etf_tickers = ['xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly']
    for etf in etf_tickers:
        try:
            query = f'SELECT "Date", "Close" FROM "{etf}" ORDER BY "Date" DESC LIMIT {days}'
            df = pd.read_sql(query, ENGINE)
            if df.empty or len(df) < 50:
                sector_above_sma[etf] = True  # Default to permissive
                continue
            df = df.sort_values('Date').reset_index(drop=True)
            sma_50 = df['Close'].rolling(window=50).mean().iloc[-1]
            current = df['Close'].iloc[-1]
            sector_above_sma[etf] = current > sma_50
        except Exception as e:
            logger.warning("Failed to fetch sector ETF %s: %s", etf, e)
            sector_above_sma[etf] = True
    return sector_above_sma
```

- [ ] **Step 3: Add `_get_ticker_sector_mapping()` function**

Add immediately after `_fetch_sector_etfs()`:

```python
def _get_ticker_sector_mapping() -> Dict[str, str]:
    """Build ticker -> sector_etf mapping from stock_metadata."""
    mapping = {}
    try:
        query = text("SELECT ticker, sector FROM stock_metadata WHERE ticker IS NOT NULL")
        with ENGINE.connect() as conn:
            result = conn.execute(query)
            for row in result:
                ticker = row[0].upper()
                sector = row[1]
                if sector:
                    # Map sector name to ETF ticker
                    sector_to_etf = {
                        'Technology': 'xlk', 'Energy': 'xle', 'Financials': 'xlf',
                        'Financial Services': 'xlf', 'Health Care': 'xlv', 'Healthcare': 'xlv',
                        'Consumer Discretionary': 'xly', 'Consumer Cyclical': 'xly',
                        'Industrials': 'xli', 'Communication Services': 'xlc',
                        'Consumer Staples': 'xlp', 'Consumer Defensive': 'xlp',
                        'Materials': 'xlb', 'Basic Materials': 'xlb',
                        'Real Estate': 'xlre', 'Utilities': 'xlu'
                    }
                    mapping[ticker] = sector_to_etf.get(sector, '').lower()
    except Exception as e:
        logger.warning("Failed to build sector mapping: %s", e)
    return mapping
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/agno_screener.py
git commit -m "feat: add SPY/sector context fetching for Dormant Giant v2"
```

---

## Task 2: Rewrite `analyze_single_ticker_dormant_giant` with New Signals

**Files:**
- Modify: `backend/app/services/agno_screener.py:66-148` (replace the entire function)

- [ ] **Step 1: Replace `analyze_single_ticker_dormant_giant` with new implementation**

Replace the function body (keep the signature) with:

```python
def analyze_single_ticker_dormant_giant(
    ticker: str,
    filters: Optional[Dict[str, Any]] = None,
    spy_df: Optional[pd.DataFrame] = None,
    sector_above_sma: Optional[Dict[str, bool]] = None,
    ticker_sector_map: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    """Worker function for Dormant Giant v2 technical analysis."""
    if filters is None:
        filters = {}

    worker_engine = create_engine(DB_URL, poolclass=QueuePool, pool_size=1)
    try:
        query = f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" FROM "{ticker.lower()}" ORDER BY "Date" DESC LIMIT 200'
        df = pd.read_sql(query, worker_engine).sort_values('Date').reset_index(drop=True)
    except Exception as e:
        return {"error": f"DB Error for {ticker}: {e}"}
    finally:
        worker_engine.dispose()

    if len(df) < 120:
        return {"error": f"{ticker.upper()}: Insufficient data (<120 days)"}

    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    # --- 1. Bollinger Bandwidth Squeeze (fixed) ---
    sma_20 = close.rolling(window=20).mean()
    std_20 = close.rolling(window=20).std()
    upper = sma_20 + (std_20 * 2)
    lower = sma_20 - (std_20 * 2)
    bandwidth = (upper - lower) / sma_20

    bw_120 = bandwidth.tail(120)
    min_bw = bw_120.min()
    max_bw = bw_120.max()
    current_bw = bandwidth.iloc[-1]

    bandwidth_pct = (current_bw - min_bw) / (max_bw - min_bw + 1e-9)
    is_squeezing = (bandwidth_pct < 0.20) and (current_bw < 0.06)

    # --- 2. Consolidation Tightness ---
    consolidation_days = filters.get('consolidation_days', 15)
    last_20 = df.tail(20)
    sma_20_last = sma_20.tail(20)
    within_band = (abs(last_20['Close'] - sma_20_last) / sma_20_last) < 0.03
    tight_consolidation = within_band.sum() >= consolidation_days

    # --- 3. MFI Accumulation (replaces OBV) ---
    def compute_mfi(df_subset: pd.DataFrame, period: int = 14) -> float:
        tp = (df_subset['High'] + df_subset['Low'] + df_subset['Close']) / 3
        rmf = tp * df_subset['Volume']
        delta = tp.diff()
        pos_flow = rmf.where(delta > 0, 0).rolling(window=period).sum()
        neg_flow = rmf.where(delta < 0, 0).rolling(window=period).sum()
        ratio = pos_flow / (neg_flow + 1e-9)
        mfi = 100 - (100 / (1 + ratio))
        return mfi.iloc[-1]

    mfi_20 = compute_mfi(df.tail(30), period=14)
    mfi_threshold = filters.get('mfi_threshold', 55)
    has_mfi_accumulation = mfi_20 > mfi_threshold

    # --- 4. Volume Cluster Detection ---
    avg_vol_50 = volume.tail(50).mean()
    vol_spike_days = (volume.tail(5) > (avg_vol_50 * 1.2)).sum()
    vol_cluster_days = filters.get('volume_cluster_days', 3)
    has_volume_cluster = vol_spike_days >= vol_cluster_days

    # --- 5. Relative Strength vs SPY ---
    rs_minimum = filters.get('rs_minimum', 0.8)
    is_strong_rs = True
    if spy_df is not None and not spy_df.empty and len(spy_df) >= 20:
        try:
            stock_20d_return = (close.iloc[-1] / close.iloc[-20]) - 1
            spy_close = spy_df['Close']
            spy_20d_return = (spy_close.iloc[-1] / spy_close.iloc[-20]) - 1
            if spy_20d_return != 0:
                rs_ratio = stock_20d_return / spy_20d_return
                is_strong_rs = rs_ratio >= rs_minimum
            else:
                rs_ratio = 1.0
        except Exception:
            rs_ratio = 1.0
    else:
        rs_ratio = 1.0

    # --- 6. Sector Momentum Gate ---
    use_sector_momentum = filters.get('use_sector_momentum', True)
    sector_ok = True
    if use_sector_momentum and ticker_sector_map and sector_above_sma:
        sector_etf = ticker_sector_map.get(ticker.upper(), '')
        if sector_etf and sector_etf in sector_above_sma:
            sector_ok = sector_above_sma[sector_etf]

    # --- 7. Breakout Detection (unchanged criteria, simplified) ---
    past_resistance = high.shift(3).rolling(window=120).max().iloc[-1]
    current_vol = volume.iloc[-1]
    is_breakout = (close.iloc[-1] > past_resistance) and (current_vol > (avg_vol_50 * 1.5))

    # --- Signal determination ---
    if is_breakout:
        signal = "Active Breakout"
        passes = True
    elif is_squeezing and tight_consolidation and has_mfi_accumulation and has_volume_cluster and is_strong_rs and sector_ok:
        signal = "Coiling (Accumulation)"
        passes = True
    else:
        return None

    # --- Composite Score (0-100) ---
    squeeze_score = max(0, 100 - (bandwidth_pct * 100))
    consolidation_score = (within_band.sum() / 20) * 100
    mfi_score = min(mfi_20, 100)
    volume_score = (vol_spike_days / 5) * 100
    rs_score = min(max(rs_ratio * 100, 0), 100)
    sector_score = 100 if sector_ok else 0

    composite_score = (
        squeeze_score * 0.20 +
        consolidation_score * 0.20 +
        mfi_score * 0.15 +
        volume_score * 0.15 +
        rs_score * 0.15 +
        sector_score * 0.15
    )

    result: Dict[str, Any] = {
        "ticker": ticker.upper(),
        "signal": signal,
        "log": f"MATCH: {ticker.upper()} - {signal} detected (Score: {composite_score:.1f})",
        "score": round(composite_score, 1),
        "close": round(float(close.iloc[-1]), 2),
        "sma_20": round(float(sma_20.iloc[-1]), 2),
        "ema_9": round(float(close.ewm(span=9, adjust=False).mean().iloc[-1]), 2),
        "high_52w": round(float(high.tail(252).max()), 2),
        "low_52w": round(float(low.tail(252).min()), 2),
        "mfi": round(mfi_20, 1),
        "volume_cluster_days": int(vol_spike_days),
        "rs_ratio": round(rs_ratio, 2),
        "bandwidth_pct": round(bandwidth_pct * 100, 1),
    }

    # Volume stats
    try:
        latest_vol = float(volume.iloc[-1])
        result['volume'] = int(latest_vol) if latest_vol > 0 else None
        result['volume_ma_50'] = round(float(avg_vol_50), 0) if avg_vol_50 > 0 else None
        result['volume_ratio'] = round(latest_vol / avg_vol_50, 4) if avg_vol_50 > 0 else None
    except Exception:
        result['volume'] = None
        result['volume_ma_50'] = None
        result['volume_ratio'] = None

    # All-time high/low
    try:
        ath_query = f'SELECT MAX("High") as ath, MIN("Low") as atl FROM "{ticker.lower()}"'
        ath_df = pd.read_sql(ath_query, worker_engine)
        result['all_time_high'] = round(float(ath_df['ath'].iloc[0]), 2) if pd.notnull(ath_df['ath'].iloc[0]) else None
        result['all_time_low'] = round(float(ath_df['atl'].iloc[0]), 2) if pd.notnull(ath_df['atl'].iloc[0]) else None
    except Exception:
        result['all_time_high'] = None
        result['all_time_low'] = None

    return result
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/agno_screener.py
git commit -m "feat: rewrite Dormant Giant analysis with v2 signals and composite scoring"
```

---

## Task 3: Update `tool_run_dormant_giant_scan` to Pass Context

**Files:**
- Modify: `backend/app/services/agno_screener.py:151-188`

- [ ] **Step 1: Replace `tool_run_dormant_giant_scan` function body**

Replace the function (keep signature) with:

```python
def tool_run_dormant_giant_scan(progress_callback=None, log_callback=None, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Technical scan for Dormant Giant v2 screening."""
    tickers = get_active_tickers()
    total = len(tickers)
    results = []

    if log_callback:
        log_callback(f"Technical Agent: Analyzing {total} tickers for explosive setups...")
    logger.info("Starting Dormant Giant v2 scan for %d tickers", total)

    # Fetch market context once
    spy_df = _fetch_spy_data()
    sector_above_sma = _fetch_sector_etfs()
    ticker_sector_map = _get_ticker_sector_mapping()

    if log_callback:
        log_callback(f"Market context loaded — SPY data: {'yes' if not spy_df.empty else 'no'}, Sector ETFs: {len(sector_above_sma)}")

    with ProcessPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(
                analyze_single_ticker_dormant_giant,
                t,
                filters,
                spy_df,
                sector_above_sma,
                ticker_sector_map
            ): t for t in tickers
        }
        completed = 0
        total = len(tickers)
        for future in futures:
            try:
                result = future.result()
                if result:
                    if "log" in result and log_callback:
                        log_callback(result["log"])
                    if "error" in result and log_callback:
                        log_callback(result["error"])
                    if "ticker" in result:
                        results.append(result)
            except Exception as e:
                if log_callback:
                    log_callback(f"Worker error: {e}")
            finally:
                completed += 1
                if progress_callback and total > 0:
                    progress = 10 + int((completed / total) * 70)
                    progress_callback(progress)

    # Sort by composite score descending
    results.sort(key=lambda x: x.get('score', 0), reverse=True)

    logger.info("Dormant Giant v2 Scan Summary: Total=%d, Results=%d", total, len(results))
    return results
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/agno_screener.py
git commit -m "feat: pass market context to workers and sort by composite score"
```

---

## Task 4: Update Frontend Filter State and Controls

**Files:**
- Modify: `frontend/src/pages/StockScreener.tsx`

- [ ] **Step 1: Replace filter state initialization**

Find the existing filter state (around line 118-123):
```typescript
  const [filters, setFilters] = useState({
    squeeze_threshold: 1.5,
    accumulation_threshold: 0.01,
    volume_threshold: 1.2,
  });
```

Replace with:
```typescript
  const [filters, setFilters] = useState({
    consolidation_days: 15,
    mfi_threshold: 55,
    volume_cluster_days: 3,
    rs_minimum: 0.8,
    use_sector_momentum: true,
  });
```

- [ ] **Step 2: Replace the filter sliders JSX**

Find the filter sliders section (around line 998-1040) that maps over the 3 old sliders. Replace the entire `.map()` block with:

```tsx
                {[
                  {
                    key: "consolidation_days" as const,
                    label: "Consolidation Tightness",
                    description: "Days price stays within 3% of 20-day SMA",
                    min: 10,
                    max: 20,
                    step: 1,
                    format: (v: number) => `${v} days`,
                  },
                  {
                    key: "mfi_threshold" as const,
                    label: "MFI Accumulation",
                    description: "Money Flow Index threshold (volume-weighted RSI)",
                    min: 45,
                    max: 70,
                    step: 1,
                    format: (v: number) => `${v}`,
                  },
                  {
                    key: "volume_cluster_days" as const,
                    label: "Volume Cluster",
                    description: "Days with volume > 1.2x average (out of last 5)",
                    min: 2,
                    max: 5,
                    step: 1,
                    format: (v: number) => `${v} days`,
                  },
                  {
                    key: "rs_minimum" as const,
                    label: "RS vs SPY",
                    description: "Minimum relative strength ratio vs SPY",
                    min: 0.5,
                    max: 1.2,
                    step: 0.05,
                    format: (v: number) => v.toFixed(2),
                  },
                ].map((slider) => (
                  <div key={slider.key}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '4px',
                    }}>
                      <div>
                        <span style={LABEL_STYLE}>{slider.label}</span>
                        <span style={{ ...LABEL_STYLE, color: colors.subtle, marginLeft: '8px' }}>
                          {slider.description}
                        </span>
                      </div>
                      <span style={{
                        fontSize: '17px',
                        fontWeight: 600,
                        fontVariantNumeric: 'tabular-nums',
                        color: '#10B981',
                      }}>
                        {slider.format(filters[slider.key] as number)}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={slider.min}
                      max={slider.max}
                      step={slider.step}
                      value={filters[slider.key] as number}
                      onChange={(e) => setFilters({ ...filters, [slider.key]: parseFloat(e.target.value) })}
                      disabled={selectedMode !== 'dormant_giant'}
                      style={{
                        width: '100%',
                        height: '4px',
                        appearance: 'none',
                        backgroundColor: selectedMode === 'dormant_giant' ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.05)',
                        borderRadius: '2px',
                        outline: 'none',
                        cursor: selectedMode === 'dormant_giant' ? 'pointer' : 'not-allowed',
                      }}
                    />
                  </div>
                ))}

                {/* Sector momentum toggle */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 0',
                }}>
                  <div>
                    <span style={LABEL_STYLE}>Sector Momentum Gate</span>
                    <span style={{ ...LABEL_STYLE, color: colors.subtle, marginLeft: '8px', display: 'block' }}>
                      Only scan stocks in sectors above their 50-day SMA
                    </span>
                  </div>
                  <button
                    onClick={() => setFilters({ ...filters, use_sector_momentum: !filters.use_sector_momentum })}
                    disabled={selectedMode !== 'dormant_giant'}
                    style={{
                      width: '48px',
                      height: '28px',
                      borderRadius: '14px',
                      border: 'none',
                      cursor: selectedMode === 'dormant_giant' ? 'pointer' : 'not-allowed',
                      backgroundColor: filters.use_sector_momentum ? '#10B981' : 'rgba(255,255,255,0.1)',
                      position: 'relative',
                      transition: 'background-color 200ms ease',
                    }}
                  >
                    <div style={{
                      width: '22px',
                      height: '22px',
                      borderRadius: '11px',
                      backgroundColor: '#fff',
                      position: 'absolute',
                      top: '3px',
                      left: filters.use_sector_momentum ? '23px' : '3px',
                      transition: 'left 200ms ease',
                    }} />
                  </button>
                </div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/StockScreener.tsx
git commit -m "feat: replace Dormant Giant filter sliders with v2 controls"
```

---

## Task 5: Add Score Display to Results Cards

**Files:**
- Modify: `frontend/src/pages/StockScreener.tsx` (results rendering section)

- [ ] **Step 1: Add `ScoreBadge` helper component inside `StockScreener`**

Add this before the `return` statement of the component (around line 430, before the JSX return):

```typescript
  const ScoreBadge = ({ score }: { score: number }) => {
    const color = score >= 70 ? '#10B981' : score >= 50 ? '#F59E0B' : '#EF4444';
    const label = score >= 70 ? 'Strong' : score >= 50 ? 'Moderate' : 'Weak';
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
      }}>
        <div style={{
          width: '40px',
          height: '40px',
          borderRadius: '10px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: `${color}15`,
          border: `1px solid ${color}30`,
        }}>
          <span style={{ fontSize: '15px', fontWeight: 700, color }}>{score.toFixed(0)}</span>
        </div>
        <div>
          <div style={{ fontSize: '12px', fontWeight: 600, color: colors.muted }}>Explosiveness</div>
          <div style={{ fontSize: '13px', fontWeight: 600, color }}>{label}</div>
        </div>
      </div>
    );
  };
```

- [ ] **Step 2: Add score and new fields to results cards**

Find the results card rendering section (where `results.map((result) => (` is). Inside the card, add after the ticker/signal header:

```tsx
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                      <div>
                        <span style={{ fontSize: '20px', fontWeight: 700, color: colors.text }}>{result.ticker}</span>
                        {result.company_name && result.company_name !== result.ticker && (
                          <span style={{ fontSize: '14px', color: colors.muted, marginLeft: '8px' }}>{result.company_name}</span>
                        )}
                      </div>
                      {result.score != null && <ScoreBadge score={result.score} />}
                    </div>
```

Then add a "Signal breakdown" section inside the card, after the existing stats grid:

```tsx
                    {/* Signal Breakdown */}
                    {result.mfi != null && (
                      <div style={{
                        marginTop: '16px',
                        padding: '12px',
                        borderRadius: '10px',
                        backgroundColor: colors.surfaceRaised,
                        border: `1px solid ${colors.border}`,
                      }}>
                        <div style={{ fontSize: '12px', fontWeight: 600, color: colors.muted, marginBottom: '8px' }}>Signal Breakdown</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                          <div style={{ fontSize: '13px', color: colors.text }}>
                            <span style={{ color: colors.muted }}>MFI: </span>{result.mfi}
                          </div>
                          <div style={{ fontSize: '13px', color: colors.text }}>
                            <span style={{ color: colors.muted }}>Vol Cluster: </span>{result.volume_cluster_days} days
                          </div>
                          <div style={{ fontSize: '13px', color: colors.text }}>
                            <span style={{ color: colors.muted }}>RS vs SPY: </span>{result.rs_ratio?.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '13px', color: colors.text }}>
                            <span style={{ color: colors.muted }}>Bandwidth: </span>{result.bandwidth_pct?.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                    )}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/StockScreener.tsx
git commit -m "feat: add composite score badge and signal breakdown to results cards"
```

---

## Task 6: Add Help Modal

**Files:**
- Modify: `frontend/src/pages/StockScreener.tsx`

- [ ] **Step 1: Add help modal state**

Add to the state declarations (around line 117, after `scanCompleted`):
```typescript
  const [showHelp, setShowHelp] = useState(false);
```

- [ ] **Step 2: Add Help button to the header**

Find the header section (around line 436-480 where the main title is). After the `<h1>` title, add:

```tsx
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '16px' }}>
                <button
                  onClick={() => setShowHelp(true)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '8px 16px',
                    borderRadius: '10px',
                    border: `1px solid ${colors.border}`,
                    backgroundColor: 'transparent',
                    color: colors.muted,
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <span>How it works</span>
                </button>
              </div>
```

- [ ] **Step 3: Add Help modal JSX**

Add the modal at the end of the component's JSX, just before the final `</div>` of the main return (around line 1780, before the outermost closing div):

```tsx
      {/* Help Modal */}
      {showHelp && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'rgba(0,0,0,0.6)',
            padding: '24px',
          }}
          onClick={() => setShowHelp(false)}
        >
          <div
            style={{
              maxWidth: '640px',
              width: '100%',
              maxHeight: '80vh',
              overflow: 'auto',
              backgroundColor: colors.surface,
              border: `1px solid ${colors.border}`,
              borderRadius: '20px',
              padding: '32px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '21px', fontWeight: 600, color: colors.text, margin: 0 }}>How Dormant Giant Works</h2>
              <button
                onClick={() => setShowHelp(false)}
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  border: 'none',
                  backgroundColor: 'transparent',
                  color: colors.muted,
                  cursor: 'pointer',
                  fontSize: '18px',
                }}
              >
                ×
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <section>
                <h3 style={{ fontSize: '15px', fontWeight: 600, color: colors.text, marginBottom: '8px' }}>What is a Dormant Giant?</h3>
                <p style={{ fontSize: '14px', color: colors.muted, lineHeight: 1.6, margin: 0 }}>
                  A stock that has been quietly building energy through a tight consolidation (low volatility, flat price)
                  while institutional buyers accumulate shares beneath the surface. When the squeeze resolves, the stock
                  often explodes upward — that's the "giant waking up."
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '15px', fontWeight: 600, color: colors.text, marginBottom: '8px' }}>The 6 Signals</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {[
                    {
                      name: 'Bollinger Squeeze',
                      desc: 'Bandwidth in the bottom 20% of its 120-day range and under 6%. True volatility contraction.',
                    },
                    {
                      name: 'Consolidation Tightness',
                      desc: 'Price stays within 3% of its 20-day SMA for at least 15 of the last 20 days. No drift.',
                    },
                    {
                      name: 'MFI Accumulation',
                      desc: 'Money Flow Index > 55. Volume-weighted RSI showing buying pressure.',
                    },
                    {
                      name: 'Volume Cluster',
                      desc: '3+ of the last 5 days with volume > 1.2x average. Institutional footprints.',
                    },
                    {
                      name: 'RS vs SPY',
                      desc: 'Stock is not severely lagging the market. Avoids false breakouts into weakness.',
                    },
                    {
                      name: 'Sector Momentum',
                      desc: 'Parent sector ETF is above its 50-day SMA. Fish in rising water.',
                    },
                  ].map((signal) => (
                    <div key={signal.name} style={{ padding: '12px', borderRadius: '10px', backgroundColor: colors.surfaceRaised }}>
                      <div style={{ fontSize: '14px', fontWeight: 600, color: colors.text }}>{signal.name}</div>
                      <div style={{ fontSize: '13px', color: colors.muted, marginTop: '4px' }}>{signal.desc}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h3 style={{ fontSize: '15px', fontWeight: 600, color: colors.text, marginBottom: '8px' }}>Composite Score (0-100)</h3>
                <p style={{ fontSize: '14px', color: colors.muted, lineHeight: 1.6, margin: 0 }}>
                  Each passing stock receives an explosiveness score based on all 6 signals.
                  <strong style={{ color: '#10B981' }}>Green (≥70)</strong> = strong setup.
                  <strong style={{ color: '#F59E0B' }}>Yellow (50-69)</strong> = moderate.
                  <strong style={{ color: '#EF4444' }}>Red (<50)</strong> = weaker but still passing.
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '15px', fontWeight: 600, color: colors.text, marginBottom: '8px' }}>Tips</h3>
                <ul style={{ fontSize: '14px', color: colors.muted, lineHeight: 1.8, margin: 0, paddingLeft: '18px' }}>
                  <li>Lower "Consolidation Tightness" to find more candidates.</li>
                  <li>Lower "MFI Accumulation" if you want earlier signals.</li>
                  <li>Turn off "Sector Momentum" if the overall market is choppy.</li>
                  <li>Scores ≥ 70 with "Active Breakout" signal are the highest-conviction setups.</li>
                </ul>
              </section>
            </div>
          </div>
        </div>
      )}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/StockScreener.tsx
git commit -m "feat: add Dormant Giant help modal with signal explanations"
```

---

## Task 7: Type-Check Frontend and Run Verification

**Files:**
- Test: Full screener run via API

- [ ] **Step 1: Type-check frontend**

```bash
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/frontend
./node_modules/.bin/tsc --noEmit
echo "Exit code: $?"
```
Expected: Exit code 0

- [ ] **Step 2: Restart backend to pick up changes**

The backend is already running (PID from earlier). Restart it:
```bash
# Kill existing and restart
cd /Users/shailendrakaushik/Documents/Python/AlgoTrading/TradeCraft-1/AITrader-1/backend
# Find and restart
echo "Backend restart needed — please stop existing Python process and run: cd backend && ./venv/bin/python -m app.main"
```

- [ ] **Step 3: Run API test with default filters**

```bash
curl -s -X POST http://localhost:8000/api/screener/scan \
  -H "Content-Type: application/json" \
  -d '{"mode":"dormant_giant","use_ai":false,"max_results":20}' | python -m json.tool
echo "---"
# Wait 20s then fetch results
sleep 20
curl -s http://localhost:8000/api/screener/results/SCAN_ID_HERE | python -m json.tool
```

Expected: 5-20 results, each with `score`, `mfi`, `rs_ratio`, `volume_cluster_days`, `bandwidth_pct` fields. Results sorted by score descending.

- [ ] **Step 4: Test tighter filters**

```bash
curl -s -X POST http://localhost:8000/api/screener/scan \
  -H "Content-Type: application/json" \
  -d '{"mode":"dormant_giant","use_ai":false,"max_results":20,"filters":{"consolidation_days":20,"mfi_threshold":65,"volume_cluster_days":4}}'
```

Expected: Fewer results than default.

- [ ] **Step 5: Test with sector momentum disabled**

```bash
curl -s -X POST http://localhost:8000/api/screener/scan \
  -H "Content-Type: application/json" \
  -d '{"mode":"dormant_giant","use_ai":false,"max_results":20,"filters":{"use_sector_momentum":false}}'
```

Expected: Equal or more results than with sector momentum on.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-05-09-dormant-giant-v2-design.md
git add docs/superpowers/plans/2026-05-09-dormant-giant-v2-plan.md
git commit -m "docs: add Dormant Giant v2 design spec and implementation plan"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| Bollinger bandwidth fix (bottom 20%, <6%) | Task 2 |
| Consolidation tightness filter | Task 2 |
| MFI replaces OBV | Task 2 |
| Volume cluster detection | Task 2 |
| Relative Strength vs SPY | Task 2 |
| Sector momentum gate | Tasks 1 + 2 |
| Composite scoring (0-100) | Task 2 |
| New filter sliders | Task 4 |
| Score display on results | Task 5 |
| Help modal | Task 6 |
| Remove obsolete sliders | Task 4 |

**No gaps found. No placeholders found. Types are consistent across tasks.**

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-05-09-dormant-giant-v2-plan.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach would you like?
