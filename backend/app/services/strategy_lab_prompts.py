"""LLM prompt templates for the AI Strategy Builder.

The AI Strategy Builder doesn't want a full vectorbt strategy — it wants
ONLY the 4 strategy-specific filter functions (precompute, entry_score,
holding_score, exit_check) plus a StrategyConfig instantiation. The fixed
mechanical engine (daily loop, portfolio state, position sizing) lives in
strategies/engine.py and the LLM must not reproduce it.

These prompts replace the generic "write a vectorbt strategy" prompt used
by the standalone QuantGen flow.
"""
from typing import List, Dict, Any


# ── Engine contract — embedded into CODE_PROMPT so the LLM knows the exact
#    signatures it must implement. ────────────────────────────────────────
ENGINE_CONTRACT = '''
# === strategies/engine.py contract (DO NOT REPRODUCE) ===

@dataclass
class StrategyConfig:
    as_of: str                           # YYYY-MM-DD, e.g. "2020-01-01"
    end: str                             # YYYY-MM-DD, e.g. "2026-07-08"
    capital: float = 100_000.0
    max_holdings: int = 5
    min_hold_days: int = 7
    trailing_stop: float = 0.20          # 20% trailing stop
    take_profit: float = 0.30            # 30% take profit
    time_stop_days: int = 60             # max hold time
    max_volatility: float = 0.05         # skip stocks with 14d return std above
    max_sector_count: int = 2
    bull_exposure: float = 1.0
    bear_exposure: float = 0.50
    angle_weight: float = 0.60
    cap_weight: float = 0.40
    precompute_fn: Optional[Callable] = None
    entry_score_fn: Optional[Callable] = None
    holding_score_fn: Optional[Callable] = None
    exit_check_fn: Optional[Callable] = None
    name: str = "Unnamed Strategy"
    score_squared_sizing: bool = True

class StrategyEngine:
    def __init__(self, config: StrategyConfig): ...
    def run(self) -> Dict[str, Any]: ...  # handles daily loop, position sizing, etc.

# === Your 4 filter functions must match these signatures ===

def precompute(tickers: List[str], start: str, end: str) -> Dict[str, Any]:
    """Return stock_db: ticker -> {
        "close": np.array, "dates": np.array, "crossovers": List[dict],
        "market_cap": float, "sector": str, ... (any extra fields are fine)
    }
    Each "crossovers" entry: {"date": "YYYY-MM-DD", "price": float, ...}
    Death crosses should set "death_cross": True.
    """
    pass

def entry_score(candidate: dict, market_cap_stats: dict) -> float:
    """Score a new candidate. candidate has: ticker, angle, market_cap, sector, price.
    market_cap_stats has: cap_min, cap_max, cap_range. Return a float in [0, 1]."""
    pass

def holding_score(ticker: str, date_str: str, holding: dict, market_cap_stats: dict) -> float:
    """Re-score an existing holding. holding._stock_data is the precomputed entry.
    Return a float in [0, 1]. 0 means "weak, rotate out"."""
    pass

def exit_check(ticker: str, date_str: str, holding: dict, stock_db: dict) -> Optional[str]:
    """Return an exit reason string ("Death Cross", "Take Profit", etc.) or None."""
    pass

# === At the bottom of the file ===

import importlib.util, sys
_engine_path = os.path.join(os.path.dirname(__file__), "engine.py")
_spec = importlib.util.spec_from_file_location("strategies_engine_inline", _engine_path)
_engine = importlib.util.module_from_spec(_spec)
sys.modules["strategies_engine_inline"] = _engine
_spec.loader.exec_module(_engine)

CONFIG = _engine.StrategyConfig(
    as_of=AS_OF, end=END, capital=CAPITAL,
    precompute_fn=precompute,
    entry_score_fn=entry_score,
    holding_score_fn=holding_score,
    exit_check_fn=exit_check,
    name="<Strategy Name>",
)
'''


# ── PLAN_PROMPT: produces a structured plan, not code ────────────────────
def make_plan_prompt(user_prompt: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a quant strategy planner. Given a user's strategy idea, "
                "produce a STRUCTURED PLAN with these sections, in this exact format:\n\n"
                "## Signal\n"
                "What triggers entries (e.g. EMA20 crosses above EMA200, RSI>70, etc.)\n\n"
                "## Entry scoring\n"
                "How to rank candidates (e.g. 60% crossover angle + 40% market cap, both normalized 0-1)\n\n"
                "## Holding re-score\n"
                "How to re-score existing positions daily (e.g. current EMA20/EMA200 spread + market cap)\n\n"
                "## Exits\n"
                "What triggers exits, in priority order (death cross, take profit, trailing stop, time stop, etc.)\n\n"
                "## Parameters\n"
                "List the numeric parameters: max_holdings, min_hold_days, trailing_stop%, take_profit%, time_stop_days, max_sector_count, etc.\n\n"
                "## Edge cases\n"
                "Any special handling (sector caps, volatility filters, regime adaptation, etc.)\n\n"
                "Be concrete and specific. Use exact percentages. Do NOT write Python code."
            ),
        },
        {
            "role": "user",
            "content": f"My strategy idea:\n\n{user_prompt}\n\nProduce the structured plan.",
        },
    ]


