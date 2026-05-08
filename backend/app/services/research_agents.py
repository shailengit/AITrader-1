"""
Multi-Agent Research Intelligence Service for TradeCraft QuantGen Dashboard.
Spawns 4 research agents with specific personas and compiles their findings
into a single executive summary document.

Modes:
- simulated: Uses local LLM to generate plausible research summaries based on
  ticker metadata and known financials.
- live: Uses local LLM with prompts tuned to surface recent real-world knowledge
  (enhanceable with actual web search integration in the future).
"""

import logging
from typing import Dict, Any, List, Optional
from app.services.llm_engine import client, MODEL_NAME, REQUEST_TIMEOUT
from app.services.fundamentals_service import get_ticker_fundamentals

logger = logging.getLogger(__name__)

# Agent personas and prompt templates
AGENT_PERSONAS = [
    {
        "name": "Market Sentiment",
        "color": "#10B981",
        "prompt": """You are a Market Sentiment Analyst. Analyze the current analyst community sentiment, institutional ownership trends, and recent rating changes for {ticker} ({company_name}).

Recent Financial Context:
- Sector: {sector}
- Industry: {industry}
- Revenue: {revenue}
- Net Income: {net_income}
- EPS: {eps}

Focus on:
1. Recent analyst rating changes (upgrades/downgrades)
2. Price target trends
3. Institutional buying/selling activity
4. Social media and retail sentiment

Write a concise 3-4 sentence summary of the current sentiment landscape. Be factual and specific."""
    },
    {
        "name": "Competitive Landscape",
        "color": "#3b82f6",
        "prompt": """You are a Competitive Intelligence Analyst. Analyze {ticker} ({company_name})'s competitive positioning in the {industry} industry.

Recent Financial Context:
- Revenue: {revenue}
- Operating Margin: {operating_margin}
- R&D Spend: {rd_spend}
- Market Cap: {market_cap}

Focus on:
1. Top 2-3 direct competitors and their relative strengths
2. Market share dynamics
3. Product/service pipeline and innovation
4. Strategic advantages and vulnerabilities

Write a concise 3-4 sentence competitive assessment. Be factual and specific."""
    },
    {
        "name": "Risk Factors",
        "color": "#f59e0b",
        "prompt": """You are a Risk Analyst. Identify the most significant risks facing {ticker} ({company_name}) over the next 6-12 months.

Recent Financial Context:
- Sector: {sector}
- Industry: {industry}
- Debt/Equity Ratio: {debt_equity}
- Free Cash Flow: {fcf}
- Beta: {beta}

Focus on:
1. Regulatory and legal risks
2. Macroeconomic and market risks
3. Operational and supply chain risks
4. Competitive and technological disruption risks

Write a concise 3-4 sentence risk summary covering the top 2-3 most material risks. Be factual and specific."""
    },
    {
        "name": "Earnings Outlook",
        "color": "#8b5cf6",
        "prompt": """You are an Earnings Forecast Analyst. Provide an outlook for {ticker} ({company_name})'s next earnings report and near-term financial trajectory.

Recent Financial Context:
- Revenue Trend (YoY): {revenue_yoy}%
- EPS Trend (YoY): {eps_yoy}%
- Net Margin: {net_margin}%
- Free Cash Flow: {fcf}
- Operating Cash Flow: {ocf}

Focus on:
1. Revenue and EPS expectations for the upcoming quarter
2. Key metrics to watch (guidance, margins, segment performance)
3. Potential beats or misses based on recent trends
4. Catalysts or headwinds affecting the next report

Write a concise 3-4 sentence earnings outlook. Be factual and specific."""
    },
]

SYNTHESIS_PROMPT = """You are a Senior Investment Analyst. Synthesize the following 4 research agent reports into a single cohesive executive summary for {ticker} ({company_name}).

AGENT REPORTS:
{reports}

Write a 200-word executive summary in professional prose (use a serif-style, memo tone). Cover:
- Overall investment thesis (bullish/bearish/neutral)
- Key strengths and catalysts
- Primary risks and concerns
- Bottom-line recommendation for a quantitative trader

Format as a single flowing paragraph or short sections. Do NOT use bullet points."""


def _format_metric(value: Any, fmt: str = "auto") -> str:
    """Format a metric value for prompt context."""
    if value is None:
        return "N/A"
    if fmt == "percent" and isinstance(value, (int, float)):
        return f"{value:.1f}%"
    if fmt == "currency" and isinstance(value, (int, float)):
        if abs(value) >= 1e9:
            return f"${value / 1e9:.1f}B"
        if abs(value) >= 1e6:
            return f"${value / 1e6:.1f}M"
        return f"${value:,.0f}"
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def _extract_metric(tabs: Dict[str, List[Dict[str, Any]]], tab: str, label: str) -> Any:
    """Extract a metric value from the fundamentals tabs."""
    for item in tabs.get(tab, []):
        if item.get("label") == label:
            return item.get("value")
    return None


