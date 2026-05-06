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

def test_fundamentals(ticker):
    try:
        query = text("""
            SELECT ticker, report_date, eps, total_revenue FROM stock_financials_quarterly
            WHERE ticker = :ticker ORDER BY report_date DESC LIMIT 3;
        """)
        with ENGINE.connect() as conn:
            df = pd.read_sql(query, conn, params={"ticker": ticker})
            print(f"Data for {ticker}:")
            print(df)
            
            if len(df) >= 2:
                current_eps = df['eps'].iloc[0]
                prev_eps = df['eps'].iloc[1]
                if prev_eps != 0:
                    growth = (current_eps - prev_eps) / abs(prev_eps)
                    print(f"EPS Growth: {growth:.2%}")
                
                curr_rev = df['total_revenue'].iloc[0]
                prev_rev = df['total_revenue'].iloc[1]
                if prev_rev and prev_rev > 0:
                    rev_growth = (curr_rev - prev_rev) / prev_rev
                    print(f"Revenue Growth: {rev_growth:.2%}")
            else:
                print("Insufficient financial data.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fundamentals("DXCM")
    test_fundamentals("ECL")
