#!/bin/bash
# TradeCraft VIX Data Sync
# Downloads latest VIX data from Yahoo Finance and updates the database.
# Should run daily after market close (e.g., 6:30 PM ET).
#
# Add to crontab:
#   45 18 * * * /path/to/scripts/sync_vix.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/backend/logs"
LOG_FILE="$LOG_DIR/vix_sync.log"

mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR/backend"
source venv/bin/activate

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting VIX sync..." >> "$LOG_FILE"

python -c "
import os, sys, yfinance as yf, pandas as pd
sys.path.insert(0, '.')
from sqlalchemy import create_engine, text
from app.db.database import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

engine = create_engine(f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')

# Get latest date in DB
with engine.connect() as conn:
    latest = conn.execute(text('SELECT MAX(\"Date\") FROM vix')).scalar()

# Download new VIX data
vix = yf.download('^VIX', period='5d', auto_adjust=True)
if isinstance(vix.columns, pd.MultiIndex):
    vix.columns = vix.columns.get_level_values(0)

vix = vix.reset_index()
vix.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
vix['Date'] = pd.to_datetime(vix['Date']).dt.date

new_rows = 0
with engine.begin() as conn:
    for _, row in vix.iterrows():
        conn.execute(text('''
            INSERT INTO vix (\"Date\", \"Open\", \"High\", \"Low\", \"Close\", \"Volume\")
            VALUES (:date, :open, :high, :low, :close, :volume)
            ON CONFLICT (\"Date\") DO UPDATE SET
                \"Open\" = EXCLUDED.\"Open\",
                \"High\" = EXCLUDED.\"High\",
                \"Low\" = EXCLUDED.\"Low\",
                \"Close\" = EXCLUDED.\"Close\",
                \"Volume\" = EXCLUDED.\"Volume\"
        '''), {
            'date': row['Date'],
            'open': float(row['Open']) if pd.notna(row['Open']) else None,
            'high': float(row['High']) if pd.notna(row['High']) else None,
            'low': float(row['Low']) if pd.notna(row['Low']) else None,
            'close': float(row['Close']) if pd.notna(row['Close']) else None,
            'volume': int(row['Volume']) if pd.notna(row['Volume']) else 0,
        })
        new_rows += 1

print(f'VIX sync: {new_rows} rows processed')
" >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] VIX sync complete" >> "$LOG_FILE"
