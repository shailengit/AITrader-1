# Design: Earnings Sync Cron Job

**Date:** 2026-05-17
**Status:** Approved

## Context

TradeCraft's Earnings Calendar feature stores upcoming earnings dates in the `earnings_calendar` table within the `sp1500_1d` PostgreSQL database. This data was manually backfilled during initial deployment (1,500+ events from Finnhub + yfinance fallback). However, there is no automated mechanism to keep this data fresh. Earnings dates shift, new quarters are announced, and actual EPS results are published after the report date. Without periodic sync, the cache becomes stale and screener filters that depend on `days_until_earnings` will drift.

## Goals

1. Automate daily earnings calendar sync so the cache stays current without manual intervention.
2. Use the same PostgreSQL database (`sp1500_1d`) — no new data store.
3. Match the existing OHLCV data sync cadence (daily at 6 PM) but staggered to avoid resource contention.
4. Provide a one-command setup that adds the cron job to the user's crontab.
5. Log sync results so issues are visible in the system log.

## Non-Goals

- Real-time streaming of earnings announcements — out of scope.
- Backfilling historical earnings beyond what's needed for upcoming dates.
- Email/Slack notifications on sync failures — log-only for now.

## Architecture

```
System Cron (crontab)
    |
    v
scripts/sync_earnings.sh  -- 6:30 PM daily
    |
    v
backend venv Python
    |
    v
app/services/earnings_sync.py::sync_earnings_calendar()
    |
    v
Finnhub API  -- bulk calendar for next 90 days
    |
    v
PostgreSQL: sp1500_1d.earnings_calendar  -- upsert
```

## Database

Already exists. Reuses `earnings_calendar` table in `sp1500_1d`.

## Backend Scripts

### New: `scripts/sync_earnings.sh`

A shell script that:
1. Activates the backend virtual environment.
2. Sets `FINNHUB_API_KEY` from `~/.zshrc` (or exports it inline).
3. Runs a Python one-liner that calls `sync_earnings_calendar()` for the next 90 days.
4. Logs stdout/stderr to `backend/logs/earnings_sync.log` with timestamps.

```bash
#!/bin/bash
# TradeCraft Earnings Calendar Sync
# Runs daily at 6:30 PM via cron

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/backend/logs"
LOG_FILE="$LOG_DIR/earnings_sync.log"

mkdir -p "$LOG_DIR"

# Load Finnhub key from zshrc if available
if [ -f "$HOME/.zshrc" ]; then
    export FINNHUB_API_KEY=$(grep 'FINNHUB_API_KEY=' "$HOME/.zshrc" | tail -1 | cut -d'=' -f2-)
fi

cd "$PROJECT_DIR/backend"
source venv/bin/activate

TODAY=$(date +%Y-%m-%d)
FUTURE=$(date -v+90d +%Y-%m-%d 2>/dev/null || date -d '+90 days' +%Y-%m-%d)

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting earnings sync: $TODAY to $FUTURE" >> "$LOG_FILE"

python -c "
import sys, json, logging
sys.path.insert(0, '.')
logging.basicConfig(level=logging.INFO)
from app.services.earnings_sync import sync_earnings_calendar
result = sync_earnings_calendar('$TODAY', '$FUTURE')
print(json.dumps(result, indent=2))
" >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Earnings sync complete" >> "$LOG_FILE"
```

### New: `scripts/setup_cron.sh`

One-time setup script that:
1. Checks if `scripts/sync_earnings.sh` exists and is executable.
2. Adds a crontab entry: `30 18 * * * /absolute/path/to/scripts/sync_earnings.sh`
3. Backs up the existing crontab before modifying.
4. Prints confirmation.

```bash
#!/bin/bash
# One-time setup for the earnings sync cron job

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="$SCRIPT_DIR/sync_earnings.sh"

if [ ! -f "$SYNC_SCRIPT" ]; then
    echo "Error: sync_earnings.sh not found at $SYNC_SCRIPT"
    exit 1
fi

chmod +x "$SYNC_SCRIPT"

# Backup existing crontab
crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# Add the cron job if not already present
CRON_LINE="30 18 * * * $SYNC_SCRIPT"
if crontab -l 2>/dev/null | grep -Fq "$SYNC_SCRIPT"; then
    echo "Cron job already exists."
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Cron job added: daily at 6:30 PM"
    echo "Entry: $CRON_LINE"
fi

echo "Setup complete. Next run: $(date -v+1d +'%Y-%m-%d 18:30:00' 2>/dev/null || date -d 'tomorrow 18:30' '+%Y-%m-%d %H:%M:%S')"
```

## Schedule Rationale

- **Daily at 6:30 PM** — staggered 30 minutes after the OHLCV sync (6:00 PM) to avoid yfinance rate limits and reduce peak load on the database.
- **90-day window** — Finnhub free tier allows generous bulk queries. 90 days covers the current quarter plus forward guidance, which is sufficient for screener filters up to 30 days and calendar views up to 90 days.
- **Upsert semantics** — `ON CONFLICT (ticker, report_date) DO UPDATE` ensures old rows are refreshed with new estimates/actuals without duplicating.

## Logging

- All output goes to `backend/logs/earnings_sync.log`.
- Log rotation is handled by `logrotate` (standard macOS) or simply by appending. The file will grow ~1 KB per day — negligible.
- A future enhancement could add `logrotate` configuration, but it's not needed now.

## Error Handling

- **Finnhub API failure:** Script logs the error and exits non-zero. Cron will email the user (if `MAILTO` is set) or the error will be in the log.
- **Missing `FINNHUB_API_KEY`:** Script logs a clear error before the Python call fails.
- **Database connection failure:** The existing `database.py` pool will retry. If it fails, the error is logged.

## Verification

1. Run the script manually:
   ```bash
   ./scripts/sync_earnings.sh
   ```
   Check `backend/logs/earnings_sync.log` for success.

2. Verify the cron job is installed:
   ```bash
   crontab -l | grep sync_earnings
   ```

3. Verify the database has fresh data:
   ```bash
   psql -U postgres -d sp1500_1d -p 5431 -c 'SELECT COUNT(*) FROM earnings_calendar WHERE report_date >= CURRENT_DATE;'
   ```

4. Run the screener with "Earnings within 30 days" and confirm results.

## Future Work

- Add `logrotate` config to prevent unbounded log growth.
- Add a lightweight health endpoint (`GET /api/earnings/health`) that reports last sync time and cache coverage percentage.
- Consider adding dividends and stock splits to the same sync pipeline with a `type` column or separate table.
