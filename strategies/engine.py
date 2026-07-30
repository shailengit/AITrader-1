"""StrategyEngine — fixed mechanical engine for daily-rotation strategies.

The engine handles everything that doesn't change between strategies:
  - Daily simulation loop
  - Portfolio state (holdings, cash, equity)
  - Position sizing (score-weighted)
  - Sector diversification
  - Markov regime adaptation (bull/bear exposure)
  - Trade logging
  - Reporting (KPIs, monthly returns, top/bottom trades)
  - JSON/CSV export

What changes per strategy is the 4-function config:
  - precompute_fn(tickers, start, end) -> stock_db
  - entry_score_fn(candidate, market_cap_stats) -> float
  - holding_score_fn(ticker, date, holding, market_cap_stats) -> float
  - exit_check_fn(ticker, date, holding, stock_db) -> str | None
"""
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any, List
import pandas as pd
import numpy as np


@dataclass
class StrategyConfig:
    """All knobs for a daily-rotation strategy run."""
    # ── Date range ──
    as_of: str
    end: str

    # ── Capital & sizing ──
    capital: float = 100_000.0
    max_holdings: int = 5
    min_hold_days: int = 7

    # ── Exits ──
    trailing_stop: float = 0.20
    take_profit: float = 0.30
    time_stop_days: int = 60

    # ── Filters ──
    max_volatility: float = 0.05  # skip stocks with 14d return std above this
    max_sector_count: int = 2

    # ── Regime ──
    bull_exposure: float = 1.0
    bear_exposure: float = 0.50

    # ── Scoring weights (used by golden_cross; ignored by others) ──
    angle_weight: float = 0.60
    cap_weight: float = 0.40

    # ── Strategy-specific 4 functions (set by golden_cross.py etc.) ──
    precompute_fn: Optional[Callable] = None
    entry_score_fn: Optional[Callable] = None
    holding_score_fn: Optional[Callable] = None
    exit_check_fn: Optional[Callable] = None

    # ── Optional metadata for reports ──
    name: str = "Unnamed Strategy"
    score_squared_sizing: bool = True  # Golden Cross uses score² weighting


