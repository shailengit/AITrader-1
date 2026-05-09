"""
Agno Multi-Agent Stock Screener Service for TradeCraft.
Implements two screening modes from original StockScreener_2:
1. Quant Strategy (agnoMultiAgentTrader_2) - TA-based with backtesting
2. Dormant Giant (agnoMultiAgentTrader_3) - Bollinger squeeze + EPS acceleration

Includes real-time progress callbacks and AGNO stdout capture for SSE streaming.
"""

import os
import sys
import io
import logging
import pandas as pd
import numpy as np
from ta import add_all_ta_features
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# Database configuration
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "sarina00")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5431")
DB_NAME = os.getenv("DB_NAME", "sp1500_1d")
DB_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

# Model configuration
OLLAMA_MODEL_ID = os.getenv("OLLAMA_MODEL_ID", "glm-5:cloud")
OLLAMA_MODEL_ID_ALT = os.getenv("OLLAMA_MODEL_ID_FALLBACK", "minimax-m2.5:cloud")

# Connection pool
ENGINE = create_engine(
    DB_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)


# =============================================================================
# DORMANT GIANT SCREENER (agnoMultiAgentTrader_3.py)
# =============================================================================

def get_active_tickers() -> List[str]:
    """Get list of active tickers from database."""
    with ENGINE.connect() as conn:
        res = conn.execute(text("SELECT ticker FROM stock_metadata WHERE ticker IS NOT NULL"))
        tickers = [row[0] for row in res]

    skip_tables = {
        'xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly',
        'stock_financials_quarterly', 'stock_financials_yearly', 'stock_metadata',
        'all', 'aci', 'cns', 'brk-b', 'bf-b', 'on', 'v', 't', 'w', 'gs', 'd', 'n',
        'ko', 'sn', 'zto', 'ac', 'nls', 'vod', 'wtv'
    }
    return [t for t in tickers if t.lower() not in skip_tables]


def _fetch_spy_data(days: int = 200, cutoff_date: Optional[str] = None) -> pd.DataFrame:
    """Fetch SPY OHLCV data for relative strength calculations."""
    try:
        if cutoff_date:
            query = f'SELECT "Date", "Close" FROM "spy" WHERE "Date" <= \'{cutoff_date}\' ORDER BY "Date" DESC LIMIT {days}'
        else:
            query = f'SELECT "Date", "Close" FROM "spy" ORDER BY "Date" DESC LIMIT {days}'
        df = pd.read_sql(query, ENGINE)
        if df.empty or len(df) < 20:
            return pd.DataFrame()
        return df.sort_values('Date').reset_index(drop=True)
    except Exception as e:
        logger.warning("Failed to fetch SPY data: %s", e)
        return pd.DataFrame()


def _fetch_sector_etfs(days: int = 200, cutoff_date: Optional[str] = None) -> Dict[str, bool]:
    """Fetch sector ETF data and compute whether each is above its 50-day SMA."""
    sector_above_sma = {}
    etf_tickers = ['xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly']
    for etf in etf_tickers:
        try:
            if cutoff_date:
                query = f'SELECT "Date", "Close" FROM "{etf}" WHERE "Date" <= \'{cutoff_date}\' ORDER BY "Date" DESC LIMIT {days}'
            else:
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


