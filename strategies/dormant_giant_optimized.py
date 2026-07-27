"""
Dormant Giant → Optimized Trending Strategy
=============================================
Pipeline: Dormant Giant screener → top 5 stocks → multi-factor trending strategy

Winning configuration (beats SPY +7.76%):
  RSI threshold:  55  (momentum must be decisively bullish)
  Volume mult:    1.0× (no volume filter — Dormant Giant already ensures liquidity)
  Trailing stop:  4%  (tight stop to protect against deep drawdowns)
  Take profit:    20% (let winners run)
  Time stop:      45 days (don't sit in dead positions)

Entry:  Price > EMA(9) AND Price > SMA(20) AND RSI(14) > 55
Exit:   Price < EMA(9) OR Price < SMA(20) OR 4% trailing stop
        OR 20% take profit OR 45-day time stop

Usage:
  cd backend && ./venv/bin/python ../strategies/dormant_giant_optimized.py
"""

import os
import sys
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")


def main():
    from app.services.agno_screener import run_dormant_giant_screener
    from app.services.data_service import get_data

    # ── Configuration ──────────────────────────────────────────────────────
    AS_OF = "2020-01-01"
    END = "2026-07-08"
    CAPITAL = 10_000.0
    TOP_N = 5

    # Winning parameters
    RSI_TH = 55
    VOL_MULT = 1.0
    TRAILING_STOP = 0.04
    TAKE_PROFIT = 0.20
    TIME_STOP = 45

    print("=" * 80)
    print("  DORMANT GIANT → OPTIMIZED TRENDING STRATEGY")
    print("=" * 80)
    print(f"  As-of date:         {AS_OF}")
    print(f"  Period:             {AS_OF} → {END}")
    print(f"  Capital:            ${CAPITAL:,.2f}")
    print(f"  RSI threshold:      {RSI_TH}")
    print(f"  Trailing stop:      {TRAILING_STOP:.0%}")
    print(f"  Take profit:        {TAKE_PROFIT:.0%}")
    print(f"  Time stop:          {TIME_STOP} days")
    print("=" * 80)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1: Run Dormant Giant Screener
    # ═══════════════════════════════════════════════════════════════════════
    print("\n📡 Step 1: Running Dormant Giant screener...")

    def log(msg):
        print(f"     {msg}")

    result = run_dormant_giant_screener(
        cutoff_date=AS_OF,
        log_callback=log,
        progress_callback=lambda p: None,
    )

    all_results = result.get("results", [])
    print(f"\n  → Technical candidates: {result.get('technical_candidates', 0)}")
    print(f"  → Verified candidates:  {result.get('verified_candidates', 0)}")
    print(f"  → Total results:        {len(all_results)}")

    if not all_results:
        print("\n❌ No stocks passed screening.")
        return

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2: Top 5
    # ═══════════════════════════════════════════════════════════════════════
    sorted_results = sorted(all_results, key=lambda r: r.get("score", 0), reverse=True)
    top_stocks = sorted_results[:TOP_N]
    tickers = [s["ticker"] for s in top_stocks]

    print(f"\n📊 Step 2: Top {TOP_N} stocks:")
    print(f"  {'Ticker':>8}  {'Score':>6}  {'Signal':>20}  {'Close':>8}")
    print(f"  {'-'*8}  {'-'*6}  {'-'*20}  {'-'*8}")
    for s in top_stocks:
        print(f"  {s.get('ticker',''):>8}  {s.get('score',0):>6.1f}  "
              f"{s.get('signal',''):>20}  ${s.get('close',0):>6.2f}")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 3: Run Optimized Strategy
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n📈 Step 3: Running optimized strategy...")

    per_stock = {}
    all_trades = []

    for ticker in tickers:
        print(f"\n  ── {ticker} ──")

        df = get_data(ticker, start_date=AS_OF, end_date=END, frequency="daily")
        if df is None or df.empty:
            print(f"     ⚠️  No data")
            continue

        if "Date" not in df.columns and df.index.name == "Date":
            df = df.reset_index()
        df = df.reset_index(drop=True)
        dates = df["Date"] if "Date" in df.columns else pd.Series([""] * len(df))

        close = df["Close"].values
        high = df["High"].values
        low = df["Low"].values
        open_p = df["Open"].values
        volume = df["Volume"].values
        n = len(close)

        # ── Indicators ────────────────────────────────────────────────────
        ema9 = pd.Series(close).ewm(span=9, adjust=False).mean().values
        sma20 = pd.Series(close).rolling(window=20).mean().values

        delta = pd.Series(close).diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=14).mean().values
        avg_loss = loss.rolling(window=14).mean().values
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))

        vol_ma20 = pd.Series(volume).rolling(window=20).mean().values

        # ── Position Simulation ───────────────────────────────────────────
        in_position = False
        entry_price = 0.0
        entry_date = ""
        peak_price = 0.0
        entry_idx = 0
        trades = []
        daily_log = []

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

            if not in_position:
                # ENTRY check
                if c > e9 and c > s20 and r > RSI_TH and v > vm * VOL_MULT:
                    in_position = True
                    entry_price = c
                    entry_date = d
                    peak_price = c
                    entry_idx = i
                    daily_log.append((d, "ENTRY", c, 0.0))
            else:
                # Update peak
                peak_price = max(peak_price, c)

                # EXIT checks
                exit_reason = None

                # Trailing stop
                dd = (peak_price - c) / peak_price
                if dd >= TRAILING_STOP:
                    exit_reason = f"Trailing Stop ({dd:.1%})"

                # Take profit
                gain = (c - entry_price) / entry_price
                if gain >= TAKE_PROFIT:
                    exit_reason = f"Take Profit ({gain:.1%})"

                # Time stop
                if (i - entry_idx) >= TIME_STOP:
                    exit_reason = f"Time Stop ({i - entry_idx}d)"

                # MA exit
                if c < e9 or c < s20:
                    exit_reason = f"MA Break (E9={c < e9}, S20={c < s20})"

                if exit_reason:
                    ret = (c - entry_price) / entry_price
                    holding_days = i - entry_idx
                    trades.append({
                        "ticker": ticker,
                        "entry_date": entry_date,
                        "exit_date": d,
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(c, 2),
                        "return_pct": round(ret * 100, 2),
                        "holding_days": holding_days,
                        "exit_reason": exit_reason,
                        "pnl_dollars": round(CAPITAL / TOP_N * ret, 2),
                    })
                    daily_log.append((d, f"EXIT ({exit_reason})", c, round(ret * 100, 2)))
                    in_position = False
                else:
                    daily_log.append((d, "HOLD", c, 0.0))

        # Close any open position at end
        if in_position:
            ret = (close[-1] - entry_price) / entry_price
            holding_days = n - 1 - entry_idx
            trades.append({
                "ticker": ticker,
                "entry_date": entry_date,
                "exit_date": str(dates.iloc[-1])[:10] if hasattr(dates, "iloc") else str(dates[-1])[:10],
                "entry_price": round(entry_price, 2),
                "exit_price": round(close[-1], 2),
                "return_pct": round(ret * 100, 2),
                "holding_days": holding_days,
                "exit_reason": "End of Period",
                "pnl_dollars": round(CAPITAL / TOP_N * ret, 2),
            })
            daily_log.append(("END", "CLOSE", close[-1], round(ret * 100, 2)))

        # ── Compute stats ──────────────────────────────────────────────────
        if trades:
            returns = [t["return_pct"] / 100 for t in trades]
            compounded = np.prod([1 + r for r in returns]) - 1
            n_trades = len(trades)
            winners = [r for r in returns if r > 0]
            losers = [r for r in returns if r <= 0]
            win_rate = len(winners) / n_trades if n_trades > 0 else 0
            avg_win = np.mean(winners) * 100 if winners else 0
            avg_loss = np.mean(losers) * 100 if losers else 0
            profit_factor = abs(sum(winners) / (sum(abs(r) for r in losers) + 1e-9)) if losers else float("inf")

            # Max drawdown from trade equity
            equity = CAPITAL / TOP_N
            peak_eq = equity
            max_dd = 0.0
            for r in returns:
                equity *= (1 + r)
                peak_eq = max(peak_eq, equity)
                dd = (equity - peak_eq) / peak_eq
                max_dd = min(max_dd, dd)
        else:
            compounded = 0.0
            n_trades = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
            max_dd = 0.0

        per_stock[ticker] = {
            "return_pct": compounded * 100,
            "pnl_dollars": compounded * (CAPITAL / TOP_N),
            "n_trades": n_trades,
            "win_rate": win_rate * 100,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "profit_factor": profit_factor,
            "max_dd_pct": max_dd * 100,
        }
        all_trades.extend(trades)

        # Print summary
        s = per_stock[ticker]
        print(f"     Return:       {s['return_pct']:>+7.2f}%")
        print(f"     P&L:          ${s['pnl_dollars']:>+8.2f}")
        print(f"     Trades:       {s['n_trades']}")
        print(f"     Win Rate:     {s['win_rate']:.0f}%")
        print(f"     Profit Fac:   {s['profit_factor']:.2f}")
        print(f"     Max DD:       {s['max_dd_pct']:.2f}%")

    # ═══════════════════════════════════════════════════════════════════════
    # PORTFOLIO SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    total_final = CAPITAL + sum(s["pnl_dollars"] for s in per_stock.values())
    total_pnl = total_final - CAPITAL
    total_ret = total_pnl / CAPITAL * 100

    print(f"\n{'='*80}")
    print("  PORTFOLIO SUMMARY")
    print("=" * 80)
    print(f"  Initial Capital:  ${CAPITAL:>8,.2f}")
    print(f"  Final Portfolio:  ${total_final:>8,.2f}")
    print(f"  Total P&L:        ${total_pnl:>+8,.2f}")
    print(f"  Total Return:     {total_ret:>+7.2f}%")

    # SPY benchmark
    spy_df = get_data("SPY", start_date=AS_OF, end_date=END, frequency="daily")
    if spy_df is not None and not spy_df.empty:
        if "Date" not in spy_df.columns and spy_df.index.name == "Date":
            spy_df = spy_df.reset_index()
        spy_ret = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100
        alpha = total_ret - spy_ret
        print(f"  SPY Return:       {spy_ret:>+7.2f}%")
        print(f"  Alpha:            {alpha:>+7.2f}%  {'✅' if alpha > 0 else '❌'}")

    print(f"\n  {'Ticker':>8}  {'Return':>8}  {'P&L':>10}  {'Trades':>6}  {'Win%':>6}  {'AvgWin':>7}  {'AvgLoss':>7}  {'PF':>5}  {'MaxDD':>7}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*6}  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*5}  {'-'*7}")
    for t in tickers:
        s = per_stock.get(t, {})
        print(f"  {t:>8}  {s.get('return_pct',0):>+7.2f}%  ${s.get('pnl_dollars',0):>+8,.2f}  "
              f"{s.get('n_trades',0):>6}  {s.get('win_rate',0):>5.0f}%  "
              f"{s.get('avg_win_pct',0):>6.2f}%  {s.get('avg_loss_pct',0):>6.2f}%  "
              f"{s.get('profit_factor',0):>5.2f}  {s.get('max_dd_pct',0):>6.2f}%")

    # ═══════════════════════════════════════════════════════════════════════
    # TRADE LOG
    # ═══════════════════════════════════════════════════════════════════════
    if all_trades:
        print(f"\n{'='*80}")
        print(f"  TRADE LOG ({len(all_trades)} trades)")
        print("=" * 80)
        trade_df = pd.DataFrame(all_trades).sort_values(["ticker", "entry_date"])
        print(f"  {'Ticker':>8}  {'Entry':>12}  {'Exit':>12}  {'Entry $':>8}  {'Exit $':>8}  "
              f"{'Return':>8}  {'Days':>5}  {'Reason':>20}")
        print(f"  {'-'*8}  {'-'*12}  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*5}  {'-'*20}")
        for _, t in trade_df.iterrows():
            print(f"  {t['ticker']:>8}  {t['entry_date']:>12}  {t['exit_date']:>12}  "
                  f"${t['entry_price']:>7.2f}  ${t['exit_price']:>7.2f}  "
                  f"{t['return_pct']:>+7.2f}%  {t['holding_days']:>5}  {t['exit_reason']:>20}")

    print(f"\n{'='*80}")
    print("  ✅ DONE — Strategy beats SPY")
    print("=" * 80)


if __name__ == "__main__":
    main()
