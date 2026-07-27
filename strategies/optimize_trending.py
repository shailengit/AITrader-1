"""
Hybrid Multi-Factor + Adaptive Exit Strategy Optimizer
========================================================
Optimizes a trending strategy for 5 Dormant Giant stocks (R, GWW, BEN, MBIN, VIAV)
to beat the SPY benchmark (+7.76% from 2026-02-02 to 2026-07-08).

Strategy:
  ENTRY: Price > EMA(9) AND Price > SMA(20) AND RSI(14) > threshold
         AND Volume > vol_mult × 20d_avg_volume
  EXIT:  Price < EMA(9) OR Price < SMA(20) OR trailing_stop hit
         OR take_profit hit OR time_stop (45 days)

Parameters tested:
  RSI threshold:  45, 50, 55
  Volume mult:    1.0×, 1.2×, 1.5×
  Trailing stop:  4%, 6%, 8%
  Take profit:    12%, 15%, 20%

Usage:
  cd backend && ./venv/bin/python ../strategies/optimize_trending.py
"""

import os
import sys
import warnings
import pandas as pd
import numpy as np
from itertools import product

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")


def main():
    from app.services.data_service import get_data

    # ── Configuration ──────────────────────────────────────────────────────
    TICKERS = ["R", "GWW", "BEN", "MBIN", "VIAV"]
    AS_OF = "2026-02-02"
    END = "2026-07-08"
    CAPITAL_PER = 2000.0  # $2,000 per stock (equal weight of $10k)
    SPY_RETURN = 7.76      # From previous run

    # Parameter grid
    RSI_THRESHOLDS = [45, 50, 55]
    VOL_MULTS = [1.0, 1.2, 1.5]
    TRAILING_STOPS = [0.04, 0.06, 0.08]
    TAKE_PROFITS = [0.12, 0.15, 0.20]
    TIME_STOP_DAYS = 45

    print("=" * 80)
    print("  HYBRID MULTI-FACTOR + ADAPTIVE EXIT OPTIMIZER")
    print("=" * 80)
    print(f"  Stocks:     {', '.join(TICKERS)}")
    print(f"  Period:     {AS_OF} → {END}")
    print(f"  Capital:    $2,000/stock ($10,000 total)")
    print(f"  Target:     Beat SPY ({SPY_RETURN:+.2f}%)")
    print(f"  Grid:       {len(RSI_THRESHOLDS)} RSI × {len(VOL_MULTS)} Vol × "
          f"{len(TRAILING_STOPS)} TS × {len(TAKE_PROFITS)} TP = "
          f"{len(RSI_THRESHOLDS) * len(VOL_MULTS) * len(TRAILING_STOPS) * len(TAKE_PROFITS)} combos")
    print("=" * 80)

    # ── Fetch data for all stocks ─────────────────────────────────────────
    print("\n📥 Loading data...")
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

    # ── Pre-compute indicators for each stock ──────────────────────────────
    print("\n🧮 Pre-computing indicators...")
    indicators = {}
    for t in TICKERS:
        df = stock_data.get(t)
        if df is None:
            continue
        close = df["Close"]
        volume = df["Volume"]
        high = df["High"]
        low = df["Low"]
        open_p = df["Open"]

        ema9 = close.ewm(span=9, adjust=False).mean()
        sma20 = close.rolling(window=20).mean()

        # RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))

        # Volume MA(20)
        vol_ma20 = volume.rolling(window=20).mean()

        indicators[t] = {
            "close": close.values,
            "high": high.values,
            "low": low.values,
            "open": open_p.values,
            "volume": volume.values,
            "ema9": ema9.values,
            "sma20": sma20.values,
            "rsi": rsi.values,
            "vol_ma20": vol_ma20.values,
            "dates": df["Date"].values if "Date" in df.columns else np.arange(len(df)),
        }

    # ── Grid search ────────────────────────────────────────────────────────
    print(f"\n🔬 Testing {len(RSI_THRESHOLDS) * len(VOL_MULTS) * len(TRAILING_STOPS) * len(TAKE_PROFITS)} combinations...")

    results = []
    param_keys = []
    total_combos = (len(RSI_THRESHOLDS) * len(VOL_MULTS) *
                    len(TRAILING_STOPS) * len(TAKE_PROFITS))
    done = 0

    for rsi_th, vol_mult, ts_pct, tp_pct in product(
        RSI_THRESHOLDS, VOL_MULTS, TRAILING_STOPS, TAKE_PROFITS
    ):
        combo_returns = []
        combo_sharpes = []
        combo_dds = []
        combo_trades = []

        for t in TICKERS:
            ind = indicators.get(t)
            if ind is None:
                continue

            n = len(ind["close"])
            entries = np.zeros(n, dtype=bool)
            exits = np.zeros(n, dtype=bool)

            # Generate signals
            for i in range(20, n):  # Skip warm-up
                c, e9, s20, r, v, vm = (
                    ind["close"][i], ind["ema9"][i], ind["sma20"][i],
                    ind["rsi"][i], ind["volume"][i], ind["vol_ma20"][i],
                )
                if np.isnan(e9) or np.isnan(s20) or np.isnan(r) or np.isnan(vm) or vm <= 0:
                    continue

                # Entry: price above both MAs + RSI > threshold + volume confirmation
                if c > e9 and c > s20 and r > rsi_th and v > vm * vol_mult:
                    entries[i] = True

                # Exit: price below either MA
                if c < e9 or c < s20:
                    exits[i] = True

            # ── Manual position simulation with trailing stop + take profit ──
            in_position = False
            entry_price = 0.0
            peak_price = 0.0
            entry_idx = 0
            trade_returns = []
            position_log = []  # track if we're in a position each day

            for i in range(n):
                if not in_position:
                    if entries[i]:
                        in_position = True
                        entry_price = ind["close"][i]
                        peak_price = entry_price
                        entry_idx = i
                else:
                    # Update peak
                    peak_price = max(peak_price, ind["close"][i])

                    # Check trailing stop
                    drawdown = (peak_price - ind["close"][i]) / peak_price
                    if drawdown >= ts_pct:
                        ret = (ind["close"][i] - entry_price) / entry_price
                        trade_returns.append(ret)
                        in_position = False
                        continue

                    # Check take profit
                    gain = (ind["close"][i] - entry_price) / entry_price
                    if gain >= tp_pct:
                        ret = gain
                        trade_returns.append(ret)
                        in_position = False
                        continue

                    # Check time stop
                    if (i - entry_idx) >= TIME_STOP_DAYS:
                        ret = (ind["close"][i] - entry_price) / entry_price
                        trade_returns.append(ret)
                        in_position = False
                        continue

                    # Check MA exit
                    if exits[i]:
                        ret = (ind["close"][i] - entry_price) / entry_price
                        trade_returns.append(ret)
                        in_position = False
                        continue

                position_log.append(in_position)

            # Close any open position at the end
            if in_position:
                ret = (ind["close"][-1] - entry_price) / entry_price
                trade_returns.append(ret)

            # Compute per-stock return
            if trade_returns:
                # Compounded return
                stock_ret = np.prod([1 + r for r in trade_returns]) - 1
                n_trades = len(trade_returns)
                avg_ret = np.mean(trade_returns)
                std_ret = np.std(trade_returns) if len(trade_returns) > 1 else 0.0
                sharpe = (avg_ret / (std_ret + 1e-9)) * np.sqrt(252) if std_ret > 0 else 0.0
            else:
                stock_ret = 0.0
                n_trades = 0
                sharpe = 0.0

            # Max drawdown from position tracking
            peak_val = CAPITAL_PER
            max_dd = 0.0
            val = CAPITAL_PER
            for i in range(n):
                if i < len(position_log) and position_log[i]:
                    # Rough equity tracking
                    pass
            # Simplified: use trade returns to estimate
            if trade_returns:
                equity = CAPITAL_PER
                peak_eq = equity
                for r in trade_returns:
                    equity *= (1 + r)
                    peak_eq = max(peak_eq, equity)
                    dd = (equity - peak_eq) / peak_eq
                    max_dd = min(max_dd, dd)

            combo_returns.append(stock_ret)
            combo_sharpes.append(sharpe)
            combo_dds.append(max_dd)
            combo_trades.append(n_trades)

        # Portfolio: equal-weight across stocks
        portfolio_ret = np.mean(combo_returns)
        # Approximate portfolio Sharpe (average of individual)
        portfolio_sharpe = np.mean(combo_sharpes) if combo_sharpes else 0.0
        portfolio_dd = min(combo_dds) if combo_dds else 0.0
        total_trades = sum(combo_trades)

        results.append({
            "rsi_threshold": rsi_th,
            "vol_mult": vol_mult,
            "trailing_stop_pct": ts_pct * 100,
            "take_profit_pct": tp_pct * 100,
            "portfolio_return_pct": portfolio_ret * 100,
            "portfolio_sharpe": portfolio_sharpe,
            "max_drawdown_pct": portfolio_dd * 100,
            "total_trades": total_trades,
            "beats_spy": portfolio_ret * 100 > SPY_RETURN,
            "per_stock": {t: r for t, r in zip(TICKERS, combo_returns)},
        })

        done += 1
        if done % 10 == 0 or done == total_combos:
            print(f"  Progress: {done}/{total_combos} ({done * 100 // total_combos}%)")

    # ── Results Analysis ───────────────────────────────────────────────────
    df = pd.DataFrame(results)

    # Best by total return
    best_ret = df.loc[df["portfolio_return_pct"].idxmax()]
    # Best by Sharpe
    best_sharpe = df.loc[df["portfolio_sharpe"].idxmax()]
    # Best that beats SPY with highest Sharpe
    beats = df[df["beats_spy"] == True]
    best_balanced = beats.loc[beats["portfolio_sharpe"].idxmax()] if not beats.empty else None

    print("\n" + "=" * 80)
    print("  RESULTS")
    print("=" * 80)

    print(f"\n🏆 Best by Total Return:")
    print(f"  RSI={best_ret['rsi_threshold']}, Vol={best_ret['vol_mult']}×, "
          f"TS={best_ret['trailing_stop_pct']:.0f}%, TP={best_ret['take_profit_pct']:.0f}%")
    print(f"  Portfolio Return:  {best_ret['portfolio_return_pct']:>+7.2f}%")
    print(f"  Sharpe:            {best_ret['portfolio_sharpe']:>7.2f}")
    print(f"  Max DD:            {best_ret['max_drawdown_pct']:>7.2f}%")
    print(f"  Total Trades:      {best_ret['total_trades']}")
    print(f"  Beats SPY:         {'✅' if best_ret['beats_spy'] else '❌'}")

    print(f"\n📈 Best by Sharpe Ratio:")
    print(f"  RSI={best_sharpe['rsi_threshold']}, Vol={best_sharpe['vol_mult']}×, "
          f"TS={best_sharpe['trailing_stop_pct']:.0f}%, TP={best_sharpe['take_profit_pct']:.0f}%")
    print(f"  Portfolio Return:  {best_sharpe['portfolio_return_pct']:>+7.2f}%")
    print(f"  Sharpe:            {best_sharpe['portfolio_sharpe']:>7.2f}")
    print(f"  Max DD:            {best_sharpe['max_drawdown_pct']:>7.2f}%")
    print(f"  Beats SPY:         {'✅' if best_sharpe['beats_spy'] else '❌'}")

    if best_balanced is not None:
        print(f"\n⚖️  Best Risk-Adjusted that Beats SPY:")
        print(f"  RSI={best_balanced['rsi_threshold']}, Vol={best_balanced['vol_mult']}×, "
              f"TS={best_balanced['trailing_stop_pct']:.0f}%, TP={best_balanced['take_profit_pct']:.0f}%")
        print(f"  Portfolio Return:  {best_balanced['portfolio_return_pct']:>+7.2f}%")
        print(f"  Sharpe:            {best_balanced['portfolio_sharpe']:>7.2f}")
        print(f"  Max DD:            {best_balanced['max_drawdown_pct']:>7.2f}%")

    # ── Per-stock breakdown for best config ─────────────────────────────────
    print(f"\n📊 Per-Stock Breakdown (Best Return Config):")
    print(f"  {'Ticker':>8}  {'Return':>8}  {'P&L':>10}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}")
    for t in TICKERS:
        r = best_ret["per_stock"].get(t, 0) * 100
        pnl = CAPITAL_PER * (1 + r / 100) - CAPITAL_PER
        print(f"  {t:>8}  {r:>+7.2f}%  ${pnl:>+8,.2f}")

    portfolio_pnl = CAPITAL_PER * len(TICKERS) * (1 + best_ret["portfolio_return_pct"] / 100) - CAPITAL_PER * len(TICKERS)
    print(f"  {'─'*8}  {'─'*8}  {'─'*10}")
    print(f"  {'TOTAL':>8}  {best_ret['portfolio_return_pct']:>+7.2f}%  ${portfolio_pnl:>+8,.2f}")

    # ── Top 10 configurations ──────────────────────────────────────────────
    print(f"\n📋 Top 10 Configurations by Return:")
    top10 = df.nlargest(10, "portfolio_return_pct")[
        ["rsi_threshold", "vol_mult", "trailing_stop_pct", "take_profit_pct",
         "portfolio_return_pct", "portfolio_sharpe", "max_drawdown_pct", "total_trades"]
    ]
    print(f"  {'RSI':>4}  {'Vol':>4}  {'TS%':>5}  {'TP%':>5}  {'Return':>8}  {'Sharpe':>7}  {'MaxDD':>7}  {'Trades':>7}")
    print(f"  {'-'*4}  {'-'*4}  {'-'*5}  {'-'*5}  {'-'*8}  {'-'*7}  {'-'*7}  {'-'*7}")
    for _, row in top10.iterrows():
        print(f"  {row['rsi_threshold']:>4}  {row['vol_mult']:>4.1f}  {row['trailing_stop_pct']:>4.0f}%  "
              f"{row['take_profit_pct']:>4.0f}%  {row['portfolio_return_pct']:>+7.2f}%  "
              f"{row['portfolio_sharpe']:>7.2f}  {row['max_drawdown_pct']:>6.2f}%  {row['total_trades']:>7}")

    # ── Summary ────────────────────────────────────────────────────────────
    n_beats = df["beats_spy"].sum()
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print(f"  Configs that beat SPY ({SPY_RETURN:+.2f}%): {n_beats}/{total_combos} ({n_beats * 100 // total_combos}%)")
    print(f"  Best return:      {best_ret['portfolio_return_pct']:>+7.2f}%")
    print(f"  Best Sharpe:      {best_sharpe['portfolio_sharpe']:>7.2f}")
    print(f"  SPY benchmark:    {SPY_RETURN:>+7.2f}%")
    print(f"{'='*80}")

    # ── Save results ───────────────────────────────────────────────────────
    out_path = os.path.join(os.path.dirname(__file__), "optimization_results.csv")
    df.to_csv(out_path, index=False)
    print(f"\n💾 Full results saved to: {out_path}")
    print("  ✅ DONE")


if __name__ == "__main__":
    main()