def analyze_single_ticker_dormant_giant(
    ticker: str,
    filters: Optional[Dict[str, Any]] = None,
    spy_df: Optional[pd.DataFrame] = None,
    sector_above_sma: Optional[Dict[str, bool]] = None,
    ticker_sector_map: Optional[Dict[str, str]] = None,
    cutoff_date: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Worker function for Dormant Giant v2 technical analysis."""
    if filters is None:
        filters = {}

    worker_engine = create_engine(DB_URL, poolclass=QueuePool, pool_size=1)
    try:
        if cutoff_date:
            query = f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" FROM "{ticker.lower()}" WHERE "Date" <= \'{cutoff_date}\' ORDER BY "Date" DESC LIMIT 200'
        else:
            query = f'SELECT "Date", "Open", "High", "Low", "Close", "Volume" FROM "{ticker.lower()}" ORDER BY "Date" DESC LIMIT 200'
        df = pd.read_sql(query, worker_engine)
        df = df.sort_values('Date').reset_index(drop=True)
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


def tool_run_dormant_giant_scan(progress_callback=None, log_callback=None, filters: Optional[Dict[str, Any]] = None, cutoff_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Technical scan for Dormant Giant v2 screening."""
    tickers = get_active_tickers()
    total = len(tickers)
    results = []

    if log_callback:
        log_callback(f"Technical Agent: Analyzing {total} tickers for explosive setups...")
    logger.info("Starting Dormant Giant v2 scan for %d tickers", total)

    # Fetch market context once
    spy_df = _fetch_spy_data(cutoff_date=cutoff_date)
    sector_above_sma = _fetch_sector_etfs(cutoff_date=cutoff_date)
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
                ticker_sector_map,
                cutoff_date
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


def tool_verify_eps_acceleration(tickers: List[Dict], log_callback=None) -> List[Dict]:
    """Verify EPS acceleration OR revenue growth for screened tickers."""
    verified_tickers = []
    if log_callback:
        log_callback(f"Fundamental Agent: Verifying catalysts for {len(tickers)} candidates...")

    for item in tickers:
        ticker = item['ticker']
        catalyst = None
        try:
            query = text("""
                SELECT diluted_eps as eps, total_revenue FROM stock_financials_quarterly
                WHERE ticker = :ticker ORDER BY report_date DESC LIMIT 3;
            """)
            with ENGINE.connect() as conn:
                fin_df = pd.read_sql(query, conn, params={"ticker": ticker})

            # EPS check: positive growth
            if len(fin_df) >= 2:
                current_eps = fin_df['eps'].iloc[0]
                prev_eps = fin_df['eps'].iloc[1]
                if pd.notnull(current_eps) and pd.notnull(prev_eps) and prev_eps != 0:
                    current_growth = (current_eps - prev_eps) / abs(prev_eps)
                    if current_growth > 0:
                        catalyst = "Confirmed EPS Acceleration"

            # Fallback: revenue growth
            if not catalyst and len(fin_df) >= 2:
                curr_rev = fin_df['total_revenue'].iloc[0]
                prev_rev = fin_df['total_revenue'].iloc[1]
                if pd.notnull(curr_rev) and pd.notnull(prev_rev) and prev_rev > 0:
                    rev_growth = (curr_rev - prev_rev) / prev_rev
                    if rev_growth > 0:
                        catalyst = "Confirmed Revenue Growth"

        except Exception as e:
            logger.error("Fundamental verification error for %s: %s", ticker, e)
            pass

        if catalyst:
            item['fundamental_catalyst'] = catalyst
            verified_tickers.append(item)

    if log_callback:
        log_callback(f"Fundamental Agent: Verification complete. {len(verified_tickers)} stocks verified.")
    return verified_tickers


# =============================================================================
# QUANT STRATEGY SCREENER (agnoMultiAgentTrader_2.py)
# =============================================================================

def _worker_ta_analysis(ticker: str, requested_indicators: List[str], cutoff_date: Optional[str] = None) -> Optional[Dict]:
    """Worker for multiprocessing TA calculations using ta library (matching standalone)."""
    if not ticker or not isinstance(ticker, str):
        return None

    safe_ticker = ticker.lower().strip()
    worker_engine = create_engine(DB_URL, poolclass=QueuePool, pool_size=1)

    try:
        if cutoff_date:
            df = pd.read_sql(
                f'SELECT * FROM {safe_ticker} WHERE "Date" <= :cutoff_date ORDER BY "Date" DESC LIMIT 250',
                worker_engine, params={"cutoff_date": cutoff_date}
            )
        else:
            df = pd.read_sql(f'SELECT * FROM {safe_ticker} ORDER BY "Date" DESC LIMIT 250', worker_engine)

        if df.empty or len(df) < 50:
            return None

        df = df.sort_values(by="Date").reset_index(drop=True)

        # Use ta library for all indicators (matching standalone)
        df = add_all_ta_features(df, "Open", "High", "Low", "Close", "Volume", fillna=True)

        latest = df.iloc[-1]
        res = {'ticker': ticker.upper(), 'close': round(latest['Close'], 2)}
        for col in requested_indicators:
            if col in latest:
                try:
                    res[col] = round(latest[col], 4)
                except (TypeError, ValueError):
                    res[col] = latest[col]

        # Enrich with price stats
        res['sma_20'] = round(float(df['Close'].rolling(window=20).mean().iloc[-1]), 2)
        res['ema_9'] = round(float(df['Close'].ewm(span=9, adjust=False).mean().iloc[-1]), 2)
        res['high_52w'] = round(float(df['High'].tail(252).max()), 2)
        res['low_52w'] = round(float(df['Low'].tail(252).min()), 2)

        # Volume ratio vs 50-day average + raw volume stats
        try:
            avg_vol_50 = float(df['Volume'].tail(50).mean())
            res['volume'] = int(latest['Volume']) if pd.notnull(latest['Volume']) else None
            res['volume_ma_50'] = round(avg_vol_50, 0) if avg_vol_50 > 0 else None
            res['volume_ratio'] = round(float(latest['Volume']) / avg_vol_50, 4) if avg_vol_50 > 0 else None
        except Exception:
            res['volume'] = None
            res['volume_ma_50'] = None
            res['volume_ratio'] = None

        # All-time high/low (fast indexed query)
        try:
            ath_query = f'SELECT MAX("High") as ath, MIN("Low") as atl FROM {safe_ticker}'
            ath_df = pd.read_sql(ath_query, worker_engine)
            ath_val = float(ath_df['ath'].iloc[0]) if pd.notnull(ath_df['ath'].iloc[0]) else None
            atl_val = float(ath_df['atl'].iloc[0]) if pd.notnull(ath_df['atl'].iloc[0]) else None
            res['all_time_high'] = round(ath_val, 2) if ath_val else None
            res['all_time_low'] = round(atl_val, 2) if atl_val else None
            if ath_val and ath_val > 0:
                res['ath_proximity'] = round(float(latest['Close']) / ath_val, 4)
        except Exception:
            res['all_time_high'] = None
            res['all_time_low'] = None
            res['ath_proximity'] = None

        return res
    except Exception as e:
        logger.debug("Error processing %s: %s", ticker, e)
        return None
    finally:
        worker_engine.dispose()


def _worker_ta_wrapper(args_tuple):
    """Module-level wrapper for multiprocessing."""
    return _worker_ta_analysis(*args_tuple)


def technical_screener(requested_indicators: List[str], sort_by: str = "ticker",
                       cutoff_date: Optional[str] = None,
                       progress_callback=None, log_callback=None,
                       filters: Optional[Dict[str, Any]] = None) -> str:
    """Screen S&P 1500 using parallel processing with ta library (matching standalone)."""
    # Source tickers from information_schema.tables (matching standalone)
    with ENGINE.connect() as conn:
        res = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ))
        tickers = [row[0] for row in res if row[0] not in
                   ['stock_metadata', 'stock_financials_quarterly', 'stock_financials_yearly']]

    total = len(tickers)
    if log_callback:
        log_callback(f"Scanning {total} stocks for {requested_indicators}...")

    args = [(ticker, requested_indicators, cutoff_date) for ticker in tickers]
    results = []
    completed = 0

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {executor.submit(_worker_ta_wrapper, a): a for a in args}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                if log_callback:
                    log_callback(f"Worker error: {e}")
            finally:
                completed += 1
                if progress_callback and total > 0:
                    progress = 10 + int((completed / total) * 60)
                    progress_callback(progress)

    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        # Apply user-defined QuantFilters if provided
        if filters:
            df = apply_quant_filters(df, filters)
            if log_callback:
                log_callback(f"Applied filters: {len(df)} stocks remain after filtering.")
        elif sort_by in df.columns:
            df = df.sort_values(by=sort_by).head(50)

    return df.to_csv(index=False) if not df.empty else "No results found."


