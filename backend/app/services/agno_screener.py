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


def analyze_single_ticker_dormant_giant(ticker: str, filters: Dict[str, Any] = None) -> Optional[Dict]:
    """Worker function for Dormant Giant technical analysis."""
    if filters is None:
        filters = {}

    worker_engine = create_engine(DB_URL, poolclass=QueuePool, pool_size=1)
    try:
        query = f'SELECT "Date", "Close", "Volume", "High" FROM "{ticker.lower()}" ORDER BY "Date" DESC LIMIT 200;'
        df = pd.read_sql(query, worker_engine).sort_values('Date')
    except Exception as e:
        return {"error": f"DB Error for {ticker}: {e}"}
    finally:
        worker_engine.dispose()

    if len(df) < 120:
        return {"error": f"{ticker.upper()}: Insufficient data (<120 days)"}

    # Bollinger Bandwidth Squeeze Logic
    df['sma'] = df['Close'].rolling(window=20).mean()
    df['std'] = df['Close'].rolling(window=20).std()
    df['bandwidth'] = ((df['sma'] + (df['std'] * 2)) - (df['sma'] - (df['std'] * 2))) / df['sma']

    squeeze_threshold = filters.get('squeeze_threshold', 1.15)
    min_bandwidth = df['bandwidth'].tail(120).min()
    current_bandwidth = df['bandwidth'].iloc[-1]
    is_squeezing = current_bandwidth <= (min_bandwidth * squeeze_threshold)

    # OBV Hidden Accumulation Logic
    close_diff = df['Close'].diff()
    df['obv'] = pd.Series(np.sign(close_diff.values) * df['Volume'].values).fillna(0).cumsum()
    obv_slope = np.polyfit(np.arange(20), df['obv'].tail(20), 1)[0]
    price_slope = np.polyfit(np.arange(20), df['Close'].tail(20), 1)[0]

    accumulation_threshold = filters.get('accumulation_threshold', 0.005)
    hidden_accumulation = (obv_slope > 0) and (abs(price_slope) < (df['Close'].iloc[-1] * accumulation_threshold))

    # Breakout Logic
    past_resistance = df['High'].shift(3).rolling(window=120).max().iloc[-1]

    volume_threshold = filters.get('volume_threshold', 1.5)
    avg_vol = df['Volume'].tail(50).mean()
    current_vol = df['Volume'].iloc[-1]
    is_breakout = (df['Close'].iloc[-1] > past_resistance) and (
        current_vol > (avg_vol * volume_threshold)
    )

    if is_breakout:
        return {"ticker": ticker.upper(), "signal": "Active Breakout", "log": f"MATCH: {ticker.upper()} - Active Breakout detected"}
    elif is_squeezing and hidden_accumulation:
        return {"ticker": ticker.upper(), "signal": "Coiling (Accumulation)", "log": f"MATCH: {ticker.upper()} - Coiling/Accumulation detected"}

    return None


def tool_run_dormant_giant_scan(progress_callback=None, log_callback=None, filters: Dict[str, Any] = None) -> List[Dict]:
    """Technical scan for Dormant Giant screening."""
    tickers = get_active_tickers()
    results = []

    with ProcessPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(analyze_single_ticker_dormant_giant, t, filters): t for t in tickers}
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
                pass
            finally:
                completed += 1
                if progress_callback and total > 0:
                    # Progress from 10% to 80%
                    progress = 10 + int((completed / total) * 70)
                    progress_callback(progress)

    logger.info(f"Dormant Giant Technical Scan Summary: Total={total}, Results={len(results)}")
    return results


def tool_verify_eps_acceleration(tickers: List[Dict]) -> List[Dict]:
    """Verify EPS acceleration OR revenue growth for screened tickers."""
    verified_tickers = []

    for item in tickers:
        ticker = item['ticker']
        catalyst = None
        try:
            query = text("""
                SELECT eps, total_revenue FROM stock_financials_quarterly
                WHERE ticker = :ticker ORDER BY report_date DESC LIMIT 3;
            """)
            with ENGINE.connect() as conn:
                fin_df = pd.read_sql(query, conn, params={"ticker": ticker})

            # EPS check: positive growth (looser than 1.5x acceleration)
            if len(fin_df) >= 2:
                current_eps = fin_df['eps'].iloc[0]
                prev_eps = fin_df['eps'].iloc[1]
                if prev_eps != 0:
                    current_growth = (current_eps - prev_eps) / abs(prev_eps)
                    if current_growth > 0:
                        catalyst = "Confirmed EPS Acceleration"

            # Fallback: revenue growth
            if not catalyst and len(fin_df) >= 2:
                curr_rev = fin_df['total_revenue'].iloc[0]
                prev_rev = fin_df['total_revenue'].iloc[1]
                if prev_rev and prev_rev > 0:
                    rev_growth = (curr_rev - prev_rev) / prev_rev
                    if rev_growth > 0:
                        catalyst = "Confirmed Revenue Growth"

        except Exception:
            pass

        if catalyst:
            item['fundamental_catalyst'] = catalyst
            verified_tickers.append(item)

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
        return res
    except Exception as e:
        logger.debug(f"Error processing {ticker}: {e}")
        return None
    finally:
        worker_engine.dispose()


def _worker_ta_wrapper(args_tuple):
    """Module-level wrapper for multiprocessing."""
    return _worker_ta_analysis(*args_tuple)


