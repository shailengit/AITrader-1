"""
Sector Rotation router for TradeCraft API.
Provides sector performance and stock leader data.
Ported from Sector-Rotation-Scanner Express.js server.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import engine, SECTOR_ETFS, SECTOR_NAME_MAP
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter()


class SectorPerformance(BaseModel):
    """Sector performance data model."""
    ticker: str
    name: str
    perf_3m: float
    perf_6m: float
    spread: float
    ref_date: Optional[str] = None
    forward_return: Optional[float] = None
    is_real_data: bool = True


class OHLCV(BaseModel):
    """OHLCV data model."""
    time: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class StockLeader(BaseModel):
    """Stock leader data model."""
    ticker: str
    name: Optional[str] = None
    price: float
    perf_3m: float
    sector_perf_3m: float
    volume_today: float
    volume_avg_20d: float
    high_10d: float
    bb_expanding: bool
    bb_upper: float
    bb_middle: float
    bb_lower: float
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    ref_date: Optional[str] = None
    forward_return: Optional[float] = None
    is_real_data: bool = True


async def get_forward_return(ticker: str, from_date: str, holding_days: int = 30) -> Optional[float]:
    """Calculate forward return from from_date to from_date + holding_days."""
    try:
        query = text(f'''
            WITH from_price AS (
                SELECT "Close", "Date" FROM {ticker.lower()}
                WHERE "Date" <= :from_date ORDER BY "Date" DESC LIMIT 1
            ),
            to_price AS (
                SELECT "Close" FROM {ticker.lower()}
                WHERE "Date" >= (SELECT "Date" FROM from_price) + INTERVAL ':hold_days days'
                ORDER BY "Date" ASC LIMIT 1
            )
            SELECT
                (SELECT "Close" FROM to_price) / NULLIF((SELECT "Close" FROM from_price), 0) - 1 as forward_return
        ''')

        with engine.connect() as conn:
            result = conn.execute(query, {"from_date": from_date, "hold_days": holding_days}).fetchone()

        if result and result[0] is not None:
            return float(result[0])
        return None
    except Exception as e:
        logger.debug(f"Error getting forward return for {ticker}: {e}")
        return None


async def get_ticker_performance(ticker: str, cutoff_date: Optional[str] = None) -> Optional[dict]:
    """Calculate 3-month and 6-month performance for a ticker."""
    try:
        if cutoff_date:
            latest_cte = f'''
                (SELECT "Close", "Date" FROM {ticker.lower()}
                 WHERE "Date" <= :cutoff_date ORDER BY "Date" DESC LIMIT 1)
            '''
        else:
            latest_cte = f'(SELECT "Close", "Date" FROM {ticker.lower()} ORDER BY "Date" DESC LIMIT 1)'

        query = text(f'''
            WITH latest_prices AS {latest_cte},
            three_months_ago AS (
                SELECT "Close" FROM {ticker.lower()}
                WHERE "Date" <= (SELECT "Date" FROM latest_prices) - INTERVAL '90 days'
                ORDER BY "Date" DESC LIMIT 1
            ),
            six_months_ago AS (
                SELECT "Close" FROM {ticker.lower()}
                WHERE "Date" <= (SELECT "Date" FROM latest_prices) - INTERVAL '180 days'
                ORDER BY "Date" DESC LIMIT 1
            )
            SELECT
                (SELECT "Close" FROM latest_prices) as current_price,
                (SELECT "Date" FROM latest_prices) as ref_date,
                (SELECT "Close" FROM latest_prices) / NULLIF((SELECT "Close" FROM three_months_ago), 0) - 1 as perf_3m,
                (SELECT "Close" FROM latest_prices) / NULLIF((SELECT "Close" FROM six_months_ago), 0) - 1 as perf_6m
        ''')

        params = {"cutoff_date": cutoff_date} if cutoff_date else {}
        with engine.connect() as conn:
            result = conn.execute(query, params).fetchone()

        if result and result[0]:
            return {
                'current_price': float(result[0]),
                'ref_date': str(result[1]) if result[1] else None,
                'perf_3m': float(result[2]) if result[2] else 0.0,
                'perf_6m': float(result[3]) if result[3] else 0.0
            }
        return None
    except Exception as e:
        logger.debug(f"Error getting performance for {ticker}: {e}")
        return None


@router.get("/sectors", response_model=List[SectorPerformance])
async def get_sectors(
    cutoff_date: Optional[str] = None,
    holding_days: int = 30
):
    """
    Get sector ETF performance data.
    Returns 3-month and 6-month performance for all sector ETFs,
    sorted by acceleration spread (3M - 6M performance).
    """
    sector_data = []
    failures = []

    for sector in SECTOR_ETFS:
        perf = await get_ticker_performance(sector['ticker'], cutoff_date)
        if perf:
            forward = None
            if perf['ref_date']:
                forward = await get_forward_return(sector['ticker'], perf['ref_date'], holding_days)
            sector_data.append({
                'ticker': sector['ticker'].upper(),
                'name': sector['name'],
                'perf_3m': perf['perf_3m'],
                'perf_6m': perf['perf_6m'],
                'spread': perf['perf_3m'] - perf['perf_6m'],
                'ref_date': perf['ref_date'],
                'forward_return': forward,
                'is_real_data': True
            })
        else:
            failures.append(sector['ticker'])

    if failures:
        logger.warning(f"Failed to fetch performance for sectors: {', '.join(failures)}")

    if not sector_data:
        # Return mock data if database is unavailable
        logger.warning("No sector data available, returning mock data")
        mock_sectors = [
            {'ticker': 'XLK', 'name': 'Technology', 'perf_3m': 0.12, 'perf_6m': 0.08},
            {'ticker': 'XLE', 'name': 'Energy', 'perf_3m': 0.15, 'perf_6m': 0.05},
            {'ticker': 'XLF', 'name': 'Financials', 'perf_3m': 0.07, 'perf_6m': 0.09},
            {'ticker': 'XLV', 'name': 'Health Care', 'perf_3m': 0.04, 'perf_6m': 0.06},
            {'ticker': 'XLY', 'name': 'Consumer Discretionary', 'perf_3m': 0.08, 'perf_6m': 0.10},
            {'ticker': 'XLI', 'name': 'Industrials', 'perf_3m': 0.06, 'perf_6m': 0.05},
            {'ticker': 'XLC', 'name': 'Communication Services', 'perf_3m': 0.11, 'perf_6m': 0.07},
            {'ticker': 'XLP', 'name': 'Consumer Staples', 'perf_3m': 0.02, 'perf_6m': 0.03},
            {'ticker': 'XLB', 'name': 'Materials', 'perf_3m': 0.05, 'perf_6m': 0.04},
            {'ticker': 'XLRE', 'name': 'Real Estate', 'perf_3m': -0.02, 'perf_6m': 0.01},
            {'ticker': 'XLU', 'name': 'Utilities', 'perf_3m': 0.01, 'perf_6m': 0.02},
        ]
        sector_data = [
            {**s, 'spread': s['perf_3m'] - s['perf_6m'], 'is_real_data': False}
            for s in mock_sectors
        ]

    return sorted(sector_data, key=lambda x: x['spread'], reverse=True)


@router.get("/stocks/{sector}", response_model=List[StockLeader])
async def get_sector_stocks(
    sector: str,
    cutoff_date: Optional[str] = None,
    holding_days: int = 30
):
    """
    Get top performing stocks within a sector.
    Returns stocks outperforming the sector ETF with momentum indicators.
    """
    sector_lower = sector.lower()
    sector_name = SECTOR_NAME_MAP.get(sector_lower, sector_lower)

    leaders = []

    try:
        # Get sector ETF performance for comparison
        sector_perf = await get_ticker_performance(sector_lower, cutoff_date)
        sector_3m = sector_perf['perf_3m'] if sector_perf else 0.0
        ref_date = sector_perf['ref_date'] if sector_perf else None

        # Get stocks in this sector from metadata
        metadata_query = text(
            'SELECT ticker, name FROM stock_metadata WHERE sector = :sector'
        )

        with engine.connect() as conn:
            result = conn.execute(metadata_query, {"sector": sector_name})
            stocks = result.fetchall()

        logger.info(f"Found {len(stocks)} stocks in sector {sector_name}")

        # Analyze each stock (limit to first 50 for performance)
        for stock in stocks[:50]:
            ticker = stock[0]
            name = stock[1]

            try:
                # Build latest CTE with optional cutoff
                if cutoff_date:
                    latest_cte = f'''
                        SELECT "Close", "Volume", "Date" FROM {ticker.lower()}
                        WHERE "Date" <= :cutoff_date ORDER BY "Date" DESC LIMIT 1
                    '''
                else:
                    latest_cte = f'''
                        SELECT "Close", "Volume", "Date" FROM {ticker.lower()}
                        ORDER BY "Date" DESC LIMIT 1
                    '''

                # Complex query to get all metrics in one call (all windows relative to ref date)
                stock_query = text(f'''
                    WITH latest AS ({latest_cte}),
                    three_months_ago AS (
                        SELECT "Close" FROM {ticker.lower()}
                        WHERE "Date" <= (SELECT "Date" FROM latest) - INTERVAL '90 days'
                        ORDER BY "Date" DESC LIMIT 1
                    ),
                    ten_day_high AS (
                        SELECT MAX("High") as high_10d FROM (
                            SELECT "High" FROM {ticker.lower()}
                            WHERE "Date" <= (SELECT "Date" FROM latest)
                            ORDER BY "Date" DESC LIMIT 10
                        ) t
                    ),
                    avg_vol AS (
                        SELECT AVG("Volume") as vol_20d FROM (
                            SELECT "Volume" FROM {ticker.lower()}
                            WHERE "Date" <= (SELECT "Date" FROM latest)
                            ORDER BY "Date" DESC LIMIT 20
                        ) v
                    ),
                    sma_20 AS (
                        SELECT AVG("Close") as sma20 FROM (
                            SELECT "Close" FROM {ticker.lower()}
                            WHERE "Date" <= (SELECT "Date" FROM latest)
                            ORDER BY "Date" DESC LIMIT 20
                        ) s
                    ),
                    sd_20 AS (
                        SELECT STDDEV("Close") as sd20 FROM (
                            SELECT "Close" FROM {ticker.lower()}
                            WHERE "Date" <= (SELECT "Date" FROM latest)
                            ORDER BY "Date" DESC LIMIT 20
                        ) d
                    ),
                    sma_50 AS (
                        SELECT AVG("Close") as sma50 FROM (
                            SELECT "Close" FROM {ticker.lower()}
                            WHERE "Date" <= (SELECT "Date" FROM latest)
                            ORDER BY "Date" DESC LIMIT 50
                        ) f
                    ),
                    sma_200 AS (
                        SELECT AVG("Close") as sma200 FROM (
                            SELECT "Close" FROM {ticker.lower()}
                            WHERE "Date" <= (SELECT "Date" FROM latest)
                            ORDER BY "Date" DESC LIMIT 200
                        ) h
                    )
                    SELECT
                        l."Close" as price,
                        l."Volume" as volume_today,
                        l."Date" as ref_date,
                        l."Close" / NULLIF((SELECT "Close" FROM three_months_ago), 0) - 1 as perf_3m,
                        h.high_10d,
                        v.vol_20d,
                        sma_20.sma20,
                        sd_20.sd20,
                        sma_50.sma50,
                        sma_200.sma200
                    FROM latest l, ten_day_high h, avg_vol v, sma_20, sd_20, sma_50, sma_200
                ''')

                params = {"cutoff_date": cutoff_date} if cutoff_date else {}
                with engine.connect() as conn:
                    row = conn.execute(stock_query, params).fetchone()

                if row and row[0]:
                    price = float(row[0])
                    volume_today = float(row[1])
                    stock_ref_date = str(row[2]) if row[2] else ref_date
                    perf_3m = float(row[3]) if row[3] else 0.0
                    high_10d = float(row[4])
                    volume_avg_20d = float(row[5])
                    sma20 = float(row[6])
                    sd20 = float(row[7])
                    sma50 = float(row[8]) if row[8] else None
                    sma200 = float(row[9]) if row[9] else None

                    # Calculate Bollinger Bands
                    bb_middle = sma20
                    bb_upper = sma20 + (2 * sd20)
                    bb_lower = sma20 - (2 * sd20)

                    # Check if outperforming sector
                    is_high_perf_sector = sector_3m > 0.20
                    min_perf = 0 if is_high_perf_sector else sector_3m * 0.5

                    if perf_3m > min_perf:
                        forward = None
                        if stock_ref_date:
                            forward = await get_forward_return(ticker, stock_ref_date, holding_days)

                        leaders.append({
                            'ticker': ticker.upper(),
                            'name': name,
                            'price': price,
                            'perf_3m': perf_3m,
                            'sector_perf_3m': sector_3m,
                            'volume_today': volume_today,
                            'volume_avg_20d': volume_avg_20d,
                            'high_10d': high_10d,
                            'bb_expanding': True,  # Simplified
                            'bb_upper': bb_upper,
                            'bb_middle': bb_middle,
                            'bb_lower': bb_lower,
                            'sma50': sma50,
                            'sma200': sma200,
                            'ref_date': stock_ref_date,
                            'forward_return': forward,
                            'is_real_data': True
                        })

            except Exception as e:
                logger.debug(f"Skipping {ticker}: {e}")
                continue

        # Sort by performance
        leaders.sort(key=lambda x: x['perf_3m'], reverse=True)

    except Exception as e:
        logger.error(f"Error getting stocks for sector {sector}: {e}")
        # Return mock data if database fails
        return [
            {
                'ticker': 'AAPL', 'name': 'Apple Inc.', 'price': 185.20, 'perf_3m': 0.18,
                'sector_perf_3m': sector_3m, 'volume_today': 75000000, 'volume_avg_20d': 50000000,
                'high_10d': 184.50, 'bb_expanding': True, 'bb_upper': 188.50, 'bb_middle': 183.00,
                'bb_lower': 177.50, 'sma50': 182.00, 'sma200': 178.00,
                'ref_date': ref_date, 'forward_return': None,
                'is_real_data': False
            }
        ]

    return leaders


@router.get("/ohlcv/{ticker}", response_model=List[OHLCV])
async def get_ohlcv(ticker: str):
    """
    Get OHLCV data for a ticker.
    Used for charting in the Sector Rotation Scanner.
    """
    try:
        # Get last 150 days of data for technical indicator calculations (Bollinger Bands etc)
        query = text(f'''
            SELECT "Date", "Open", "High", "Low", "Close", "Volume"
            FROM {ticker.lower()}
            ORDER BY "Date" DESC
            LIMIT 150
        ''')

        with engine.connect() as conn:
            result = conn.execute(query).fetchall()

        if not result:
            return []

        ohlcv_data = []
        for row in result:
            # Convert Date to Unix timestamp (seconds)
            # Row structure: [Date, Open, High, Low, Close, Volume]
            import datetime
            dt = row[0]
            if isinstance(dt, str):
                ts = datetime.datetime.fromisoformat(dt.replace('Z', '')).timestamp()
            else:
                ts = dt.timestamp()

            ohlcv_data.append({
                'time': ts,
                'open': float(row[1]),
                'high': float(row[2]),
                'low': float(row[3]),
                'close': float(row[4]),
                'volume': float(row[5])
            })

        # Return sorted by time ascending (requirement for lightweight-charts)
        return sorted(ohlcv_data, key=lambda x: x['time'])

    except Exception as e:
        logger.error(f"Error getting OHLCV for {ticker}: {e}")
        # Return empty list or mock data
        return []