def query_fundamental_health(tickers: List[str], cutoff_date: Optional[str] = None) -> str:
    """Analyze fundamental data for tickers (matching standalone: adds net_margin, same column names)."""
    date_filter = 'WHERE report_date <= :cutoff_date' if cutoff_date else ''

    query = text(f"""
        WITH Ranked AS (
            SELECT ticker, report_date, total_revenue, net_income,
            LAG(total_revenue) OVER (PARTITION BY ticker ORDER BY report_date ASC) as prev_rev
            FROM stock_financials_quarterly {date_filter}
        )
        SELECT * FROM Ranked WHERE ticker = ANY(:t) ORDER BY ticker, report_date DESC
    """)
    # Note: The WHERE ticker = ANY(:t) is in the outer query to preserve LAG partitioning

    try:
        params: dict = {"t": [t.upper() for t in tickers]}
        if cutoff_date:
            params["cutoff_date"] = cutoff_date
        df = pd.read_sql(query, ENGINE, params=params)

        if df.empty:
            return "No fundamental data found."

        summary = []
        for t in tickers:
            t_df = df[df['ticker'] == t.upper()]
            if len(t_df) < 2:
                continue
            curr, prev = t_df.iloc[0], t_df.iloc[1]
            growth = (curr['total_revenue'] - curr['prev_rev']) / curr['prev_rev'] if curr['prev_rev'] else 0
            margin = curr['net_income'] / curr['total_revenue'] if curr['total_revenue'] else 0
            summary.append({
                'ticker': t.upper(),
                'rev_growth_qoq': f"{growth:.2%}",
                'net_margin': f"{margin:.2%}",
                'trend': "Improving" if curr['total_revenue'] > prev['total_revenue'] else "Declining"
            })
        return pd.DataFrame(summary).to_csv(index=False)
    except Exception as e:
        return f"Fundamental Error: {str(e)}"


def tool_query_metadata(tickers: List[str]) -> str:
    """Fetch Sector, Market Cap, and Beta for tickers."""
    query = text("SELECT ticker, name, sector, market_cap, beta FROM stock_metadata WHERE ticker = ANY(:t)")
    try:
        df = pd.read_sql(query, ENGINE, params={"t": [t.upper() for t in tickers]})
        return df.to_csv(index=False) if not df.empty else "No metadata found."
    except Exception as e:
        return f"Metadata Error: {str(e)}"


def tool_get_historical_performance(tickers: List[str], cutoff_date: str) -> str:
    """Calculate performance from cutoff_date to today."""
    if not cutoff_date:
        return "No cutoff_date provided."

    try:
        datetime.strptime(cutoff_date, "%Y-%m-%d")
    except ValueError:
        return f"Invalid cutoff_date format. Use YYYY-MM-DD."

    results = []
    for ticker in tickers:
        if not ticker or not isinstance(ticker, str) or not ticker.isalnum():
            continue

        try:
            ticker_lower = ticker.lower().strip()

            price_at_cutoff_query = text(f'''
                SELECT "Close", "Date" FROM "{ticker_lower}"
                WHERE "Date" <= :cutoff_date
                ORDER BY "Date" DESC LIMIT 1
            ''')
            cutoff_df = pd.read_sql(price_at_cutoff_query, ENGINE, params={"cutoff_date": cutoff_date})

            if cutoff_df.empty:
                continue

            price_at_cutoff = cutoff_df.iloc[0]['Close']
            cutoff_actual_date = cutoff_df.iloc[0]['Date']

            latest_query = text(f'SELECT "Close", "Date" FROM "{ticker_lower}" ORDER BY "Date" DESC LIMIT 1')
            latest_df = pd.read_sql(latest_query, ENGINE)

            if latest_df.empty:
                continue

            current_price = latest_df.iloc[0]['Close']
            latest_date = latest_df.iloc[0]['Date']
            pct_change = ((current_price - price_at_cutoff) / price_at_cutoff) * 100

            results.append({
                'ticker': ticker.upper(),
                'cutoff_date': str(cutoff_actual_date)[:10],
                'price_at_cutoff': round(price_at_cutoff, 2),
                'latest_date': str(latest_date)[:10],
                'current_price': round(current_price, 2),
                'pct_change': round(pct_change, 2)
            })
        except Exception as e:
            logger.warning("Error processing %s: %s", ticker, e)
            continue

    return pd.DataFrame(results).to_csv(index=False) if results else "No performance data available."


# =============================================================================
# QUANT FILTER PARSING & APPLICATION
# =============================================================================

QUANT_FILTER_SCHEMA = {
    "ath_proximity_min": "float|null  // 0-1, e.g. 0.95 = within 5% of ATH",
    "ath_proximity_max": "float|null",
    "rsi_min": "float|null  // 0-100",
    "rsi_max": "float|null  // 0-100",
    "volume_ratio_min": "float|null  // vs 50-day avg",
    "sma_20_relation": "'above'|'below'|'any'",
    "sma_50_relation": "'above'|'below'|'any'",
    "sector_whitelist": "[string]  // e.g. ['Technology','Healthcare']",
    "market_cap_min": "float|null  // in billions",
    "market_cap_max": "float|null  // in billions",
    "eps_growth_min": "float|null  // decimal, e.g. 0.10 = 10%",
    "revenue_growth_min": "float|null  // decimal, e.g. 0.10 = 10%",
    "sort_by": "'ticker'|'ath_proximity'|'rsi'|'volume_ratio'|'close'",
    "sort_order": "'asc'|'desc'",
    "max_results": "int  // default 20"
}

FILTER_PARSER_PROMPT = """You are a stock screener filter parser.
Convert the user's request into a JSON object matching this schema exactly.
Only include non-null fields. Return ONLY valid JSON, no markdown, no explanation.

Schema fields:
{schema}

Default rules:
- If user asks for stocks "close to all time high", set ath_proximity_min to 0.90-0.98 depending on wording (very close = 0.98, close = 0.95, near = 0.90).
- If user specifies a count (e.g. "top 20", "find 50"), set max_results to that number.
- sort_by defaults to "ath_proximity" if ATH mentioned, otherwise "ticker".
- sort_order defaults to "desc" for proximity-based sorts, "asc" for ticker.
- sma_20_relation and sma_50_relation default to "any".
- sector_whitelist should be exact sector names as they appear in stock_metadata (e.g. "Technology", "Healthcare", "Financials").
""".format(schema="\n".join(f'  "{k}": {v}' for k, v in QUANT_FILTER_SCHEMA.items()))