def _build_agent_context(ticker: str, fundamentals: Dict[str, Any]) -> Dict[str, str]:
    """Build prompt context variables from fundamentals data."""
    meta = fundamentals.get("metadata", {})
    tabs = fundamentals.get("tabs", {})

    return {
        "ticker": ticker.upper(),
        "company_name": meta.get("name") or ticker.upper(),
        "sector": meta.get("sector") or "Unknown",
        "industry": meta.get("industry") or "Unknown",
        "market_cap": _format_metric(meta.get("market_cap"), "currency"),
        "beta": _format_metric(meta.get("beta")),
        "latest_price": _format_metric(fundamentals.get("latest_price")),
        "revenue": _format_metric(_extract_metric(tabs, "income_statement", "Revenue"), "currency"),
        "net_income": _format_metric(_extract_metric(tabs, "income_statement", "Net Income"), "currency"),
        "eps": _format_metric(_extract_metric(tabs, "income_statement", "EPS (Diluted)"), "currency"),
        "operating_margin": _format_metric(_extract_metric(tabs, "margins_ratios", "Operating Margin"), "percent"),
        "net_margin": _format_metric(_extract_metric(tabs, "margins_ratios", "Net Margin"), "percent"),
        "rd_spend": _format_metric(_extract_metric(tabs, "income_statement", "R&D Expense"), "currency"),
        "debt_equity": _format_metric(_extract_metric(tabs, "margins_ratios", "Debt / Equity")),
        "fcf": _format_metric(_extract_metric(tabs, "cash_flow", "Free Cash Flow"), "currency"),
        "ocf": _format_metric(_extract_metric(tabs, "cash_flow", "Operating CF"), "currency"),
        "revenue_yoy": _format_metric(_extract_metric(tabs, "income_statement", "Revenue") and _extract_metric(tabs, "income_statement", "Revenue") or 0),
        "eps_yoy": _format_metric(_extract_metric(tabs, "income_statement", "EPS (Diluted)") and _extract_metric(tabs, "income_statement", "EPS (Diluted)") or 0),
    }


def _call_llm(system: str, user: str, max_tokens: int = 4000) -> str:
    """Call the local LLM with system and user prompts."""
    if client is None:
        logger.error("LLM client not available")
        return "Research agent unavailable — LLM client not initialized."

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0.4,
            max_tokens=max_tokens,
            timeout=REQUEST_TIMEOUT,
        )
        msg = response.choices[0].message
        content = msg.content
        if content and content.strip():
            return content.strip()
        # Fallback for reasoning models that may put analysis in reasoning field
        reasoning = getattr(msg, "reasoning", None) or getattr(msg, "thinking", None)
        if reasoning and str(reasoning).strip():
            return str(reasoning).strip()
        return "No response from research agent."
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return f"Research agent error: {str(e)}"


def run_research_agents(ticker: str, mode: str = "simulated") -> Dict[str, Any]:
    """
    Run 4 research agents for a ticker and compile their findings.

    Args:
        ticker: Stock ticker symbol
        mode: 'simulated' or 'live'

    Returns:
        Dict with agent outputs and compiled document
    """
    ticker_upper = ticker.upper()
    logger.info("Running research agents for %s (mode=%s)", ticker_upper, mode)

    # Fetch fundamentals to enrich prompts
    fundamentals = get_ticker_fundamentals(ticker_upper)
    context = _build_agent_context(ticker_upper, fundamentals)

    # Mode-specific prompt adjustments
    mode_prefix = ""
    if mode == "live":
        mode_prefix = (
            "Use your most current knowledge about real-world events, analyst reports, "
            "and market developments up to your knowledge cutoff. Focus on actual recent "
            "news and verified market intelligence rather than general background.\n\n"
        )
    else:
        mode_prefix = (
            "Based on the provided financial context and your general knowledge of this company, "
            "generate a plausible, well-reasoned research summary. This is a simulated analysis "
            "for dashboard demonstration purposes.\n\n"
        )

    # Run each agent
    agents_output: List[Dict[str, str]] = []
    for persona in AGENT_PERSONAS:
        prompt = mode_prefix + persona["prompt"].format(**context)
        content = _call_llm(
            system="You are a senior financial research analyst. Be concise, factual, and specific. Write 3-4 sentences only.",
            user=prompt,
            max_tokens=4000
        )
        agents_output.append({
            "name": persona["name"],
            "content": content,
            "color": persona["color"],
        })
        logger.info("Agent '%s' completed for %s", persona["name"], ticker_upper)

    # Compile synthesis document
    reports_text = "\n\n".join(
        f"[{a['name']}]\n{a['content']}" for a in agents_output
    )
    synthesis_prompt = SYNTHESIS_PROMPT.format(
        ticker=ticker_upper,
        company_name=context["company_name"],
        reports=reports_text
    )
    compiled_document = _call_llm(
        system="You are a senior investment strategist. Write concise, professional prose. No bullet points.",
        user=synthesis_prompt,
        max_tokens=6000
    )
    logger.info("Synthesis document compiled for %s", ticker_upper)

    return {
        "mode": mode,
        "agents": agents_output,
        "compiled_document": compiled_document,
    }
