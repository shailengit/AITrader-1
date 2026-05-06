import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

DB_USER = "postgres"
DB_PASSWORD = "sarina00"
DB_HOST = "127.0.0.1"
DB_PORT = "5431"
DB_NAME = "sp1500_1d"
DB_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

ENGINE = create_engine(DB_URL)

def analyze_single_ticker_dormant_giant(ticker: str, filters: dict = None):
    if filters is None:
        filters = {}
    try:
        with ENGINE.connect() as conn:
            query = f'SELECT "Date", "Close", "Volume", "High" FROM "{ticker.lower()}" ORDER BY "Date" DESC LIMIT 200;'
            df = pd.read_sql(query, conn).sort_values('Date')
    except Exception as e:
        return {"error": f"DB Error for {ticker}: {e}"}

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
    is_breakout = (df['Close'].iloc[-1] > past_resistance) and (current_vol > (avg_vol * volume_threshold))

    return {
        "ticker": ticker.upper(),
        "is_squeezing": bool(is_squeezing),
        "hidden_accumulation": bool(hidden_accumulation),
        "is_breakout": bool(is_breakout),
        "bandwidth": float(current_bandwidth),
        "min_bandwidth": float(min_bandwidth),
        "obv_slope": float(obv_slope),
        "price_slope": float(price_slope)
    }

if __name__ == "__main__":
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
    for t in tickers:
        print(f"Analyzing {t}...")
        print(analyze_single_ticker_dormant_giant(t))