def parse_quant_filters(prompt: str) -> Dict[str, Any]:
    """Parse a natural language prompt into structured QuantFilters using an LLM."""
    from agno.agent import Agent
    from agno.models.ollama import Ollama
    import json

    try:
        parser = Agent(
            model=Ollama(id=OLLAMA_MODEL_ID, options={"num_ctx": 8192}),
            instructions=FILTER_PARSER_PROMPT,
            markdown=False,
        )
        response = parser.run(prompt)
        content = response.content if hasattr(response, 'content') else str(response)

        if content is None:
            content = ""

        # Extract JSON from the response
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            filters = json.loads(content[start:end + 1])
        else:
            filters = {}
    except Exception as e:
        logger.warning("Filter parsing failed: %s. Returning empty filters.", e)
        filters = {}

    # Normalize and set sensible defaults
    normalized: Dict[str, Any] = {
        "ath_proximity_min": filters.get("ath_proximity_min"),
        "ath_proximity_max": filters.get("ath_proximity_max"),
        "rsi_min": filters.get("rsi_min"),
        "rsi_max": filters.get("rsi_max"),
        "volume_ratio_min": filters.get("volume_ratio_min"),
        "sma_20_relation": filters.get("sma_20_relation", "any"),
        "sma_50_relation": filters.get("sma_50_relation", "any"),
        "sector_whitelist": filters.get("sector_whitelist", []),
        "market_cap_min": filters.get("market_cap_min"),
        "market_cap_max": filters.get("market_cap_max"),
        "eps_growth_min": filters.get("eps_growth_min"),
        "revenue_growth_min": filters.get("revenue_growth_min"),
        "sort_by": filters.get("sort_by", "ticker"),
        "sort_order": filters.get("sort_order", "asc"),
        "max_results": filters.get("max_results", 20),
    }
    return normalized


def apply_quant_filters(df: pd.DataFrame, filters: Dict[str, Any]) -> pd.DataFrame:
    """Apply QuantFilters to a DataFrame of technical screening results."""
    if df.empty:
        return df

    # ATH proximity
    ath_min = filters.get("ath_proximity_min")
    if ath_min is not None and "ath_proximity" in df.columns:
        df = df[df["ath_proximity"] >= ath_min]
    ath_max = filters.get("ath_proximity_max")
    if ath_max is not None and "ath_proximity" in df.columns:
        df = df[df["ath_proximity"] <= ath_max]

    # RSI
    rsi_min = filters.get("rsi_min")
    if rsi_min is not None and "momentum_rsi" in df.columns:
        df = df[df["momentum_rsi"] >= rsi_min]
    rsi_max = filters.get("rsi_max")
    if rsi_max is not None and "momentum_rsi" in df.columns:
        df = df[df["momentum_rsi"] <= rsi_max]

    # Volume ratio
    vol_min = filters.get("volume_ratio_min")
    if vol_min is not None and "volume_ratio" in df.columns:
        df = df[df["volume_ratio"] >= vol_min]

    # SMA relations
    sma20_rel = filters.get("sma_20_relation", "any")
    if sma20_rel == "above" and "trend_sma_fast" in df.columns:
        df = df[df["Close"] > df["trend_sma_fast"]]
    elif sma20_rel == "below" and "trend_sma_fast" in df.columns:
        df = df[df["Close"] < df["trend_sma_fast"]]

    sma50_rel = filters.get("sma_50_relation", "any")
    if sma50_rel == "above" and "trend_sma_slow" in df.columns:
        df = df[df["Close"] > df["trend_sma_slow"]]
    elif sma50_rel == "below" and "trend_sma_slow" in df.columns:
        df = df[df["Close"] < df["trend_sma_slow"]]

    # Sort and limit
    sort_by = filters.get("sort_by", "ticker")
    sort_order = filters.get("sort_order", "asc")
    ascending = sort_order != "desc"

    if sort_by in df.columns:
        df = df.sort_values(by=sort_by, ascending=ascending)
    elif sort_by == "ticker" and "ticker" in df.columns:
        df = df.sort_values(by="ticker", ascending=ascending)

    max_results = filters.get("max_results", 50)
    df = df.head(max_results)

    return df


# =============================================================================
# AGENT INITIALIZATION
# =============================================================================

def create_dormant_giant_team():
    """Create the Dormant Giant Screener team (agnoMultiAgentTrader_3)."""
    from agno.agent import Agent
    from agno.team import Team
    from agno.models.ollama import Ollama

    tech_specialist = Agent(
        name="Technical Specialist",
        role="Identify stocks experiencing volatility contraction (Bollinger Squeeze), hidden institutional accumulation (OBV), or key resistance breakouts.",
        tools=[tool_run_dormant_giant_scan],
        model=Ollama(id=OLLAMA_MODEL_ID, options={"num_ctx": 32768}),
        instructions="Call the `tool_run_dormant_giant_scan` to process the sp1500_1d database using parallel processing. Return a structured list of tickers showing 'Active Breakout' or 'Coiling' signals."
    )

    fund_specialist = Agent(
        name="Fundamental Specialist",
        role="Filter technical candidates by verifying EPS acceleration OR positive revenue growth as the breakout catalyst.",
        tools=[tool_verify_eps_acceleration],
        model=Ollama(id=OLLAMA_MODEL_ID, options={"num_ctx": 32768}),
        instructions="Take the list of tickers provided by the Technical Specialist and call `tool_verify_eps_acceleration`. The tool now checks for EPS acceleration OR revenue growth as a valid catalyst. Only pass forward tickers that have a confirmed fundamental catalyst."
    )

    risk_manager = Agent(
        name="Risk Manager",
        role="Evaluate the final candidates for downside risk.",
        model=Ollama(id=OLLAMA_MODEL_ID, options={"num_ctx": 32768}),
        instructions="Review the final list. Provide a brief risk assessment for trading a 'Dormant Giant' breakout, emphasizing the importance of setting stop losses just below the breakout zone or the lower Bollinger Band."
    )

    team_lead = Team(
        name="Dormant Giant Screener Team Lead",
        members=[tech_specialist, fund_specialist, risk_manager],
        model=Ollama(id=OLLAMA_MODEL_ID, options={"num_ctx": 32768}),
        instructions="""
        Orchestrate the stock screening process:
        1. Ask the Technical Specialist to run the database scan.
        2. Pass the results to the Fundamental Specialist for fundamental verification (EPS acceleration OR revenue growth).
        3. Pass the surviving candidates to the Risk Manager for final trade parameters.
        4. Output a comprehensive final report summarizing the viable 'Dormant Giant' candidates.
        """,
        debug_mode=True,
        markdown=True
    )

    return team_lead


