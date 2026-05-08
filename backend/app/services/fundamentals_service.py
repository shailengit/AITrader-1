"""
Fundamentals Service for TradeCraft QuantGen Dashboard.
Queries stock_financials_quarterly and yearly tables, computes YoY/QoQ growth,
and formats data for the frontend fundamentals panel.
"""

import logging
from typing import Dict, Any, List, Optional
import pandas as pd
from sqlalchemy import text
from app.db.database import engine
from app.services.data_service import DataService

logger = logging.getLogger(__name__)

# Metric definitions per tab
# Each entry: (db_column, display_label, formatter_type)
# formatter_type: 'auto' | 'currency' | 'ratio' | 'percent' | 'eps'
TAB_DEFINITIONS = {
    "income_statement": [
        ("total_revenue", "Revenue", "auto"),
        ("gross_profit", "Gross Profit", "auto"),
        ("operating_income", "Operating Income", "auto"),
        ("net_income", "Net Income", "auto"),
        ("diluted_eps", "EPS (Diluted)", "eps"),
        ("ebitda", "EBITDA", "auto"),
        ("research_and_development", "R&D Expense", "auto"),
        ("selling_general_and_administration", "SG&A", "auto"),
    ],
    "balance_sheet": [
        ("total_assets", "Total Assets", "auto"),
        ("total_liabilities_net_minority_interest", "Total Liabilities", "auto"),
        ("stockholders_equity", "Shareholders' Equity", "auto"),
        ("total_debt", "Total Debt", "auto"),
        ("net_debt", "Net Debt", "auto"),
        ("cash_and_cash_equivalents", "Cash", "auto"),
        ("working_capital", "Working Capital", "auto"),
        ("tangible_book_value", "Book Value", "auto"),
    ],
    "cash_flow": [
        ("operating_cash_flow", "Operating CF", "auto"),
        ("free_cash_flow", "Free Cash Flow", "auto"),
        ("investing_cash_flow", "Investing CF", "auto"),
        ("financing_cash_flow", "Financing CF", "auto"),
        ("capital_expenditure", "CapEx", "auto"),
        ("repurchase_of_capital_stock", "Buybacks", "auto"),
    ],
    "margins_ratios": [
        ("gross_margin", "Gross Margin", "percent"),
        ("operating_margin", "Operating Margin", "percent"),
        ("net_margin", "Net Margin", "percent"),
        ("fcf_margin", "FCF Margin", "percent"),
        ("roe", "ROE", "percent"),
        ("debt_equity", "Debt / Equity", "ratio"),
    ],
}


def _format_number(value: Optional[float], fmt: str) -> str:
    """Format a numeric value for display."""
    if value is None or pd.isna(value):
        return "N/A"

    if fmt == "percent":
        return f"{value * 100:.1f}%"
    if fmt == "ratio":
        return f"{value:.2f}x"
    if fmt == "eps":
        return f"${value:.2f}"

    # auto — currency with B/M/K
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1e12:
        return f"{sign}${abs_val / 1e12:.2f}T"
    if abs_val >= 1e9:
        return f"{sign}${abs_val / 1e9:.1f}B"
    if abs_val >= 1e6:
        return f"{sign}${abs_val / 1e6:.1f}M"
    if abs_val >= 1e3:
        return f"{sign}${abs_val / 1e3:.1f}K"
    return f"{sign}${abs_val:,.0f}"


