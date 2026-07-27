"""
EMA20/200 Golden Cross Screener + Markov Triad Strategy
==========================================================
1. Scan S&P 1500 for stocks where EMA(20) crossed above EMA(200) near 2020-01-01
2. Pick top stocks by trend strength
3. Run Markov regime-adaptive strategy (long + short + dynamic sizing)

Usage:
  cd backend && ./venv/bin/python ../strategies/ema_cross_markov.py
"""

import os
import sys
import warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")


# ── Regime → Parameter Map ────────────────────────────────────────────────
REGIME_PARAMS = {
    ("BULL", "LOW"):  {"rsi": 50, "ts": 0.06, "tp": 0.20},
    ("BULL", "HIGH"): {"rsi": 55, "ts": 0.04, "tp": 0.15},
    ("BEAR", "LOW"):  {"rsi": 45, "ts": 0.08, "tp": 0.25},
    ("BEAR", "HIGH"): {"rsi": 60, "ts": 0.03, "tp": 0.10},
}
TIME_STOP_DAYS = 60
BULL_LONG_PCT = 1.0
BEAR_LONG_PCT = 0.25
BEAR_SHORT_PCT = 0.25

SECTOR_TO_ETF = {
    "Technology": "XLK", "Energy": "XLE", "Financial Services": "XLF",
    "Healthcare": "XLV", "Consumer Cyclical": "XLY", "Industrials": "XLI",
    "Communication Services": "XLC", "Consumer Defensive": "XLP",
    "Basic Materials": "XLB", "Real Estate": "XLRE", "Utilities": "XLU",
}


def get_sector_etf(ticker: str) -> str:
    """Get sector ETF for a ticker from stock_metadata."""
    from app.db.database import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT sector FROM stock_metadata WHERE ticker = :t"),
                {"t": ticker.upper()}
            ).fetchone()
        if row and row[0]:
            sector = row[0]
            # Map common sector names
            sector_map = {
                "Technology": "XLK", "Energy": "XLE", "Financials": "XLF",
                "Financial Services": "XLF", "Health Care": "XLV", "Healthcare": "XLV",
                "Consumer Discretionary": "XLY", "Consumer Cyclical": "XLY",
                "Industrials": "XLI", "Communication Services": "XLC",
                "Consumer Staples": "XLP", "Consumer Defensive": "XLP",
                "Materials": "XLB", "Basic Materials": "XLB",
                "Real Estate": "XLRE", "Utilities": "XLU",
            }
            return sector_map.get(sector, "XLK")
    except Exception:
        pass
    return "XLK"


def compute_rsi(close: pd.Series, period: int = 14) -> np.ndarray:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return (100 - (100 / (1 + rs))).values