def create_quant_strategy_team():
    """Create the Quant Strategy team (agnoMultiAgentTrader_2)."""
    from agno.agent import Agent
    from agno.team import Team
    from agno.models.ollama import Ollama

    tech_agent = Agent(
        name="Technical Specialist",
        role="Identify price-action setups using technical indicators.",
        model=Ollama(id=OLLAMA_MODEL_ID_ALT, options={"num_ctx": 32768}),
        tools=[technical_screener],
        instructions=["Return only the top 10-15 tickers that meet the criteria. Pass cutoff_date parameter if provided."]
    )

    fund_agent = Agent(
        name="Fundamental Specialist",
        role="Vet stocks for financial health.",
        model=Ollama(id=OLLAMA_MODEL_ID_ALT, options={"num_ctx": 32768}),
        tools=[query_fundamental_health],
        instructions=["Check trends and reject weak companies. Pass cutoff_date parameter if provided."]
    )

    risk_manager = Agent(
        name="Risk Manager",
        role="Evaluate volatility and stability using metadata.",
        model=Ollama(id=OLLAMA_MODEL_ID_ALT, options={"num_ctx": 32768}),
        tools=[tool_query_metadata],
        instructions=[
            "Use 'query_metadata' to check Market Cap and Beta for the tickers.",
            "Flag 'Small Cap' (< 2B) or 'High Volatility' (Beta > 1.5).",
            "Ensure the final selection is not overly concentrated in one sector."
        ]
    )

    perf_analyst = Agent(
        name="Performance Analyst",
        role="Track historical performance from cutoff date to today.",
        model=Ollama(id=OLLAMA_MODEL_ID_ALT, options={"num_ctx": 32768}),
        tools=[tool_get_historical_performance],
        instructions=[
            "Use 'tool_get_historical_performance' to calculate how stocks performed from the cutoff_date to today.",
            "Report the price at cutoff, current price, and percentage change.",
            "This helps evaluate if the screening criteria would have picked winners."
        ]
    )

    quant_team = Team(
        name="Quant Strategy Team",
        members=[tech_agent, fund_agent, risk_manager, perf_analyst],
        model=Ollama(id=OLLAMA_MODEL_ID_ALT, options={"num_ctx": 32768}),
        instructions=[
            "1. Ask the Technical Specialist to find candidates using 'technical_screener' (pass cutoff_date parameter if provided).",
            "2. Pass candidates to the Fundamental Specialist for a health check using 'query_fundamental_health'.",
            "3. Have the Risk Manager use 'tool_query_metadata' on the final list.",
            "4. Have the Performance Analyst calculate historical performance from cutoff_date to today using 'tool_get_historical_performance'.",
            "5. Synthesize everything into a final Markdown table with Technical, Fundamental, Risk, and Performance columns.",
            "CRITICAL: Complete the task in ONE cycle. If no stocks pass all filters, explain WHY instead of searching again."
        ],
        markdown=True,
        debug_mode=True
    )

    return quant_team


# =============================================================================
# RESULT ENRICHMENT
# =============================================================================

def enrich_results(results: List[Dict]) -> List[Dict]:
    """
    Enrich screener results with metadata, fundamentals, and price stats.
    Adds: company_name, sector, market_cap, beta, eps_growth_qoq,
          revenue_growth_qoq, peg_ratio.
    """
    if not results:
        return results

    tickers = [r['ticker'].upper() for r in results if r.get('ticker')]
    if not tickers:
        return results

    # 1. Metadata (single batched query)
    try:
        meta_query = text(
            "SELECT ticker, name, sector, market_cap, beta FROM stock_metadata WHERE ticker = ANY(:t)"
        )
        meta_df = pd.read_sql(meta_query, ENGINE, params={"t": tickers})
        meta_map = {row['ticker'].upper(): row for _, row in meta_df.iterrows()}
    except Exception as e:
        logger.warning("Metadata enrichment failed: %s", e)
        meta_map = {}

    # 2. Financials — last 2 quarters per ticker (single batched query)
    try:
        fin_query = text("""
            SELECT ticker, report_date, diluted_eps, total_revenue, net_income
            FROM stock_financials_quarterly
            WHERE ticker = ANY(:t)
            ORDER BY ticker, report_date DESC
        """)
        fin_df = pd.read_sql(fin_query, ENGINE, params={"t": tickers})
    except Exception as e:
        logger.warning("Financial enrichment failed: %s", e)
        fin_df = pd.DataFrame()

    for r in results:
        t = r.get('ticker', '').upper()
        if not t:
            continue

        # Metadata
        m = meta_map.get(t)
        if m is not None:
            r['company_name'] = m.get('name') or t
            r['sector'] = m.get('sector') or 'N/A'
            r['market_cap'] = float(m['market_cap']) if pd.notnull(m.get('market_cap')) else None
            r['beta'] = float(m['beta']) if pd.notnull(m.get('beta')) else None
        else:
            r['company_name'] = t
            r['sector'] = 'N/A'

        # Financials
        t_df = fin_df[fin_df['ticker'] == t]
        if len(t_df) >= 2:
            curr = t_df.iloc[0]
            prev = t_df.iloc[1]
            close_price = r.get('close')

            # EPS growth QoQ
            curr_eps = curr['diluted_eps']
            prev_eps = prev['diluted_eps']
            if pd.notnull(curr_eps) and pd.notnull(prev_eps) and prev_eps != 0:
                eps_growth = (curr_eps - prev_eps) / abs(prev_eps)
                r['eps_growth_qoq'] = round(eps_growth * 100, 2)

                # PEG ratio approximation
                if close_price and eps_growth > 0:
                    pe = close_price / max(float(curr_eps), 0.001)
                    annualized_growth = eps_growth * 4
                    peg = pe / max(annualized_growth, 0.001)
                    r['peg_ratio'] = round(peg, 2)
                else:
                    r['peg_ratio'] = None
            else:
                r['eps_growth_qoq'] = None
                r['peg_ratio'] = None

            # Revenue growth QoQ
            curr_rev = curr['total_revenue']
            prev_rev = prev['total_revenue']
            if pd.notnull(curr_rev) and pd.notnull(prev_rev) and prev_rev > 0:
                rev_growth = (curr_rev - prev_rev) / prev_rev
                r['revenue_growth_qoq'] = round(rev_growth * 100, 2)
            else:
                r['revenue_growth_qoq'] = None

    return results