def _compute_growth(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    """Compute percentage growth between two values."""
    if current is None or prior is None or pd.isna(current) or pd.isna(prior):
        return None
    if prior == 0:
        return None
    return ((current - prior) / abs(prior)) * 100


def _compute_margins(row: pd.Series) -> Dict[str, float]:
    """Compute margin and ratio metrics from a financial row."""
    margins: Dict[str, float] = {}
    revenue = row.get("total_revenue")
    net_income = row.get("net_income")
    gross_profit = row.get("gross_profit")
    operating_income = row.get("operating_income")
    fcf = row.get("free_cash_flow")
    equity = row.get("stockholders_equity")
    total_debt = row.get("total_debt")

    if revenue and revenue != 0:
        if gross_profit is not None and not pd.isna(gross_profit):
            margins["gross_margin"] = gross_profit / revenue
        if operating_income is not None and not pd.isna(operating_income):
            margins["operating_margin"] = operating_income / revenue
        if net_income is not None and not pd.isna(net_income):
            margins["net_margin"] = net_income / revenue
        if fcf is not None and not pd.isna(fcf):
            margins["fcf_margin"] = fcf / revenue

    if equity and equity != 0 and net_income is not None and not pd.isna(net_income):
        margins["roe"] = net_income / equity

    if equity and equity != 0 and total_debt is not None and not pd.isna(total_debt):
        margins["debt_equity"] = total_debt / equity

    return margins


def get_ticker_fundamentals(ticker: str) -> Dict[str, Any]:
    """
    Fetch fundamentals for a ticker from the database.

    Returns structured data with metadata, latest price, and tabbed metrics
    including YoY and QoQ growth rates.
    """
    ticker_upper = ticker.upper()
    result: Dict[str, Any] = {
        "ticker": ticker_upper,
        "metadata": {},
        "latest_price": None,
        "latest_quarter": None,
        "tabs": {
            "income_statement": [],
            "balance_sheet": [],
            "cash_flow": [],
            "margins_ratios": [],
        },
    }

    # 1. Fetch metadata
    try:
        meta_query = text("""
            SELECT ticker, name, sector, industry, market_cap, beta
            FROM stock_metadata
            WHERE ticker = :ticker
        """)
        with engine.connect() as conn:
            meta_row = conn.execute(meta_query, {"ticker": ticker_upper}).fetchone()

        if meta_row:
            result["metadata"] = {
                "ticker": meta_row[0],
                "name": meta_row[1] or ticker_upper,
                "sector": meta_row[2] or "Unknown",
                "industry": meta_row[3] or "Unknown",
                "market_cap": float(meta_row[4]) if meta_row[4] is not None else None,
                "beta": float(meta_row[5]) if meta_row[5] is not None else None,
            }
    except Exception as e:
        logger.error("Error fetching metadata for %s: %s", ticker_upper, e)

    # 2. Fetch latest price
    try:
        latest_price = DataService.get_latest_price(ticker_upper)
        if latest_price is not None:
            result["latest_price"] = round(latest_price, 2)
    except Exception as e:
        logger.error("Error fetching latest price for %s: %s", ticker_upper, e)

    # 3. Fetch quarterly financials (last 5 quarters for YoY)
    quarterly_df: Optional[pd.DataFrame] = None
    try:
        q_query = text("""
            SELECT * FROM stock_financials_quarterly
            WHERE ticker = :ticker
            ORDER BY report_date DESC
            LIMIT 5
        """)
        with engine.connect() as conn:
            quarterly_df = pd.read_sql(q_query, conn, params={"ticker": ticker_upper})

        if quarterly_df is not None and not quarterly_df.empty:
            # Sort ascending for easier indexing (oldest first)
            quarterly_df = quarterly_df.sort_values("report_date").reset_index(drop=True)
            result["latest_quarter"] = str(quarterly_df["report_date"].iloc[-1])[:10]
    except Exception as e:
        logger.error("Error fetching quarterly data for %s: %s", ticker_upper, e)

    if quarterly_df is None or quarterly_df.empty:
        logger.warning("No quarterly financials found for %s", ticker_upper)
        return result

    # 4. Build metric cards per tab
    latest_row = quarterly_df.iloc[-1]
    prior_row = quarterly_df.iloc[-2] if len(quarterly_df) >= 2 else None
    yoy_row = quarterly_df.iloc[-5] if len(quarterly_df) >= 5 else None

    # Compute margins for latest and prior
    latest_margins = _compute_margins(latest_row)
    prior_margins = _compute_margins(prior_row) if prior_row is not None else {}
    yoy_margins = _compute_margins(yoy_row) if yoy_row is not None else {}

    for tab_key, definitions in TAB_DEFINITIONS.items():
        for db_col, label, fmt in definitions:
            # Value lookup: first try quarterly column, then margins
            if db_col in latest_row.index:
                raw_value = latest_row.get(db_col)
            elif db_col in latest_margins:
                raw_value = latest_margins.get(db_col)
            else:
                raw_value = None

            # Skip all-null metrics
            if raw_value is None or pd.isna(raw_value):
                continue

            # QoQ value
            qoq_raw = None
            if prior_row is not None:
                if db_col in prior_row.index:
                    qoq_raw = prior_row.get(db_col)
                elif db_col in prior_margins:
                    qoq_raw = prior_margins.get(db_col)

            # YoY value
            yoy_raw = None
            if yoy_row is not None:
                if db_col in yoy_row.index:
                    yoy_raw = yoy_row.get(db_col)
                elif db_col in yoy_margins:
                    yoy_raw = yoy_margins.get(db_col)

            yoy = _compute_growth(raw_value, yoy_raw)
            qoq = _compute_growth(raw_value, qoq_raw)

            result["tabs"][tab_key].append({
                "label": label,
                "value": float(raw_value) if not pd.isna(raw_value) else None,
                "yoy": round(yoy, 1) if yoy is not None else None,
                "qoq": round(qoq, 1) if qoq is not None else None,
                "formatted": _format_number(raw_value, fmt),
            })

    return result
