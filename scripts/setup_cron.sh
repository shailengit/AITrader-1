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