# =============================================================================
# SERVICE FUNCTIONS
# =============================================================================

def run_dormant_giant_screener(prompt: Optional[str] = None, progress_callback=None, log_callback=None, filters: Optional[Dict[str, Any]] = None, cutoff_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the Dormant Giant screener without AI agents (fast, pure Python).
    Returns structured results for API response.
    """
    logger.info("Running Dormant Giant screener...")

    # Technical scan
    technical_results = tool_run_dormant_giant_scan(progress_callback=progress_callback, log_callback=log_callback, filters=filters, cutoff_date=cutoff_date)
    logger.info("Technical scan found %d candidates", len(technical_results))

    if not technical_results:
        return {
            "technical_candidates": 0,
            "verified_candidates": 0,
            "results": [],
            "summary": "No stocks matched the technical criteria (Squeeze/Accumulation/Breakout). Try relaxing the filters."
        }

    # Fundamental verification
    verified_results = tool_verify_eps_acceleration(technical_results, log_callback=log_callback)
    logger.info("Fundamental verification found %d stocks with catalysts", len(verified_results))

    # Enrich with metadata, fundamentals, and price stats
    verified_results = enrich_results(verified_results)

    return {
        "technical_candidates": len(technical_results),
        "verified_candidates": len(verified_results),
        "results": verified_results,
        "summary": f"Found {len(technical_results)} technical candidates, {len(verified_results)} with EPS acceleration or revenue growth catalysts."
    }


class AgnoLogCapture:
    """Custom handler to capture Agno agent output for streaming to frontend."""
    def __init__(self, logs_buffer: List[Dict[str, Any]], agent_log_callback: Optional[Callable] = None):
        self.logs_buffer = logs_buffer
        self.agent_log_callback = agent_log_callback
        self.current_agent = None

    def _emit(self, entry: dict):
        """Push to buffer and optionally to external callback."""
        self.logs_buffer.append(entry)
        if self.agent_log_callback:
            self.agent_log_callback(
                agent=entry["agent"],
                message=entry["message"],
                log_type=entry.get("type", "system"),
                color=entry.get("color", "gray")
            )

    def log_agent_start(self, agent_name: str, role: str = ""):
        """Log when an agent starts working."""
        emoji = self._get_agent_emoji(agent_name)
        color = self._get_agent_color(agent_name)
        msg = f"{emoji} **{agent_name}** is starting analysis..."
        if role:
            msg += f"\n   *Role: {role}*"
        self._emit({"agent": agent_name, "message": msg, "type": "start", "color": color})

    def log_agent_complete(self, agent_name: str, result_summary: str = ""):
        """Log when an agent completes work."""
        emoji = self._get_agent_emoji(agent_name)
        color = self._get_agent_color(agent_name)
        msg = f"{emoji} **{agent_name}** completed analysis"
        if result_summary:
            msg += f": {result_summary}"
        self._emit({"agent": agent_name, "message": msg, "type": "complete", "color": color})

    def log_tool_call(self, agent_name: str, tool_name: str, status: str = "executing"):
        """Log when an agent calls a tool."""
        color = self._get_agent_color(agent_name)
        status_emoji = "⚙️" if status == "executing" else "✅"
        msg = f"{status_emoji} **{agent_name}** {status} tool: `{tool_name}`"
        self._emit({"agent": agent_name, "message": msg, "type": "tool", "color": color})

    def log_reasoning(self, agent_name: str, thought: str):
        """Log agent reasoning/thought process."""
        color = self._get_agent_color(agent_name)
        emoji = self._get_agent_emoji(agent_name)
        msg = f"{emoji} **{agent_name}** thinking: {thought[:200]}{'...' if len(thought) > 200 else ''}"
        self._emit({"agent": agent_name, "message": msg, "type": "reasoning", "color": color})

    def log_system(self, message: str):
        """Log system-level messages."""
        msg = f"🚀 {message}"
        self._emit({"agent": "System", "message": msg, "type": "system", "color": "gray"})

    def _get_agent_emoji(self, agent_name: str) -> str:
        """Get emoji for agent type."""
        emojis = {
            "Technical Specialist": "📊",
            "Fundamental Specialist": "💰",
            "Risk Manager": "⚠️",
            "Performance Analyst": "📈",
            "Dormant Giant Screener Team Lead": "🎯",
            "Quant Strategy Team": "🔬",
            "System": "⚙️"
        }
        return emojis.get(agent_name, "🤖")

    def _get_agent_color(self, agent_name: str) -> str:
        """Get color theme for agent."""
        colors = {
            "Technical Specialist": "blue",
            "Fundamental Specialist": "green",
            "Risk Manager": "amber",
            "Performance Analyst": "purple",
            "Dormant Giant Screener Team Lead": "white",
            "Quant Strategy Team": "white",
            "System": "gray"
        }
        return colors.get(agent_name, "white")


def _capture_agno_stdout(team, prompt: str, log_capture: AgnoLogCapture):
    """Run the Agno team with streaming events, logging real agent activity."""
    from typing import get_args
    from agno.team.team import TeamRunOutput, TeamRunOutputEvent

    response = None
    # Track member names by iteration index (populated as TaskIterationStarted fires)
    members = getattr(team, 'members', [])
    _iteration_member_cache = {}

    for event in team.run(prompt, stream=True, stream_events=True, yield_run_output=True):
        # Final aggregated response
        if isinstance(event, TeamRunOutput):
            response = event
            continue

        if not isinstance(event, tuple(get_args(TeamRunOutputEvent))):
            continue

        evt_type = event.event

        # --- Tool call started ---
        if evt_type == 'TeamToolCallStarted' and hasattr(event, 'tool') and event.tool:
            tool = event.tool
            agent_name = tool.tool_name or "Team"
            log_capture.log_tool_call(agent_name, tool.tool_name or "unknown", "executing")
            if tool.tool_args:
                log_capture.log_reasoning("Team", f"Args: {str(tool.tool_args)[:300]}")

        # --- Tool call completed ---
        elif evt_type == 'TeamToolCallCompleted' and hasattr(event, 'tool') and event.tool:
            tool = event.tool
            log_capture.log_tool_call("Team", tool.tool_name or "unknown", "completed")
            if hasattr(event, 'content') and event.content:
                log_capture.log_reasoning("Team", f"Result: {str(event.content)[:300]}")

        # --- Reasoning step ---
        elif evt_type == 'TeamReasoningStep' and hasattr(event, 'content') and event.content:
            content = str(event.content)[:300]
            if content.strip():
                log_capture.log_reasoning("Team", content)

        # --- Streaming content ---
        elif evt_type == 'TeamRunContent' and hasattr(event, 'content') and event.content:
            if isinstance(event.content, str) and event.content.strip():
                log_capture.log_reasoning("Team", event.content[:300])

        # --- Task iteration (member agent activation) ---
        elif evt_type == 'TeamTaskIterationStarted' and hasattr(event, 'iteration'):
            iteration = event.iteration
            if members and 0 < iteration <= len(members):
                member_name = members[iteration - 1].name or f"Agent {iteration}"
                _iteration_member_cache[iteration] = member_name
                log_capture.log_agent_start(member_name, f"Starting analysis (step {iteration}/{len(members)})")

        # --- Task iteration completed ---
        elif evt_type == 'TeamTaskIterationCompleted' and hasattr(event, 'iteration'):
            iteration = event.iteration
            member_name = _iteration_member_cache.get(iteration)
            if member_name:
                summary = getattr(event, 'task_summary', None) or "Analysis completed"
                log_capture.log_agent_complete(member_name, str(summary)[:200])

    return response


def run_dormant_giant_screener_with_ai(prompt: Optional[str] = None, progress_callback=None, log_callback=None, filters: Optional[Dict[str, Any]] = None, logs_buffer: Optional[List[Dict[str, Any]]] = None, agent_log_callback=None, cutoff_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the Dormant Giant screener with AI multi-agent analysis.
    Returns both structured results and AI-generated report.
    """
    if logs_buffer is None:
        logs_buffer = []

    log_capture = AgnoLogCapture(logs_buffer, agent_log_callback=agent_log_callback)

    try:
        # 1. Run technical scan first to provide immediate progress updates (10% -> 80%)
        log_capture.log_system("Starting Dormant Giant technical analysis...")
        structured = run_dormant_giant_screener(progress_callback=progress_callback, log_callback=log_callback, filters=filters, cutoff_date=cutoff_date)
        log_capture.log_system(f"Technical scan complete. Found {structured.get('technical_candidates', 0)} candidates.")

        if structured.get('verified_candidates', 0) == 0:
            log_capture.log_system("No stocks passed technical/fundamental filters. Skipping AI analysis.")
            return {
                "ai_report": None,
                "technical_candidates": structured["technical_candidates"],
                "verified_candidates": 0,
                "results": structured["results"],
                "summary": "No candidates passed technical/fundamental screening. AI analysis skipped.",
                "logs": logs_buffer
            }

        # 2. Run the AI team for natural language analysis
        log_capture.log_system("Initializing AI multi-agent team...")
        if progress_callback:
            progress_callback(85)

        team = create_dormant_giant_team()
        user_prompt = prompt or "Begin the daily Dormant Giant screening workflow across the S&P 1500 universe."

        if log_callback:
            log_callback("AI Agents are now synthesizing the final report...")

        if progress_callback:
            progress_callback(90)

        # Run team with streaming events — real agent activity logs come via _capture_agno_stdout
        response = _capture_agno_stdout(team, user_prompt, log_capture)

        if progress_callback:
            progress_callback(97)

        log_capture.log_system("AI analysis complete")

        ai_report = response.content if response and hasattr(response, 'content') else str(response) if response else "No response"  # type: ignore[union-attr]

        if progress_callback:
            progress_callback(99)

        return {
            "ai_report": ai_report,
            "technical_candidates": structured["technical_candidates"],
            "verified_candidates": structured["verified_candidates"],
            "results": structured["results"],
            "summary": "AI analysis complete with structured results.",
            "logs": logs_buffer
        }
    except Exception as e:
        logger.error("AI screener failed: %s", e)
        log_capture.log_system(f"Error in AI analysis: {str(e)[:100]}... Falling back to non-AI mode.")
        # Fallback to non-AI mode
        logger.info("Falling back to non-AI screener...")
        return run_dormant_giant_screener(prompt, progress_callback=progress_callback, log_callback=log_callback, filters=filters)


def run_quant_strategy_screener(prompt: str, cutoff_date: Optional[str] = None, progress_callback=None,
                                log_callback=None, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run the Quant Strategy screener without AI agents (fast, pure Python).
    Uses ta library column names and maps to frontend-friendly keys.
    Applies user-defined QuantFilters if provided.
    """
    logger.info("Running Quant Strategy screener (cutoff_date=%s, filters=%s)...", cutoff_date, filters)

    if progress_callback:
        progress_callback(5)

    # Use ta-compatible column names, then map to frontend-friendly keys
    ta_indicators = ['trend_sma_fast', 'trend_sma_slow', 'momentum_rsi', 'trend_macd', 'Volume']
    ta_to_friendly = {
        'trend_sma_fast': 'sma_20',
        'trend_sma_slow': 'sma_50',
        'momentum_rsi': 'rsi',
        'trend_macd': 'macd',
        'Volume': 'volume',
    }

    # Technical scan with progress and optional filters
    tech_csv = technical_screener(
        ta_indicators,
        cutoff_date=cutoff_date,
        progress_callback=progress_callback,
        log_callback=log_callback,
        filters=filters
    )
    tech_df = pd.read_csv(pd.io.common.StringIO(tech_csv)) if tech_csv != "No results found." else pd.DataFrame()

    if progress_callback:
        progress_callback(75)

    if tech_df.empty:
        if progress_callback:
            progress_callback(100)
        return {
            "technical_candidates": 0,
            "results": [],
            "summary": "No stocks matched the technical criteria."
        }

    # Map ta column names to frontend-friendly names
    results_records = []
    for _, row in tech_df.iterrows():
        record = {'ticker': row.get('ticker', ''), 'close': row.get('close', None)}
        for ta_col, friendly_col in ta_to_friendly.items():
            if ta_col in tech_df.columns and pd.notna(row.get(ta_col)):
                record[friendly_col] = round(row[ta_col], 4) if isinstance(row[ta_col], (int, float)) else row[ta_col]
        # Include additional price stats computed in _worker_ta_analysis
        for extra in ['ema_9', 'high_52w', 'low_52w', 'all_time_high', 'all_time_low', 'ath_proximity', 'volume', 'volume_ma_50', 'volume_ratio']:
            if extra in tech_df.columns and pd.notna(row.get(extra)):
                record[extra] = round(row[extra], 4) if isinstance(row[extra], (int, float)) else row[extra]
        results_records.append(record)

    max_results = filters.get("max_results", 20) if filters else 20
    tickers = [r['ticker'] for r in results_records if r.get('ticker')][:max_results]

    # Fundamental check
    if log_callback:
        log_callback("Running fundamental health check...")
    fund_csv = query_fundamental_health(tickers, cutoff_date=cutoff_date)

    if progress_callback:
        progress_callback(85)

    # Metadata
    if log_callback:
        log_callback("Fetching risk metadata...")
    meta_csv = tool_query_metadata(tickers)

    if progress_callback:
        progress_callback(90)

    # Historical performance if cutoff_date
    perf_csv = "No performance data available."
    if cutoff_date:
        if log_callback:
            log_callback("Calculating historical performance...")
        perf_csv = tool_get_historical_performance(tickers, cutoff_date)

    if progress_callback:
        progress_callback(95)

    # Enrich with metadata, fundamentals, and price stats
    results_records = enrich_results(results_records)

    return {
        "technical_candidates": len(results_records),
        "results": results_records[:max_results],
        "fundamental_data": fund_csv,
        "metadata": meta_csv,
        "performance": perf_csv,
        "summary": f"Found {len(results_records)} technical candidates. Fundamental and risk analysis complete."
    }


def run_quant_strategy_screener_with_ai(prompt: str, cutoff_date: Optional[str] = None, logs_buffer: Optional[List[Dict[str, Any]]] = None,
                                        progress_callback=None, agent_log_callback=None,
                                        filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run the Quant Strategy screener with AI multi-agent analysis.
    Uses user-defined QuantFilters to pre-filter candidates before AI synthesis.
    """
    if logs_buffer is None:
        logs_buffer = []

    log_capture = AgnoLogCapture(logs_buffer, agent_log_callback=agent_log_callback)

    try:
        log_capture.log_system("Initializing Quant Strategy AI screener...")
        log_capture.log_system("Assembling multi-agent team with Technical, Fundamental, Risk, and Performance specialists")

        team = create_quant_strategy_team()

        import json
        full_prompt = f"""User directive: {prompt}

Screening criteria applied:
{json.dumps(filters, indent=2) if filters else "No custom filters applied."}"""
        if cutoff_date:
            full_prompt += f"\n\nBacktest cutoff date: {cutoff_date}"
            log_capture.log_system(f"Backtesting mode enabled: cutoff_date={cutoff_date}")

        log_capture.log_agent_start("Quant Strategy Team", "Coordinating multi-phase screening analysis")
        log_capture.log_agent_start("Technical Specialist", "Screening S&P 1500 for TA patterns")
        log_capture.log_tool_call("Technical Specialist", "technical_screener", "executing")

        logger.info("Running Quant Strategy AI screener...")

        # Get structured results first (for immediate feedback), passing filters
        log_capture.log_system("Running technical screen across S&P 1500...")
        structured = run_quant_strategy_screener(
            prompt, cutoff_date,
            progress_callback=progress_callback,
            log_callback=None,
            filters=filters
        )

        log_capture.log_system(f"Technical screen complete: {structured['technical_candidates']} candidates found")

        if structured['technical_candidates'] > 0:
            log_capture.log_system(f"Fundamental health check on {len(structured.get('results', []))} candidates...")

        # Run the AI team for final synthesis with streaming events
        log_capture.log_system("Running AI synthesis across all data...")
        if progress_callback:
            progress_callback(97)

        response = _capture_agno_stdout(team, full_prompt, log_capture)

        if progress_callback:
            progress_callback(99)

        ai_report = response.content if response and hasattr(response, 'content') else str(response) if response else "No response"  # type: ignore[union-attr]

        return {
            "ai_report": ai_report,
            "technical_candidates": structured["technical_candidates"],
            "results": structured["results"],
            "fundamental_data": structured["fundamental_data"],
            "metadata": structured["metadata"],
            "performance": structured["performance"],
            "summary": "AI analysis complete with structured results.",
            "logs": logs_buffer
        }
    except Exception as e:
        logger.error("AI screener failed: %s", e)
        log_capture.log_system(f"Error in AI analysis: {str(e)[:100]}... Falling back to non-AI mode.")
        logger.info("Falling back to non-AI screener...")
        return run_quant_strategy_screener(prompt, cutoff_date, progress_callback=progress_callback)
