"""
Dormant Giant → Trending Strategy Pipeline
=============================================
1. Run Dormant Giant screener as of 2026-02-02
2. Pick top 5 stocks by composite score
3. Run a SMA/EMA crossover trending strategy on each
4. Calculate ROI with $10,000 initial capital (equal-weight: $2,000/stock)

The trending strategy:
  ENTRY: Close > EMA(9) AND Close > SMA(20)  (price above both MAs = uptrend)
  EXIT:  Close < EMA(9) OR Close < SMA(20)   (price falls below either = trend broken)

Usage:
  cd backend && ./venv/bin/python -c "exec(open('../strategies/dormant_giant_trending.py').read())"
"""

import os
import sys
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

# ── Ensure we can import from the backend ──────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Set DB credentials before any backend import
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")


def main():
    # ── Imports ─────────────────────────────────────────────────────────────
    from app.services.agno_screener import run_dormant_giant_screener
    from app.services.data_service import get_data

    # ── Configuration ──────────────────────────────────────────────────────
    AS_OF_DATE = "2026-02-02"
    TOP_N = 5
    INITIAL_CAPITAL = 10_000.0  # $10,000 total
    END_DATE = "2026-07-08"     # Latest available date in DB

    # Trending strategy parameters
    EMA_WINDOW = 9
    SMA_WINDOW = 20

    print("=" * 72)
    print("  DORMANT GIANT → TRENDING STRATEGY PIPELINE")
    print("=" * 72)
    print(f"  As-of date:         {AS_OF_DATE}")
    print(f"  Top N stocks:       {TOP_N}")
    print(f"  Initial capital:    ${INITIAL_CAPITAL:,.2f}")
    print(f"  Backtest end date:  {END_DATE}")
    print(f"  Strategy:           EMA({EMA_WINDOW}) / SMA({SMA_WINDOW}) crossover")
    print("=" * 72)

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 1: Run Dormant Giant Screener
    # ═════════════════════════════════════════════════════════════════════════
    print("\n📡 Step 1: Running Dormant Giant screener...")

    def log_callback(msg):
        print(f"     {msg}")

    def progress_callback(pct):
        pass  # Keep output clean

    result = run_dormant_giant_screener(
        cutoff_date=AS_OF_DATE,
        log_callback=log_callback,
        progress_callback=progress_callback,
    )

    all_results = result.get("results", [])
    print(f"\n  → Technical candidates: {result.get('technical_candidates', 0)}")
    print(f"  → Verified candidates:  {result.get('verified_candidates', 0)}")
    print(f"  → Total results:        {len(all_results)}")

    if not all_results:
        print("\n❌ No stocks passed screening. Cannot proceed.")
        sys.exit(1)

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 2: Pick Top 5 by Score
    # ═════════════════════════════════════════════════════════════════════════
    print("\n📊 Step 2: Top 5 stocks by composite score:")

    # Sort by score descending (already sorted, but be safe)
    sorted_results = sorted(all_results, key=lambda r: r.get("score", 0), reverse=True)
    top_stocks = sorted_results[:TOP_N]

    print(f"  {'Ticker':>8}  {'Score':>6}  {'Signal':>20}  {'Close':>8}  {'MFI':>6}")
    print(f"  {'-'*8}  {'-'*6}  {'-'*20}  {'-'*8}  {'-'*6}")
    for s in top_stocks:
        print(f"  {s.get('ticker',''):>8}  {s.get('score',0):>6.1f}  {s.get('signal',''):>20}  "
              f"${s.get('close',0):>6.2f}  {s.get('mfi',0):>5.1f}")

    tickers = [s["ticker"] for s in top_stocks]

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 3: Run Trending Strategy on Each Stock
    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n📈 Step 3: Running EMA({EMA_WINDOW})/SMA({SMA_WINDOW}) trending strategy...")

    import vectorbt as vbt

    per_stock = {}
    all_trades = []

    for ticker in tickers:
        print(f"\n  ── {ticker} ──")

        # Fetch OHLCV data from as_of_date forward
        df = get_data(ticker, start_date=AS_OF_DATE, end_date=END_DATE, frequency="daily")
        if df is None or df.empty:
            print(f"     ⚠️  No data available, skipping")
            continue

        # Ensure we have a Date column
        if "Date" not in df.columns and df.index.name == "Date":
            df = df.reset_index()
        df = df.reset_index(drop=True)

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        open_p = df["Open"]

        # Calculate indicators
        ema = vbt.MA.run(close, window=EMA_WINDOW, ewm=True, short_name="EMA")
        sma = vbt.MA.run(close, window=SMA_WINDOW, short_name="SMA")

        ema_vals = ema.ma
        sma_vals = sma.ma

        # Valid mask: skip warm-up period where indicators aren't ready
        valid = ema_vals.notna() & sma_vals.notna()

        # ENTRY: Price above BOTH EMA and SMA (uptrend confirmed)
        above_ema = close > ema_vals
        above_sma = close > sma_vals
        entries = above_ema & above_sma & valid

        # EXIT: Price falls below EITHER EMA or SMA (trend broken)
        below_ema = close < ema_vals
        below_sma = close < sma_vals
        exits = (below_ema | below_sma) & valid

        # Ensure no bar is both entry and exit
        exits = exits & ~entries

        # Build portfolio
        pf = vbt.Portfolio.from_signals(
            close=close,
            open=open_p,
            high=high,
            low=low,
            entries=entries,
            exits=exits,
            direction="longonly",
            freq="1d",
            init_cash=INITIAL_CAPITAL / TOP_N,  # Equal weight: $2,000/stock
            fees=0.001,  # 0.1% per trade
            accumulate=False,
        )

        # Collect stats
        trades_df = pf.trades.records_readable if hasattr(pf.trades, "records_readable") else None
        n_trades = pf.trades.count()
        total_ret = pf.total_return()
        sharpe = pf.sharpe_ratio()
        max_dd = pf.max_drawdown()

        # Final equity
        final_equity = pf.final_value()

        per_stock[ticker] = {
            "total_return_pct": float(total_ret) * 100,
            "final_value": float(final_equity),
            "n_trades": n_trades,
            "sharpe": float(sharpe),
            "max_drawdown_pct": float(max_dd) * 100,
            "pnl_dollars": float(final_equity) - (INITIAL_CAPITAL / TOP_N),
        }

        print(f"     Trades:        {n_trades:>4}")
        print(f"     Total Return:  {per_stock[ticker]['total_return_pct']:>+7.2f}%")
        print(f"     Final Value:  ${per_stock[ticker]['final_value']:>8.2f}")
        print(f"     P&L:           ${per_stock[ticker]['pnl_dollars']:>+8.2f}")
        print(f"     Sharpe:        {per_stock[ticker]['sharpe']:>7.2f}")
        print(f"     Max DD:        {per_stock[ticker]['max_drawdown_pct']:>7.2f}%")

        # Collect individual trades
        if trades_df is not None and not trades_df.empty:
            for _, t in trades_df.iterrows():
                all_trades.append({
                    "ticker": ticker,
                    "entry_date": str(t.get("Entry Date", ""))[:10],
                    "exit_date": str(t.get("Exit Date", ""))[:10],
                    "entry_price": float(t.get("Entry Price", 0)),
                    "exit_price": float(t.get("Exit Price", 0)),
                    "pnl_pct": float(t.get("Return", 0)) * 100,
                    "holding_days": int(t.get("Period", 0)),
                })

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 4: Portfolio Summary
    # ═════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("  PORTFOLIO SUMMARY")
    print("=" * 72)

    total_final = sum(s["final_value"] for s in per_stock.values())
    total_pnl = total_final - INITIAL_CAPITAL
    total_return_pct = (total_pnl / INITIAL_CAPITAL) * 100

    print(f"\n  Initial Capital:  ${INITIAL_CAPITAL:>8,.2f}")
    print(f"  Final Portfolio:  ${total_final:>8,.2f}")
    print(f"  Total P&L:        ${total_pnl:>+8,.2f}")
    print(f"  Total Return:     {total_return_pct:>+7.2f}%")
    print(f"  Total Trades:     {sum(s['n_trades'] for s in per_stock.values()):>4}")

    print(f"\n  {'Ticker':>8}  {'Return':>8}  {'P&L':>10}  {'Trades':>6}  {'Sharpe':>7}  {'Max DD':>8}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*6}  {'-'*7}  {'-'*8}")
    for t in tickers:
        if t in per_stock:
            s = per_stock[t]
            print(f"  {t:>8}  {s['total_return_pct']:>+7.2f}%  ${s['pnl_dollars']:>+8,.2f}  "
                  f"{s['n_trades']:>6}  {s['sharpe']:>7.2f}  {s['max_drawdown_pct']:>7.2f}%")
        else:
            print(f"  {t:>8}  {'N/A':>8}")

    # SPY Benchmark
    print(f"\n  ── SPY Benchmark ──")
    spy_df = get_data("SPY", start_date=AS_OF_DATE, end_date=END_DATE, frequency="daily")
    if spy_df is not None and not spy_df.empty:
        if "Date" not in spy_df.columns and spy_df.index.name == "Date":
            spy_df = spy_df.reset_index()
        spy_buy = spy_df["Close"].iloc[0]
        spy_sell = spy_df["Close"].iloc[-1]
        spy_return = (spy_sell - spy_buy) / spy_buy * 100
        alpha = total_return_pct - spy_return
        print(f"     SPY Buy:       ${spy_buy:>7.2f}")
        print(f"     SPY Sell:      ${spy_sell:>7.2f}")
        print(f"     SPY Return:    {spy_return:>+7.2f}%")
        print(f"     Alpha:         {alpha:>+7.2f}%")
    else:
        print(f"     SPY data unavailable")

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 5: Detailed Trade Log
    # ═════════════════════════════════════════════════════════════════════════
    if all_trades:
        print(f"\n  ── Trade Log ({len(all_trades)} total trades) ──")
        trade_df = pd.DataFrame(all_trades)
        trade_df = trade_df.sort_values(["ticker", "entry_date"])
        print(f"  {'Ticker':>8}  {'Entry':>12}  {'Exit':>12}  {'Entry $':>8}  {'Exit $':>8}  "
              f"{'Return':>8}  {'Days':>5}")
        print(f"  {'-'*8}  {'-'*12}  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*5}")
        for _, t in trade_df.iterrows():
            print(f"  {t['ticker']:>8}  {t['entry_date']:>12}  {t['exit_date']:>12}  "
                  f"${t['entry_price']:>7.2f}  ${t['exit_price']:>7.2f}  "
                  f"{t['pnl_pct']:>+7.2f}%  {t['holding_days']:>5}")

    print("\n" + "=" * 72)
    print("  ✅ DONE")
    print("=" * 72)


if __name__ == "__main__":
    main()