def scan_ema_cross(lookback_start: str = "2018-01-01", cross_date: str = "2020-01-01",
                   max_stocks: int = 20) -> list:
    """Scan all stocks for EMA20 crossing above EMA200 near cross_date.

    Returns list of tickers sorted by trend strength (EMA20/EMA200 ratio at cross).
    """
    from app.db.database import engine
    from sqlalchemy import text
    from app.utils.security import get_safe_table_name

    print(f"\n🔍 Scanning for EMA20/200 golden cross near {cross_date}...")

    # Get all tickers
    with engine.connect() as conn:
        res = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        skip = {'stock_metadata', 'stock_financials_quarterly', 'stock_financials_yearly',
                'xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly'}
        tickers = [row[0] for row in res if row[0] not in skip]

    cross_dt = datetime.strptime(cross_date, "%Y-%m-%d")
    lookback_dt = datetime.strptime(lookback_start, "%Y-%m-%d")

    candidates = []
    total = len(tickers)
    for idx, ticker in enumerate(tickers):
        if (idx + 1) % 200 == 0:
            print(f"  Progress: {idx+1}/{total} ({((idx+1)/total*100):.0f}%)")

        try:
            safe = get_safe_table_name(ticker)
        except ValueError:
            continue

        with engine.connect() as conn:
            df = pd.read_sql(
                f'SELECT "Date", "Close" FROM "{safe}" WHERE "Date" >= \'{lookback_start}\' AND "Date" <= \'{cross_date}\' ORDER BY "Date"',
                conn
            )

        if df.empty or len(df) < 250:
            continue

        close = df["Close"]
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema200 = close.rolling(window=200).mean()

        # Check for crossover in the last 365 days before cross_date
        lookback = min(365, len(df) - 1)
        recent = df.tail(lookback)
        e20 = ema20.tail(lookback)
        e200 = ema200.tail(lookback)

        # Find if EMA20 crossed above EMA200
        crossed = False
        cross_strength = 0.0
        for i in range(1, len(recent)):
            if pd.notna(e20.iloc[i]) and pd.notna(e200.iloc[i]) and pd.notna(e20.iloc[i-1]) and pd.notna(e200.iloc[i-1]):
                if e20.iloc[i-1] <= e200.iloc[i-1] and e20.iloc[i] > e200.iloc[i]:
                    crossed = True
                    cross_strength = (e20.iloc[i] / e200.iloc[i] - 1) * 100
                    break

        if crossed:
            # Trend strength: how far above EMA200 is price?
            price_vs_200 = (close.iloc[-1] / ema200.iloc[-1] - 1) * 100
            candidates.append({
                "ticker": ticker.upper(),
                "cross_strength": round(cross_strength, 2),
                "price_vs_ema200": round(price_vs_200, 2),
                "close": round(float(close.iloc[-1]), 2),
            })

    # Sort by trend strength
    candidates.sort(key=lambda c: c["price_vs_ema200"], reverse=True)
    print(f"\n  Found {len(candidates)} stocks with EMA20/200 golden cross near {cross_date}")
    return candidates[:max_stocks]