def technical_screener(requested_indicators: List[str], sort_by: str = "ticker",
                       cutoff_date: Optional[str] = None,
                       progress_callback=None, log_callback=None) -> str:
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
    if not df.empty and sort_by in df.columns:
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
            logger.warning(f"Error processing {ticker}: {e}")
            continue

    return pd.DataFrame(results).to_csv(index=False) if results else "No performance data available."


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
# SERVICE FUNCTIONS
# =============================================================================

def run_dormant_giant_screener(prompt: str = None, progress_callback=None, log_callback=None, filters: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Run the Dormant Giant screener without AI agents (fast, pure Python).
    Returns structured results for API response.
    """
    logger.info("Running Dormant Giant screener...")

    # Technical scan
    technical_results = tool_run_dormant_giant_scan(progress_callback=progress_callback, log_callback=log_callback, filters=filters)
    logger.info(f"Technical scan found {len(technical_results)} candidates")

    if not technical_results:
        return {
            "technical_candidates": 0,
            "verified_candidates": 0,
            "results": [],
            "summary": "No stocks matched the technical criteria (Squeeze/Accumulation/Breakout). Try relaxing the filters."
        }

    # Fundamental verification
    verified_results = tool_verify_eps_acceleration(technical_results)
    logger.info(f"Fundamental verification found {len(verified_results)} stocks with catalysts")

    return {
        "technical_candidates": len(technical_results),
        "verified_candidates": len(verified_results),
        "results": verified_results,
        "summary": f"Found {len(technical_results)} technical candidates, {len(verified_results)} with EPS acceleration or revenue growth catalysts."
    }


class AgnoLogCapture:
    """Custom handler to capture Agno agent output for streaming to frontend."""
    def __init__(self, logs_buffer: List[str], agent_log_callback: Optional[Callable] = None):
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


def run_dormant_giant_screener_with_ai(prompt: str = None, progress_callback=None, log_callback=None, filters: Dict[str, Any] = None, logs_buffer: List[Dict] = None, agent_log_callback=None) -> Dict[str, Any]:
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
        structured = run_dormant_giant_screener(progress_callback=progress_callback, log_callback=log_callback, filters=filters)
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

        ai_report = response.content if hasattr(response, 'content') else str(response) if response else "No response"

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
        logger.error(f"AI screener failed: {e}")
        log_capture.log_system(f"Error in AI analysis: {str(e)[:100]}... Falling back to non-AI mode.")
        # Fallback to non-AI mode
        logger.info("Falling back to non-AI screener...")
        return run_dormant_giant_screener(prompt, progress_callback=progress_callback, log_callback=log_callback, filters=filters)


def run_quant_strategy_screener(prompt: str, cutoff_date: str = None, progress_callback=None, log_callback=None) -> Dict[str, Any]:
    """
    Run the Quant Strategy screener without AI agents (fast, pure Python).
    Uses ta library column names and maps to frontend-friendly keys.
    """
    logger.info(f"Running Quant Strategy screener (cutoff_date={cutoff_date})...")

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

    # Technical scan with progress
    tech_csv = technical_screener(
        ta_indicators,
        cutoff_date=cutoff_date,
        progress_callback=progress_callback,
        log_callback=log_callback
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
        results_records.append(record)

    tickers = [r['ticker'] for r in results_records if r.get('ticker')][:20]

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

    return {
        "technical_candidates": len(results_records),
        "results": results_records[:50],
        "fundamental_data": fund_csv,
        "metadata": meta_csv,
        "performance": perf_csv,
        "summary": f"Found {len(results_records)} technical candidates. Fundamental and risk analysis complete."
    }


def run_quant_strategy_screener_with_ai(prompt: str, cutoff_date: str = None, logs_buffer: List[Dict] = None, progress_callback=None, agent_log_callback=None) -> Dict[str, Any]:
    """
    Run the Quant Strategy screener with AI multi-agent analysis.
    """
    if logs_buffer is None:
        logs_buffer = []

    log_capture = AgnoLogCapture(logs_buffer, agent_log_callback=agent_log_callback)

    try:
        log_capture.log_system("Initializing Quant Strategy AI screener...")
        log_capture.log_system("Assembling multi-agent team with Technical, Fundamental, Risk, and Performance specialists")

        team = create_quant_strategy_team()

        full_prompt = prompt
        if cutoff_date:
            full_prompt = f"{prompt} cutoff_date={cutoff_date}"
            log_capture.log_system(f"Backtesting mode enabled: cutoff_date={cutoff_date}")

        log_capture.log_agent_start("Quant Strategy Team", "Coordinating multi-phase screening analysis")
        log_capture.log_agent_start("Technical Specialist", "Screening S&P 1500 for TA patterns")
        log_capture.log_tool_call("Technical Specialist", "technical_screener", "executing")

        logger.info("Running Quant Strategy AI screener...")

        # Get structured results first (for immediate feedback)
        log_capture.log_system("Running technical screen across S&P 1500...")
        structured = run_quant_strategy_screener(prompt, cutoff_date, progress_callback=progress_callback, log_callback=None)

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

        ai_report = response.content if hasattr(response, 'content') else str(response) if response else "No response"

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
        logger.error(f"AI screener failed: {e}")
        log_capture.log_system(f"Error in AI analysis: {str(e)[:100]}... Falling back to non-AI mode.")
        logger.info("Falling back to non-AI screener...")
        return run_quant_strategy_screener(prompt, cutoff_date, progress_callback=progress_callback)