# ── CODE_PROMPT: produces ONLY the 4 filter functions + config ───────────
def make_code_prompt(plan: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a quant strategy coder. You write the 4 strategy-specific "
                "filter functions for TradeCraft's StrategyEngine. You do NOT write "
                "the engine itself — that is provided.\n\n"
                "OUTPUT FORMAT: a single Python file wrapped in a markdown ```python block. "
                "Do NOT include any prose before or after the code block.\n\n"
                "The file must contain EXACTLY these 4 functions (signatures must match):\n"
                "1. precompute(tickers, start, end) -> dict[ticker, stock_data]\n"
                "2. entry_score(candidate, market_cap_stats) -> float\n"
                "3. holding_score(ticker, date_str, holding, market_cap_stats) -> float\n"
                "4. exit_check(ticker, date_str, holding, stock_db) -> str | None\n\n"
                "Plus at the bottom, a CONFIG = StrategyConfig(...) instantiation that "
                "wires the 4 functions into the engine. Load engine.py via importlib.util.\n\n"
                "ENGINE CONTRACT (do not reproduce this code, just match the signatures):\n"
                f"{ENGINE_CONTRACT}\n\n"
                "RULES:\n"
                "- Use pandas and numpy. Read from `app.db.database.engine` and `app.utils.security.get_safe_table_name`.\n"
                "- For 'precompute', query each ticker's OHLCV table, compute indicators, "
                "  and populate 'crossovers' with entries like {\"date\": \"YYYY-MM-DD\", "
                "  \"price\": float, \"angle\": float, \"volatility\": float, "
                "  \"volume_ratio\": float} for golden crosses, and add "
                "  {\"date\": ..., \"death_cross\": True} for death crosses.\n"
                "- For 'entry_score', return a float in [0, 1]. Higher = better candidate.\n"
                "- For 'holding_score', use holding.get('_stock_data') to access the "
                "  precomputed indicator arrays (close, ema20, ema200, dates).\n"
                "- For 'exit_check', return a short reason string like 'Death Cross', "
                "  'Take Profit', 'Trailing Stop (24.3%)', 'Time Stop (60d)', "
                "  'Death Cross Warning', or None to hold.\n"
                "- At module top, set env defaults: DB_USER, DB_PASSWORD, DB_HOST, "
                "  DB_PORT, DB_NAME.\n"
                "- Constants (CAPITAL, AS_OF, END, parameter weights) go above the "
                "  functions, with reasonable defaults.\n"
                "- For the CONFIG instantiation, use importlib.util.spec_from_file_location "
                "  to load the engine module (don't rely on sys.path being set).\n"
                "- Do NOT use any VBT (vectorbt) APIs. This is a pure daily-rotation engine."
            ),
        },
        {
            "role": "user",
            "content": f"Here is the structured plan to implement:\n\n{plan}\n\nNow write the Python code.",
        },
    ]


# ── REFINE_PROMPT: produces a unified diff against current code ──────────
def make_refine_prompt(current_code: str, instruction: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a quant strategy refiner. The user has an existing strategy file "
                "(the 4 filter functions + CONFIG) and wants a specific change.\n\n"
                "OUTPUT FORMAT: a unified diff in standard unified-diff format, "
                "wrapped in a markdown ```diff block. Do NOT include any prose.\n\n"
                "The diff format:\n"
                "```diff\n"
                "--- a/strategy.py\n"
                "+++ b/strategy.py\n"
                "@@ -<start>,<lines> +<start>,<lines> @@\n"
                " unchanged line\n"
                "-removed line\n"
                "+added line\n"
                "```\n\n"
                "Rules:\n"
                "- Include 2-3 lines of context before and after each change.\n"
                "- The diff must apply cleanly to the current code (no conflicts).\n"
                "- Keep changes minimal and surgical — only what the instruction asks for."
            ),
        },
        {
            "role": "user",
            "content": f"Current code:\n\n```python\n{current_code}\n```\n\nInstruction: {instruction}\n\nProduce the unified diff.",
        },
    ]


# ── SUMMARIZE_PROMPT: takes 100 backtest rows, writes 3-paragraph analysis
def make_summarize_prompt(kpis_table: str, n_runs: int) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                f"You are a quant analyst. The user has run {n_runs} backtests of one "
                "strategy with different time windows. Write a 3-paragraph analysis:\n\n"
                "Paragraph 1: Overall performance and consistency. Mention the average "
                "and range of total return, Sharpe, win rate. Is the strategy's edge "
                "consistent or does it depend on a specific time window?\n\n"
                "Paragraph 2: Which time windows performed worst and why? Look at the "
                "start_date column — do bear-market windows (2008, 2020 covid, 2022 "
                "inflation) underperform? What does that tell you about the strategy's "
                "weakness?\n\n"
                "Paragraph 3: One specific, actionable parameter change to improve "
                "the worst-performing runs. Be specific (e.g. 'widen trailing stop "
                "from 20% to 25% to let winners compound in trending markets').\n\n"
                "Be concise. Total ~250 words."
            ),
        },
        {
            "role": "user",
            "content": f"Here are the {n_runs} backtest results:\n\n{kpis_table}",
        },
    ]


# ── REFINE_STRATEGY_PROMPT: LLM proposes a code tweak based on batch summary
def make_refine_strategy_prompt(current_code: str, summary: str, worst_runs_table: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a quant strategy refiner. Given a current strategy file and an "
                "AI-generated analysis of 100 backtest runs, propose ONE specific code "
                "change that targets the worst-performing time windows.\n\n"
                "OUTPUT FORMAT: a unified diff in standard unified-diff format wrapped "
                "in a markdown ```diff block. No prose before or after.\n\n"
                "Make the change minimal and surgical. Include 2-3 lines of context. "
                "The diff must apply cleanly to the current code."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Current strategy code:\n\n```python\n{current_code}\n```\n\n"
                f"Backtest analysis:\n{summary}\n\n"
                f"Worst-performing runs (lowest Sharpe):\n{worst_runs_table}\n\n"
                "Propose the unified diff."
            ),
        },
    ]