def main():
    from app.services.data_service import get_data
    from app.services.markov.regime_model import SectorRegimeManager

    # ── Configuration ──────────────────────────────────────────────────────
    AS_OF = "2020-01-01"
    END = "2026-07-08"
    CAPITAL = 10_000.0
    MAX_STOCKS = 10  # Top 10 by trend strength

    # ── Step 1: Scan for EMA20/200 golden cross ────────────────────────────
    candidates = scan_ema_cross(max_stocks=MAX_STOCKS)

    if not candidates:
        print("\n❌ No stocks with EMA20/200 golden cross found.")
        return

    TICKERS = [c["ticker"] for c in candidates]
    N_STOCKS = len(TICKERS)

    # ── Fetch market caps ──────────────────────────────────────────────────
    print("\n📊 Fetching market caps...")
    from app.db.database import engine
    from sqlalchemy import text

    market_caps = {}
    for c in candidates:
        t = c["ticker"]
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT market_cap FROM stock_metadata WHERE ticker = :t"),
                    {"t": t}
                ).fetchone()
            if row and row[0] is not None:
                market_caps[t] = float(row[0])
            else:
                market_caps[t] = 0.0
        except Exception:
            market_caps[t] = 0.0

    # ── Combined momentum + market cap weighting ────────────────────────────
    # Score = 50% momentum rank + 50% market cap rank
    # Then allocate proportionally to combined score
    n = len(candidates)
    momentum_ranks = {c["ticker"]: n - i for i, c in enumerate(candidates)}  # n, n-1, ..., 1

    # Market cap ranks (highest cap = best rank)
    sorted_by_cap = sorted(candidates, key=lambda c: market_caps.get(c["ticker"], 0), reverse=True)
    cap_ranks = {c["ticker"]: n - i for i, c in enumerate(sorted_by_cap)}

    # Combined score
    combined_scores = {}
    for c in candidates:
        t = c["ticker"]
        mom_score = momentum_ranks[t] / n  # 0-1
        cap_score = cap_ranks[t] / n       # 0-1
        combined_scores[t] = 0.5 * mom_score + 0.5 * cap_score

    # Allocate proportionally to combined score
    total_score = sum(combined_scores.values())
    capital_per_stock = {}
    for c in candidates:
        t = c["ticker"]
        capital_per_stock[t] = CAPITAL * (combined_scores[t] / total_score)

    print(f"\n  Top {N_STOCKS} stocks — Momentum + Market Cap weighting:")
    print(f"  {'Ticker':>8}  {'Price/200':>10}  {'Mkt Cap':>12}  {'Mom Rk':>6}  {'Cap Rk':>6}  {'Alloc':>10}")
    print(f"  {'-'*8}  {'-'*10}  {'-'*12}  {'-'*6}  {'-'*6}  {'-'*10}")
    for c in candidates:
        t = c["ticker"]
        mc = market_caps.get(t, 0)
        mc_str = f"${mc/1e9:.1f}B" if mc > 0 else "N/A"
        print(f"  {t:>8}  {c['price_vs_ema200']:>+9.2f}%  {mc_str:>12}  "
              f"{momentum_ranks[t]:>6}  {cap_ranks[t]:>6}  "
              f"${capital_per_stock[t]:>7,.0f}")

    print("\n" + "=" * 80)
    print("  MARKOV TRIAD STRATEGY ON EMA20/200 GOLDEN CROSS STOCKS")
    print("=" * 80)
    print(f"  Period:     {AS_OF} → {END}")
    print(f"  Stocks:     {N_STOCKS}")
    print(f"  Capital:    ${CAPITAL:,.2f}")
    print(f"  Sizing:     Momentum-weighted (top 3: 20%, mid 4: 10%, bot 3: 3.3%)")
    print(f"  BULL:       100% long, 0% short")
    print(f"  BEAR:       25% long, 25% short, 50% cash")
    print("=" * 80)

    # ── Step 2: Load stock data ────────────────────────────────────────────
    print("\n📥 Loading stock data...")
    stock_data = {}
    for t in TICKERS:
        df = get_data(t, start_date=AS_OF, end_date=END, frequency="daily")
        if df is not None and not df.empty:
            if "Date" not in df.columns and df.index.name == "Date":
                df = df.reset_index()
            stock_data[t] = df.reset_index(drop=True)
            print(f"  {t}: {len(df)} bars")
        else:
            print(f"  {t}: ⚠️  No data")

    # ── Step 3: Walk-forward regime training ───────────────────────────────
    print("\n🧠 Training Markov regime models (walk-forward)...")

    start_dt = datetime.strptime(AS_OF, "%Y-%m-%d")
    end_dt = datetime.strptime(END, "%Y-%m-%d")

    retrain_dates = []
    d = start_dt + timedelta(days=3 * 365)
    while d < end_dt:
        retrain_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=180)

    print(f"  {len(retrain_dates)} checkpoints")

    regime_cache = {}
    for i, retrain_date in enumerate(retrain_dates):
        train_start = (datetime.strptime(retrain_date, "%Y-%m-%d") - timedelta(days=3 * 365 + 35)).strftime("%Y-%m-%d")
        train_end = retrain_date
        print(f"  Model #{i+1}: {train_start} → {train_end}")

        rm = SectorRegimeManager(jump_penalty=10.0)
        rm.train_all(train_start, train_end)

        window_end = retrain_dates[i + 1] if i + 1 < len(retrain_dates) else END
        current = datetime.strptime(retrain_date, "%Y-%m-%d")
        window_end_dt = datetime.strptime(window_end, "%Y-%m-%d")

        day = current
        while day <= window_end_dt:
            date_str = day.strftime("%Y-%m-%d")
            day_regimes = {}
            for t in TICKERS:
                etf = get_sector_etf(t)
                regime = rm.get_regime(etf, date_str)
                day_regimes[t] = regime
            regime_cache[date_str] = day_regimes
            day += timedelta(days=1)

    # ── Step 4: Run strategy ────────────────────────────────────────────────
    print(f"\n📈 Running strategy on {N_STOCKS} stocks...")

    per_stock = {}
    all_trades = []

    for ticker in TICKERS:
        df = stock_data.get(ticker)
        if df is None:
            continue

        dates = df["Date"] if "Date" in df.columns else pd.Series([""] * len(df))
        close = df["Close"].values
        high = df["High"].values
        low = df["Low"].values
        open_p = df["Open"].values
        volume = df["Volume"].values
        n = len(close)

        capital_this = capital_per_stock.get(ticker, CAPITAL / N_STOCKS)

        ema9 = pd.Series(close).ewm(span=9, adjust=False).mean().values
        sma20 = pd.Series(close).rolling(window=20).mean().values
        rsi = compute_rsi(pd.Series(close))
        vol_ma20 = pd.Series(volume).rolling(window=20).mean().values

        long_pos = False
        short_pos = False
        long_entry = 0.0
        short_entry = 0.0
        long_date = ""
        short_date = ""
        long_peak = 0.0
        short_peak = 0.0
        long_idx = 0
        short_idx = 0
        trades = []

        for i in range(20, n):
            c = close[i]
            e9 = ema9[i]
            s20 = sma20[i]
            r = rsi[i]
            v = volume[i]
            vm = vol_ma20[i]
            d = str(dates.iloc[i])[:10] if hasattr(dates, "iloc") else str(dates[i])[:10]

            if np.isnan(e9) or np.isnan(s20) or np.isnan(r) or np.isnan(vm) or vm <= 0:
                continue

            day_regime = regime_cache.get(d, {})
            regime_info = day_regime.get(ticker, {})
            regime = regime_info.get("regime", "BULL")
            vol_regime = regime_info.get("vol_regime", "LOW")
            is_bear = (regime == "BEAR")

            params = REGIME_PARAMS.get((regime, vol_regime), REGIME_PARAMS[("BULL", "LOW")])
            rsi_th = params["rsi"]
            ts_pct = params["ts"]
            tp_pct = params["tp"]

            # ── LONG ────────────────────────────────────────────────────────
            if not long_pos:
                if c > e9 and c > s20 and r > rsi_th:
                    long_pos = True
                    long_entry = c
                    long_date = d
                    long_peak = c
                    long_idx = i
            else:
                long_peak = max(long_peak, c)
                reason = None
                if (long_peak - c) / long_peak >= ts_pct:
                    reason = f"L-TS ({((long_peak-c)/long_peak):.1%})"
                if (c - long_entry) / long_entry >= tp_pct:
                    reason = f"L-TP ({((c-long_entry)/long_entry):.1%})"
                if (i - long_idx) >= TIME_STOP_DAYS:
                    reason = f"L-Time ({i-long_idx}d)"
                if c < e9 or c < s20:
                    reason = f"L-MA"
                if reason:
                    ret = (c - long_entry) / long_entry
                    sizing = BULL_LONG_PCT if not is_bear else BEAR_LONG_PCT
                    trades.append({
                        "ticker": ticker, "side": "LONG",
                        "entry_date": long_date, "exit_date": d,
                        "entry_price": round(long_entry, 2), "exit_price": round(c, 2),
                        "return_pct": round(ret * 100, 2),
                        "holding_days": i - long_idx,
                        "exit_reason": reason, "regime": f"{regime}/{vol_regime}",
                        "sizing_pct": sizing,
                        "pnl_dollars": round(capital_this * sizing * ret, 2),
                    })
                    long_pos = False

            # ── SHORT (BEAR only, trend-break entry) ───────────────────────
            if is_bear:
                if not short_pos:
                    prev_c = close[i - 1] if i > 0 else c
                    prev_s20 = sma20[i - 1] if i > 0 else s20
                    if (prev_c > prev_s20) and (c < s20):
                        short_pos = True
                        short_entry = c
                        short_date = d
                        short_peak = c
                        short_idx = i
                else:
                    short_peak = min(short_peak, c)
                    reason = None
                    rise = (c - short_entry) / short_entry
                    if rise >= ts_pct:
                        reason = f"S-TS ({rise:.1%})"
                    decline = (short_entry - c) / short_entry
                    if decline >= tp_pct:
                        reason = f"S-TP ({decline:.1%})"
                    if (i - short_idx) >= TIME_STOP_DAYS:
                        reason = f"S-Time ({i-short_idx}d)"
                    if c > e9 or c > s20:
                        reason = f"S-MA"
                    if reason:
                        ret = (short_entry - c) / short_entry
                        trades.append({
                            "ticker": ticker, "side": "SHORT",
                            "entry_date": short_date, "exit_date": d,
                            "entry_price": round(short_entry, 2), "exit_price": round(c, 2),
                            "return_pct": round(ret * 100, 2),
                            "holding_days": i - short_idx,
                            "exit_reason": reason, "regime": f"{regime}/{vol_regime}",
                            "sizing_pct": BEAR_SHORT_PCT,
                            "pnl_dollars": round(capital_this * BEAR_SHORT_PCT * ret, 2),
                        })
                        short_pos = False
            else:
                if short_pos:
                    ret = (short_entry - c) / short_entry
                    trades.append({
                        "ticker": ticker, "side": "SHORT",
                        "entry_date": short_date, "exit_date": d,
                        "entry_price": round(short_entry, 2), "exit_price": round(c, 2),
                        "return_pct": round(ret * 100, 2),
                        "holding_days": i - short_idx,
                        "exit_reason": "→ BULL", "regime": f"{regime}/{vol_regime}",
                        "sizing_pct": BEAR_SHORT_PCT,
                        "pnl_dollars": round(capital_this * BEAR_SHORT_PCT * ret, 2),
                    })
                    short_pos = False

        # Close open positions
        if long_pos:
            ret = (close[-1] - long_entry) / long_entry
            sizing = BULL_LONG_PCT if regime != "BEAR" else BEAR_LONG_PCT
            trades.append({
                "ticker": ticker, "side": "LONG",
                "entry_date": long_date,
                "exit_date": str(dates.iloc[-1])[:10] if hasattr(dates, "iloc") else str(dates[-1])[:10],
                "entry_price": round(long_entry, 2), "exit_price": round(close[-1], 2),
                "return_pct": round(ret * 100, 2),
                "holding_days": n - 1 - long_idx,
                "exit_reason": "End", "regime": f"{regime}/{vol_regime}",
                "sizing_pct": sizing,
                "pnl_dollars": round(capital_this * sizing * ret, 2),
            })
        if short_pos:
            ret = (short_entry - close[-1]) / short_entry
            trades.append({
                "ticker": ticker, "side": "SHORT",
                "entry_date": short_date,
                "exit_date": str(dates.iloc[-1])[:10] if hasattr(dates, "iloc") else str(dates[-1])[:10],
                "entry_price": round(short_entry, 2), "exit_price": round(close[-1], 2),
                "return_pct": round(ret * 100, 2),
                "holding_days": n - 1 - short_idx,
                "exit_reason": "End", "regime": f"{regime}/{vol_regime}",
                "sizing_pct": BEAR_SHORT_PCT,
                "pnl_dollars": round(capital_this * BEAR_SHORT_PCT * ret, 2),
            })

        # ── Stats ──────────────────────────────────────────────────────────
        if trades:
            long_pnl = sum(t["pnl_dollars"] for t in trades if t["side"] == "LONG")
            short_pnl = sum(t["pnl_dollars"] for t in trades if t["side"] == "SHORT")
            total_pnl_s = long_pnl + short_pnl
            total_ret_s = total_pnl_s / capital_this
            n_trades = len(trades)
            n_long = sum(1 for t in trades if t["side"] == "LONG")
            n_short = sum(1 for t in trades if t["side"] == "SHORT")
            winners = [t for t in trades if t["pnl_dollars"] > 0]
            losers = [t for t in trades if t["pnl_dollars"] <= 0]
            win_rate = len(winners) / n_trades if n_trades > 0 else 0
            gross_profit = sum(t["pnl_dollars"] for t in winners)
            gross_loss = abs(sum(t["pnl_dollars"] for t in losers))
            profit_factor = gross_profit / (gross_loss + 1e-9)

            equity = capital_this
            peak_eq = equity
            max_dd = 0.0
            for t in trades:
                equity += t["pnl_dollars"]
                peak_eq = max(peak_eq, equity)
                dd = (equity - peak_eq) / peak_eq
                max_dd = min(max_dd, dd)
        else:
            total_pnl_s = 0.0
            total_ret_s = 0.0
            n_trades = 0
            n_long = 0
            n_short = 0
            win_rate = 0
            profit_factor = 0
            max_dd = 0.0

        per_stock[ticker] = {
            "return_pct": total_ret_s * 100,
            "pnl_dollars": total_pnl_s,
            "n_trades": n_trades, "n_long": n_long, "n_short": n_short,
            "long_pnl": long_pnl, "short_pnl": short_pnl,
            "win_rate": win_rate * 100, "profit_factor": profit_factor,
            "max_dd_pct": max_dd * 100,
        }
        all_trades.extend(trades)

        s = per_stock[ticker]
        print(f"  {ticker:>8}: Long ${s['long_pnl']:>+7,.2f} ({s['n_long']}t)  "
              f"Short ${s['short_pnl']:>+7,.2f} ({s['n_short']}t)  "
              f"Total ${s['pnl_dollars']:>+8,.2f} ({s['return_pct']:>+6.2f}%)")

    # ── Portfolio Summary ──────────────────────────────────────────────────
    total_pnl = sum(s["pnl_dollars"] for s in per_stock.values())
    total_final = CAPITAL + total_pnl
    total_ret = total_pnl / CAPITAL * 100

    print(f"\n{'='*80}")
    print("  PORTFOLIO SUMMARY")
    print("=" * 80)
    print(f"  Initial Capital:  ${CAPITAL:>8,.2f}")
    print(f"  Final Portfolio:  ${total_final:>8,.2f}")
    print(f"  Total P&L:        ${total_pnl:>+8,.2f}")
    print(f"  Total Return:     {total_ret:>+7.2f}%")

    spy_df = get_data("SPY", start_date=AS_OF, end_date=END, frequency="daily")
    if spy_df is not None and not spy_df.empty:
        if "Date" not in spy_df.columns and spy_df.index.name == "Date":
            spy_df = spy_df.reset_index()
        spy_ret = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100
        alpha = total_ret - spy_ret
        print(f"  SPY Return:       {spy_ret:>+7.2f}%")
        print(f"  Alpha:            {alpha:>+7.2f}%  {'✅' if alpha > 0 else '❌'}")

    # Top/bottom performers
    sorted_stocks = sorted(per_stock.items(), key=lambda x: x[1]["return_pct"], reverse=True)
    print(f"\n  {'Ticker':>8}  {'Return':>8}  {'P&L':>10}  {'Trades':>6}  {'Long':>5}  {'Short':>5}  "
          f"{'Long$':>9}  {'Short$':>9}  {'Win%':>5}  {'PF':>5}  {'MaxDD':>7}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*6}  {'-'*5}  {'-'*5}  "
          f"{'─'*9}  {'─'*9}  {'─'*5}  {'─'*5}  {'─'*7}")
    for t, s in sorted_stocks:
        print(f"  {t:>8}  {s['return_pct']:>+7.2f}%  ${s['pnl_dollars']:>+8,.2f}  "
              f"{s['n_trades']:>6}  {s['n_long']:>5}  {s['n_short']:>5}  "
              f"${s['long_pnl']:>+7,.2f}  ${s['short_pnl']:>+7,.2f}  "
              f"{s['win_rate']:>4.0f}%  {s['profit_factor']:>4.2f}  {s['max_dd_pct']:>6.2f}%")

    # Regime distribution
    print(f"\n📊 Regime Distribution:")
    rc = {}
    sc = {"LONG": 0, "SHORT": 0}
    for t in all_trades:
        r = t.get("regime", "?")
        rc[r] = rc.get(r, 0) + 1
        sc[t.get("side", "?")] += 1
    for r, c in sorted(rc.items()):
        print(f"  {r:>20}: {c} trades")
    print(f"  {'LONG':>20}: {sc['LONG']} trades")
    print(f"  {'SHORT':>20}: {sc['SHORT']} trades")

    print(f"\n{'='*80}")
    print("  ✅ DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
