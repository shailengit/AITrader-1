import os
import time
import pandas as pd
from typing import List, Optional, Dict
from sqlalchemy import create_engine, text
from ta import add_all_ta_features
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

from agno.agent import Agent
from agno.team import Team
from agno.models.ollama import Ollama

# --- CONFIGURATION ---
DB_URL = 'postgresql://postgres:sarina00@127.0.0.1:5431/sp1500_1d'
ENGINE = create_engine(DB_URL)

# --- TOOL 1: PARALLEL TECHNICAL SCREENER ---

def _worker_ta(ticker: str, requested_columns: List[str]):
    """Internal worker for multiprocessing TA calculations."""
    try:
        # Fetch data for technicals
        df = pd.read_sql(f'SELECT * FROM {ticker.lower()} ORDER BY "Date" DESC LIMIT 250', ENGINE)
        if len(df) < 50: return None

        df = df.sort_values(by="Date").reset_index(drop=True)
        df = add_all_ta_features(df, "Open", "High", "Low", "Close", "Volume", fillna=True)

        latest = df.iloc[-1]
        res = {'ticker': ticker.upper(), 'close': round(latest['Close'], 2)}
        for col in requested_columns:
            if col in latest:
                res[col] = round(latest[col], 4)
        return res
    except:
        return None

def technical_screener(requested_indicators: List[str], sort_by: str = "ticker") -> str:
    """
    Screens the S&P 1500 using parallel processing on M1 cores.
    Returns only the columns requested by the agent to keep context lean.
    """
    with ENGINE.connect() as conn:
        res = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tickers = [row[0] for row in res if row[0] not in ['stock_metadata', 'stock_financials_quarterly']]

    print(f"🧬 Tech Analyst: Scanning {len(tickers)} stocks for {requested_indicators}...")

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        # Using list comprehension to prepare args for the worker
        results = list(tqdm(executor.map(_worker_ta, tickers, [requested_indicators]*len(tickers)), total=len(tickers)))

    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty and sort_by in df.columns:
        df = df.sort_values(by=sort_by).head(50)

    return df.to_csv(index=False)

# --- TOOL 2: QUARTERLY FUNDAMENTAL ANALYZER ---

def query_fundamental_health(tickers: List[str]) -> str:
    """
    Analyzes the 'stock_financials_quarterly' table for growth and margins.
    Calculates Quarter-over-Quarter trends for the provided tickers.
    """
    query = text("""
        WITH Ranked AS (
            SELECT ticker, report_date, total_revenue, net_income,
            LAG(total_revenue) OVER (PARTITION BY ticker ORDER BY report_date ASC) as prev_rev
            FROM stock_financials_quarterly WHERE ticker = ANY(:t)
        )
        SELECT * FROM Ranked ORDER BY ticker, report_date DESC
    """)

    try:
        df = pd.read_sql(query, ENGINE, params={"t": [t.upper() for t in tickers]})
        if df.empty: return "No fundamental data found."

        summary = []
        for t in tickers:
            t_df = df[df['ticker'] == t.upper()]
            if len(t_df) < 2: continue
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

# --- MULTI-AGENT TEAM COMPOSITION (AGNO v1.0+) ---

# 1. The Technical Specialist
tech_agent = Agent(
    name="Technical Specialist",
    role="Identify price-action setups using the S&P 1500 parallel technical screener.",
    model=Ollama(id="minimax-m2.5:cloud"),
    tools=[technical_screener],
    instructions=["Return only the top 10-15 tickers that meet the user's technical criteria."]
)

# 2. The Quality Control Analyst (Fundamentals)
fund_agent = Agent(
    name="Fundamental Specialist",
    role="Vet tickers for financial health and revenue growth using quarterly data.",
    model=Ollama(id="minimax-m2.5:cloud"),
    tools=[query_fundamental_health],
    instructions=["Review the provided tickers. Reject any with declining revenue trends."]
)

# 3. The Risk Manager
risk_manager = Agent(
    name="Risk Manager",
    role="Evaluate volatility (Beta) and Market Cap stability of the final list.",
    model=Ollama(id="minimax-m2.5:cloud"),
    instructions=[
        "Flag stocks that are 'Small Cap' (Market Cap < 2B) or 'High Volatility' (Beta > 1.5).",
        "Ensure the final selection is not overly concentrated in one sector."
    ]
)

# 4. The Orchestrator (Using the new Team Class)
quant_team = Team(
    name="Quant Strategy Team",
    members=[tech_agent, fund_agent, risk_manager],
    model=Ollama(id="minimax-m2.5:cloud", options={"num_ctx": 32768}),
    instructions=[
        "1. Start by asking the Technical Specialist to find stocks matching the user's technical setup.",
        "2. Pass the resulting tickers to the Fundamental Specialist for a health check.",
        "3. Have the Risk Manager evaluate the final vetted list for Beta and Market Cap stability.",
        "4. Provide a final unified Markdown table with Technical, Fundamental, and Risk summaries.",
        "5. Be highly selective: only recommend the highest quality setups."
    ],
    debug_mode=True,
    markdown=True
)

# --- EXECUTION ---
if __name__ == "__main__":
    prompt = (
        "Find me candidates for a high-growth breakout. "
        "Technically, they should be in a Volatility Squeeze (volatility_bbw). "
        "Fundamentally, they must have positive QoQ revenue growth."
    )

    print(f"🚀 Quant Team initiating strategy: {prompt}")
    quant_team.print_response(prompt)
