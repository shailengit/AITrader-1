import os
import pandas as pd
from sqlalchemy import create_engine, text

DB_USER = "postgres"
DB_PASSWORD = "sarina00"
DB_HOST = "127.0.0.1"
DB_PORT = "5431"
DB_NAME = "sp1500_1d"
DB_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

ENGINE = create_engine(DB_URL)

def check():
    try:
        with ENGINE.connect() as conn:
            res = conn.execute(text("SELECT ticker FROM stock_metadata LIMIT 10;"))
            tickers = [row[0] for row in res]
            print(f"Tickers found: {tickers}")
            
            if tickers:
                t = tickers[0].lower()
                print(f"Checking data for {t}...")
                df = pd.read_sql(f'SELECT "Date", "Close" FROM "{t}" ORDER BY "Date" DESC LIMIT 5;', conn)
                print(df)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
