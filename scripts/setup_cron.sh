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

# Add earnings sync cron job if not already present
CRON_LINE="30 18 * * * $SYNC_SCRIPT"
if crontab -l 2>/dev/null | grep -Fq "$SYNC_SCRIPT"; then
    echo "Earnings cron job already exists."
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Earnings cron job added: daily at 6:30 PM"
fi

# Add VIX sync cron job (runs 15 min after earnings sync)
VIX_SCRIPT="$SCRIPT_DIR/sync_vix.sh"
chmod +x "$VIX_SCRIPT"
CRON_LINE_VIX="45 18 * * * $VIX_SCRIPT"
if crontab -l 2>/dev/null | grep -Fq "$VIX_SCRIPT"; then
    echo "VIX cron job already exists."
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE_VIX") | crontab -
    echo "VIX cron job added: daily at 6:45 PM"
fi

echo "Setup complete. Next earnings sync: 6:30 PM, VIX sync: 6:45 PM"
