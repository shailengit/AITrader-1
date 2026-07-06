"""Result enrichment — fundamentals + EPS/revenue growth + valuation multiples.

`enrich_results` was moved from app.services.agno_screener (which is being
deleted as part of the screener page consolidation). The function takes a
list of result dicts (each with at least `ticker` and optionally `close`),
joins against `stock_metadata` and `stock_financials_quarterly`, and adds:

    company_name, sector, market_cap, beta, eps_growth_qoq,
    revenue_growth_qoq, peg_ratio

The function mutates each input dict in place and also returns the list,
matching the original behavior. It is safe to call with an empty list.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd
from sqlalchemy import create_engine, text

from app.db.database import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

logger = logging.getLogger(__name__)

DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
ENGINE = create_engine(DB_URL, pool_pre_ping=True)


def enrich_results(results: List[Dict]) -> List[Dict]:
    """
    Enrich screener results with metadata, fundamentals, and price stats.
    Adds: company_name, sector, market_cap, beta, eps_growth_qoq,
          revenue_growth_qoq, peg_ratio.
    """
    if not results:
        return results

    tickers = [r['ticker'].upper() for r in results if r.get('ticker')]
    if not tickers:
        return results

    # 1. Metadata (single batched query)
    try:
        meta_query = text(
            "SELECT ticker, name, sector, market_cap, beta FROM stock_metadata WHERE ticker = ANY(:t)"
        )
        meta_df = pd.read_sql(meta_query, ENGINE, params={"t": tickers})
        meta_map = {row['ticker'].upper(): row for _, row in meta_df.iterrows()}
    except Exception as e:
        logger.warning("Metadata enrichment failed: %s", e)
        meta_map = {}

    # 2. Financials — last 2 quarters per ticker (single batched query)
    try:
        fin_query = text("""
            SELECT ticker, report_date, diluted_eps, total_revenue, net_income
            FROM stock_financials_quarterly
            WHERE ticker = ANY(:t)
            ORDER BY ticker, report_date DESC
        """)
        fin_df = pd.read_sql(fin_query, ENGINE, params={"t": tickers})
    except Exception as e:
        logger.warning("Financial enrichment failed: %s", e)
        fin_df = pd.DataFrame()

    for r in results:
        t = r.get('ticker', '').upper()
        if not t:
            continue

        # Metadata
        m = meta_map.get(t)
        if m is not None:
            r['company_name'] = m.get('name') or t
            r['sector'] = m.get('sector') or 'N/A'
            r['market_cap'] = float(m['market_cap']) if pd.notnull(m.get('market_cap')) else None
            r['beta'] = float(m['beta']) if pd.notnull(m.get('beta')) else None
        else:
            r['company_name'] = t
            r['sector'] = 'N/A'

        # Financials
        t_df = fin_df[fin_df['ticker'] == t]
        if len(t_df) >= 2:
            curr = t_df.iloc[0]
            prev = t_df.iloc[1]
            close_price = r.get('close')

            # EPS growth QoQ
            curr_eps = curr['diluted_eps']
            prev_eps = prev['diluted_eps']
            if pd.notnull(curr_eps) and pd.notnull(prev_eps) and prev_eps != 0:
                eps_growth = (curr_eps - prev_eps) / abs(prev_eps)
                r['eps_growth_qoq'] = round(eps_growth * 100, 2)

                # PEG ratio approximation
                if close_price and eps_growth > 0:
                    pe = close_price / max(float(curr_eps), 0.001)
                    annualized_growth = eps_growth * 4
                    peg = pe / max(annualized_growth, 0.001)
                    r['peg_ratio'] = round(peg, 2)
                else:
                    r['peg_ratio'] = None
            else:
                r['eps_growth_qoq'] = None
                r['peg_ratio'] = None

            # Revenue growth QoQ
            curr_rev = curr['total_revenue']
            prev_rev = prev['total_revenue']
            if pd.notnull(curr_rev) and pd.notnull(prev_rev) and prev_rev > 0:
                rev_growth = (curr_rev - prev_rev) / prev_rev
                r['revenue_growth_qoq'] = round(rev_growth * 100, 2)
            else:
                r['revenue_growth_qoq'] = None

    return results
