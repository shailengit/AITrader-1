"""
Markov Regime-Adaptive Trending Strategy
===========================================
Uses a 2-state Markov switching model (bull/bear) + GJR-GARCH (high/low vol)
to detect market regimes and adapt strategy parameters automatically.

Regime → Parameter Map (rule-based, NOT optimized — no overfitting):
  BULL + LOW VOL:  RSI=50, TS=6%,  TP=20%  (normal trending)
  BULL + HIGH VOL: RSI=55, TS=4%,  TP=15%  (tight, protect gains)
  BEAR + LOW VOL:  RSI=45, TS=8%,  TP=25%  (wide, catch bounces)
  BEAR + HIGH VOL: RSI=60, TS=3%,  TP=10%  (very tight, quick flips)

Walk-forward: Markov model trained on rolling 3-year windows, retrained
every 6 months. No look-ahead bias.

Usage:
  cd backend && ./venv/bin/python ../strategies/markov_adaptive_strategy.py
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
    ("BULL", "LOW"):  {"rsi": 50, "trailing_stop": 0.06, "take_profit": 0.20},
    ("BULL", "HIGH"): {"rsi": 55, "trailing_stop": 0.04, "take_profit": 0.15},
    ("BEAR", "LOW"):  {"rsi": 45, "trailing_stop": 0.08, "take_profit": 0.25},
    ("BEAR", "HIGH"): {"rsi": 60, "trailing_stop": 0.03, "take_profit": 0.10},
}

TIME_STOP_DAYS = 60

# Sector mapping for the 5 Dormant Giant stocks
STOCK_SECTOR_MAP = {
    "PEGA": "Technology",      # XLK
    "QDEL": "Healthcare",      # XLV
    "R":    "Industrials",     # XLI
    "GWW":  "Industrials",     # XLI
    "BEN":  "Financial Services",  # XLF
    "MBIN": "Financial Services",  # XLF
    "VIAV": "Technology",      # XLK
}

SECTOR_TO_ETF = {
    "Technology": "XLK", "Energy": "XLE", "Financial Services": "XLF",
    "Healthcare": "XLV", "Consumer Cyclical": "XLY", "Industrials": "XLI",
    "Communication Services": "XLC", "Consumer Defensive": "XLP",
    "Basic Materials": "XLB", "Real Estate": "XLRE", "Utilities": "XLU",
}


def get_sector_etf(ticker: str) -> str:
    """Map a ticker to its sector ETF."""
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
    TICKERS = ["PEGA", "QDEL"]
    AS_OF = "2020-01-01"
    END = "2026-07-08"
    CAPITAL = 10_000.0
    CAPITAL_PER = CAPITAL / len(TICKERS)

    print("=" * 80)
    print("  MARKOV REGIME-ADAPTIVE TRENDING STRATEGY")
    print("=" * 80)
    print(f"  Period:     {AS_OF} → {END}")
    print(f"  Stocks:     {', '.join(TICKERS)}")
    print(f"  Capital:    ${CAPITAL:,.2f}")
    print(f"  Regimes:    BULL/BEAR × HIGH/LOW vol = 4 modes")
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
            print(f"  {t}: {len(df)} bars")
        else:
            print(f"  {t}: ⚠️  No data")

    # ── Walk-forward regime training ───────────────────────────────────────
    # Train Markov model on rolling 3-year windows, retrain every 6 months
    print("\n🧠 Training Markov regime models (walk-forward)...")

    start_dt = datetime.strptime(AS_OF, "%Y-%m-%d")
    end_dt = datetime.strptime(END, "%Y-%m-%d")

    # Build list of retrain dates (every 6 months)
    retrain_dates = []
    d = start_dt + timedelta(days=3 * 365)  # First train needs 3 years of history
    while d < end_dt:
        retrain_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=180)

    print(f"  Retraining at {len(retrain_dates)} checkpoints: "
          f"{retrain_dates[0]} ... {retrain_dates[-1]}")

    # Pre-compute regime for each day using the appropriate model window
    # We'll train models at each checkpoint and cache them
    regime_cache = {}  # date -> {ticker: regime_dict}

    for i, retrain_date in enumerate(retrain_dates):
        train_start = (datetime.strptime(retrain_date, "%Y-%m-%d") - timedelta(days=3 * 365 + 35)).strftime("%Y-%m-%d")
        train_end = retrain_date

        print(f"  Training Markov model #{i+1}: {train_start} → {train_end}")

        rm = SectorRegimeManager(jump_penalty=10.0)
        results = rm.train_all(train_start, train_end)
        n_trained = sum(1 for v in results.values() if v)
        print(f"    {n_trained}/11 sector ETFs trained")

        # Get regime for each day in the next 6-month window
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

    # ── Run strategy with regime-adaptive parameters ───────────────────────
    print(f"\n📈 Running regime-adaptive strategy...")

    per_stock = {}
    all_trades = []

    for ticker in TICKERS:
        df = stock_data.get(ticker)
        if df is None:
            continue

        print(f"\n  ── {ticker} (Sector: {STOCK_SECTOR_MAP.get(ticker, '?')}) ──")

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

        # Position simulation
        in_position = False
        entry_price = 0.0
        entry_date = ""
        peak_price = 0.0
        entry_idx = 0
        trades = []
        regime_log = []

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

            # ── Get regime for this day ─────────────────────────────────────
            day_regime = regime_cache.get(d, {})
            regime_info = day_regime.get(ticker, {})
            regime = regime_info.get("regime", "BULL")
            vol_regime = regime_info.get("vol_regime", "LOW")
            bull_prob = regime_info.get("bull_probability", 0.5)

            params = REGIME_PARAMS.get((regime, vol_regime), REGIME_PARAMS[("BULL", "LOW")])
            rsi_th = params["rsi"]
            ts_pct = params["trailing_stop"]
            tp_pct = params["take_profit"]

            if not in_position:
                # ENTRY: price above both MAs + RSI > threshold
                if c > e9 and c > s20 and r > rsi_th:
                    in_position = True
                    entry_price = c
                    entry_date = d
                    peak_price = c
                    entry_idx = i
                    regime_log.append((d, "ENTRY", regime, vol_regime, rsi_th, ts_pct, tp_pct, c, 0.0))
            else:
                peak_price = max(peak_price, c)
                exit_reason = None

                # Trailing stop
                dd = (peak_price - c) / peak_price
                if dd >= ts_pct:
                    exit_reason = f"Trailing Stop ({dd:.1%}) [{regime}/{vol_regime}]"

                # Take profit
                gain = (c - entry_price) / entry_price
                if gain >= tp_pct:
                    exit_reason = f"Take Profit ({gain:.1%}) [{regime}/{vol_regime}]"

                # Time stop
                if (i - entry_idx) >= TIME_STOP_DAYS:
                    exit_reason = f"Time Stop ({i - entry_idx}d) [{regime}/{vol_regime}]"

                # MA exit
                if c < e9 or c < s20:
                    exit_reason = f"MA Break [{regime}/{vol_regime}]"

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
                        "regime": f"{regime}/{vol_regime}",
                        "pnl_dollars": round(CAPITAL_PER * ret, 2),
                    })
                    regime_log.append((d, f"EXIT ({exit_reason})", regime, vol_regime,
                                       rsi_th, ts_pct, tp_pct, c, round(ret * 100, 2)))
                    in_position = False

        # Close open position at end
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
                "regime": f"{regime}/{vol_regime}",
                "pnl_dollars": round(CAPITAL_PER * ret, 2),
            })

        # ── Stats ───────────────────────────────────────────────────────────
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

            equity = CAPITAL_PER
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
            "pnl_dollars": compounded * CAPITAL_PER,
            "n_trades": n_trades,
            "win_rate": win_rate * 100,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "profit_factor": profit_factor,
            "max_dd_pct": max_dd * 100,
        }
        all_trades.extend(trades)

        s = per_stock[ticker]
        print(f"     Return:       {s['return_pct']:>+7.2f}%")
        print(f"     P&L:          ${s['pnl_dollars']:>+8.2f}")
        print(f"     Trades:       {s['n_trades']}")
        print(f"     Win Rate:     {s['win_rate']:.0f}%")
        print(f"     Profit Fac:   {s['profit_factor']:.2f}")
        print(f"     Max DD:       {s['max_dd_pct']:.2f}%")

    # ── Portfolio Summary ──────────────────────────────────────────────────
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

    print(f"\n  {'Ticker':>8}  {'Return':>8}  {'P&L':>10}  {'Trades':>6}  {'Win%':>6}  "
          f"{'AvgWin':>7}  {'AvgLoss':>7}  {'PF':>5}  {'MaxDD':>7}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*6}  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*5}  {'-'*7}")
    for t in TICKERS:
        s = per_stock.get(t, {})
        print(f"  {t:>8}  {s.get('return_pct',0):>+7.2f}%  ${s.get('pnl_dollars',0):>+8,.2f}  "
              f"{s.get('n_trades',0):>6}  {s.get('win_rate',0):>5.0f}%  "
              f"{s.get('avg_win_pct',0):>6.2f}%  {s.get('avg_loss_pct',0):>6.2f}%  "
              f"{s.get('profit_factor',0):>5.2f}  {s.get('max_dd_pct',0):>6.2f}%")

    # ── Regime Distribution ────────────────────────────────────────────────
    print(f"\n📊 Regime Distribution Across All Trades:")
    regime_counts = {}
    for t in all_trades:
        r = t.get("regime", "?")
        regime_counts[r] = regime_counts.get(r, 0) + 1
    for r, c in sorted(regime_counts.items()):
        print(f"  {r:>20}: {c} trades")

    # ── Trade Log ──────────────────────────────────────────────────────────
    if all_trades:
        print(f"\n{'='*80}")
        print(f"  TRADE LOG ({len(all_trades)} trades)")
        print("=" * 80)
        trade_df = pd.DataFrame(all_trades).sort_values(["ticker", "entry_date"])
        print(f"  {'Ticker':>8}  {'Entry':>12}  {'Exit':>12}  {'Entry $':>8}  {'Exit $':>8}  "
              f"{'Return':>8}  {'Days':>5}  {'Regime':>16}")
        print(f"  {'-'*8}  {'-'*12}  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*5}  {'-'*16}")
        for _, t in trade_df.iterrows():
            print(f"  {t['ticker']:>8}  {t['entry_date']:>12}  {t['exit_date']:>12}  "
                  f"${t['entry_price']:>7.2f}  ${t['exit_price']:>7.2f}  "
                  f"{t['return_pct']:>+7.2f}%  {t['holding_days']:>5}  {t.get('regime','?'):>16}")

    print(f"\n{'='*80}")
    print("  ✅ DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
