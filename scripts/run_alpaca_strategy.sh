#!/bin/bash
# TradeCraft Golden Cross Rotation — Daily Alpaca Strategy Runner
# Runs daily at 6:00 PM ET via cron
#
# Add to crontab:
#   0 18 * * 1-5 /path/to/scripts/run_alpaca_strategy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/backend/logs"
LOG_FILE="$LOG_DIR/alpaca_strategy_$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

# Load environment variables
if [ -f "$PROJECT_DIR/backend/.env" ]; then
    set -a
    source "$PROJECT_DIR/backend/.env"
    set +a
fi

cd "$PROJECT_DIR/backend"
source venv/bin/activate

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting daily strategy run..." >> "$LOG_FILE"

python -m app.services.alpaca_runner >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily strategy run complete" >> "$LOG_FILE"

# Keep only last 30 days of logs
find "$LOG_DIR" -name "alpaca_strategy_*.log" -mtime +30 -delete
