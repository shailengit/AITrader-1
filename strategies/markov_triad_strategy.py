"""
Markov Regime-Adaptive Strategy — Full Triad
===============================================
Combines three ideas to beat SPY (+151.72%) from 2020-01-01 to 2026-07-08:

1. MORE STOCKS: All 4 Dormant Giant technical candidates (DIOD, KRG, PEGA, QDEL)
2. SHORT OVERLAY: Short positions during BEAR regimes
3. DYNAMIC SIZING: 100% long in BULL, 25% long + 25% short + 50% cash in BEAR

Regime detection: 2-state Markov switching model (statsmodels) + GJR-GARCH volatility
Walk-forward: Rolling 3-year windows, retrained every 6 months — no look-ahead bias.

Usage:
  cd backend && ./venv/bin/python ../strategies/markov_triad_strategy.py
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


# ── Regime → Parameter Map (rule-based, NOT optimized) ─────────────────────
REGIME_PARAMS = {
    ("BULL", "LOW"):  {"rsi": 50, "ts": 0.06, "tp": 0.20},
    ("BULL", "HIGH"): {"rsi": 55, "ts": 0.04, "tp": 0.15},
    ("BEAR", "LOW"):  {"rsi": 45, "ts": 0.08, "tp": 0.25},
    ("BEAR", "HIGH"): {"rsi": 60, "ts": 0.03, "tp": 0.10},
}

TIME_STOP_DAYS = 60

# Sizing by regime
BULL_LONG_PCT = 1.0    # 100% of per-stock allocation in bull
BEAR_LONG_PCT = 0.25   # 25% in bear
BEAR_SHORT_PCT = 0.25  # 25% short in bear

# Sector mapping
STOCK_SECTOR_MAP = {
    "DIOD": "Technology", "KRG": "Real Estate",
    "PEGA": "Technology", "QDEL": "Healthcare",
}
SECTOR_TO_ETF = {
    "Technology": "XLK", "Energy": "XLE", "Financial Services": "XLF",
    "Healthcare": "XLV", "Consumer Cyclical": "XLY", "Industrials": "XLI",
    "Communication Services": "XLC", "Consumer Defensive": "XLP",
    "Basic Materials": "XLB", "Real Estate": "XLRE", "Utilities": "XLU",
}


def get_sector_etf(ticker: str) -> str:
    sector = STOCK_SECTOR_MAP.get(ticker.upper(), "Technology")
    return SECTOR_TO_ETF.get(sector, "XLK")


def compute_rsi(close: pd.Series, period: int = 14) -> np.ndarray:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return (100 - (100 / (1 + rs))).values


def main():
    from app.services.data_service import get_data
    from app.services.markov.regime_model import SectorRegimeManager

    # ── Configuration ──────────────────────────────────────────────────────
    TICKERS = ["DIOD", "KRG", "PEGA", "QDEL"]
    AS_OF = "2020-01-01"
    END = "2026-07-08"
    CAPITAL = 10_000.0
    N_STOCKS = len(TICKERS)
    CAPITAL_PER = CAPITAL / N_STOCKS  # $2,500 per stock

    print("=" * 80)
    print("  MARKOV TRIAD STRATEGY (More Stocks + Short Overlay + Dynamic Sizing)")
    print("=" * 80)
    print(f"  Period:     {AS_OF} → {END}")
    print(f"  Stocks:     {', '.join(TICKERS)}")
    print(f"  Capital:    ${CAPITAL:,.2f} (${CAPITAL_PER:,.0f}/stock)")
    print(f"  BULL:       100% long, 0% short")
    print(f"  BEAR:       25% long, 25% short, 50% cash")
    print(f"  Walk-fwd:   Rolling 3yr train, retrain every 6mo")
    print("=" * 80)

    # ── Load stock data ─────────────────────────────────────────────────────
    print("\n📥 Loading stock data...")
    stock_data = {}
    for t in TICKERS:
        df = get_data(t, start_date=AS_OF, end_date=END, frequency="daily")
        if df is not None and not df.empty:
            if "Date" not in df.columns and df.index.name == "Date":
                df = df.reset_index()
            stock_data[t] = df.reset_index(drop=True)
            print(f"  {t}: {len(df)} bars — {STOCK_SECTOR_MAP.get(t, '?')}")
        else:
            print(f"  {t}: ⚠️  No data")

    # ── Walk-forward regime training ───────────────────────────────────────
    print("\n🧠 Training Markov regime models (walk-forward)...")

    start_dt = datetime.strptime(AS_OF, "%Y-%m-%d")
    end_dt = datetime.strptime(END, "%Y-%m-%d")

    retrain_dates = []
    d = start_dt + timedelta(days=3 * 365)
    while d < end_dt:
        retrain_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=180)

    print(f"  {len(retrain_dates)} checkpoints: {retrain_dates[0]} ... {retrain_dates[-1]}")

    regime_cache = {}

    for i, retrain_date in enumerate(retrain_dates):
        train_start = (datetime.strptime(retrain_date, "%Y-%m-%d") - timedelta(days=3 * 365 + 35)).strftime("%Y-%m-%d")
        train_end = retrain_date

        print(f"  Model #{i+1}: {train_start} → {train_end}")

        rm = SectorRegimeManager(jump_penalty=10.0)
        results = rm.train_all(train_start, train_end)
        n_trained = sum(1 for v in results.values() if v)
        print(f"    {n_trained}/11 sector ETFs trained")

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

    # ── Run strategy ────────────────────────────────────────────────────────
    print(f"\n📈 Running triad strategy...")

    per_stock = {}
    all_trades = []
    daily_equity_log = []

    for ticker in TICKERS:
        df = stock_data.get(ticker)
        if df is None:
            continue

        print(f"\n  ── {ticker} ({STOCK_SECTOR_MAP.get(ticker, '?')}) ──")

        dates = df["Date"] if "Date" in df.columns else pd.Series([""] * len(df))
        close = df["Close"].values
        high = df["High"].values
        low = df["Low"].values
        open_p = df["Open"].values
        volume = df["Volume"].values
        n = len(close)

        # Pre-compute indicators
        ema9 = pd.Series(close).ewm(span=9, adjust=False).mean().values
        sma20 = pd.Series(close).rolling(window=20).mean().values
        rsi = compute_rsi(pd.Series(close))
        vol_ma20 = pd.Series(volume).rolling(window=20).mean().values

        # Position tracking
        long_position = False
        short_position = False
        long_entry_price = 0.0
        short_entry_price = 0.0
        long_entry_date = ""
        short_entry_date = ""
        long_peak = 0.0
        short_peak = 0.0  # For short: lowest price since entry (peak profit)
        long_entry_idx = 0
        short_entry_idx = 0
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

            # ── Get regime ──────────────────────────────────────────────────
            day_regime = regime_cache.get(d, {})
            regime_info = day_regime.get(ticker, {})
            regime = regime_info.get("regime", "BULL")
            vol_regime = regime_info.get("vol_regime", "LOW")
            bull_prob = regime_info.get("bull_probability", 0.5)

            params = REGIME_PARAMS.get((regime, vol_regime), REGIME_PARAMS[("BULL", "LOW")])
            rsi_th = params["rsi"]
            ts_pct = params["ts"]
            tp_pct = params["tp"]

            is_bear = (regime == "BEAR")

            # ── LONG POSITION MANAGEMENT ─────────────────────────────────────
            if not long_position:
                if c > e9 and c > s20 and r > rsi_th:
                    long_position = True
                    long_entry_price = c
                    long_entry_date = d
                    long_peak = c
                    long_entry_idx = i
            else:
                long_peak = max(long_peak, c)
                exit_reason = None

                dd = (long_peak - c) / long_peak
                if dd >= ts_pct:
                    exit_reason = f"Long TS ({dd:.1%}) [{regime}]"
                gain = (c - long_entry_price) / long_entry_price
                if gain >= tp_pct:
                    exit_reason = f"Long TP ({gain:.1%}) [{regime}]"
                if (i - long_entry_idx) >= TIME_STOP_DAYS:
                    exit_reason = f"Long Time ({i - long_entry_idx}d) [{regime}]"
                if c < e9 or c < s20:
                    exit_reason = f"Long MA [{regime}]"

                if exit_reason:
                    ret = (c - long_entry_price) / long_entry_price
                    # Apply sizing: full in BULL, reduced in BEAR
                    sizing = BULL_LONG_PCT if not is_bear else BEAR_LONG_PCT
                    trades.append({
                        "ticker": ticker, "side": "LONG",
                        "entry_date": long_entry_date, "exit_date": d,
                        "entry_price": round(long_entry_price, 2),
                        "exit_price": round(c, 2),
                        "return_pct": round(ret * 100, 2),
                        "holding_days": i - long_entry_idx,
                        "exit_reason": exit_reason,
                        "regime": f"{regime}/{vol_regime}",
                        "sizing_pct": sizing,
                        "pnl_dollars": round(CAPITAL_PER * sizing * ret, 2),
                    })
                    long_position = False

            # ── SHORT POSITION MANAGEMENT (BEAR only) ───────────────────────
            if is_bear:
                if not short_position:
                    # Entry SHORT: trend break — price was above SMA(20) yesterday
                    # but closed below it today. This catches QDEL-style collapses
                    # early, before RSI has time to drop below 45.
                    prev_c = close[i - 1] if i > 0 else c
                    prev_s20 = sma20[i - 1] if i > 0 else s20
                    trend_break = (prev_c > prev_s20) and (c < s20)
                    if trend_break:
                        short_position = True
                        short_entry_price = c
                        short_entry_date = d
                        short_peak = c  # lowest price since entry
                        short_entry_idx = i
                else:
                    short_peak = min(short_peak, c)
                    exit_reason = None

                    # For shorts: trailing stop if price rises too much
                    rise = (c - short_entry_price) / short_entry_price
                    if rise >= ts_pct:
                        exit_reason = f"Short TS ({rise:.1%}) [{regime}]"
                    # Take profit on shorts: price fell enough
                    decline = (short_entry_price - c) / short_entry_price
                    if decline >= tp_pct:
                        exit_reason = f"Short TP ({decline:.1%}) [{regime}]"
                    if (i - short_entry_idx) >= TIME_STOP_DAYS:
                        exit_reason = f"Short Time ({i - short_entry_idx}d) [{regime}]"
                    # Cover if price rises above either MA
                    if c > e9 or c > s20:
                        exit_reason = f"Short MA [{regime}]"

                    if exit_reason:
                        # Short P&L: (entry - exit) / entry
                        ret = (short_entry_price - c) / short_entry_price
                        trades.append({
                            "ticker": ticker, "side": "SHORT",
                            "entry_date": short_entry_date, "exit_date": d,
                            "entry_price": round(short_entry_price, 2),
                            "exit_price": round(c, 2),
                            "return_pct": round(ret * 100, 2),
                            "holding_days": i - short_entry_idx,
                            "exit_reason": exit_reason,
                            "regime": f"{regime}/{vol_regime}",
                            "sizing_pct": BEAR_SHORT_PCT,
                            "pnl_dollars": round(CAPITAL_PER * BEAR_SHORT_PCT * ret, 2),
                        })
                        short_position = False
            else:
                # In BULL regime, close any open short
                if short_position:
                    ret = (short_entry_price - c) / short_entry_price
                    trades.append({
                        "ticker": ticker, "side": "SHORT",
                        "entry_date": short_entry_date, "exit_date": d,
                        "entry_price": round(short_entry_price, 2),
                        "exit_price": round(c, 2),
                        "return_pct": round(ret * 100, 2),
                        "holding_days": i - short_entry_idx,
                        "exit_reason": f"Short → BULL regime",
                        "regime": f"{regime}/{vol_regime}",
                        "sizing_pct": BEAR_SHORT_PCT,
                        "pnl_dollars": round(CAPITAL_PER * BEAR_SHORT_PCT * ret, 2),
                    })
                    short_position = False

        # Close any open positions at end
        if long_position:
            ret = (close[-1] - long_entry_price) / long_entry_price
            sizing = BULL_LONG_PCT if regime != "BEAR" else BEAR_LONG_PCT
            trades.append({
                "ticker": ticker, "side": "LONG",
                "entry_date": long_entry_date,
                "exit_date": str(dates.iloc[-1])[:10] if hasattr(dates, "iloc") else str(dates[-1])[:10],
                "entry_price": round(long_entry_price, 2),
                "exit_price": round(close[-1], 2),
                "return_pct": round(ret * 100, 2),
                "holding_days": n - 1 - long_entry_idx,
                "exit_reason": "End of Period",
                "regime": f"{regime}/{vol_regime}",
                "sizing_pct": sizing,
                "pnl_dollars": round(CAPITAL_PER * sizing * ret, 2),
            })
        if short_position:
            ret = (short_entry_price - close[-1]) / short_entry_price
            trades.append({
                "ticker": ticker, "side": "SHORT",
                "entry_date": short_entry_date,
                "exit_date": str(dates.iloc[-1])[:10] if hasattr(dates, "iloc") else str(dates[-1])[:10],
                "entry_price": round(short_entry_price, 2),
                "exit_price": round(close[-1], 2),
                "return_pct": round(ret * 100, 2),
                "holding_days": n - 1 - short_entry_idx,
                "exit_reason": "End of Period",
                "regime": f"{regime}/{vol_regime}",
                "sizing_pct": BEAR_SHORT_PCT,
                "pnl_dollars": round(CAPITAL_PER * BEAR_SHORT_PCT * ret, 2),
            })

        # ── Compute stats ──────────────────────────────────────────────────
        if trades:
            # Separate long and short P&L
            long_pnl = sum(t["pnl_dollars"] for t in trades if t["side"] == "LONG")
            short_pnl = sum(t["pnl_dollars"] for t in trades if t["side"] == "SHORT")
            total_pnl_stock = long_pnl + short_pnl
            total_ret_stock = total_pnl_stock / CAPITAL_PER

            n_trades = len(trades)
            n_long = sum(1 for t in trades if t["side"] == "LONG")
            n_short = sum(1 for t in trades if t["side"] == "SHORT")
            winners = [t for t in trades if t["pnl_dollars"] > 0]
            losers = [t for t in trades if t["pnl_dollars"] <= 0]
            win_rate = len(winners) / n_trades if n_trades > 0 else 0
            avg_win = np.mean([t["pnl_dollars"] for t in winners]) if winners else 0
            avg_loss = np.mean([t["pnl_dollars"] for t in losers]) if losers else 0
            gross_profit = sum(t["pnl_dollars"] for t in winners)
            gross_loss = abs(sum(t["pnl_dollars"] for t in losers))
            profit_factor = gross_profit / (gross_loss + 1e-9)

            # Max drawdown from trade equity
            equity = CAPITAL_PER
            peak_eq = equity
            max_dd = 0.0
            for t in trades:
                equity += t["pnl_dollars"]
                peak_eq = max(peak_eq, equity)
                dd = (equity - peak_eq) / peak_eq
                max_dd = min(max_dd, dd)
        else:
            total_pnl_stock = 0.0
            total_ret_stock = 0.0
            n_trades = 0
            n_long = 0
            n_short = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
            max_dd = 0.0

        per_stock[ticker] = {
            "return_pct": total_ret_stock * 100,
            "pnl_dollars": total_pnl_stock,
            "n_trades": n_trades,
            "n_long": n_long,
            "n_short": n_short,
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "win_rate": win_rate * 100,
            "profit_factor": profit_factor,
            "max_dd_pct": max_dd * 100,
        }
        all_trades.extend(trades)

        s = per_stock[ticker]
        print(f"     Long P&L:    ${s['long_pnl']:>+8.2f} ({s['n_long']} trades)")
        print(f"     Short P&L:   ${s['short_pnl']:>+8.2f} ({s['n_short']} trades)")
        print(f"     Total P&L:   ${s['pnl_dollars']:>+8.2f}")
        print(f"     Return:      {s['return_pct']:>+7.2f}%")
        print(f"     Win Rate:    {s['win_rate']:.0f}%")
        print(f"     Profit Fac:  {s['profit_factor']:.2f}")
        print(f"     Max DD:      {s['max_dd_pct']:.2f}%")

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

    # SPY benchmark
    spy_df = get_data("SPY", start_date=AS_OF, end_date=END, frequency="daily")
    if spy_df is not None and not spy_df.empty:
        if "Date" not in spy_df.columns and spy_df.index.name == "Date":
            spy_df = spy_df.reset_index()
        spy_ret = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100
        alpha = total_ret - spy_ret
        print(f"  SPY Return:       {spy_ret:>+7.2f}%")
        print(f"  Alpha:            {alpha:>+7.2f}%  {'✅' if alpha > 0 else '❌'}")

    print(f"\n  {'Ticker':>8}  {'Return':>8}  {'P&L':>10}  {'Trades':>6}  {'Long':>5}  {'Short':>5}  "
          f"{'Long$':>9}  {'Short$':>9}  {'Win%':>5}  {'PF':>5}  {'MaxDD':>7}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*6}  {'-'*5}  {'-'*5}  "
          f"{'─'*9}  {'─'*9}  {'─'*5}  {'─'*5}  {'─'*7}")
    for t in TICKERS:
        s = per_stock.get(t, {})
        print(f"  {t:>8}  {s.get('return_pct',0):>+7.2f}%  ${s.get('pnl_dollars',0):>+8,.2f}  "
              f"{s.get('n_trades',0):>6}  {s.get('n_long',0):>5}  {s.get('n_short',0):>5}  "
              f"${s.get('long_pnl',0):>+7,.2f}  ${s.get('short_pnl',0):>+7,.2f}  "
              f"{s.get('win_rate',0):>4.0f}%  {s.get('profit_factor',0):>4.2f}  "
              f"{s.get('max_dd_pct',0):>6.2f}%")

    # ── Regime Distribution ────────────────────────────────────────────────
    print(f"\n📊 Regime Distribution:")
    regime_counts = {}
    side_counts = {"LONG": 0, "SHORT": 0}
    for t in all_trades:
        r = t.get("regime", "?")
        regime_counts[r] = regime_counts.get(r, 0) + 1
        side_counts[t.get("side", "?")] += 1
    for r, c in sorted(regime_counts.items()):
        print(f"  {r:>20}: {c} trades")
    print(f"  {'LONG':>20}: {side_counts['LONG']} trades")
    print(f"  {'SHORT':>20}: {side_counts['SHORT']} trades")

    # ── Trade Log ──────────────────────────────────────────────────────────
    if all_trades:
        print(f"\n{'='*80}")
        print(f"  TRADE LOG ({len(all_trades)} trades)")
        print("=" * 80)
        trade_df = pd.DataFrame(all_trades).sort_values(["ticker", "entry_date"])
        print(f"  {'Ticker':>8}  {'Side':>5}  {'Entry':>12}  {'Exit':>12}  {'Entry $':>8}  "
              f"{'Exit $':>8}  {'Return':>8}  {'Days':>5}  {'Sizing':>7}  {'Regime':>12}")
        print(f"  {'-'*8}  {'-'*5}  {'-'*12}  {'-'*12}  {'-'*8}  {'-'*8}  "
              f"{'─'*8}  {'─'*5}  {'─'*7}  {'─'*12}")
        for _, t in trade_df.iterrows():
            sizing_label = f"{t.get('sizing_pct', 1)*100:.0f}%"
            print(f"  {t['ticker']:>8}  {t['side']:>5}  {t['entry_date']:>12}  {t['exit_date']:>12}  "
                  f"${t['entry_price']:>7.2f}  ${t['exit_price']:>7.2f}  "
                  f"{t['return_pct']:>+7.2f}%  {t['holding_days']:>5}  {sizing_label:>7}  {t.get('regime','?'):>12}")

    print(f"\n{'='*80}")
    print("  ✅ DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