class StrategyEngine:
    """Runs a daily-rotation strategy based on a StrategyConfig.

    The engine handles the daily simulation loop, portfolio state, position
    sizing, sector caps, Markov regime adaptation, trade logging, and reporting.
    The 4 user-supplied functions in StrategyConfig answer strategy-specific
    questions (when to emit a candidate, how to score it, how to re-score
    existing holdings, when to exit a position).
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        if not all([config.precompute_fn, config.entry_score_fn,
                    config.holding_score_fn, config.exit_check_fn]):
            raise ValueError("StrategyConfig must have all 4 function slots filled")

    def run(self) -> Dict[str, Any]:
        """Run the daily simulation. Returns trades, daily_equity, summary."""
        from app.services.markov.regime_model import SectorRegimeManager
        from app.services.data_service import get_data
        from app.db.database import engine as db_engine
        from sqlalchemy import text
        from datetime import datetime, timedelta
        from collections import OrderedDict

        cfg = self.config

        # ── 1. Get all tickers ──────────────────────────────────────────
        with db_engine.connect() as conn:
            res = conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ))
            skip = {'stock_metadata', 'stock_financials_quarterly', 'stock_financials_yearly',
                    'xlb', 'xlc', 'xle', 'xlf', 'xli', 'xlk', 'xlp', 'xlre', 'xlu', 'xlv', 'xly'}
            all_tickers = [row[0] for row in res if row[0] not in skip]

        # ── 2. Pre-compute ──────────────────────────────────────────────
        # Use a 3-year lookback so EMA200 has data on day 1
        lookback_start = (pd.Timestamp(cfg.as_of) - pd.Timedelta(days=3 * 365)).strftime("%Y-%m-%d")
        stock_db = cfg.precompute_fn(all_tickers, lookback_start, cfg.end)

        # ── 3. Build trading calendar ───────────────────────────────────
        all_trading_dates = set()
        for ticker, data in stock_db.items():
            dates_arr = data.get("dates")
            if dates_arr is None or len(dates_arr) == 0:
                continue
            for d in dates_arr:
                ds = str(pd.Timestamp(d))[:10]
                if cfg.as_of <= ds <= cfg.end:
                    all_trading_dates.add(ds)
        all_dates = sorted(all_trading_dates)

        # ── 4. Train Markov regime ──────────────────────────────────────
        start_dt = datetime.strptime(cfg.as_of, "%Y-%m-%d")
        end_dt = datetime.strptime(cfg.end, "%Y-%m-%d")
        retrain_dates = []
        d = start_dt + timedelta(days=3 * 365)
        while d < end_dt:
            retrain_dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=180)

        regime_cache = {}
        for i, rd in enumerate(retrain_dates):
            ts = (datetime.strptime(rd, "%Y-%m-%d") - timedelta(days=3 * 365 + 35)).strftime("%Y-%m-%d")
            rm = SectorRegimeManager(jump_penalty=10.0)
            rm.train_all(ts, rd)
            we = retrain_dates[i + 1] if i + 1 < len(retrain_dates) else cfg.end
            cur = datetime.strptime(rd, "%Y-%m-%d")
            we_dt = datetime.strptime(we, "%Y-%m-%d")
            day = cur
            while day <= we_dt:
                ds = day.strftime("%Y-%m-%d")
                regime_cache[ds] = rm.get_regime("SPY", ds)
                day += timedelta(days=1)

        def get_regime(date_str: str) -> str:
            r = regime_cache.get(date_str, {})
            return r.get("regime", "BULL")

        # ── 5. Daily simulation loop ────────────────────────────────────
        holdings = OrderedDict()
        trades = []
        daily_equity = []
        cash = cfg.capital
        portfolio_value = cfg.capital

        # Pre-compute market-cap normalization stats
        all_market_caps = [v.get("market_cap", 0) for v in stock_db.values() if v.get("market_cap") is not None and v.get("market_cap", 0) > 0]
        cap_max = max(all_market_caps) if all_market_caps else 1
        cap_min = min(all_market_caps) if all_market_caps else 0
        cap_range = cap_max - cap_min if cap_max > cap_min else 1
        market_cap_stats = {"cap_min": cap_min, "cap_max": cap_max, "cap_range": cap_range}

        def get_stock_value(ticker: str, date_str: str, field: str) -> float:
            data = stock_db.get(ticker)
            if data is None:
                return 0.0
            arr = data.get(field)
            dates = data.get("dates")
            if arr is None or dates is None:
                return 0.0
            target = pd.Timestamp(date_str)
            for i in range(len(dates) - 1, -1, -1):
                if pd.Timestamp(dates[i]) <= target:
                    return float(arr[i])
            return 0.0

        def get_price(ticker: str, date_str: str) -> float:
            return get_stock_value(ticker, date_str, "close")

        for sim_idx, current_date in enumerate(all_dates):
            regime = get_regime(current_date)
            is_bear = (regime == "BEAR")
            exposure = cfg.bear_exposure if is_bear else cfg.bull_exposure

            # ── 5a. Check exits via user function ────────────────────────
            to_remove = []
            for ticker in list(holdings.keys()):
                h = holdings[ticker]
                current_price = get_price(ticker, current_date)
                if current_price <= 0:
                    continue

                h["peak_price"] = max(h["peak_price"], current_price)
                ret = (current_price - h["entry_price"]) / h["entry_price"]
                pnl = h["shares"] * (current_price - h["entry_price"])

                reason = cfg.exit_check_fn(ticker, current_date, h, stock_db)
                if reason is not None:
                    trades.append({
                        "ticker": ticker, "side": "SELL",
                        "entry_date": h["entry_date"], "exit_date": current_date,
                        "entry_price": round(h["entry_price"], 2),
                        "exit_price": round(current_price, 2),
                        "return_pct": round(ret * 100, 2),
                        "holding_days": (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days,
                        "exit_reason": reason,
                        "pnl_dollars": round(pnl, 2),
                    })
                    cash += h["shares"] * current_price
                    to_remove.append(ticker)
                    continue

            for t in to_remove:
                del holdings[t]

            # ── 5b. Get new candidates for this date ─────────────────────
            new_candidates = self._get_candidates_for_date(stock_db, current_date, cfg)

            for c in new_candidates:
                c["score"] = cfg.entry_score_fn(c, market_cap_stats)

            # ── 5c. Merge holdings + new candidates, rank ───────────────
            all_stocks = []
            held_tickers = set(holdings.keys())
            for ticker, h in holdings.items():
                current_score = cfg.holding_score_fn(ticker, current_date, h, market_cap_stats)
                all_stocks.append({
                    "ticker": ticker, "score": current_score,
                    "market_cap": h["market_cap"], "sector": h["sector"],
                    "is_holding": True,
                })
            for c in new_candidates:
                if c["ticker"] not in held_tickers:
                    all_stocks.append({
                        "ticker": c["ticker"], "score": c["score"],
                        "angle": c.get("angle", 0),
                        "market_cap": c["market_cap"], "price": c["price"],
                        "sector": c["sector"],
                        "is_holding": False,
                    })
            all_stocks.sort(key=lambda x: x["score"], reverse=True)

            # ── 5d. Top N with sector diversification ───────────────────
            top_n = []
            sector_counts = {}
            for s in all_stocks:
                if len(top_n) >= cfg.max_holdings:
                    break
                sec = s.get("sector", "Unknown")
                if sector_counts.get(sec, 0) >= cfg.max_sector_count:
                    continue
                top_n.append(s)
                sector_counts[sec] = sector_counts.get(sec, 0) + 1
            top_n_tickers = set(s["ticker"] for s in top_n)

            # ── 5e. Sell dropped (with min hold check) ───────────────────
            to_drop = []
            for ticker in holdings:
                if ticker not in top_n_tickers:
                    h = holdings[ticker]
                    hold_days = (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days
                    if hold_days < cfg.min_hold_days:
                        continue
                    to_drop.append(ticker)
            for ticker in to_drop:
                h = holdings[ticker]
                current_price = get_price(ticker, current_date)
                if current_price > 0:
                    ret = (current_price - h["entry_price"]) / h["entry_price"]
                    pnl = h["shares"] * (current_price - h["entry_price"])
                    hold_days = (pd.Timestamp(current_date) - pd.Timestamp(h["entry_date"])).days
                    trades.append({
                        "ticker": ticker, "side": "SELL",
                        "entry_date": h["entry_date"], "exit_date": current_date,
                        "entry_price": round(h["entry_price"], 2),
                        "exit_price": round(current_price, 2),
                        "return_pct": round(ret * 100, 2),
                        "holding_days": hold_days,
                        "exit_reason": "Rotated Out",
                        "pnl_dollars": round(pnl, 2),
                    })
                    cash += h["shares"] * current_price
                del holdings[ticker]

            # ── 5f. Buy new top N (score-weighted sizing) ────────────────
            slots_available = cfg.max_holdings - len(holdings)
            if slots_available > 0:
                new_entries = [s for s in top_n if s["ticker"] not in holdings][:slots_available]
                if cfg.score_squared_sizing:
                    total_score = sum(s["score"] ** 2 for s in new_entries if s["score"] > 0)
                else:
                    total_score = sum(s["score"] for s in new_entries if s["score"] > 0)
                if total_score > 0:
                    for s in new_entries:
                        price = s.get("price", get_price(s["ticker"], current_date))
                        if price <= 0:
                            continue
                        if cfg.score_squared_sizing:
                            weight = (s["score"] ** 2) / total_score
                        else:
                            weight = s["score"] / total_score
                        target_value = portfolio_value * exposure * weight
                        shares = int(target_value / price)
                        cost = shares * price
                        if cost > cash:
                            shares = int(cash / price)
                            cost = shares * price
                        if shares <= 0:
                            continue
                        cash -= cost
                        holdings[s["ticker"]] = {
                            "entry_date": current_date,
                            "entry_price": price,
                            "peak_price": price,
                            "shares": shares,
                            "score": s["score"],
                            "angle": s.get("angle", 0),
                            "market_cap": s.get("market_cap", 0),
                            "sector": s.get("sector", "Unknown"),
                            "volume_ratio": s.get("volume_ratio", 0),
                            # Inject the stock_db entry so strategy-specific
                            # holding_score / exit_check can re-score based on
                            # current indicator values without re-querying the DB.
                            "_stock_data": stock_db.get(s["ticker"]),
                        }
                        trades.append({
                            "ticker": s["ticker"], "side": "BUY",
                            "entry_date": current_date, "exit_date": "",
                            "entry_price": round(price, 2), "exit_price": 0,
                            "return_pct": 0.0, "holding_days": 0,
                            "exit_reason": "New Entry", "pnl_dollars": 0.0,
                        })

            # ── 5g. Track daily equity ──────────────────────────────────
            holdings_value = 0.0
            for ticker, h in holdings.items():
                price = get_price(ticker, current_date)
                if price > 0:
                    holdings_value += h["shares"] * price
            portfolio_value = cash + holdings_value
            daily_equity.append({
                "date": current_date, "value": round(portfolio_value, 2),
                "cash": round(cash, 2), "holdings": round(holdings_value, 2),
                "n_holdings": len(holdings),
            })

        # ── 6. Summary KPIs ─────────────────────────────────────────────
        total_pnl = portfolio_value - cfg.capital
        total_ret = total_pnl / cfg.capital * 100
        buy_trades = [t for t in trades if t["side"] == "BUY"]
        sell_trades = [t for t in trades if t["side"] == "SELL"]
        winners = [t for t in sell_trades if t["pnl_dollars"] > 0]
        losers = [t for t in sell_trades if t["pnl_dollars"] <= 0]
        win_rate = len(winners) / len(sell_trades) * 100 if sell_trades else 0
        avg_win = float(np.mean([t["pnl_dollars"] for t in winners])) if winners else 0
        avg_loss = float(np.mean([t["pnl_dollars"] for t in losers])) if losers else 0
        gross_profit = sum(t["pnl_dollars"] for t in winners)
        gross_loss = abs(sum(t["pnl_dollars"] for t in losers))
        profit_factor = gross_profit / (gross_loss + 1e-9) if gross_loss > 0 else 0.0

        reasons = {}
        for t in sell_trades:
            r = t["exit_reason"].split("(")[0].strip()
            reasons[r] = reasons.get(r, 0) + 1

        # SPY benchmark
        spy_df = get_data("SPY", start_date=cfg.as_of, end_date=cfg.end, frequency="daily")
        spy_ret = 0.0
        if spy_df is not None and not spy_df.empty:
            if "Date" not in spy_df.columns and spy_df.index.name == "Date":
                spy_df = spy_df.reset_index()
            spy_ret = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100

        years = (datetime.strptime(cfg.end, "%Y-%m-%d") - datetime.strptime(cfg.as_of, "%Y-%m-%d")).days / 365.25
        cagr = ((portfolio_value / cfg.capital) ** (1 / max(years, 0.01)) - 1) * 100

        # Annualized Sharpe ratio from daily equity
        sharpe = 0.0
        max_dd = 0.0
        if len(daily_equity) > 1:
            eq_vals = np.array([d["value"] for d in daily_equity], dtype=float)
            daily_rets = np.diff(eq_vals) / eq_vals[:-1]
            if np.std(daily_rets) > 0 and len(daily_rets) > 0:
                sharpe = float(np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252))
            # Max drawdown from peak
            peak = eq_vals[0]
            for v in eq_vals:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak
                if dd > max_dd:
                    max_dd = dd
        max_dd_pct = round(max_dd * 100, 2)

        def _json_safe(val: float) -> float:
            """Replace Infinity/NaN with 0.0 for JSON serialization."""
            if np.isinf(val) or np.isnan(val):
                return 0.0
            return float(val)

        summary = {
            "initial_capital": cfg.capital,
            "final_portfolio": portfolio_value,
            "total_return_pct": _json_safe(round(total_ret, 2)),
            "cagr_pct": _json_safe(round(cagr, 2)),
            "sharpe_ratio": _json_safe(round(sharpe, 2)),
            "max_drawdown_pct": _json_safe(max_dd_pct),
            "total_trades": len(sell_trades),
            "win_rate": _json_safe(round(win_rate, 1)),
            "profit_factor": _json_safe(round(profit_factor, 2)),
            "avg_winner": _json_safe(round(avg_win, 2)),
            "avg_loser": _json_safe(round(avg_loss, 2)),
            "exit_reasons": reasons,
            "spy_return_pct": _json_safe(round(spy_ret, 2)),
            "alpha_pct": _json_safe(round(total_ret - spy_ret, 2)),
        }

        # Add top winners/losers for the run viewer report
        sell_trades_sorted = sorted(sell_trades, key=lambda t: t.get("pnl_dollars", 0), reverse=True)
        top_winners = sell_trades_sorted[:5]
        top_losers = sell_trades_sorted[-5:] if len(sell_trades_sorted) >= 5 else sell_trades_sorted[::-1]
        summary["top_winners"] = [
            {"ticker": t.get("ticker", ""), "return_pct": t.get("return_pct", 0),
             "pnl_dollars": t.get("pnl_dollars", 0), "exit_reason": t.get("exit_reason", "")}
            for t in top_winners
        ]
        summary["top_losers"] = [
            {"ticker": t.get("ticker", ""), "return_pct": t.get("return_pct", 0),
             "pnl_dollars": t.get("pnl_dollars", 0), "exit_reason": t.get("exit_reason", "")}
            for t in top_losers
        ]

        return {"trades": trades, "daily_equity": daily_equity, "summary": summary}

    def _get_candidates_for_date(self, stock_db, current_date, cfg):
        """Default candidate extractor: pull from stock_db['crossovers'] for this date.

        Strategy-specific precompute functions are responsible for populating
        each stock's 'crossovers' list with {'date', 'angle', 'market_cap', 'price', 'sector'}.
        Volatility filter is applied here (engine-level, not strategy-level).
        """
        candidates = []
        for ticker, data in stock_db.items():
            for co in data.get("crossovers", []):
                if co.get("death_cross"):
                    continue
                if co["date"] != current_date:
                    continue
                if co.get("volatility", 0) > cfg.max_volatility:
                    continue
                candidates.append({
                    "ticker": ticker,
                    "angle": co.get("angle", 0),
                    "market_cap": data.get("market_cap", 0),
                    "price": co.get("price", 0),
                    "sector": data.get("sector", "Unknown"),
                    "volume_ratio": co.get("volume_ratio", 0),
                })
        return candidates
